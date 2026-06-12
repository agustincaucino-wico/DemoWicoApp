from rest_framework import mixins, viewsets, status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiExample
from django.db import transaction, IntegrityError
from django.utils import timezone

from myapp.permissions import StrictDjangoModelPermissions
from .permissions import DjangoModelOrObjectOwner, IsPlayero
from users.utils import should_apply_flota_restrictions


from .models import (
    Account,
    Dependents,
    Plates,
    AuthorizedPlate,
    Company,
    CompanyAssignment,
    DependentInvitation,
    Organism,
    AuthorizedEmail,
)
from .serializers import (
    AccountSerializer,
    AccountBalanceUpdateSerializer,
    AdminAccountCreateSerializer,
    AdminAccountUpdateSerializer,
    DependentsSerializer,
    PlatesSerializer,
    PlatesUpdateSerializer,
    AuthorizedPlateSerializer,
    CompanySerializer,
    CompanyAssignmentSerializer,
    OrganismSerializer,
    AuthorizedEmailSerializer,
)
from actions.serializers import DependentInvitationSerializer


class BaseLCViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [StrictDjangoModelPermissions]


class BaseLCUDViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet con soporte completo para actualización (PATCH/PUT)"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [StrictDjangoModelPermissions]


class AccountViewSet(BaseLCViewSet):
    queryset = Account.objects.filter(is_active=True).order_by("id")
    serializer_class = AccountSerializer
    def get_queryset(self):
        """
        Filtrar cuentas según el usuario:
        - Acciones admin (admin-update, reactivate, deactivate, list_all): incluir todas
        - Usuarios Flota (sin rol Gestor): solo sus propias cuentas
        - Usuarios con rol Gestor: acceso completo
        - Otros: según permisos del modelo
        """
        # Para acciones admin, incluir cuentas inactivas también
        if self.action in (
            "admin_update",
            "reactivate",
            "deactivate_account",
            "list_all",
        ):
            queryset = Account.objects.all().order_by("id")
        else:
            queryset = Account.objects.filter(is_active=True).order_by("id")
        if should_apply_flota_restrictions(self.request.user):
            # Usuarios Flota solo ven sus propias cuentas
            return queryset.filter(user=self.request.user)
        # Gestores/admins: filtro opcional por usuario
        user_id = self.request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset
    @extend_schema(
        request=AccountBalanceUpdateSerializer,
        responses={200: AccountBalanceUpdateSerializer},
        description="Actualiza el balance de una cuenta específica. Crea un registro en ModifyFunds.",
        examples=[
            OpenApiExample(
                "Ejemplo de actualización de balance",
                value={
                    "balance": 1000.50,
                    "comments": "Pago de cliente X",
                },
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["patch"], url_path="update-balance")
    def update_balance(self, request, pk=None):
        """
        Actualiza únicamente el balance de una cuenta.
        También crea un registro en ModifyFunds con comentarios.
        """
        from operation.models import ModifyFunds, PaymentMethod
        from django.db import transaction

        account = self.get_object()
        serializer = AccountBalanceUpdateSerializer(
            account, data=request.data, partial=True
        )

        if serializer.is_valid():
            new_balance = serializer.validated_data.get("balance")
            amount_change = new_balance - account.balance
            comments = serializer.validated_data.get("comments", "")

            try:
                with transaction.atomic():
                    # Actualizar el balance
                    serializer.save()

                    # Obtener o crear el método de pago "Ajuste manual"
                    payment_method, _ = PaymentMethod.objects.get_or_create(
                        name="Ajuste manual", defaults={"is_active": True}
                    )

                    # Crear entrada en ModifyFunds
                    ModifyFunds.objects.create(
                        account=account,
                        gestor=request.user,
                        amount=amount_change,
                        payment_method=payment_method,
                        comments=comments or None,
                    )

                return Response(
                    {
                        "id": account.id,
                        "balance": account.balance,
                        "message": "Balance actualizado correctamente",
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"error": f"Error al actualizar el balance: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Motivo de la desactivación",
                    },
                },
            }
        },
        responses={200: AccountSerializer},
        description="Desactiva una cuenta (titular o adherida). Cancela todas las relaciones activas asociadas a la cuenta.",
    )
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate_account(self, request, pk=None):
        """
        Desactiva una cuenta (titular o adherida).

        Para cuentas TITULARES:
        - Finaliza relaciones de Dependents activos (end_date = hoy)
        - Da de baja Plates activas (end_date = hoy)
        - Revoca AuthorizedPlates (end_date = hoy)
        - Cancela invitaciones pendientes
        - Marca la cuenta como inactiva

        Para cuentas ADHERIDAS:
        - Finaliza su relación como dependiente (end_date = hoy)
        - Revoca sus autorizaciones de patentes (end_date = hoy)
        - Marca la cuenta como inactiva
        """
        from django.db import transaction

        account = self.get_object()

        # Validar que no esté ya desactivada
        if not account.is_active:
            return Response(
                {
                    "error": "Esta cuenta ya está desactivada",
                    "deactivated_at": account.deactivated_at,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Obtener motivo de desactivación (opcional)
        reason = request.data.get("reason", "")

        try:
            with transaction.atomic():
                today = timezone.now().date()
                summary = {}

                if account.account_type == "holder":
                    # CUENTA TITULAR: Desactivar todas sus relaciones

                    # 1. Finalizar relaciones de Dependents activos y desactivar las cuentas adheridas
                    active_dependents = Dependents.objects.filter(
                        holder_account=account, end_date__isnull=True
                    ).select_related("dependent_account__user")
                    dependents_count = active_dependents.count()

                    dependent_accounts_to_deactivate = []
                    for dep_relation in active_dependents:
                        dep_account = dep_relation.dependent_account
                        if dep_account.is_active:
                            dependent_accounts_to_deactivate.append(dep_account)

                    active_dependents.update(end_date=today)
                    summary["dependents_finalized"] = dependents_count

                    # Desactivar cada cuenta adherida y gestionar rol Flota
                    from django.contrib.auth.models import Group as AuthGroup

                    flota_group_obj = None
                    try:
                        flota_group_obj = AuthGroup.objects.get(name="Flota")
                    except AuthGroup.DoesNotExist:
                        pass

                    for dep_account in dependent_accounts_to_deactivate:
                        dep_account.is_active = False
                        dep_account.deactivated_at = timezone.now()
                        dep_account.deactivated_by = request.user
                        dep_account.deactivation_reason = "Cuenta titular dada de baja"
                        dep_account.save()

                        # Revocar autorizaciones de patentes del adherido
                        AuthorizedPlate.objects.filter(
                            dependent_account=dep_account, end_date__isnull=True
                        ).update(end_date=today)

                        # Quitar rol Flota si ya no tiene cuentas activas
                        if flota_group_obj and dep_account.user:
                            dep_user = dep_account.user
                            remaining = Account.objects.filter(
                                user=dep_user, is_active=True
                            ).exists()
                            if not remaining:
                                dep_user.groups.remove(flota_group_obj)

                    summary["dependent_accounts_deactivated"] = len(
                        dependent_accounts_to_deactivate
                    )

                    # 2. Dar de baja Plates activas
                    active_plates = Plates.objects.filter(
                        holder_account=account, end_date__isnull=True
                    )
                    plates_count = active_plates.count()
                    active_plates.update(end_date=today)
                    summary["plates_deactivated"] = plates_count

                    # 3. Revocar AuthorizedPlates activas
                    active_authorized_plates = AuthorizedPlate.objects.filter(
                        plate__holder_account=account, end_date__isnull=True
                    )
                    auth_plates_count = active_authorized_plates.count()
                    active_authorized_plates.update(end_date=today)
                    summary["authorized_plates_revoked"] = auth_plates_count

                    # 4. Cancelar invitaciones pendientes
                    pending_invitations = DependentInvitation.objects.filter(
                        holder_account=account, status="pending"
                    )
                    invitations_count = pending_invitations.count()
                    for invitation in pending_invitations:
                        invitation.status = "cancelled"
                        invitation.response_date = timezone.now()
                        invitation.save()
                    summary["invitations_cancelled"] = invitations_count

                elif account.account_type == "dependent":
                    # CUENTA ADHERIDA: Finalizar su relación como dependiente

                    # 1. Finalizar relación como dependiente
                    active_dependent_relations = Dependents.objects.filter(
                        dependent_account=account, end_date__isnull=True
                    )
                    relations_count = active_dependent_relations.count()
                    active_dependent_relations.update(end_date=today)
                    summary["dependent_relations_finalized"] = relations_count

                    # 2. Revocar autorizaciones de patentes
                    active_authorized_plates = AuthorizedPlate.objects.filter(
                        dependent_account=account, end_date__isnull=True
                    )
                    auth_plates_count = active_authorized_plates.count()
                    active_authorized_plates.update(end_date=today)
                    summary["authorized_plates_revoked"] = auth_plates_count

                # 5. Desactivar la cuenta (aplica para ambos tipos)
                account.is_active = False
                account.deactivated_at = timezone.now()
                account.deactivated_by = request.user
                account.deactivation_reason = reason or None
                account.save()

                # 6. Verificar si el usuario queda sin cuentas activas y remover rol 'Flota'
                from django.contrib.auth.models import Group

                user = account.user
                remaining_accounts = Account.objects.filter(user=user, is_active=True)
                flota_role_removed = False

                if not remaining_accounts.exists():
                    try:
                        flota_group = Group.objects.get(name="Flota")
                        if user.groups.filter(name="Flota").exists():
                            user.groups.remove(flota_group)
                            user.save()
                            flota_role_removed = True
                    except Group.DoesNotExist:
                        pass

                response_data = {
                    "message": f"Cuenta {account.get_account_type_display().lower()} desactivada exitosamente",
                    "account_id": account.id,
                    "account_type": account.account_type,
                    "deactivated_at": account.deactivated_at,
                    "balance_remaining": float(account.balance),
                    "summary": summary,
                }

                if flota_role_removed:
                    response_data["flota_role_removed"] = True
                    response_data["message"] += (
                        ". Se removió el rol 'Flota' porque el usuario quedó sin cuentas activas."
                    )

                return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": f"Error al desactivar la cuenta: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ── Admin-only endpoints ──────────────────────────────────────────────

    def _is_admin_or_gestor(self, request):
        return (
            request.user.is_superuser
            or request.user.groups.filter(name="Gestor").exists()
        )

    @extend_schema(
        description="Lista TODAS las cuentas (activas e inactivas). Solo Gestor/superuser.",
        responses={200: AccountSerializer(many=True)},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="all",
        permission_classes=[IsAuthenticated],
    )
    def list_all(self, request):
        """Return all accounts including inactive ones. Gestor/superuser only."""
        if not self._is_admin_or_gestor(request):
            return Response(
                {"error": "No tiene permisos para esta acción."},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = Account.objects.all().order_by("-created_at")
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=AdminAccountCreateSerializer,
        responses={201: AccountSerializer},
        description="Crea una cuenta para un usuario. Solo Gestor/superuser.",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="admin-create",
        permission_classes=[IsAuthenticated],
    )
    def admin_create(self, request):
        """Create an account for a user. Gestor/superuser only."""
        if not self._is_admin_or_gestor(request):
            return Response(
                {"error": "No tiene permisos para crear cuentas."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AdminAccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()

        # Asignar rol Flota al usuario si no lo tiene
        try:
            from django.contrib.auth.models import Group

            fleet_group, _ = Group.objects.get_or_create(name="Flota")
            account.user.groups.add(fleet_group)
        except Exception:
            pass

        return Response(
            AccountSerializer(account).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=AdminAccountUpdateSerializer,
        responses={200: AccountSerializer},
        description="Modifica parámetros de una cuenta (display_type, special, unlimited_balance). Solo Gestor/superuser.",
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path="admin-update",
        permission_classes=[IsAuthenticated],
    )
    def admin_update(self, request, pk=None):
        """Update account params. Gestor/superuser only."""
        if not self._is_admin_or_gestor(request):
            return Response(
                {"error": "No tiene permisos para modificar cuentas."},
                status=status.HTTP_403_FORBIDDEN,
            )
        account = self.get_object()
        serializer = AdminAccountUpdateSerializer(
            account, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AccountSerializer(account).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=None,
        responses={200: AccountSerializer},
        description="Reactiva una cuenta desactivada. Solo Gestor/superuser.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="reactivate",
        permission_classes=[IsAuthenticated],
    )
    def reactivate(self, request, pk=None):
        """Re-activate a deactivated account. Gestor/superuser only."""
        if not self._is_admin_or_gestor(request):
            return Response(
                {"error": "No tiene permisos para reactivar cuentas."},
                status=status.HTTP_403_FORBIDDEN,
            )
        account = self.get_object()
        if account.is_active:
            return Response(
                {"error": "La cuenta ya está activa."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account.is_active = True
        account.deactivated_at = None
        account.deactivated_by = None
        account.deactivation_reason = None
        account.save()

        # Re-asignar rol Flota si corresponde
        try:
            from django.contrib.auth.models import Group

            fleet_group, _ = Group.objects.get_or_create(name="Flota")
            account.user.groups.add(fleet_group)
        except Exception:
            pass

        return Response(
            {
                "message": f"Cuenta #{account.id} reactivada correctamente.",
                "account": AccountSerializer(account).data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        description="Consulta el saldo de una cuenta por DNI y patente. Retorna información de la cuenta asociada.",
        parameters=[
            {
                "name": "dni",
                "in": "query",
                "description": "DNI del usuario",
                "required": True,
                "schema": {"type": "string"},
            },
            {
                "name": "plate_number",
                "in": "query",
                "description": "Número de patente",
                "required": True,
                "schema": {"type": "string"},
            },
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="balance-by-dni-plate",
        permission_classes=[IsPlayero],
    )
    def balance_by_dni_plate(self, request):
        """
        Endpoint para playeros: consultar saldo de cuenta por DNI y patente.
        Retorna el balance de la cuenta asociada al DNI y la patente proporcionada.
        """
        from users.models import CustomUser

        dni = request.query_params.get("dni", "").strip()
        plate_number = request.query_params.get("plate_number", "").strip().upper()

        if not dni or not plate_number:
            return Response(
                {"error": "DNI y número de patente son requeridos"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Buscar usuario por DNI
            user = CustomUser.objects.filter(dni=dni).first()
            if not user:
                return Response(
                    {"error": "No se encontró ningún usuario con ese DNI"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Buscar todas las patentes activas con ese número
            active_plates = Plates.objects.filter(
                plate_number=plate_number, end_date__isnull=True
            ).select_related("holder_account__user")

            if not active_plates.exists():
                return Response(
                    {"error": "No se encontró ninguna patente activa con ese número"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Buscar la patente que esté asociada a la cuenta del usuario
            # (puede ser titular o dependiente autorizado)
            plate = None
            account = None
            for candidate_plate in active_plates:
                holder_account = candidate_plate.holder_account
                if holder_account.user_id == user.id:
                    plate = candidate_plate
                    account = holder_account
                    break
                authorized_plate = AuthorizedPlate.objects.filter(
                    plate=candidate_plate,
                    dependent_account__user=user,
                    end_date__isnull=True,
                ).first()
                if authorized_plate:
                    plate = candidate_plate
                    account = authorized_plate.dependent_account
                    break

            if plate is None:
                return Response(
                    {"error": "El DNI proporcionado no está asociado a esta patente"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Verificar que la cuenta esté activa
            if not account.is_active:
                return Response(
                    {"error": "La cuenta asociada está desactivada"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Retornar información de la cuenta
            return Response(
                {
                    "account_id": account.id,
                    "account_type": account.get_account_type_display(),
                    "balance": float(account.balance),
                    "special": account.special,
                    "unlimited_balance": account.unlimited_balance,
                    "user_name": f"{user.first_name} {user.last_name}".strip()
                    or user.email,
                    "user_email": user.email,
                    "user_dni": user.dni,
                    "plate_number": plate.plate_number,
                    "plate_brand": plate.brand,
                    "plate_model": plate.model,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Error al consultar la cuenta: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DependentsViewSet(BaseLCViewSet):
    queryset = Dependents.objects.filter(end_date__isnull=True).order_by("id")
    serializer_class = DependentsSerializer
    permission_classes = [DjangoModelOrObjectOwner]

    def get_queryset(self):
        """
        Filtrar adheridos según el usuario:
        - Usuarios Flota (sin rol Gestor): solo adheridos activos de sus cuentas titulares
        - Usuarios con rol Gestor / admin: activos por defecto; todos (incluyendo finalizados)
          si se pasa ?include_ended=true
        - Otros: según permisos del modelo
        """
        if should_apply_flota_restrictions(self.request.user):
            queryset = Dependents.objects.filter(end_date__isnull=True).order_by("id")
            user_accounts = self.request.user.account_set.filter(account_type="holder")
            return queryset.filter(holder_account__in=user_accounts)

        include_ended = self.request.query_params.get("include_ended", "false").lower() == "true"
        queryset = Dependents.objects.all().order_by("id") if include_ended else Dependents.objects.filter(end_date__isnull=True).order_by("id")
        # Gestores/admins: filtro opcional por cuenta titular
        holder_account_id = self.request.query_params.get('holder_account')
        if holder_account_id:
            queryset = queryset.filter(holder_account_id=holder_account_id)
        return queryset

    def destroy(self, request, *args, **kwargs):
        """
        Soft-delete: en lugar de eliminar el registro, establece end_date = hoy,
        desactiva la cuenta adherente y cierra todas las AuthorizedPlate activas
        del par titular/adherente.
        """
        instance = self.get_object()
        now = timezone.now()
        today = now.date()
        with transaction.atomic():
            instance.end_date = today
            instance.save(update_fields=["end_date"])
            dep_account = instance.dependent_account
            dep_account.is_active = False
            dep_account.deactivated_at = now
            dep_account.deactivated_by = request.user
            dep_account.save(update_fields=["is_active", "deactivated_at", "deactivated_by"])
            AuthorizedPlate.objects.filter(
                dependent_account=dep_account,
                plate__holder_account=instance.holder_account,
                end_date__isnull=True,
            ).update(end_date=today)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlatesViewSet(BaseLCUDViewSet):
    queryset = Plates.objects.all().order_by("id")
    serializer_class = PlatesSerializer
    permission_classes = [DjangoModelOrObjectOwner]

    def get_queryset(self):
        """
        Filtrar patentes según el usuario y acción:
        - Listado: solo patentes activas
        - Usuarios Flota (sin rol Gestor): solo patentes de sus cuentas titulares
        - Usuarios con rol Gestor: acceso completo
        - Otros: según permisos del modelo
        """
        queryset = super().get_queryset()

        # Filtrar por usuario Flota
        if should_apply_flota_restrictions(self.request.user):
            user_accounts = self.request.user.account_set.filter(account_type="holder")
            queryset = queryset.filter(holder_account__in=user_accounts)
        else:
            # Gestores/admins: filtro opcional por cuenta titular
            holder_account_id = self.request.query_params.get('holder_account')
            if holder_account_id:
                queryset = queryset.filter(holder_account_id=holder_account_id)

        # Filtrar solo activas para listados
        if self.action == "list":
            queryset = queryset.filter(end_date__isnull=True)

        return queryset.order_by("id")

    def get_serializer_class(self):
        """Usar PlatesUpdateSerializer solo para actualizaciones (PATCH/PUT)"""
        if self.action in ["update", "partial_update"]:
            return PlatesUpdateSerializer
        return PlatesSerializer

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {"error": "Esta patente ya se encuentra activa para esta cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def destroy(self, request, *args, **kwargs):
        """
        En lugar de eliminar la patente, se le asigna una end_date (soft delete).
        """
        plate = self.get_object()

        # Verificar si ya tiene end_date
        if plate.end_date is not None:
            return Response(
                {"error": "Esta patente ya fue dada de baja anteriormente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Asignar la fecha de fin (soft delete)
        plate.end_date = timezone.now().date()
        plate.save()

        return Response(
            {
                "message": f"La patente '{plate.plate_number}' fue dada de baja exitosamente.",
                "end_date": plate.end_date,
            },
            status=status.HTTP_200_OK,
        )


class AuthorizedPlateViewSet(BaseLCViewSet):
    queryset = AuthorizedPlate.objects.all().order_by("id")
    serializer_class = AuthorizedPlateSerializer
    permission_classes = [DjangoModelOrObjectOwner]

    def get_queryset(self):
        """
        Filtrar autorizaciones según el usuario y acción:
        - Listado: solo autorizaciones activas
        - Usuarios Flota: solo autorizaciones de patentes de sus cuentas titulares
        - Otros: según permisos del modelo
        """
        queryset = super().get_queryset()

        # Filtrar por usuario Flota
        if self.request.user.groups.filter(name="Flota").exists():
            user_accounts = self.request.user.account_set.filter(account_type="holder")
            queryset = queryset.filter(plate__holder_account__in=user_accounts)
        else:
            # Gestores/admins: filtro opcional por cuenta titular
            holder_account_id = self.request.query_params.get('holder_account')
            if holder_account_id:
                queryset = queryset.filter(plate__holder_account_id=holder_account_id)

        # Filtrar solo activas para listados
        if self.action == "list":
            queryset = queryset.filter(
                end_date__isnull=True, plate__end_date__isnull=True
            )

        return queryset.order_by("id")

    def create(self, request, *args, **kwargs):
        """
        Crear una nueva autorización de patente, pero primero verificar que no exista
        una autorización activa (end_date nulo) para la misma patente y cuenta adherida.
        """
        plate_id = request.data.get("plate")
        dependent_account_id = request.data.get("dependent_account")

        if plate_id and dependent_account_id:
            # Verificar si existe una autorización activa
            existing_active_auth = AuthorizedPlate.objects.filter(
                plate_id=plate_id,
                dependent_account_id=dependent_account_id,
                end_date__isnull=True,
            ).first()

            if existing_active_auth:
                return Response(
                    {
                        "error": "Ya existe una autorización activa para esta patente y cuenta adherida. "
                        "No se puede crear una nueva autorización."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        En lugar de eliminar la autorización, se le asigna una end_date (soft delete).
        """
        authorized_plate = self.get_object()

        # Verificar si ya tiene end_date
        if authorized_plate.end_date is not None:
            return Response(
                {"error": "Esta autorización ya fue revocada anteriormente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Asignar la fecha de fin (soft delete)
        authorized_plate.end_date = timezone.now().date()
        authorized_plate.save()

        return Response(
            {
                "message": f"La autorización de la patente '{authorized_plate.plate.plate_number}' fue revocada exitosamente.",
                "end_date": authorized_plate.end_date,
            },
            status=status.HTTP_200_OK,
        )


class CompanyViewSet(BaseLCUDViewSet):
    queryset = Company.objects.all().order_by("id")
    serializer_class = CompanySerializer


class CompanyAssignmentViewSet(BaseLCViewSet):
    queryset = CompanyAssignment.objects.all().order_by("id")
    serializer_class = CompanyAssignmentSerializer


class OrganismViewSet(BaseLCUDViewSet):
    queryset = Organism.objects.all().order_by("id")
    serializer_class = OrganismSerializer


class DependentInvitationsViewSet(BaseLCViewSet):
    queryset = DependentInvitation.objects.all().order_by("-invitation_date")
    serializer_class = DependentInvitationSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class AuthorizedEmailViewSet(BaseLCViewSet):
    """ViewSet for managing AuthorizedEmail records (invitations to unregistered users)."""

    queryset = AuthorizedEmail.objects.all().order_by("-invited_at")
    serializer_class = AuthorizedEmailSerializer
    permission_classes = [DjangoModelOrObjectOwner]

    def get_queryset(self):
        queryset = super().get_queryset()
        dependent_of_id = self.request.query_params.get("dependent_of")
        if dependent_of_id:
            return queryset.filter(dependent_of_id=dependent_of_id)
        # Sin filtro explícito: mostrar solo las invitaciones propias del usuario
        user_accounts = self.request.user.account_set.filter(
            account_type="holder", is_active=True
        )
        return queryset.filter(dependent_of__in=user_accounts)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_authorized_email(self, request, pk=None):
        """Cancel a pending authorized email invitation."""
        authorized_email = self.get_object()
        if authorized_email.status != "pending":
            return Response(
                {"error": "Solo se pueden cancelar invitaciones pendientes"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        authorized_email.cancel()
        serializer = self.get_serializer(authorized_email)
        return Response(
            {"message": "Invitación cancelada exitosamente", "data": serializer.data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="add-plates")
    def add_plates_to_invitation(self, request, pk=None):
        """Add plates to a pending invitation without re-sending the email."""
        authorized_email = self.get_object()
        if authorized_email.status != "pending":
            return Response(
                {"error": "Solo se pueden modificar invitaciones pendientes"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        plate_ids = request.data.get("plate_ids", [])
        if not plate_ids:
            return Response(
                {"error": "Se requiere al menos un plate_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid_plates = Plates.objects.filter(
            id__in=plate_ids,
            holder_account=authorized_email.dependent_of,
            end_date__isnull=True,
        )
        authorized_email.pending_plates.add(*valid_plates)
        serializer = self.get_serializer(authorized_email)
        return Response(serializer.data, status=status.HTTP_200_OK)
