from rest_framework import mixins, viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from drf_spectacular.utils import extend_schema

from users.models import CustomUser
from users.serializers import UserSerializer
from .permissions import DjangoModelOrObjectOwner
from utils.email_service import email_service


from .models import (
    Account,
    Dependents,
    Plates,
    AuthorizedPlate,
    Company,
    CompanyAssignment,
    DependentInvitation,
)
from .serializers import (
    AccountSerializer,
    DependentsSerializer,
    PlatesSerializer,
    AuthorizedPlateSerializer,
    CompanySerializer,
    CompanyAssignmentSerializer,
    AddDependentSerializer,
    RemoveDependentSerializer,
    DependentInvitationSerializer,
    CreateInvitationSerializer,
    InvitationResponseSerializer,
)


class BaseLCViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [DjangoModelPermissions]


class AccountViewSet(BaseLCViewSet):
    queryset = Account.objects.all().order_by("id")
    serializer_class = AccountSerializer


class DependentsViewSet(BaseLCViewSet):
    queryset = Dependents.objects.all().order_by("id")
    serializer_class = DependentsSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class PlatesViewSet(BaseLCViewSet):
    queryset = Plates.objects.all().order_by("id")
    serializer_class = PlatesSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class AuthorizedPlateViewSet(BaseLCViewSet):
    queryset = AuthorizedPlate.objects.all().order_by("id")
    serializer_class = AuthorizedPlateSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class CompanyViewSet(BaseLCViewSet):
    queryset = Company.objects.all().order_by("id")
    serializer_class = CompanySerializer


class CompanyAssignmentViewSet(BaseLCViewSet):
    queryset = CompanyAssignment.objects.all().order_by("id")
    serializer_class = CompanyAssignmentSerializer


