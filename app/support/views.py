from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from .models import ErrorReport
from .serializers import ErrorReportSerializer
from .permissions import IsManagerOrOwner


@extend_schema_view(
    list=extend_schema(
        summary="Listar reportes de errores",
        description="Los gestores pueden ver todos los reportes.",
        tags=["soporte - reportes de errores"],
        responses={
            200: ErrorReportSerializer(many=True),
            403: None,
        },
    ),
    create=extend_schema(
        summary="Crear un reporte de error",
        description="Cualquier usuario autenticado puede crear un reporte de error. El usuario se asigna automáticamente.",
        tags=["soporte - reportes de errores"],
        examples=[
            OpenApiExample(
                "Ejemplo de reporte",
                value={
                    "category": "fuel_load",
                    "description": "No puedo cargar combustible, la app se cierra al intentar escanear el QR de la estación.",
                },
                request_only=True,
            ),
        ],
        responses={
            201: ErrorReportSerializer,
            400: None,
        },
    ),
    retrieve=extend_schema(
        summary="Obtener detalle de un reporte",
        description="Solo los gestores pueden ver el detalle de cualquier reporte.",
        tags=["soporte - reportes de errores"],
        responses={
            200: ErrorReportSerializer,
            403: None,
            404: None,
        },
    ),
    partial_update=extend_schema(
        summary="Actualizar estado del reporte",
        description="Solo los gestores pueden actualizar el estado de un reporte (pending, in_progress, resolved, closed).",
        tags=["soporte - reportes de errores"],
        examples=[
            OpenApiExample(
                "Actualizar estado a 'en progreso'",
                value={"status": "in_progress"},
                request_only=True,
            ),
            OpenApiExample(
                "Marcar como resuelto",
                value={"status": "resolved"},
                request_only=True,
            ),
        ],
        responses={
            200: ErrorReportSerializer,
            403: None,
            404: None,
        },
    ),
    destroy=extend_schema(
        summary="Eliminar un reporte",
        description="Solo los gestores pueden eliminar reportes de errores.",
        tags=["soporte - reportes de errores"],
        responses={
            200: None,
            403: None,
            404: None,
        },
    ),
)
class ErrorReportViewSet(viewsets.ModelViewSet):
    """
    API para gestionar reportes de errores de la aplicación.

    **Permisos:**
    - **Gestores (is_staff=True):** Acceso completo a todos los endpoints
    - **Usuarios regulares:** Solo pueden crear reportes (POST)

    **Endpoints disponibles:**
    - `GET /support/error-reports/` - Listar todos los reportes (solo gestores)
    - `POST /support/error-reports/` - Crear un nuevo reporte (todos los usuarios)
    - `GET /support/error-reports/{id}/` - Ver detalle de un reporte (solo gestores)
    - `PATCH /support/error-reports/{id}/` - Actualizar estado (solo gestores)
    - `DELETE /support/error-reports/{id}/` - Eliminar un reporte (solo gestores)
    """

    serializer_class = ErrorReportSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsManagerOrOwner]
    http_method_names = [
        "get",
        "post",
        "delete",
        "patch",
    ]  # Solo permitir estos métodos

    def get_queryset(self):
        """
        Los gestores ven todos los reportes.
        """
        user = self.request.user
        if user.is_staff:
            return ErrorReport.objects.all()
        return ErrorReport.objects.none()

    def perform_create(self, serializer):
        """Asignar el usuario autenticado al crear el reporte."""
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Eliminar un reporte."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"message": "Reporte eliminado correctamente."},
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        """
        Actualización parcial del reporte.
        Solo los gestores pueden actualizar el estado.
        """
        if not request.user.is_staff:
            return Response(
                {"error": "Solo los gestores pueden actualizar reportes."},
                status=status.HTTP_403_FORBIDDEN,
            )

        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)
