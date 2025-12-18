from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import (
    action,
    api_view,
    permission_classes as permission_classes_decorator,
)
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from accounts.models import (
    Account,
    DependentInvitation,
    Dependents,
    Plates,
    CompanyAssignment,
    AuthorizedPlate,
)
from accounts.serializers import (
    AccountSerializer,
    PlatesSerializer,
    CompanySerializer,
)
from users.models import CustomUser
from users.serializers import UserSerializer
from utils.email_service import email_service
from .serializers import (
    DependentInvitationSerializer,
    CreateInvitationSerializer,
    InvitationResponseSerializer,
    CancelInvitationSerializer,
    InvitationsListResponseSerializer,
    RemoveDependentSerializer,
    RemoveDependentResponseSerializer,
    AddDependentDirectlySerializer,
    UserPlateSerializer,
    TransferBalanceSerializer,
)


class InvitationViewSet(viewsets.ViewSet):
    """
    ViewSet for managing dependent invitations and direct dependent addition
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = DependentInvitationSerializer

    @extend_schema(
        request=AddDependentDirectlySerializer,
        responses={201: None, 400: None},
        description="Directly add a user as dependent to a holder account by email",
        summary="Add Dependent Directly",
    )
    @action(detail=False, methods=["post"], url_path="add-dependent")
    def add_dependent_directly(self, request):
        """
        Directly add a user as dependent to a holder account.
        Creates the dependent account and relationship without requiring invitation acceptance.
        Expects: holder_account_id, dependent_email
        """
        serializer = AddDependentDirectlySerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            validated_data = serializer.validated_data
            try:
                with transaction.atomic():
                    holder_account = validated_data["holder_account"]
                    dependent_user = validated_data["dependent_user"]

                    # Create dependent account
                    dependent_account = Account.objects.create(
                        user=dependent_user,
                        balance=0,
                        account_type="dependent",
                    )

                    # Create dependent relationship
                    dependent_relationship = Dependents.objects.create(
                        holder_account=holder_account,
                        dependent_account=dependent_account,
                        start_date=timezone.now().date(),
                    )

                    # Send notification email to the dependent
                    try:
                        holder_user = holder_account.user
                        email_service.send_dependent_added_notification(
                            holder_user=holder_user,
                            dependent_user=dependent_user,
                            dependent_account=dependent_account,
                        )
                    except Exception:
                        print("Error sending dependent added notification email")
                        pass

                    return Response(
                        {
                            "message": "Dependent added successfully",
                            "dependent_account_id": dependent_account.id,
                            "relationship_id": dependent_relationship.id,
                        },
                        status=status.HTTP_201_CREATED,
                    )

            except Exception as e:
                return Response(
                    {"error": f"Error adding dependent: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=CreateInvitationSerializer,
        responses={201: DependentInvitationSerializer, 400: None},
        description="Create a new dependent invitation (legacy method, use add-dependent for direct addition)",
        summary="Create Dependent Invitation",
    )
    @action(detail=False, methods=["post"], url_path="create")
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
                        dependent_email=validated_data["dependent_email"],
                    )

                    # Send email notification to the dependent user
                    try:
                        holder_user = validated_data["holder_account"].user
                        holder_name = (
                            f"{holder_user.first_name} {holder_user.last_name}".strip()
                            or holder_user.email
                        )

                        # Try to get the dependent user's name, fallback to email
                        try:
                            dependent_user = CustomUser.objects.get(
                                email=validated_data["dependent_email"]
                            )
                            dependent_name = (
                                f"{dependent_user.first_name} {dependent_user.last_name}".strip()
                                or dependent_user.email
                            )
                        except CustomUser.DoesNotExist:
                            dependent_name = validated_data["dependent_email"]

                        email_service.send_invitation_email(
                            to_email=validated_data["dependent_email"],
                            holder_name=holder_name,
                            holder_email=holder_user.email,
                            dependent_name=dependent_name,
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
            OpenApiParameter(
                name="invitation_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="ID of the invitation to respond to",
                required=True,
            )
        ],
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="respond/(?P<invitation_id>[^/.]+)",
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

        # Verify invitation is still pending
        if invitation.status != "pending":
            return Response(
                {"error": "This invitation has already been responded to"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = InvitationResponseSerializer(data=request.data)
        if serializer.is_valid():
            action_type = serializer.validated_data["action"]

            try:
                if action_type == "accept":
                    invitation.accept_invitation()
                    message = "Invitation accepted successfully"
                elif action_type == "reject":
                    invitation.reject_invitation()
                    message = "Invitation rejected successfully"

                # Send email notification to the holder
                try:
                    email_service.send_invitation_response_email(
                        to_email=invitation.holder_account.user.email,
                        dependent_name=invitation.dependent_email,
                        action=action_type,
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
        request=CancelInvitationSerializer,
        responses={200: None, 400: None, 403: None, 404: None},
        description="Cancel a pending invitation",
        summary="Cancel Invitation",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="cancel",
    )
    def cancel_invitation(self, request):
        """
        Cancel a pending invitation (only for holder accounts)
        Expects: holder_account_id, dependent_email
        """
        holder_account_id = request.data.get("holder_account_id")
        dependent_email = request.data.get("dependent_email")

        if not holder_account_id or not dependent_email:
            return Response(
                {"error": "holder_account_id and dependent_email are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Verify the holder account belongs to the current user and is holder type
            try:
                holder_account = Account.objects.get(
                    id=holder_account_id, user=request.user, account_type="holder"
                )
            except Account.DoesNotExist:
                return Response(
                    {"error": "Holder account not found or does not belong to you"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Find the pending invitation between this holder and dependent email
            try:
                invitation = DependentInvitation.objects.get(
                    holder_account=holder_account,
                    dependent_email=dependent_email,
                    status="pending",
                )
            except DependentInvitation.DoesNotExist:
                return Response(
                    {"error": "Pending invitation not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            with transaction.atomic():
                invitation.cancel_invitation()

                # Send email notification to the dependent user
                try:
                    email_service.send_invitation_cancelled_email(
                        to_email=dependent_email,
                        holder_name=f"{holder_account.user.first_name} {holder_account.user.last_name}".strip(),
                    )
                except Exception:
                    # Log email error but don't fail the cancellation
                    pass

                return Response(
                    {"message": "Invitation cancelled successfully"},
                    status=status.HTTP_200_OK,
                )

        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        responses={200: InvitationsListResponseSerializer},
        description="Get all invitations (sent and received) for the user",
        summary="Get User Invitations (sent and received)",
    )
    @action(detail=False, methods=["get"], url_path="list")
    def get_invitations(self, request):
        """
        Get all invitations related to the user (both sent and received)
        """
        user = request.user
        user_accounts = Account.objects.filter(user=user)
        user_holder_accounts = user_accounts.filter(account_type="holder")

        # Get sent invitations (from holder accounts)
        sent_invitations = DependentInvitation.objects.filter(
            holder_account__in=user_holder_accounts
        ).order_by("-invitation_date")

        # Get received invitations (by user's email)
        received_invitations = DependentInvitation.objects.filter(
            dependent_email=user.email
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


class UserInfoView(APIView):
    """
    API view for retrieving comprehensive user account information
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: None},
        description="Get user account information including accounts, dependents, plates, and company",
        summary="Get User Account Info",
    )
    def get(self, request):
        """
        Get comprehensive user account information
        """
        user = request.user
        # Get accounts associated to user
        accounts = Account.objects.filter(user=user, is_active=True)
        accounts_data = []

        for account in accounts:
            account_data = AccountSerializer(account).data

            if account.account_type == "dependent":
                # Find the holder account related to this dependent account
                holder_relation = Dependents.objects.filter(
                    dependent_account=account, end_date__isnull=True
                ).first()
                if holder_relation:
                    holder_account_user = holder_relation.holder_account.user
                    # TODO: use the company name related to the holder_account_user if any
                    account_data["fleet_owner"] = (
                        f"{holder_account_user.first_name} {holder_account_user.last_name}".strip()
                    )

            accounts_data.append(account_data)

        # Get dependents data for those accounts (only active ones)
        dependent_relations = Dependents.objects.filter(
            holder_account__in=accounts,
            end_date__isnull=True,
            dependent_account__is_active=True,
        )
        dependents_data = []

        for dependent_relation in dependent_relations:
            dependent_account = dependent_relation.dependent_account
            dependent_account_user = dependent_account.user

            # Fetch authorized plates for this dependent account
            authorized_plates = AuthorizedPlate.objects.filter(
                dependent_account=dependent_account, end_date__isnull=True
            )
            authorized_plates_data = []
            for ap in authorized_plates:
                authorized_plates_data.append(
                    {
                        "id": ap.plate.id,
                        "authorization_id": ap.id,
                        "plate_number": ap.plate.plate_number,
                        "brand": ap.plate.brand,
                        "model": ap.plate.model,
                    }
                )

            dependents_data.append(
                {
                    "dependent_account": AccountSerializer(dependent_account).data,
                    "dependent_user": UserSerializer(dependent_account_user).data,
                    "authorized_plates": authorized_plates_data,
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

        # Get sent invitations (from holder accounts)
        sent_invitations = DependentInvitation.objects.filter(
            holder_account__in=user_holder_accounts
        ).order_by("-invitation_date")
        sent_invitations_data = DependentInvitationSerializer(
            sent_invitations, many=True
        ).data

        # Get received invitations (by user's email)
        received_invitations = DependentInvitation.objects.filter(
            dependent_email=user.email
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


class RemoveDependentView(APIView):
    """
    API view for removing a dependent from a holder account
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=RemoveDependentSerializer,
        responses={
            200: RemoveDependentResponseSerializer,
            400: None,
            404: None,
            500: None,
        },
        description="Remove a dependent user from a holder account. This will end the relationship, transfer any remaining balance from the dependent account to the holder account, and deactivate the dependent account.",
        summary="Remove Dependent",
    )
    def post(self, request):
        """
        Remove a dependent from a holder account.

        This operation will:
        1. End the dependent relationship by setting an end_date
        2. Transfer the dependent account's balance to the holder account
        3. Set the dependent account balance to 0
        4. Deactivate the dependent account
        5. Send a notification email to the dependent user

        Expects: holder_account_id, dependent_account_id
        """
        serializer = RemoveDependentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        holder_account_id = serializer.validated_data["holder_account_id"]
        dependent_account_id = serializer.validated_data["dependent_account_id"]

        try:
            # Verify the holder account belongs to the current user and is holder type
            try:
                holder_account = Account.objects.get(
                    id=holder_account_id, user=request.user, account_type="holder"
                )
            except Account.DoesNotExist:
                return Response(
                    {"error": "Holder account not found or does not belong to you"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get the dependent account by ID
            try:
                dependent_account = Account.objects.get(
                    id=dependent_account_id, account_type="dependent"
                )
            except Account.DoesNotExist:
                return Response(
                    {"error": "Dependent account not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Prevent users from removing themselves (edge case)
            if dependent_account.user == request.user:
                return Response(
                    {"error": "Invalid operation"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Find the active relationship between this holder and dependent account
            try:
                dependent_relation = Dependents.objects.get(
                    holder_account=holder_account,
                    dependent_account=dependent_account,
                    end_date__isnull=True,
                )
            except Dependents.DoesNotExist:
                return Response(
                    {"error": "Dependent relationship not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            with transaction.atomic():
                # Get the balance to transfer before modifying anything
                dependent_balance = dependent_account.balance

                # Transfer the dependent account balance to the holder account
                if dependent_balance > 0:
                    holder_account.balance += dependent_balance
                    holder_account.save()

                    dependent_account.balance = 0
                    dependent_account.save()

                dependent_relation.end_date = timezone.now().date()
                dependent_relation.save()

                # Set updated_at on dependent account to mark when it was deactivated
                # The account is not deleted, just deactivated
                dependent_account.is_active = False
                dependent_account.updated_at = timezone.now()
                dependent_account.save()

                # Send removal notification email
                try:
                    email_service.send_dependent_removal_notification(
                        holder_user=request.user,
                        dependent_user=dependent_account.user,
                        holder_account=holder_account,
                        balance_transferred=float(dependent_balance),
                    )
                except Exception:
                    print("Error sending dependent removal notification email")
                    pass

                response_data = {
                    "message": "Dependent removed successfully",
                    "balance_transferred": float(dependent_balance),
                    "new_holder_balance": float(holder_account.balance),
                }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TransferBalanceView(APIView):
    """
    API view for transferring balance between accounts
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=TransferBalanceSerializer,
        responses={200: None, 400: None, 403: None, 404: None},
        description="Transfer balance between two accounts. The source account must belong to the authenticated user.",
        summary="Transfer Balance",
    )
    def post(self, request):
        serializer = TransferBalanceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        source_account_id = serializer.validated_data["source_account_id"]
        destination_account_id = serializer.validated_data["destination_account_id"]
        amount = serializer.validated_data["amount"]

        try:
            with transaction.atomic():
                # Get source account (must belong to user and be active)
                try:
                    source_account = Account.objects.select_for_update().get(
                        id=source_account_id, user=request.user, is_active=True
                    )
                except Account.DoesNotExist:
                    return Response(
                        {
                            "error": "La cuenta de origen no fue encontrada o no te pertenece"
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # Get destination account (must be active)
                try:
                    destination_account = Account.objects.select_for_update().get(
                        id=destination_account_id, is_active=True
                    )
                except Account.DoesNotExist:
                    return Response(
                        {"error": "La cuenta de destino no fue encontrada"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # Verify relationship between accounts (optional but recommended for security)
                # For now, we allow transfer if source is holder and destination is dependent
                # and they are related.
                is_related = False
                if source_account.account_type == "holder":
                    is_related = Dependents.objects.filter(
                        holder_account=source_account,
                        dependent_account=destination_account,
                        end_date__isnull=True,
                    ).exists()

                if not is_related:
                    return Response(
                        {
                            "error": "Las cuentas no están relacionadas o no tienes permiso para transferir entre ellas"
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                # Check sufficient balance
                if source_account.balance < amount:
                    return Response(
                        {"error": "Saldo insuficiente"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Perform transfer
                source_account.balance -= amount
                destination_account.balance += amount

                source_account.save()
                destination_account.save()

                return Response(
                    {
                        "message": "Transfer successful",
                        "source_balance": source_account.balance,
                        "destination_balance": destination_account.balance,
                    },
                    status=status.HTTP_200_OK,
                )

        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    responses={200: UserPlateSerializer(many=True)},
    description="Get all plates accessible by the user, including owned plates and authorized plates (both active and inactive).",
    summary="Get User Plates",
)
@api_view(["GET"])
@permission_classes_decorator([IsAuthenticated])
def get_user_plates(request):
    """
    Returns all plates accessible by the authenticated user.
    Includes:
    - Plates owned by the user's holder account
    - Plates for which the user has authorization through dependent accounts
    Both active and inactive plates are returned.
    """
    user = request.user
    plates_data = []

    # Get all accounts for the user (holder and dependent)
    user_accounts = Account.objects.filter(user=user, is_active=True)

    for account in user_accounts:
        if account.account_type == "holder":
            # Get all plates owned by this holder account (active and inactive)
            owned_plates = Plates.objects.filter(holder_account=account)

            for plate in owned_plates:
                plates_data.append(
                    {
                        "id": plate.id,
                        "plate_number": plate.plate_number,
                        "brand": plate.brand,
                        "model": plate.model,
                        "ownership_type": "owned",
                        "is_active": plate.end_date is None,
                        "start_date": plate.start_date,
                        "end_date": plate.end_date,
                    }
                )

        elif account.account_type == "dependent":
            # Get all authorized plates for this dependent account (active and inactive)
            authorized_plates = AuthorizedPlate.objects.filter(
                dependent_account=account
            ).select_related("plate")

            for auth in authorized_plates:
                plates_data.append(
                    {
                        "id": auth.plate.id,
                        "plate_number": auth.plate.plate_number,
                        "brand": auth.plate.brand,
                        "model": auth.plate.model,
                        "ownership_type": "authorized",
                        "is_active": auth.end_date is None,
                        "start_date": auth.start_date,
                        "end_date": auth.end_date,
                    }
                )

    serializer = UserPlateSerializer(plates_data, many=True)
    return Response(serializer.data)
