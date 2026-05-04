"""
Proxy hacia el Sistema de Ventas externo.

Gestiona el token de servicio internamente (nunca sale al frontend).
El frontend se autentica con su JWT normal; este proxy reenvía las
llamadas al sistema de ventas usando las credenciales de cuenta de servicio.
"""

import os
import threading
import logging

import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

VENTAS_BASE = os.getenv("SISTEMA_VENTAS_API", "").rstrip("/")
VENTAS_USER = os.getenv("VENTAS_USER", "")
VENTAS_PASSWORD = os.getenv("VENTAS_PASSWORD", "")


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------

class IsVendedor(BasePermission):
    """El usuario debe pertenecer al grupo Vendedor (o ser staff/superuser)."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        return request.user.groups.filter(name="Vendedor").exists()


def _es_propio_dni(request, dni: str) -> bool:
    """Verifica que el DNI solicitado corresponde al usuario autenticado."""
    if request.user.is_staff or request.user.is_superuser:
        return True
    return str(getattr(request.user, "dni", "")).strip() == str(dni).strip()


PERMISOS_VENDEDOR = [IsAuthenticated, IsVendedor]

VENTAS_BASE = os.getenv("SISTEMA_VENTAS_API", "").rstrip("/")
VENTAS_USER = os.getenv("VENTAS_USER", "")
VENTAS_PASSWORD = os.getenv("VENTAS_PASSWORD", "")

# Token cacheado en memoria (se renueva automáticamente ante 401)
_ventas_token: str | None = None
_token_lock = threading.Lock()


def _obtener_token_ventas() -> str:
    """Hace POST /login al sistema de ventas y retorna el token."""
    url = f"{VENTAS_BASE}/login"
    response = requests.post(
        url,
        data={"username": VENTAS_USER, "password": VENTAS_PASSWORD},  # form-encoded
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token") or data.get("token") or (data.get("data") or {}).get("token")
    if not token:
        raise ValueError(f"No se recibió token en /login. Respuesta: {data}")
    logger.info("[ventas proxy] Token de servicio obtenido")
    return token


def _get_token() -> str:
    """Retorna el token cacheado, obteniendo uno nuevo si es necesario."""
    global _ventas_token
    with _token_lock:
        if not _ventas_token:
            _ventas_token = _obtener_token_ventas()
        return _ventas_token


def _invalidar_token():
    global _ventas_token
    with _token_lock:
        _ventas_token = None


def _proxy_request(method: str, path: str, django_request) -> Response:
    """Reenvía la request al sistema de ventas con el token de servicio."""
    if not VENTAS_BASE:
        return Response(
            {"error": "SISTEMA_VENTAS_API no está configurado."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    url = f"{VENTAS_BASE}/{path.lstrip('/')}"
    params = django_request.query_params.dict()

    def do_request(token: str):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        kwargs = dict(params=params, headers=headers, timeout=15)
        if method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = django_request.data
        return requests.request(method, url, **kwargs)

    try:
        token = _get_token()
        resp = do_request(token)

        # Si el token expiró, renovar y reintentar una vez
        if resp.status_code == 401:
            logger.warning("[ventas proxy] Token expirado, renovando...")
            _invalidar_token()
            token = _get_token()
            resp = do_request(token)

        try:
            data = resp.json()
        except Exception:
            data = resp.text

        return Response(data, status=resp.status_code)

    except requests.exceptions.ConnectionError:
        logger.error("[ventas proxy] No se pudo conectar a %s", VENTAS_BASE)
        return Response(
            {"error": "No se pudo conectar al sistema de ventas."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except requests.exceptions.Timeout:
        return Response(
            {"error": "Timeout al conectar con el sistema de ventas."},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except Exception as exc:
        logger.exception("[ventas proxy] Error inesperado")
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def vendedor_por_dni(request, dni: str):
    if not _es_propio_dni(request, dni):
        return Response(
            {"error": "No tenés permiso para consultar datos de otro vendedor."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return _proxy_request("GET", f"/vendedores/dni/{dni}", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def clientes_por_vendedor(request, id_vendedor: str):
    return _proxy_request("GET", f"/vendedorClientes/{id_vendedor}/", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def precios_por_area(request, id_area: str):
    return _proxy_request("GET", f"/precioTiposCombXArea/{id_area}/", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def telemarketers(request):
    return _proxy_request("GET", "/vendedores/telemarketers/", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def formas_de_pago(request):
    return _proxy_request("GET", "/formasDePago/", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def provincias(request):
    return _proxy_request("GET", "/provincias/", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def localidades_por_provincia(request, id_provincia: str):
    return _proxy_request(
        "GET", f"/localidadesProvinciasView/provincia/{id_provincia}", request
    )


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def puntos_entrega_por_cliente(request, id_cliente: str):
    return _proxy_request("GET", f"/puntosEntrega/cliente/{id_cliente}/", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def notas_venta_por_dni(request, dni: str):
    if not _es_propio_dni(request, dni):
        return Response(
            {"error": "No tenés permiso para ver las notas de otro vendedor."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return _proxy_request("GET", f"/NotasVentasApp/dni/{dni}", request)


@api_view(["POST"])
@permission_classes(PERMISOS_VENDEDOR)
def submit_nota_venta(request):
    # Verificar que el DNI en el payload corresponde al usuario autenticado
    dni_payload = str(request.data.get("dni") or request.data.get("dni_vendedor") or "").strip()
    if dni_payload and not _es_propio_dni(request, dni_payload):
        return Response(
            {"error": "No podés crear notas de venta en nombre de otro vendedor."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return _proxy_request("POST", "/NotasVentasApp/", request)


@api_view(["POST"])
@permission_classes(PERMISOS_VENDEDOR)
def upload_imagenes_nota_venta(request):
    """Para uploads multipart, reenvía el contenido raw en lugar de JSON."""
    if not VENTAS_BASE:
        return Response(
            {"error": "SISTEMA_VENTAS_API no está configurado."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    url = f"{VENTAS_BASE}/NotasVentasApp/upload"

    def do_upload(token: str):
        headers = {"Authorization": f"Bearer {token}"}
        files = {
            key: (file.name, file, file.content_type)
            for key, file in request.FILES.items()
        }
        return requests.post(url, headers=headers, files=files, timeout=30)

    try:
        token = _get_token()
        resp = do_upload(token)
        if resp.status_code == 401:
            _invalidar_token()
            token = _get_token()
            resp = do_upload(token)

        try:
            data = resp.json()
        except Exception:
            data = resp.text

        return Response(data, status=resp.status_code)

    except requests.exceptions.ConnectionError:
        return Response(
            {"error": "No se pudo conectar al sistema de ventas."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except Exception as exc:
        logger.exception("[ventas proxy] Error en upload")
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
