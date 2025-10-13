from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from drf_spectacular.utils import extend_schema

from operation.models import FuelLoadOperation
from operation.serializers import FuelLoadOperationSerializer
from actions.fuel_load_serializers import (
    InitiateFuelLoadSerializer,
    StartFuelLoadSerializer,
    CompleteFuelLoadSerializer,
    PendingFuelLoadSerializer,
    CancelFuelLoadResponseSerializer,
    CheckOperationStatusSerializer,
)
from stations.models import StationAttendantAssignment, Station
from accounts.models import Plates

#####################
### Client endpoints
#####################


@extend_schema(
    request=InitiateFuelLoadSerializer,
    responses={201: FuelLoadOperationSerializer, 400: None},
    tags=["actions - fuel load - client"],
    description="Client initiates a fuel load operation. Creates FuelLoadOperation with pending or no_balance status.",
    summary="Initiate Fuel Load",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_fuel_load(request):
    """
    Client initiates a fuel load operation.
    Creates FuelLoadOperation with pending or no_balance status.
    """
    serializer = InitiateFuelLoadSerializer(data=request.data)
    if serializer.is_valid():
        account_id = serializer.validated_data["account"]
        amount = serializer.validated_data["amount"]
        station_id = serializer.validated_data["station"]
        plate_id = serializer.validated_data["plate"]

        # Validate account exists and belongs to user
        from accounts.models import Account

        try:
            account = Account.objects.get(id=account_id, user=request.user)
        except Account.DoesNotExist:
            return Response(
                {"error": "Account not found or does not belong to you"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if user already has a pending or in-progress fuel load operation
        existing_operation = FuelLoadOperation.objects.filter(
            account__user=request.user,
            status__in=[
                FuelLoadOperation.STATUS_PENDING,
                FuelLoadOperation.STATUS_IN_PROGRESS,
            ],
        ).first()

        if existing_operation:
            return Response(
                {
                    "error": "You already have a fuel load operation in progress",
                    "operation_id": existing_operation.id,
                    "status": existing_operation.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate station exists
        try:
            station = Station.objects.get(id=station_id)
        except Station.DoesNotExist:
            return Response(
                {"error": "Station not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Validate plate exists and is accessible by the user through the specified account
        try:
            plate = Plates.objects.get(id=plate_id)
        except Plates.DoesNotExist:
            return Response(
                {"error": "Plate not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if user has access to this plate through the specified account
        has_access = False

        if account.account_type == "holder":
            # If it's a holder account, check if the plate belongs to this account
            if plate.holder_account == account:
                has_access = True
        elif account.account_type == "dependent":
            # If it's a dependent account, check if there's an active authorization
            from accounts.models import AuthorizedPlate

            has_authorization = AuthorizedPlate.objects.filter(
                dependent_account=account,
                plate=plate,
                end_date__isnull=True,  # Active authorization
            ).exists()
            if has_authorization:
                has_access = True

        if not has_access:
            return Response(
                {
                    "error": "The specified account does not have permission to use this plate"
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if account.balance < amount:
            operation_status = "no_balance"
        else:
            operation_status = "pending"

        # For future implementation of payment methods
        # from operation.models import PaymentMethod

        # # Possible change in the future
        # try:
        #     payment_method = PaymentMethod.objects.filter(name="wico-app").first()
        #     if not payment_method:
        #         return Response(
        #             {"error": "No active payment method available"},
        #             status=status.HTTP_400_BAD_REQUEST,
        #         )
        # except Exception:
        #     return Response(
        #         {"error": "Payment method not configured"},
        #         status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        #     )

        operation = FuelLoadOperation.objects.create(
            account=account,
            station=station,
            plate=plate,
            initial_amount=amount,
            status=operation_status,
        )

        response_serializer = FuelLoadOperationSerializer(operation)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    request=None,  # No request body needed
    responses={200: CancelFuelLoadResponseSerializer, 404: None, 400: None},
    tags=["actions - fuel load - client"],
    description="Client cancels a pending fuel load operation.",
    summary="Cancel Fuel Load",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_fuel_load(request, operation_id):
    """
    Client cancels a pending fuel load operation.
    """
    try:
        operation = FuelLoadOperation.objects.get(
            id=operation_id, account__user=request.user
        )
        if operation.status == FuelLoadOperation.STATUS_PENDING:
            operation.status = FuelLoadOperation.STATUS_CANCELED
            operation.save()
            return Response({"message": "Operation cancelled successfully"})
        return Response(
            {"error": f"Cannot cancel operation with status: {operation.status}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except FuelLoadOperation.DoesNotExist:
        return Response(
            {"error": "Operation not found"}, status=status.HTTP_404_NOT_FOUND
        )


###########################
### Attendant endpoints ###
###########################


@extend_schema(
    responses={200: PendingFuelLoadSerializer(many=True)},
    tags=["actions - fuel load - attendant"],
    description="Get pending and in-progress fuel loads for the attendant's assigned station.",
    summary="Get Pending Loads",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_fuel_loads(request):
    """
    Get pending and in-progress fuel loads for the attendant's assigned station.
    Filters loads based on the attendant's assigned station.
    """
    try:
        # Get attendant's assigned station (active assignment)
        assignment = StationAttendantAssignment.objects.filter(
            attendant=request.user, end_date__isnull=True
        ).first()

        if not assignment:
            return Response(
                {"error": "No active station assigned to this attendant"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Filter operations by station and pending/in_progress status
        operations = (
            FuelLoadOperation.objects.filter(
                station=assignment.station,
                status__in=[
                    FuelLoadOperation.STATUS_PENDING,
                    FuelLoadOperation.STATUS_IN_PROGRESS,
                ],
            )
            .select_related("account__user", "plate")
            .order_by("timestamp_started")
        )

        serializer = PendingFuelLoadSerializer(operations, many=True)
        return Response(serializer.data)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    request=StartFuelLoadSerializer,
    responses={200: FuelLoadOperationSerializer, 400: None, 404: None},
    tags=["actions - fuel load - attendant"],
    description="Attendant starts processing a fuel load. Changes status to in_progress and sets timestamp_atended.",
    summary="Start Fuel Load",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_fuel_load(request):
    """
    Attendant starts processing a fuel load.
    Changes status to in_progress and sets timestamp_atended.
    Returns initial_amount in response.
    """
    serializer = StartFuelLoadSerializer(data=request.data)
    if serializer.is_valid():
        operation_id = serializer.validated_data["id_operation"]
        try:
            # Verify attendant's station assignment
            assignment = StationAttendantAssignment.objects.filter(
                attendant=request.user, end_date__isnull=True
            ).first()

            if not assignment:
                return Response(
                    {"error": "No active station assigned to this attendant"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            operation = FuelLoadOperation.objects.get(
                id=operation_id,
                station=assignment.station,
                status=FuelLoadOperation.STATUS_PENDING,
            )

            operation.status = FuelLoadOperation.STATUS_IN_PROGRESS
            operation.timestamp_atended = timezone.now()
            operation.attendant = request.user
            operation.save()

            response_serializer = FuelLoadOperationSerializer(operation)
            return Response(
                {
                    **response_serializer.data,
                    "initial_amount": str(operation.initial_amount),
                }
            )
        except FuelLoadOperation.DoesNotExist:
            return Response(
                {
                    "error": "Operation not found, not pending, or not for your assigned station"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    request=CompleteFuelLoadSerializer,
    responses={200: FuelLoadOperationSerializer, 400: None, 404: None},
    tags=["actions - fuel load - attendant"],
    description="Attendant completes a fuel load operation. Changes status to completed and sets timestamp_finished.",
    summary="Complete Fuel Load",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_fuel_load(request):
    """
    Attendant completes a fuel load operation.
    Changes status to completed and sets timestamp_finished.
    """
    serializer = CompleteFuelLoadSerializer(data=request.data)
    if serializer.is_valid():
        operation_id = serializer.validated_data["id_operation"]
        final_amount = serializer.validated_data["final_amount"]

        try:
            operation = FuelLoadOperation.objects.get(
                id=operation_id,
                status=FuelLoadOperation.STATUS_IN_PROGRESS,
                attendant=request.user,
            )

            operation.status = FuelLoadOperation.STATUS_COMPLETED
            operation.final_amount = final_amount
            operation.timestamp_finished = timezone.now()
            operation.save()

            response_serializer = FuelLoadOperationSerializer(operation)
            return Response(response_serializer.data)
        except FuelLoadOperation.DoesNotExist:
            return Response(
                {
                    "error": "Operation not found, not in progress, or not assigned to you"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    responses={200: CheckOperationStatusSerializer, 404: None},
    tags=["actions - fuel load - client"],
    description="Check the status and final amount of a fuel load operation.",
    summary="Check Operation Status",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_operation_status(request):
    """
    Client checks the status of their most recent fuel load operation.
    Returns state and final_amount.
    """
    try:
        # Get the most recent operation for the user across all their accounts
        operation = (
            FuelLoadOperation.objects.filter(account__user=request.user)
            .order_by("-timestamp_started")
            .first()
        )

        if not operation:
            return Response(
                {"error": "No fuel load operation found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CheckOperationStatusSerializer(
            {"state": operation.status, "final_amount": operation.final_amount}
        )
        return Response(serializer.data)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
