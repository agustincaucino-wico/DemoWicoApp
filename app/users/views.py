from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import viewsets, status
from rest_framework.decorators import action
from django.db import IntegrityError
from users.serializers import (
    UserSerializer,
    EmailVerificationSerializer,
    ResendVerificationSerializer,
    DevUserLoginSerializer,
    AssignRoleSerializer,
    RemoveRoleSerializer,
)
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from users.permissions import DjangoModelOrTargetUser
from django.contrib.auth import get_user_model
from users.models import EmailVerificationToken
from utils.email_service import email_service
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from datetime import date
from django.contrib.auth.models import Group
from promotions.actions import PromotionActions

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be created, viewed or edited.
    """

    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [DjangoModelOrTargetUser]

    def get_permissions(self):
        if self.action in ["create", "verify_email", "resend_verification"]:
            return [AllowAny()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except IntegrityError:
            return Response(
                {"email": ["El correo electrónico ya se encuentra registrado."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate verification token
        token = EmailVerificationToken.create_for_user(user)

        # Send verification email
        email_sent = email_service.send_verification_email(
            to_email=user.email,
            user_name=user.get_full_name(),
            verification_code=token.token,
        )

        # Process any pending AuthorizedEmail records for this user
        authorized_emails_processed = self._process_authorized_emails(user)

        headers = self.get_success_headers(serializer.data)

        response_data = serializer.data
        if email_sent:
            response_data["message"] = (
                "Usuario creado. Se ha enviado un código de verificación a tu correo."
            )
        else:
            response_data["warning"] = (
                "Usuario creado, pero hubo un error al enviar el correo de verificación."
            )

        if authorized_emails_processed > 0:
            response_data["authorized_emails_processed"] = authorized_emails_processed
            response_data["fleet_message"] = (
                f"Se procesaron {authorized_emails_processed} invitación(es) pendiente(s). "
                "Ya tenés cuenta(s) de adherente activa(s)."
            )

        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

    def _process_authorized_emails(self, user):
        """
        Process any pending AuthorizedEmail records for this user's email.
        Auto-creates dependent accounts, Dependents relationships,
        assigns Flota role, and CompanyAssignment if applicable.
        Returns the number of processed records.
        """
        from accounts.models import AuthorizedEmail
        from django.db import transaction as db_transaction
        import logging

        logger = logging.getLogger(__name__)

        pending_authorizations = AuthorizedEmail.objects.filter(
            email__iexact=user.email,
            status="pending",
        ).select_related("dependent_of", "company")

        processed_count = 0

        for auth_email in pending_authorizations:
            try:
                with db_transaction.atomic():
                    auth_email.accept(user)
                    processed_count += 1
            except Exception as e:
                # Log but don't fail registration if one authorization fails
                logger.error(
                    f"Error processing AuthorizedEmail {auth_email.id} for user {user.email}: {e}"
                )

        return processed_count

    @extend_schema(
        request=EmailVerificationSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
        },
        summary="Verify Email",
        description="Verify user email with the 6-digit code.",
    )
    @action(detail=False, methods=["post"], url_path="verify_email")
    def verify_email(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Usuario no encontrado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = user.verification_tokens.filter(token=code, used=False).latest(
                "created_at"
            )

            if token.is_expired():
                # Generate new verification token
                new_token = EmailVerificationToken.create_for_user(user)

                # Send new verification email
                email_service.send_verification_email(
                    to_email=user.email,
                    user_name=user.get_full_name(),
                    verification_code=new_token.token,
                )

                return Response(
                    {
                        "error": "El código ha expirado. Te enviamos uno nuevo a tu correo."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verify user
            user.email_verified = True
            user.save()

            # Mark token as used
            token.used = True
            token.save()

            return Response(
                {"message": "Email verificado correctamente."},
                status=status.HTTP_200_OK,
            )

        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"error": "Código inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        request=ResendVerificationSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
        },
        summary="Resend Verification Code",
        description="Resend a new verification code to the user's email.",
    )
    @action(detail=False, methods=["post"], url_path="resend_verification")
    def resend_verification(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Usuario no encontrado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.email_verified:
            return Response(
                {"error": "El email ya está verificado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate new verification token
        token = EmailVerificationToken.create_for_user(user)

        # Send verification email
        email_sent = email_service.send_verification_email(
            to_email=user.email,
            user_name=user.get_full_name(),
            verification_code=token.token,
        )

        if email_sent:
            return Response(
                {
                    "message": "Se ha enviado un nuevo código de verificación a tu correo."
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": "Error al enviar el correo. Intenta nuevamente."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        request=None,
        responses={
            200: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
        summary="Assign Fleet Role",
        description="Assign 'Flota' group to the user and create a titular account.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="assign_fleet_role",
        permission_classes=[IsAuthenticated],
    )
    def assign_fleet_role(self, request, pk=None):
        user = self.get_object()

        result = PromotionActions.create_holder_account(user)

        return Response(
            {
                "message": "Rol 'Flota' asignado y cuenta verificada.",
                "account_result": result,
            }
        )

    @extend_schema(
        request=AssignRoleSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        summary="Assign Role to User",
        description="Assign 'Playero', 'Encargado', or 'Marketing' role to a user. Requires Gestor permissions.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="assign_role",
        permission_classes=[IsAuthenticated],
    )
    def assign_role(self, request, pk=None):
        """Assign Playero, Encargado, or Marketing role to a user."""
        user = self.get_object()
        serializer = AssignRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role_name = serializer.validated_data["role_name"]

        # Verificar que el usuario autenticado tenga el rol de Gestor
        if not request.user.groups.filter(name="Gestor").exists():
            return Response(
                {"error": "Solo los usuarios con rol Gestor pueden asignar roles."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validar que para asignar Encargado, el usuario debe tener Playero y estación asignada
        if role_name == "Encargado":
            from stations.models import StationAttendantAssignment

            if not user.groups.filter(name="Playero").exists():
                return Response(
                    {
                        "error": "El usuario debe tener el rol de Playero antes de asignarle el rol de Encargado."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verificar que tenga una estación asignada activa
            has_active_station = StationAttendantAssignment.objects.filter(
                attendant=user, end_date__isnull=True
            ).exists()

            if not has_active_station:
                return Response(
                    {
                        "error": "El usuario debe tener una estación asignada antes de asignarle el rol de Encargado."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            group, created = Group.objects.get_or_create(name=role_name)
            user.groups.add(group)
            user.save()

            return Response(
                {
                    "message": f"Rol '{role_name}' asignado correctamente al usuario {user.email}.",
                    "user_id": user.id,
                    "email": user.email,
                    "groups": [g.name for g in user.groups.all()],
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"error": f"Error al asignar el rol: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        request=RemoveRoleSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        summary="Remove Role from User",
        description="Remove 'Playero', 'Encargado', or 'Marketing' role from a user. Requires Gestor permissions.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="remove_role",
        permission_classes=[IsAuthenticated],
    )
    def remove_role(self, request, pk=None):
        """Remove Playero, Encargado, or Marketing role from a user."""
        user = self.get_object()
        serializer = RemoveRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role_name = serializer.validated_data["role_name"]

        # Verificar que el usuario autenticado tenga el rol de Gestor
        if not request.user.groups.filter(name="Gestor").exists():
            return Response(
                {"error": "Solo los usuarios con rol Gestor pueden remover roles."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            # Si se remueve el rol de Playero, también se debe remover Encargado y desasignar estación
            if role_name == "Playero":
                from stations.models import StationAttendantAssignment

                # Remover rol de Encargado si lo tiene
                encargado_group = Group.objects.filter(name="Encargado").first()
                if encargado_group:
                    user.groups.remove(encargado_group)

                # Desasignar estación activa si existe
                StationAttendantAssignment.objects.filter(
                    attendant=user, end_date__isnull=True
                ).update(end_date=date.today())

            group = Group.objects.get(name=role_name)
            user.groups.remove(group)
            user.save()

            return Response(
                {
                    "message": f"Rol '{role_name}' removido correctamente del usuario {user.email}.",
                    "user_id": user.id,
                    "email": user.email,
                    "groups": [g.name for g in user.groups.all()],
                },
                status=status.HTTP_200_OK,
            )
        except Group.DoesNotExist:
            return Response(
                {"error": f"El rol '{role_name}' no existe."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Error al remover el rol: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        request=None,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
        },
        summary="Mark Email as Verified",
        description="Admin action to mark a user's email as verified. Requires Gestor permissions.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="mark_email_verified",
        permission_classes=[IsAuthenticated],
    )
    def mark_email_verified(self, request, pk=None):
        """Mark a user's email as verified. Gestor/superuser only."""
        if (
            not request.user.is_superuser
            and not request.user.groups.filter(name="Gestor").exists()
        ):
            return Response(
                {
                    "error": "Solo los usuarios con rol Gestor pueden marcar emails como verificados."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = self.get_object()

        if user.email_verified:
            return Response(
                {"error": "El email del usuario ya está verificado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.email_verified = True
        user.save()

        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated],
    )
    def me(self, request):
        """Return the current authenticated user's data."""
        # Get user data
        user_serializer = self.get_serializer(request.user)

        return Response(user_serializer.data)


from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenObtainPairSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# =============================================================================
# DEV-ONLY VIEWS - These endpoints only work when DEBUG=True
# =============================================================================
from django.conf import settings
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


class DevUserListView(APIView):
    """
    DEV ONLY: Returns a list of users for quick account switching.
    Only accessible when DEBUG=True.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
        summary="Dev User List",
        description="DEV ONLY: Returns a list of all users for quick account switching.",
    )
    def get(self, request):
        if not settings.DEBUG:
            return Response(
                {"error": "This endpoint is only available in development mode."},
                status=status.HTTP_404_NOT_FOUND,
            )

        users = User.objects.all().order_by("id")
        user_list = [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.get_full_name(),
                "groups": [g.name for g in user.groups.all()],
            }
            for user in users
        ]
        return Response({"users": user_list})


class DevUserLoginView(APIView):
    """
    DEV ONLY: Force login as any user by ID or email.
    Only accessible when DEBUG=True.
    Returns JWT tokens for the specified user.
    """

    permission_classes = [AllowAny]
    serializer_class = DevUserLoginSerializer

    @extend_schema(
        request=DevUserLoginSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
        summary="Dev User Login",
        description="DEV ONLY: Force login as any user by ID or email. Returns JWT tokens.",
    )
    def post(self, request):
        if not settings.DEBUG:
            return Response(
                {"error": "This endpoint is only available in development mode."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user_id = request.data.get("user_id")
        email = request.data.get("email")

        if not user_id and not email:
            return Response(
                {"error": "Either user_id or email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if user_id:
                user = User.objects.get(id=user_id)
            else:
                user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Generate tokens
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.get_full_name(),
                },
            }
        )
