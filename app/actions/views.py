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
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.contrib.auth.models import Group

from accounts.models import (
    Account,
    DependentInvitation,
    Dependents,
    Plates,
    AuthorizedPlate,
    AuthorizedEmail,
)
from stations.models import StationAttendantAssignment
from stations.serializers import StationSerializer
from accounts.serializers import (
    AccountSerializer,
    PlatesSerializer,
    CompanySerializer,
)
from users.models import CustomUser
from users.serializers import UserSerializer
from operation.models import Transfer, FuelLoadOperation, ModifyFunds
from utils.email_service import email_service
from utils.remito_pdf import (
    build_fuel_load_remito_pdf,
    build_fuel_load_remito_empresa_pdf,
)
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
    WithdrawFromDependentSerializer,
    AccountMovementSerializer,
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
        If the user is registered, creates the dependent account and relationship directly.
        If the user is NOT registered, creates an AuthorizedEmail and sends an invitation
        to download the app. When the user registers, the dependent account is auto-created.
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
                    user_registered = validated_data["user_registered"]

                    # If user is not registered, create AuthorizedEmail and send invitation
                    if not user_registered:
                        holder_company = holder_account.company

                        authorized_email = AuthorizedEmail.objects.create(
                            email=validated_data["dependent_email"],
                            dependent_of=holder_account,
                            special=holder_account.special,
                            display_type=holder_account.display_type,
                            unlimited_balance=holder_account.unlimited_balance,
                            company=holder_company,
                            organism=holder_company.organism
                            if holder_company
                            else None,
                        )

                        # Store any pre-assigned plates so they are assigned when the user registers
                        plate_ids = validated_data.get("plate_ids") or []
                        if plate_ids:
                            from accounts.models import Plates as PlatesModel
                            valid_plates = PlatesModel.objects.filter(
                                id__in=plate_ids,
                                holder_account=holder_account,
                                end_date__isnull=True,
                            )
                            authorized_email.pending_plates.set(valid_plates)

                        # Send invitation email to download the app
                        try:
                            holder_user = holder_account.user
                            holder_name = (
                                f"{holder_user.first_name} {holder_user.last_name}".strip()
                                or holder_user.email
                            )
                            email_kwargs = dict(
                                to_email=validated_data["dependent_email"],
                                holder_name=holder_name,
                                holder_email=holder_user.email,
                                company_name=holder_company.name if holder_company else None,
                            )
                            if holder_account.special == "cordoba":
                                email_service.send_cordoba_app_download_invitation(**email_kwargs)
                            else:
                                email_service.send_app_download_invitation(**email_kwargs)
                        except Exception:
                            print("Error sending app download invitation email")

                        return Response(
                            {
                                "message": "El usuario no está registrado en la app. Se envió una invitación por email.",
                                "authorized_email_id": authorized_email.id,
                                "user_registered": False,
                                "pending_plate_ids": list(authorized_email.pending_plates.values_list("id", flat=True)),
                            },
                            status=status.HTTP_201_CREATED,
                        )

                    # User is registered - proceed with direct addition
                    dependent_account = Account.objects.create(
                        user=dependent_user,
                        balance=0,
                        account_type="dependent",
                        special=holder_account.special,
                        display_type=holder_account.display_type,
                        unlimited_balance=holder_account.unlimited_balance,
                        company=holder_account.company,
                    )

                    # Create dependent relationship
                    dependent_relationship = Dependents.objects.create(
                        holder_account=holder_account,
                        dependent_account=dependent_account,
                        start_date=timezone.now().date(),
                    )

                    # Asignar rol de Flota al usuario adherido
                    try:
                        fleet_group = Group.objects.get(name="Flota")
                        dependent_user.groups.add(fleet_group)
                    except Group.DoesNotExist:
                        pass

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
                            "user_registered": True,
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

        # Verify invitation belongs to the requesting user
        if invitation.dependent_email.lower() != request.user.email.lower():
            return Response(
                {"error": "You are not authorized to respond to this invitation"},
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
                    account_data["holder_email"] = holder_account_user.email
                else:
                    # Dependent account with no active relation — skip it
                    continue

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

            # Fetch authorized plates for this dependent account (only active ones)
            authorized_plates = AuthorizedPlate.objects.filter(
                dependent_account=dependent_account, end_date__isnull=True
            ).select_related("plate")
            authorized_plates_data = []
            for ap in authorized_plates:
                # Also verify that the plate itself is active
                if ap.plate.end_date is None:
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

        # Get plates for those accounts (only active ones with end_date null)
        plates = Plates.objects.filter(
            holder_account__in=accounts, end_date__isnull=True
        )
        plates_data = PlatesSerializer(plates, many=True).data

        # Get company data from the holder account
        holder_account_obj = accounts.filter(account_type="holder").first()
        company_data = None
        if holder_account_obj and holder_account_obj.company:
            company_data = {
                "company": CompanySerializer(holder_account_obj.company).data,
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

        # Get assigned stations (for Encargado role)
        assigned_stations_data = []
        if user.groups.filter(name="Encargado").exists():
            assignments = StationAttendantAssignment.objects.filter(
                attendant=user,
                end_date__isnull=True,
            ).select_related("station", "station__province", "station__city")
            for assignment in assignments:
                station_data = StationSerializer(assignment.station).data
                station_data["assignment_id"] = assignment.id
                station_data["assignment_start_date"] = assignment.start_date
                assigned_stations_data.append(station_data)

        return Response(
            {
                "accounts": accounts_data,
                "dependents": dependents_data,
                "plates": plates_data,
                "company": company_data,
                "sent_invitations": sent_invitations_data,
                "received_invitations": received_invitations_data,
                "assigned_stations": assigned_stations_data,
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

                # Create transfer record
                Transfer.objects.create(
                    source_account=source_account,
                    destination_account=destination_account,
                    amount=amount,
                )

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


class WithdrawFromDependentView(APIView):
    """
    API view for withdrawing balance from a dependent account back to the holder account.
    Only the holder can initiate this operation.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=WithdrawFromDependentSerializer,
        responses={200: None, 400: None, 403: None, 404: None},
        description="Withdraw balance from a dependent account to the holder account. The holder account must belong to the authenticated user and the dependent must be related to that holder.",
        summary="Withdraw Balance from Dependent",
    )
    def post(self, request):
        serializer = WithdrawFromDependentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        holder_account_id = serializer.validated_data["holder_account_id"]
        dependent_account_id = serializer.validated_data["dependent_account_id"]
        amount = serializer.validated_data["amount"]

        try:
            with transaction.atomic():
                # Verify the holder account belongs to the authenticated user
                try:
                    holder_account = Account.objects.select_for_update().get(
                        id=holder_account_id,
                        user=request.user,
                        account_type="holder",
                        is_active=True,
                    )
                except Account.DoesNotExist:
                    return Response(
                        {"error": "La cuenta titular no fue encontrada o no te pertenece"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # Verify the dependent account exists and is active
                try:
                    dependent_account = Account.objects.select_for_update().get(
                        id=dependent_account_id,
                        account_type="dependent",
                        is_active=True,
                    )
                except Account.DoesNotExist:
                    return Response(
                        {"error": "La cuenta adherida no fue encontrada"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # Verify the dependent is actually related to this holder
                is_related = Dependents.objects.filter(
                    holder_account=holder_account,
                    dependent_account=dependent_account,
                    end_date__isnull=True,
                ).exists()

                if not is_related:
                    return Response(
                        {"error": "Las cuentas no están relacionadas o no tenés permiso para realizar esta operación"},
                        status=status.HTTP_403_FORBIDDEN,
                    )

                # Check the dependent has sufficient balance
                if dependent_account.balance < amount:
                    return Response(
                        {"error": "Saldo insuficiente en la cuenta adherida"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Perform the transfer: dependent → holder
                dependent_account.balance -= amount
                holder_account.balance += amount

                dependent_account.save()
                holder_account.save()

                # Record the transfer
                Transfer.objects.create(
                    source_account=dependent_account,
                    destination_account=holder_account,
                    amount=amount,
                )

                return Response(
                    {
                        "message": "Saldo retirado correctamente",
                        "dependent_balance": dependent_account.balance,
                        "holder_balance": holder_account.balance,
                    },
                    status=status.HTTP_200_OK,
                )

        except Exception as e:
            return Response(
                {"error": f"Ocurrió un error: {str(e)}"},
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
    Returns all ACTIVE plates accessible by the authenticated user.
    Includes:
    - Plates owned by the user's holder account (with end_date null)
    - Plates for which the user has authorization through dependent accounts (with end_date null)
    Only active plates (end_date is null) are returned.
    """
    user = request.user
    plates_data = []

    # Get all accounts for the user (holder and dependent)
    user_accounts = Account.objects.filter(user=user, is_active=True)

    for account in user_accounts:
        if account.account_type == "holder":
            # Get only ACTIVE plates owned by this holder account (end_date is null)
            owned_plates = Plates.objects.filter(
                holder_account=account, end_date__isnull=True
            )

            for plate in owned_plates:
                plates_data.append(
                    {
                        "id": plate.id,
                        "plate_number": plate.plate_number,
                        "brand": plate.brand,
                        "model": plate.model,
                        "ownership_type": "owned",
                        "is_active": True,
                        "start_date": plate.start_date,
                        "end_date": None,
                    }
                )

        elif account.account_type == "dependent":
            # Get only ACTIVE authorized plates for this dependent account (end_date is null)
            authorized_plates = AuthorizedPlate.objects.filter(
                dependent_account=account, end_date__isnull=True
            ).select_related("plate")

            for auth in authorized_plates:
                # Also verify that the plate itself is active
                if auth.plate.end_date is None:
                    plates_data.append(
                        {
                            "id": auth.plate.id,
                            "plate_number": auth.plate.plate_number,
                            "brand": auth.plate.brand,
                            "model": auth.plate.model,
                            "ownership_type": "authorized",
                            "is_active": True,
                            "start_date": auth.start_date,
                            "end_date": None,
                        }
                    )

    serializer = UserPlateSerializer(plates_data, many=True)
    return Response(serializer.data)


@extend_schema(
    responses={200: AccountMovementSerializer(many=True)},
    description="Get all movements (transactions) for user's accounts. Includes fuel loads, transfers sent (for holder accounts), transfers received, and balance recharges.",
    summary="Get Account Movements",
    parameters=[
        OpenApiParameter(
            name="account_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Filter movements by specific account ID. If not provided, returns movements for all user's accounts.",
            required=False,
        ),
    ],
)
@api_view(["GET"])
@permission_classes_decorator([IsAuthenticated])
def get_account_movements(request):
    """
    Retrieve all movements (transactions) for the authenticated user's accounts.

    Returns a unified list of:
    - Fuel load operations
    - Transfers sent (for holder accounts)
    - Transfers received (for any account)
    - Balance recharges (ModifyFunds with positive amounts)

    The list is sorted by timestamp in descending order (most recent first).
    """
    user = request.user
    account_id = request.query_params.get("account_id", None)

    # Get user's accounts
    if account_id:
        # Check if account belongs to user directly or if user is the holder of a dependent account
        user_account = Account.objects.filter(
            user=user, id=account_id, is_active=True
        ).first()

        if user_account:
            user_accounts = [user_account]
        else:
            # Check if user is holder and account_id belongs to a dependent
            holder_account = Account.objects.filter(
                user=user, account_type="holder", is_active=True
            ).first()

            if holder_account:
                # Check if the account_id is a dependent of this holder
                dependent_relationship = Dependents.objects.filter(
                    holder_account=holder_account,
                    dependent_account_id=account_id,
                    end_date__isnull=True,
                ).exists()

                if dependent_relationship:
                    user_accounts = Account.objects.filter(
                        id=account_id, is_active=True
                    )
                else:
                    return Response(
                        {
                            "error": "La cuenta no fue encontrada o no tienes permiso para verla"
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )
            else:
                return Response(
                    {"error": "La cuenta no fue encontrada o no te pertenece"},
                    status=status.HTTP_404_NOT_FOUND,
                )
    else:
        user_accounts = Account.objects.filter(user=user, is_active=True)

    movements = []

    for account in user_accounts:
        # 1. Fuel Load Operations
        fuel_loads = FuelLoadOperation.objects.filter(
            account=account, status=FuelLoadOperation.STATUS_COMPLETED
        ).select_related("station", "station__city", "plate", "fuel_type")

        for fuel_load in fuel_loads:
            movements.append(
                {
                    "id": fuel_load.id,
                    "type": "fuel_load",
                    "timestamp": fuel_load.timestamp_finished,
                    "amount": -fuel_load.final_amount
                    if fuel_load.final_amount
                    else -fuel_load.initial_amount,
                    "description": f"Carga de combustible",
                    "station_name": fuel_load.station.name
                    if fuel_load.station
                    else None,
                    "plate_number": fuel_load.plate.plate_number
                    if fuel_load.plate
                    else None,
                    "status": fuel_load.get_status_display(),
                    "remito_url": f"/actions/user/movements/fuel-load/{fuel_load.id}/remito/",
                    "fuel_type_name": fuel_load.fuel_type.name
                    if fuel_load.fuel_type
                    else None,
                    "quantity_liters": str(fuel_load.quantity_liters)
                    if fuel_load.quantity_liters
                    else None,
                    "odometer_km": fuel_load.odometer_km,
                    "station_address": (
                        f"{fuel_load.station.street} {fuel_load.station.street_number or ''}, {fuel_load.station.city.name}".strip(
                            ", "
                        )
                        if fuel_load.station and fuel_load.station.street
                        else None
                    ),
                }
            )

        # 2. Transfers Sent (only for holder accounts)
        if account.account_type == "holder":
            transfers_sent = Transfer.objects.filter(
                source_account=account
            ).select_related("destination_account__user")

            for transfer in transfers_sent:
                dest_user = transfer.destination_account.user
                movements.append(
                    {
                        "id": transfer.id,
                        "type": "transfer_sent",
                        "timestamp": transfer.timestamp,
                        "amount": -transfer.amount,
                        "description": f"Transferencia enviada",
                        "related_user_name": f"{dest_user.first_name} {dest_user.last_name}".strip(),
                        "station_name": None,
                        "plate_number": None,
                        "status": None,
                    }
                )

        # 3. Transfers Received (for any account)
        transfers_received = Transfer.objects.filter(
            destination_account=account
        ).select_related("source_account__user")

        for transfer in transfers_received:
            source_user = transfer.source_account.user
            movements.append(
                {
                    "id": transfer.id,
                    "type": "transfer_received",
                    "timestamp": transfer.timestamp,
                    "amount": transfer.amount,
                    "description": f"Transferencia recibida",
                    "related_user_name": f"{source_user.first_name} {source_user.last_name}".strip(),
                    "station_name": None,
                    "plate_number": None,
                    "status": None,
                }
            )

        # 4. Balance Recharges (ModifyFunds with positive amounts)
        balance_recharges = ModifyFunds.objects.filter(
            account=account, amount__gt=0
        ).select_related("gestor", "payment_method")

        for recharge in balance_recharges:
            gestor_name = (
                f"{recharge.gestor.first_name} {recharge.gestor.last_name}".strip()
                or recharge.gestor.email
            )
            payment_info = (
                recharge.payment_method.name if recharge.payment_method else "Manual"
            )

            movements.append(
                {
                    "id": recharge.id,
                    "type": "balance_recharge",
                    "timestamp": recharge.timestamp,
                    "amount": recharge.amount,
                    "description": f"Recarga de saldo - {payment_info}",
                    "related_user_name": gestor_name,
                    "station_name": None,
                    "plate_number": None,
                    "status": "Aprobada",
                }
            )

    # Sort by timestamp descending (most recent first)
    movements.sort(key=lambda x: x["timestamp"], reverse=True)

    # Apply conditional pagination (only when ?page or ?page_size are present).
    # DEFAULT_PAGINATION_CLASS only activates automatically on ViewSets/GenericAPIViews,
    # so we invoke the paginator manually here.
    from utils.pagination import ConditionalPageNumberPagination

    paginator = ConditionalPageNumberPagination()
    page = paginator.paginate_queryset(movements, request)
    if page is not None:
        serializer = AccountMovementSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = AccountMovementSerializer(movements, many=True)
    return Response(serializer.data)


def _user_can_access_account(user, account):
    if not account or not account.is_active:
        return False
    if account.user_id == user.id:
        return True
    if account.account_type != "dependent":
        return False
    holder_account = Account.objects.filter(
        user=user, account_type="holder", is_active=True
    ).first()
    if not holder_account:
        return False
    return Dependents.objects.filter(
        holder_account=holder_account,
        dependent_account=account,
        end_date__isnull=True,
    ).exists()


@extend_schema(
    responses={200: None},
    description="Download remito PDF for a completed fuel load operation.",
    summary="Download Fuel Load Remito",
)
@api_view(["GET"])
@permission_classes_decorator([IsAuthenticated])
def get_fuel_load_remito(request, operation_id):
    try:
        fuel_load = (
            FuelLoadOperation.objects.select_related(
                "account__user",
                "account__company__organism",
                "station__city",
                "station__province",
                "plate",
                "attendant",
                "payment_method",
            )
            .all()
            .get(id=operation_id)
        )
    except FuelLoadOperation.DoesNotExist:
        return Response(
            {"error": "Operacion no encontrada"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if fuel_load.status != FuelLoadOperation.STATUS_COMPLETED:
        return Response(
            {"error": "El remito solo esta disponible para cargas completadas"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not _user_can_access_account(request.user, fuel_load.account):
        return Response(
            {"error": "No tenes permiso para ver este remito"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Detectar si la cuenta tiene empresa asociada
    company = fuel_load.account.company if fuel_load.account else None
    if company:
        organism = company.organism
        pdf_bytes = build_fuel_load_remito_empresa_pdf(fuel_load, company, organism)
    else:
        pdf_bytes = build_fuel_load_remito_pdf(fuel_load)

    filename = f"remito_carga_{fuel_load.id}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
