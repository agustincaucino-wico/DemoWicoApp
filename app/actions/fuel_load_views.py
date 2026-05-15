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
    CancelFuelLoadRequestSerializer,
    CancelFuelLoadResponseSerializer,
    CancelWaitingRequestSerializer,
    CheckOperationStatusSerializer,
    FuelLoadStatusSerializer,
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
    print(serializer.initial_data)  # Debug: print incoming data
    if serializer.is_valid():
        account_id = serializer.validated_data["account"]
        amount = serializer.validated_data["amount"]
        station_id = serializer.validated_data["station"]
        plate_id = serializer.validated_data.get("plate")
        fill_full_tank = serializer.validated_data.get("fill_full_tank", False)
        # Córdoba-specific fields
        fuel_type_id = serializer.validated_data.get("fuel_type")
        odometer_km = serializer.validated_data.get("odometer_km")

        # Validate account exists and belongs to user
        from accounts.models import Account

        try:
            account = Account.objects.get(
                id=account_id, user=request.user, is_active=True
            )
        except Account.DoesNotExist:
            return Response(
                {"error": "Cuenta no encontrada, inactiva o no te pertenece"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if plate is required (all accounts must provide a plate)
        if not plate_id:
            return Response(
                {"error": "Todas las cuentas deben especificar una patente"},
                status=status.HTTP_400_BAD_REQUEST,
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
                    "error": "Ya tenés una operación de carga de combustible en progreso",
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
                {"error": "Estación no encontrada"}, status=status.HTTP_404_NOT_FOUND
            )

        # Validate plate if provided
        plate = None
        if plate_id:
            try:
                plate = Plates.objects.get(id=plate_id)
            except Plates.DoesNotExist:
                return Response(
                    {"error": "Patente no encontrada"}, status=status.HTTP_404_NOT_FOUND
                )

            # Verify that the plate is active (end_date is null)
            if plate.end_date is not None:
                return Response(
                    {"error": "Esta patente ya no está activa"},
                    status=status.HTTP_400_BAD_REQUEST,
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
                print("Account is: ", account)  # Debug: print account info
                print(AuthorizedPlate.objects.filter(
                    # dependent_account=account,
                    plate=plate,
                ))  # Debug: print the queryset for authorization check
                has_authorization = AuthorizedPlate.objects.filter(
                    dependent_account=account,
                    plate=plate,
                    end_date__isnull=True,  # Active authorization
                ).exists()
                if has_authorization:
                    has_access = True

            if not has_access:
                return Response(
                    {"error": "La cuenta no tiene permisos para usar esta patente"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Accounts with unlimited_balance skip balance validation (e.g. Cordoba accounts)
        if account.unlimited_balance:
            operation_status = "pending"
        elif account.balance < amount:
            operation_status = "no_balance"
            operation = FuelLoadOperation.objects.create(
                account=account,
                station=station,
                plate=plate,
                initial_amount=amount,
                status=operation_status,
                fill_full_tank=fill_full_tank,
            )
            return Response(
                {"error": "No tenés saldo suficiente para realizar esta carga."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            operation_status = "pending"

        # Validate required fields
        from stations.models import FuelType

        # fuel_type: optional in backend (older app versions may not send it)
        # but enforced as required from the frontend
        fuel_type_obj = None
        if fuel_type_id:
            try:
                fuel_type_obj = FuelType.objects.get(id=fuel_type_id, is_active=True)
            except FuelType.DoesNotExist:
                return Response(
                    {"error": "Tipo de combustible no encontrado o inactivo"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Cordoba accounts: odometer is required
        if account.special == "cordoba":
            if odometer_km is None:
                return Response(
                    {"error": "El odómetro es obligatorio."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

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
            fill_full_tank=fill_full_tank,
            fuel_type=fuel_type_obj,
            odometer_km=odometer_km,
        )

        response_serializer = FuelLoadOperationSerializer(operation)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    request=CancelFuelLoadRequestSerializer,
    responses={200: CancelFuelLoadResponseSerializer, 404: None, 400: None},
    tags=["actions - fuel load - client"],
    description="Client cancels a pending fuel load operation.",
    summary="Cancel Fuel Load",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_fuel_load(request, operation_id):
    """
    Client cancels a pending fuel load operation with a message.
    Used when canceling during the fuel loading process (waitingFuelLoad screen).
    """
    serializer = CancelFuelLoadRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    comment = serializer.validated_data.get("message") or ""

    try:
        operation = FuelLoadOperation.objects.get(
            id=operation_id, account__user=request.user
        )
        if operation.status in [
            FuelLoadOperation.STATUS_PENDING,
            FuelLoadOperation.STATUS_IN_PROGRESS,
        ]:
            operation.status = FuelLoadOperation.CANCELED_BY_USER
            operation.comments = comment
            operation.timestamp_finished = timezone.now()
            operation.save()
            return Response(
                {"message": "Operación cancelada exitosamente por el usuario"}
            )
        return Response(
            {
                "error": f"No se puede cancelar la operación con estado: {operation.status}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except FuelLoadOperation.DoesNotExist:
        return Response(
            {"error": "Operación no encontrada"}, status=status.HTTP_404_NOT_FOUND
        )


@extend_schema(
    request=CancelWaitingRequestSerializer,
    responses={200: CancelFuelLoadResponseSerializer, 404: None, 400: None},
    tags=["actions - fuel load - client"],
    description="Client cancels waiting for attendant without a message.",
    summary="Cancel Waiting for Attendant",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_waiting_for_attendant(request):
    """
    Client cancels waiting for attendant (waitingAttendant screen).
    No message required, simply cancels the pending operation.
    """
    try:
        # Get the most recent pending operation for the user
        operation = (
            FuelLoadOperation.objects.filter(
                account__user=request.user, status=FuelLoadOperation.STATUS_PENDING
            )
            .order_by("-timestamp_started")
            .first()
        )

        if not operation:
            return Response(
                {"error": "No se encontró ninguna operación pendiente"},
                status=status.HTTP_404_NOT_FOUND,
            )

        operation.status = FuelLoadOperation.WAITING_CANCELED
        operation.timestamp_finished = timezone.now()
        operation.save()

        return Response({"message": "Operación cancelada exitosamente"})
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
                {"error": "No hay estación activa asignada a este playero"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Filter operations by station and pending/in_progress status
        # For IN_PROGRESS operations, only show those assigned to this attendant
        from django.db.models import Q

        operations = (
            FuelLoadOperation.objects.filter(
                station=assignment.station,
                status__in=[
                    FuelLoadOperation.STATUS_PENDING,
                    FuelLoadOperation.STATUS_IN_PROGRESS,
                ],
            )
            .filter(
                Q(status=FuelLoadOperation.STATUS_PENDING)
                | Q(status=FuelLoadOperation.STATUS_IN_PROGRESS, attendant=request.user)
            )
            .select_related("account__user", "plate", "fuel_type")
            .order_by("timestamp_started")
        )

        serializer = PendingFuelLoadSerializer(operations, many=True)

        # Include station information in the response
        station_info = {
            "id": assignment.station.id,
            "name": assignment.station.name,
            "city": assignment.station.city.name if assignment.station.city else None,
        }

        return Response({"station": station_info, "pending_loads": serializer.data})
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
                    {"error": "No hay estación activa asignada a este playero"},
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
                    "error": "Operación no encontrada, no está pendiente, o no pertenece a tu estación asignada"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    request=CompleteFuelLoadSerializer,
    responses={200: FuelLoadOperationSerializer, 400: None, 404: None},
    tags=["actions - fuel load - attendant"],
    description="Attendant completes a fuel load operation. Changes status to completed, sets timestamp_finished, and deducts the amount from the account balance.",
    summary="Complete Fuel Load",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_fuel_load(request):
    """
    Attendant completes a fuel load operation.
    Changes status to completed, sets timestamp_finished, and deducts the amount from the account balance.
    """
    from django.db import transaction

    serializer = CompleteFuelLoadSerializer(data=request.data)
    if serializer.is_valid():
        operation_id = serializer.validated_data["id_operation"]
        final_amount = serializer.validated_data["final_amount"]
        fuel_type_id = serializer.validated_data.get("fuel_type")
        odometer_km = serializer.validated_data.get("odometer_km")
        quantity_liters = serializer.validated_data.get("quantity_liters")

        try:
            with transaction.atomic():
                operation = FuelLoadOperation.objects.select_related("account").get(
                    id=operation_id,
                    status=FuelLoadOperation.STATUS_IN_PROGRESS,
                    attendant=request.user,
                )

                account = operation.account

                # Cordoba accounts require quantity_liters from attendant
                # (fuel_type and odometer_km were already set during initiation)
                if account.special == "cordoba":
                    if not quantity_liters:
                        return Response(
                            {
                                "error": "El campo cantidad de litros es obligatorio para cuentas Córdoba"
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # Balance validation & deduction: skip for unlimited_balance accounts
                if not account.unlimited_balance:
                    if account.balance < final_amount:
                        return Response(
                            {
                                "error": "Saldo insuficiente en la cuenta para completar la carga"
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    # Deduct the final amount from the account balance
                    account.balance -= final_amount
                    account.save()

                # Update the operation
                operation.status = FuelLoadOperation.STATUS_COMPLETED
                operation.final_amount = final_amount
                operation.timestamp_finished = timezone.now()

                # Save optional fuel load details
                if fuel_type_id:
                    from stations.models import FuelType

                    try:
                        operation.fuel_type = FuelType.objects.get(id=fuel_type_id)
                    except FuelType.DoesNotExist:
                        return Response(
                            {"error": "Tipo de combustible no encontrado"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                if odometer_km is not None:
                    operation.odometer_km = odometer_km
                if quantity_liters:
                    operation.quantity_liters = quantity_liters

                # ── Carbon footprint calculation ─────────────────────────────
                from utils.carbon_calculator import calculate_carbon_saving

                fuel_name = operation.fuel_type.name if operation.fuel_type else ""
                liters_for_calc = quantity_liters or operation.quantity_liters
                if fuel_name and liters_for_calc:
                    operation.co2_saved_kg = calculate_carbon_saving(
                        fuel_name, liters_for_calc
                    )

                operation.save()

                response_serializer = FuelLoadOperationSerializer(operation)
                return Response(response_serializer.data)
        except FuelLoadOperation.DoesNotExist:
            return Response(
                {
                    "error": "Operación no encontrada, no está en progreso, o no está asignada a vos"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    request=CancelFuelLoadResponseSerializer,
    responses={
        200: {"message": "Operación cancelada exitosamente"},
        404: None,
        400: None,
    },
    tags=["actions - fuel load - attendant"],
    description="Attendant cancels a fuel load operation with a reason.",
    summary="Cancel Fuel Load by Attendant",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_fuel_load_by_attendant(request, operation_id):
    """
    Attendant cancels a fuel load operation with a reason.
    """
    try:
        operation = FuelLoadOperation.objects.get(id=operation_id)

        # Ensure the operation is at the attendant's assigned station
        assignment = StationAttendantAssignment.objects.filter(
            attendant=request.user, station=operation.station, end_date__isnull=True
        ).first()

        if not assignment:
            return Response(
                {"error": "No tienes permiso para cancelar esta operación."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if operation.status in [
            FuelLoadOperation.STATUS_IN_PROGRESS,
        ]:
            comment = request.data.get("message", "")
            operation.status = FuelLoadOperation.CANCELED_BY_ATENDEE
            operation.comments = comment
            operation.timestamp_finished = timezone.now()
            operation.save()
            return Response({"message": "Operación cancelada exitosamente"})

        return Response(
            {
                "error": f"No se puede cancelar la operación con estado: {operation.status}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except FuelLoadOperation.DoesNotExist:
        return Response(
            {"error": "Operación no encontrada"}, status=status.HTTP_404_NOT_FOUND
        )


@extend_schema(
    responses={200: CheckOperationStatusSerializer, 404: None},
    tags=["actions - fuel load - client"],
    description="Check the status, operation ID, final amount, and other details of a fuel load operation.",
    summary="Check Operation Status",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_last_operation_status(request):
    """
    Client checks the status of their most recent fuel load operation.
    Returns status, operation_id, final_amount, and related details.
    """
    try:
        # Get the most recent operation for the user
        operation = (
            FuelLoadOperation.objects.filter(account__user=request.user)
            .select_related("account", "account__user", "station", "plate", "fuel_type")
            .order_by("-timestamp_started")
            .first()
        )

        if not operation:
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Build account_name from the account's user
        account_name = None
        if operation.account and operation.account.user:
            user = operation.account.user
            if user.first_name and user.last_name:
                account_name = f"{user.first_name} {user.last_name}"
            else:
                account_name = user.email

        serializer = CheckOperationStatusSerializer(
            {
                "status": operation.status,
                "operation_id": operation.id,
                "final_amount": operation.final_amount,
                "initial_amount": operation.initial_amount,
                "balance": operation.account.balance if operation.account else None,
                "station_name": operation.station.name if operation.station else None,
                "plate": operation.plate.plate_number if operation.plate else None,
                "account_name": account_name,
                "display_type": operation.account.display_type
                if operation.account
                else None,
                "quantity_liters": operation.quantity_liters,
                "fuel_type_name": operation.fuel_type.name
                if operation.fuel_type
                else None,
                "unlimited_balance": operation.account.unlimited_balance
                if operation.account
                else False,
            }
        )
        return Response(serializer.data)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    responses={200: FuelLoadStatusSerializer, 404: None, 403: None},
    tags=["actions - fuel load - attendant"],
    description="Attendant checks the status of a specific fuel load operation by operation ID.",
    summary="Get Fuel Load Status",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_fuel_load_status(request, operation_id):
    """
    Attendant checks the status of a specific fuel load operation.
    Used to monitor if the client has canceled the operation during confirmation.
    """
    try:
        # Get attendant's assigned station (active assignment)
        assignment = StationAttendantAssignment.objects.filter(
            attendant=request.user, end_date__isnull=True
        ).first()

        if not assignment:
            return Response(
                {"error": "No hay estación activa asignada a este playero"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the operation and verify it belongs to the attendant's station
        operation = FuelLoadOperation.objects.select_related(
            "account__user", "plate", "station"
        ).get(id=operation_id, station=assignment.station)

        # Use the FuelLoadStatusSerializer to format the response
        serializer = FuelLoadStatusSerializer(operation)
        return Response(serializer.data)

    except FuelLoadOperation.DoesNotExist:
        return Response(
            {"error": "Operación no encontrada o no pertenece a tu estación"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


###########################
### Manager (Encargado) endpoints
###########################

from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="station_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="ID de la estación de la cual obtener las operaciones",
            required=True,
        ),
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filtrar por estado de la operación (pending, in_progress, completed, no_balance, waiting_canceled, canceled_by_attendee, canceled_by_user)",
            required=False,
            enum=[
                "pending",
                "in_progress",
                "completed",
                "no_balance",
                "waiting_canceled",
                "canceled_by_attendee",
                "canceled_by_user",
            ],
        ),
        OpenApiParameter(
            name="date_from",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filtrar operaciones desde esta fecha (formato: YYYY-MM-DD)",
            required=False,
        ),
        OpenApiParameter(
            name="date_to",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filtrar operaciones hasta esta fecha (formato: YYYY-MM-DD)",
            required=False,
        ),
    ],
    responses={
        200: FuelLoadOperationSerializer(many=True),
        403: None,
    },
    tags=["actions - fuel load - encargado"],
    description=(
        "Obtiene todas las operaciones de carga de combustible de una estación específica.\n\n"
        "**Permisos requeridos:**\n"
        "- El usuario debe tener el rol 'Encargado'\n"
        "- El usuario debe estar asignado a la estación solicitada (asignación activa sin fecha de fin)\n\n"
        "**Filtros disponibles:**\n"
        "- `status`: Filtra por estado de la operación\n"
        "- `date_from`: Filtra operaciones desde una fecha específica\n"
        "- `date_to`: Filtra operaciones hasta una fecha específica"
    ),
    summary="Obtener operaciones de una estación (Encargado)",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_station_operations(request, station_id):
    """
    Get all fuel load operations for a specific station.
    Only accessible by users with Encargado role who are assigned to the station.
    """
    user = request.user

    # Check if user has Encargado role
    if not user.groups.filter(name="Encargado").exists():
        return Response(
            {"error": "No tenés permisos para ver las operaciones de esta estación"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Check if user is assigned to this station
    assignment = StationAttendantAssignment.objects.filter(
        attendant=user,
        station_id=station_id,
        end_date__isnull=True,
    ).first()

    if not assignment:
        return Response(
            {"error": "No estás asignado a esta estación"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Get query params for filtering
    status_filter = request.query_params.get("status")
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")

    # Get operations for the station
    operations = (
        FuelLoadOperation.objects.filter(station_id=station_id)
        .select_related(
            "account__user",
            "plate",
            "attendant",
            "station",
            "payment_method",
        )
        .order_by("-timestamp_started")
    )

    # Apply filters
    if status_filter:
        operations = operations.filter(status=status_filter)
    if date_from:
        operations = operations.filter(timestamp_started__date__gte=date_from)
    if date_to:
        operations = operations.filter(timestamp_started__date__lte=date_to)

    # Serialize and return
    serializer = FuelLoadOperationSerializer(operations, many=True)
    return Response(serializer.data)


@extend_schema(
    responses={200: None},
    tags=["actions - carbon"],
    description=(
        "Returns all completed fuel loads for the authenticated user that have a "
        "positive co2_saved_kg value. Used to populate the carbon footprint screen."
    ),
    summary="Get Carbon Loads",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_carbon_loads(request):
    """
    Returns the user's completed biofuel loads with their CO₂ savings.
    Only loads with co2_saved_kg > 0 are included.
    """
    from actions.fuel_load_serializers import CarbonLoadSerializer

    operations = (
        FuelLoadOperation.objects.filter(
            account__user=request.user,
            status=FuelLoadOperation.STATUS_COMPLETED,
            co2_saved_kg__isnull=False,
            co2_saved_kg__gt=0,
        )
        .select_related("station", "fuel_type")
        .order_by("-timestamp_finished")
    )

    serializer = CarbonLoadSerializer(operations, many=True)
    return Response(serializer.data)
