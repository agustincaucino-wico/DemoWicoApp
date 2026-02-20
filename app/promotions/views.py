from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import PromotionCode, PromotionRedemption, PromotionalImage
from .actions import PromotionActions
from .serializers import (
    RedeemPromotionSerializer,
    PromotionalImageSerializer,
    PromotionalImageListSerializer,
)
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_spectacular.types import OpenApiTypes
from users.permissions import IsMarketingOrGestor


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


@extend_schema_view(
    list=extend_schema(
        summary="List Active Promotional Images",
        description="Public endpoint to retrieve all active promotional images ordered by 'order' field.",
    ),
    retrieve=extend_schema(
        summary="Get Promotional Image Details",
        description="Retrieve details of a specific promotional image. Requires Marketing or Gestor role.",
    ),
    create=extend_schema(
        summary="Create Promotional Image",
        description="Upload a new promotional image. Requires Marketing or Gestor role.",
    ),
    update=extend_schema(
        summary="Update Promotional Image",
        description="Update an existing promotional image. Requires Marketing or Gestor role.",
    ),
    partial_update=extend_schema(
        summary="Partial Update Promotional Image",
        description="Partially update a promotional image. Requires Marketing or Gestor role.",
    ),
    destroy=extend_schema(
        summary="Delete Promotional Image",
        description="Delete a promotional image. Requires Marketing or Gestor role.",
    ),
)
class PromotionalImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing promotional images.
    - List endpoint is public (only active images)
    - All other endpoints require Marketing or Gestor role
    """

    queryset = PromotionalImage.objects.all()
    serializer_class = PromotionalImageSerializer

    def get_permissions(self):
        """
        Public access for listing active images,
        Marketing or Gestor required for all other operations
        """
        if self.action == "list":
            return [AllowAny()]
        return [IsAuthenticated(), IsMarketingOrGestor()]

    def get_queryset(self):
        """
        Filter to only active images for public list endpoint,
        show all for authenticated users with proper permissions
        """
        if self.action == "list" and not (
            self.request.user.is_authenticated
            and (
                self.request.user.groups.filter(
                    name__in=["Marketing", "Gestor"]
                ).exists()
                or self.request.user.is_staff
            )
        ):
            # Public access: only active images
            return PromotionalImage.objects.filter(is_active=True).order_by(
                "order", "-created_at"
            )
        # Authenticated Marketing/Gestor: all images
        return PromotionalImage.objects.all().order_by("order", "-created_at")

    def get_serializer_class(self):
        """Use lightweight serializer for public list"""
        if self.action == "list" and not (
            self.request.user.is_authenticated
            and self.request.user.groups.filter(
                name__in=["Marketing", "Gestor"]
            ).exists()
        ):
            return PromotionalImageListSerializer
        return PromotionalImageSerializer

    @extend_schema(
        request=None,
        responses={200: PromotionalImageSerializer(many=True)},
        summary="Reorder Promotional Images",
        description="Batch update the order of promotional images. Expects array of {id, order}.",
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsMarketingOrGestor],
    )
    def reorder(self, request):
        """
        Batch update order field for multiple images.
        Expects: [{"id": 1, "order": 0}, {"id": 2, "order": 1}, ...]
        """
        updates = request.data
        if not isinstance(updates, list):
            return Response(
                {"error": "Expected a list of {id, order} objects"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                for item in updates:
                    image_id = item.get("id")
                    new_order = item.get("order")
                    if image_id is None or new_order is None:
                        continue
                    PromotionalImage.objects.filter(id=image_id).update(order=new_order)

            return Response(
                {"message": "Order updated successfully"}, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
