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

    message = "No tenés permisos para acceder al sistema de ventas. Por favor, contactate con el encargado de sistemas."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        try:
            return request.user.groups.filter(name="Vendedor").exists()
        except Exception:
            logger.exception("[ventas] Error al verificar permisos de Vendedor para usuario %s", request.user)
            return False


class IsTransporte(BasePermission):
    """El usuario debe pertenecer al grupo Transporte (o ser staff/superuser)."""

    message = "No tenés permisos para acceder al sistema de transporte. Por favor, contactate con el encargado de sistemas."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        try:
            return request.user.groups.filter(name="Transporte").exists()
        except Exception:
            logger.exception("[ventas] Error al verificar permisos de Transporte para usuario %s", request.user)
            return False


def _es_propio_dni(request, dni: str) -> bool:
    """Verifica que el DNI solicitado corresponde al usuario autenticado."""
    if request.user.is_staff or request.user.is_superuser:
        return True
    return str(getattr(request.user, "dni", "")).strip() == str(dni).strip()


PERMISOS_VENDEDOR = [IsAuthenticated, IsVendedor]
PERMISOS_TRANSPORTE = [IsAuthenticated, IsTransporte]

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


def _proxy_request(method: str, path: str, django_request, override_data=None) -> Response:
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
            kwargs["json"] = override_data if override_data is not None else django_request.data
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
def precio_flete_x_litro(request):
    # Intentar camelCase primero (consistente con otras rutas del upstream)
    resp = _proxy_request("GET", "/precioFleteXLitro/", request)
    if resp.status_code == 404:
        resp = _proxy_request("GET", "/precio_flete_x_litro/", request)
    return resp


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def distancia_desde_planta(request, destino: str):
    return _proxy_request("GET", f"/mapas/distancia_desde_planta/{destino}", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def localidades_provincia_lista(request):
    return _proxy_request("GET", "/localidadesView/localidadProvincia", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def costo_flete_desde_planta(request, destino: str):
    return _proxy_request("GET", f"/costo_flete_x_km/distancia_desde_planta/{destino}", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def puntos_entrega_por_cliente(request, id_cliente: str):
    # El upstream puede o no aceptar trailing slash; intentar sin barra primero.
    resp = _proxy_request("GET", f"/puntosEntrega/cliente/{id_cliente}", request)
    if resp.status_code == 404:
        resp = _proxy_request("GET", f"/puntosEntrega/cliente/{id_cliente}/", request)
    return resp


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def notas_venta_por_dni(request, dni: str):
    if not _es_propio_dni(request, dni):
        return Response(
            {"error": "No tenés permiso para ver las notas de otro vendedor."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return _proxy_request("GET", f"/NotasVentasApp/dni/{dni}", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def imagenes_nota_venta(request, nro_nota_vta: str):
    return _proxy_request("GET", f"/NotasVentasApp/imagenes/{nro_nota_vta}", request)


@api_view(["POST"])
@permission_classes(PERMISOS_VENDEDOR)
def submit_nota_venta(request):
    if not VENTAS_BASE:
        return Response(
            {"error": "SISTEMA_VENTAS_API no está configurado."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    url = f"{VENTAS_BASE}/NotasVentasApp/"

    def do_submit(token: str):
        headers = {"Authorization": f"Bearer {token}"}
        # Reenviar como multipart/form-data igual que la web
        data_str = request.data.get("data", "")
        files_list = [
            (key, (file.name, file, file.content_type))
            for key in request.FILES
            for file in request.FILES.getlist(key)
        ]
        return requests.post(
            url,
            headers=headers,
            data={"data": data_str},
            files=files_list if files_list else None,
            timeout=30,
        )

    try:
        token = _get_token()
        resp = do_submit(token)
        if resp.status_code == 401:
            _invalidar_token()
            token = _get_token()
            resp = do_submit(token)

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


@api_view(["POST"])
@permission_classes(PERMISOS_VENDEDOR)
def upload_imagenes_nota_venta(request):
    if not VENTAS_BASE:
        return Response(
            {"error": "SISTEMA_VENTAS_API no está configurado."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    url = f"{VENTAS_BASE}/NotasVentasApp/upload/"

    def do_upload(token: str):
        headers = {"Authorization": f"Bearer {token}"}
        files = [
            (key, (file.name, file, file.content_type))
            for key in request.FILES
            for file in request.FILES.getlist(key)
        ]
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


# ---------------------------------------------------------------------------
# Vistas - Transporte (autorizaciones de precio de combustible)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes(PERMISOS_TRANSPORTE)
def aut_precio_comb_pendientes(request):
    return _proxy_request("GET", "/autPrecioComb/pendientes/", request)


@api_view(["PUT"])
@permission_classes(PERMISOS_TRANSPORTE)
def aut_precio_comb_actualizar(request, id_aut: str):
    data = {**dict(request.data), "ult_usuario": (request.user.get_full_name() or request.user.email)[:20]}
    return _proxy_request("PUT", f"/autPrecioComb/{id_aut}/", request, override_data=data)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def aut_precio_comb_proximo_id(request):
    return _proxy_request("GET", "/autPrecioComb/proximo_id/", request)


@api_view(["POST"])
@permission_classes(PERMISOS_VENDEDOR)
def aut_precio_comb_crear(request):
    return _proxy_request("POST", "/autPrecioComb/", request)


@api_view(["GET"])
@permission_classes(PERMISOS_VENDEDOR)
def aut_precio_comb_estado(request, codigo: str):
    return _proxy_request("GET", f"/autPrecioComb/estado/{codigo}/", request)