class UserActionsViewSet(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = AccountSerializer  # Default serializer for schema generation

    @extend_schema(
        responses={200: None},
        description="Get user account information including accounts, dependents, plates, and company",
        summary="Get User Account Info",
    )
    @action(detail=False, methods=["get"], url_path="info")
    def info(self, request):
        user = request.user
        # Get accounts associated to user
        accounts = Account.objects.filter(user=user)
        accounts_data = AccountSerializer(accounts, many=True).data

        # Get dependents data for those accounts (only active ones)
        dependent_relations = Dependents.objects.filter(
            holder_account__in=accounts, end_date__isnull=True
        )
        dependents_data = []

        for dependent_relation in dependent_relations:
            dependent_account = dependent_relation.dependent_account

            dependent_account_user = dependent_account.user

            dependents_data.append(
                {
                    "dependent_account": AccountSerializer(dependent_account).data,
                    "dependent_user": UserSerializer(dependent_account_user).data,
                }
            )

        # Get plates for those accounts
        plates = Plates.objects.filter(holder_account__in=accounts)
        plates_data = PlatesSerializer(plates, many=True).data

        # Get company assignment and company data
        company_assignment = CompanyAssignment.objects.filter(user=user).first()
        company_data = None
        if company_assignment:
            company_data = {
                "company": CompanySerializer(company_assignment.company).data,
                "start_date": company_assignment.start_date,
                "end_date": company_assignment.end_date,
            }

        # Get invitation data
        user_holder_accounts = accounts.filter(account_type="holder")
        user_dependent_accounts = accounts.filter(account_type="dependent")

        # Get sent invitations (from holder accounts)
        sent_invitations = DependentInvitation.objects.filter(
            holder_account__in=user_holder_accounts
        ).order_by("-invitation_date")
        sent_invitations_data = DependentInvitationSerializer(
            sent_invitations, many=True
        ).data

        # Get received invitations (to dependent accounts)
        received_invitations = DependentInvitation.objects.filter(
            dependent_account__in=user_dependent_accounts
        ).order_by("-invitation_date")
        received_invitations_data = DependentInvitationSerializer(
            received_invitations, many=True
        ).data

        return Response(
            {
                "accounts": accounts_data,
                "dependents": dependents_data,
                "plates": plates_data,
                "company": company_data,
                "sent_invitations": sent_invitations_data,
                "received_invitations": received_invitations_data,
            }
        )

    @extend_schema(
        request=RemoveDependentSerializer,
        responses={200: None, 400: None, 404: None, 500: None},
        description="Remove a dependent user from a holder account",
        summary="Remove Dependent",
    )
    @action(detail=False, methods=["post"], url_path="remove-dependent")
    def remove_dependent(self, request):
        """
        Remove a dependent from a holder account.
        Expects: holder_account_id, dependent_account_id
        """
        serializer = RemoveDependentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        holder_account_id = serializer.validated_data["holder_account_id"]
        dependent_account_id = serializer.validated_data["dependent_account_id"]

        try:
            # Verify the holder account belongs to the current user and is holder type
            holder_account = get_object_or_404(
                Account, id=holder_account_id, user=request.user, account_type="holder"
            )

            # Get the dependent account by ID
            dependent_account = get_object_or_404(
                Account, id=dependent_account_id, account_type="dependent"
            )

            # Prevent users from removing themselves (edge case)
            if dependent_account.user == request.user:
                return Response(
                    {"error": "Invalid operation"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Find the active relationship between this holder and dependent account
            dependent_relation = get_object_or_404(
                Dependents,
                holder_account=holder_account,
                dependent_account=dependent_account,
                end_date__isnull=True,
            )

            with transaction.atomic():
                # Set end_date to mark as inactive instead of deleting
                dependent_relation.end_date = timezone.now().date()
                dependent_relation.save()

                # Send removal notification email
                email_service.send_dependent_removal_notification(
                    request.user, dependent_account.user, holder_account
                )

                response_data = {
                    "message": "Dependent removed successfully",
                }

                return Response(response_data, status=status.HTTP_200_OK)

        except Account.DoesNotExist:
            return Response(
                {"error": "Holder account not found or does not belong to you"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User with this email does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Dependents.DoesNotExist:
            return Response(
                {"error": "Dependent relationship not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        request=CreateInvitationSerializer,
        responses={201: DependentInvitationSerializer, 400: None},
        description="Create a new dependent invitation",
        summary="Create Dependent Invitation",
    )
    @action(detail=False, methods=["post"], url_path="create-invitation")
    def create_invitation(self, request):
        """
        Create a new dependent invitation using the invitation system
        Expects: holder_account_id, dependent_email
        """
        serializer = CreateInvitationSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            validated_data = serializer.validated_data

            try:
                with transaction.atomic():
                    invitation = DependentInvitation.objects.create(
                        holder_account=validated_data["holder_account"],
                        dependent_account=validated_data["dependent_account"],
                    )

                    # Send email notification to the dependent user
                    try:
                        email_service.send_invitation_email(
                            to_email=validated_data["dependent_account"].user.email,
                            holder_name=f"{validated_data['holder_account'].user.first_name} {validated_data['holder_account'].user.last_name}".strip(),
                            invitation_id=invitation.id,
                        )
                    except Exception:
                        # Log email error but don't fail the invitation creation
                        pass

                    response_serializer = DependentInvitationSerializer(invitation)
                    return Response(
                        {
                            "message": "Invitation created successfully",
                            "invitation": response_serializer.data,
                        },
                        status=status.HTTP_201_CREATED,
                    )

            except Exception as e:
                return Response(
                    {"error": f"Error creating invitation: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=InvitationResponseSerializer,
        responses={200: DependentInvitationSerializer, 400: None, 403: None, 404: None},
        description="Respond to a dependent invitation (accept or reject)",
        summary="Respond to Invitation",
        parameters=[
            {
                "name": "invitation_id",
                "in": "path",
                "required": True,
                "schema": {"type": "integer"},
                "description": "ID of the invitation to respond to",
            }
        ],
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="respond-invitation/(?P<invitation_id>[^/.]+)",
    )
    def respond_invitation(self, request, invitation_id: int = None):
        """
        Accept or reject a dependent invitation
        Expects: action (accept/reject)
        """
        try:
            invitation = DependentInvitation.objects.get(id=invitation_id)
        except DependentInvitation.DoesNotExist:
            return Response(
                {"error": "Invitation not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Verify that the user owns the dependent account
        if invitation.dependent_account.user != request.user:
            return Response(
                {"error": "You can only respond to invitations sent to your account"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Verify invitation is still pending
        if invitation.status != "pending":
            return Response(
                {"error": "This invitation has already been responded to"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = InvitationResponseSerializer(data=request.data)
        if serializer.is_valid():
            action = serializer.validated_data["action"]

            try:
                if action == "accept":
                    invitation.accept_invitation()
                    message = "Invitation accepted successfully"
                elif action == "reject":
                    invitation.reject_invitation()
                    message = "Invitation rejected successfully"

                # Send email notification to the holder
                try:
                    email_service.send_invitation_response_email(
                        to_email=invitation.holder_account.user.email,
                        dependent_name=f"{invitation.dependent_account.user.first_name} {invitation.dependent_account.user.last_name}".strip(),
                        action=action,
                    )
                except Exception:
                    # Log email error but don't fail the response
                    pass

                response_serializer = DependentInvitationSerializer(invitation)
                return Response(
                    {"message": message, "invitation": response_serializer.data},
                    status=status.HTTP_200_OK,
                )

            except Exception as e:
                return Response(
                    {"error": f"Error processing invitation response: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={200: None, 400: None, 403: None, 404: None},
        description="Cancel a pending invitation",
        summary="Cancel Invitation",
        parameters=[
            {
                "name": "invitation_id",
                "in": "path",
                "required": True,
                "schema": {"type": "integer"},
                "description": "ID of the invitation to cancel",
            }
        ],
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="cancel-invitation/(?P<invitation_id>[^/.]+)",
    )
    def cancel_invitation(self, request, invitation_id: int = None):
        """
        Cancel a pending invitation (only for holder accounts)
        """
        try:
            invitation = DependentInvitation.objects.get(id=invitation_id)
        except DependentInvitation.DoesNotExist:
            return Response(
                {"error": "Invitation not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Verify that the user owns the holder account
        if invitation.holder_account.user != request.user:
            return Response(
                {"error": "You can only cancel invitations sent from your account"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Verify invitation is still pending
        if invitation.status != "pending":
            return Response(
                {"error": "Only pending invitations can be cancelled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invitation.cancel_invitation()

            # Send email notification to the dependent user
            try:
                email_service.send_invitation_cancelled_email(
                    to_email=invitation.dependent_account.user.email,
                    holder_name=f"{invitation.holder_account.user.first_name} {invitation.holder_account.user.last_name}".strip(),
                )
            except Exception:
                # Log email error but don't fail the cancellation
                pass

            response_serializer = DependentInvitationSerializer(invitation)
            return Response(
                {
                    "message": "Invitation cancelled successfully",
                    "invitation": response_serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Error cancelling invitation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        responses={200: DependentInvitationSerializer},
        description="Get all invitations (sent and received) for the user",
        summary="Get User Invitations",
    )
    @action(detail=False, methods=["get"], url_path="invitations")
    def get_invitations(self, request):
        """
        Get all invitations related to the user (both sent and received)
        """
        user = request.user
        user_accounts = Account.objects.filter(user=user)
        user_holder_accounts = user_accounts.filter(account_type="holder")
        user_dependent_accounts = user_accounts.filter(account_type="dependent")

        # Get sent invitations (from holder accounts)
        sent_invitations = DependentInvitation.objects.filter(
            holder_account__in=user_holder_accounts
        ).order_by("-invitation_date")

        # Get received invitations (to dependent accounts)
        received_invitations = DependentInvitation.objects.filter(
            dependent_account__in=user_dependent_accounts
        ).order_by("-invitation_date")

        return Response(
            {
                "sent_invitations": DependentInvitationSerializer(
                    sent_invitations, many=True
                ).data,
                "received_invitations": DependentInvitationSerializer(
                    received_invitations, many=True
                ).data,
            }
        )

    @extend_schema(
        responses={200: DependentInvitationSerializer},
        description="Get pending invitations received by the user",
        summary="Get Pending Received Invitations",
    )
    @action(detail=False, methods=["get"], url_path="pending-invitations")
    def get_pending_invitations(self, request):
        """
        Get pending invitations received by the user's dependent accounts
        """
        user = request.user
        user_dependent_accounts = Account.objects.filter(
            user=user, account_type="dependent"
        )

        pending_invitations = DependentInvitation.objects.filter(
            dependent_account__in=user_dependent_accounts, status="pending"
        ).order_by("-invitation_date")

        serializer = DependentInvitationSerializer(pending_invitations, many=True)
        return Response(
            {
                "pending_invitations": serializer.data,
                "count": pending_invitations.count(),
            }
        )


class DependentInvitationViewSet(BaseLCViewSet):
    queryset = DependentInvitation.objects.all().order_by("-invitation_date")
    serializer_class = DependentInvitationSerializer
