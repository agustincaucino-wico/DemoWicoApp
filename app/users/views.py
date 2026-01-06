from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import viewsets, status
from rest_framework.decorators import action
from users.serializers import UserSerializer, EmailVerificationSerializer
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from users.permissions import DjangoModelOrTargetUser
from django.contrib.auth import get_user_model
from users.models import EmailVerificationToken
from utils.email_service import email_service
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes

User = get_user_model()
from django.contrib.auth.models import Group
from promotions.actions import PromotionActions



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
        user = serializer.save()

        # Generate verification token
        token = EmailVerificationToken.create_for_user(user)

        # Send verification email
        email_sent = email_service.send_verification_email(
            to_email=user.email,
            user_name=user.get_full_name(),
            verification_code=token.token,
        )

        headers = self.get_success_headers(serializer.data)
        
        response_data = serializer.data
        if email_sent:
            response_data["message"] = "Usuario creado. Se ha enviado un código de verificación a tu correo."
        else:
            response_data["warning"] = "Usuario creado, pero hubo un error al enviar el correo de verificación."

        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )

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
            token = user.verification_tokens.filter(
                token=code,
                used=False
            ).latest("created_at")
            
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
                    {"error": "El código ha expirado. Te enviamos uno nuevo a tu correo."},
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
        request={"type": "object", "properties": {"email": {"type": "string"}}},
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
        },
        summary="Resend Verification Code",
        description="Resend a new verification code to the user's email.",
    )
    @action(detail=False, methods=["post"], url_path="resend_verification")
    def resend_verification(self, request):
        email = request.data.get("email")
        
        if not email:
            return Response(
                {"error": "Email es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
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
                {"message": "Se ha enviado un nuevo código de verificación a tu correo."},
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
    @action(detail=True, methods=["post"], url_path="assign_fleet_role", permission_classes=[IsAuthenticated])
    def assign_fleet_role(self, request, pk=None):
        user = self.get_object()
        
        result = PromotionActions.create_holder_account(user)
        
        return Response({
            "message": "Rol 'Flota' asignado y cuenta verificada.",
            "account_result": result
        })


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

        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.get_full_name(),
            }
        })
