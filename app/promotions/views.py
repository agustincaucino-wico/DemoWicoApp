from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import PromotionCode, PromotionRedemption
from .actions import PromotionActions
from .serializers import RedeemPromotionSerializer
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes


class RedeemPromotionView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RedeemPromotionSerializer

    @extend_schema(
        request=RedeemPromotionSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
        },
        summary="Redeem Promotion Code",
        description="Redeem a promotion code to receive benefits like account creation with balance.",
    )
    def post(self, request):
        serializer = RedeemPromotionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code_str = serializer.validated_data["code"]

        try:
            promotion = PromotionCode.objects.get(code=code_str)
        except PromotionCode.DoesNotExist:
            return Response(
                {"error": "El código ingresado no existe."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user already redeemed this code (cada usuario solo puede canjear cada código una vez)
        if PromotionRedemption.objects.filter(
            user=request.user, promotion_code=promotion
        ).exists():
            return Response(
                {"error": "Ya canjeaste este código."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate validity (includes global usage limit check)
        if not promotion.is_valid():
            if not promotion.has_uses_remaining():
                return Response(
                    {"error": "Este código ha alcanzado su límite de usos."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {"error": "El código ha expirado o no es válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Execute Action
        with transaction.atomic():
            result = PromotionActions.execute(
                promotion.action_type, request.user, promotion.action_params
            )

            if not result.get("success"):
                # rollback not strictly necessary for logical check failures,
                # but good practice if partial DB writes occurred inside action.
                # However, if it's just "Account exists", we might not want to 500.
                # The user asked for specific error messages.
                return Response(
                    {"error": result.get("message")}, status=status.HTTP_400_BAD_REQUEST
                )

            # Record redemption
            redemption = PromotionRedemption.objects.create(
                user=request.user,
                promotion_code=promotion,
                amount_gifted=result.get("amount"),  # Store gifted amount if applicable
            )

        return Response(
            {
                "message": "Código canjeado exitosamente.",
                "detail": result.get("message"),
            },
            status=status.HTTP_200_OK,
        )
