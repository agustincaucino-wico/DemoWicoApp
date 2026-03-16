"""
store_version.py
Obtiene la última versión publicada en cada tienda, de forma independiente.

- iOS:     iTunes Lookup API (oficial y pública de Apple).
- Android: Scraping de la página de Play Store (no hay API oficial).

Cada plataforma tiene su propio caché en memoria con TTL de 1 hora.
En caso de error la función retorna el valor cacheado anterior (aunque esté
vencido) para no degradar el health check. Si nunca se pudo obtener un
valor, retorna None (el frontend lo ignora silenciosamente).
"""

import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

# ── Identificadores ────────────────────────────────────────────────────────────
IOS_BUNDLE_ID = "com.equilybrio.Wico-App"
ANDROID_PACKAGE_ID = "com.wico.app"

# ── URLs ───────────────────────────────────────────────────────────────────────
ITUNES_LOOKUP_URL = (
    f"https://itunes.apple.com/lookup?bundleId={IOS_BUNDLE_ID}&country=ar"
)
PLAY_STORE_URL = (
    f"https://play.google.com/store/apps/details?id={ANDROID_PACKAGE_ID}&hl=en"
)

# ── Caché ──────────────────────────────────────────────────────────────────────
CACHE_TTL = 3600  # 1 hora

_ios_cache: dict = {"version": None, "fetched_at": 0.0}
_android_cache: dict = {"version": None, "fetched_at": 0.0}

# User-Agent de Chrome para que Play Store sirva el HTML completo
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Patrones para extraer la versión del HTML de Play Store (en orden de confianza)
_ANDROID_VERSION_PATTERNS = [
    # Patrón principal: la versión aparece como [["x.x.x"]] en el JS embebido
    re.compile(r'\[\["(\d+\.\d+(?:\.\d+)*)"\]\]'),
    # Patrón alternativo: clave softwareVersion en JSON embebido
    re.compile(r'"softwareVersion"[,:\s]+"([^"]+)"'),
    # Patrón de respaldo: cualquier semver cercano al package id
    re.compile(r'"' + re.escape(ANDROID_PACKAGE_ID) + r'"[^]]*?(\d+\.\d+\.\d+)'),
]


# ── iOS ────────────────────────────────────────────────────────────────────────


def get_latest_ios_version() -> str | None:
    """
    Retorna la última versión publicada en la App Store de Apple.
    Usa la iTunes Lookup API (endpoint oficial, sin autenticación).
    """
    now = time.time()

    if (
        _ios_cache["version"] is not None
        and (now - _ios_cache["fetched_at"]) < CACHE_TTL
    ):
        return _ios_cache["version"]

    try:
        response = requests.get(ITUNES_LOOKUP_URL, timeout=5)
        response.raise_for_status()
        results = response.json().get("results", [])
        if results:
            version = results[0].get("version")
            if version:
                _ios_cache["version"] = version
                _ios_cache["fetched_at"] = now
                logger.info("iOS store version actualizada: %s", version)
                return version
        logger.warning("iTunes API no devolvió resultados para %s", IOS_BUNDLE_ID)
    except requests.exceptions.Timeout:
        logger.warning("Timeout al consultar iTunes API (iOS version)")
    except requests.exceptions.RequestException as exc:
        logger.warning("Error consultando iTunes API: %s", exc)
    except Exception as exc:
        logger.warning("Error inesperado en get_latest_ios_version: %s", exc)

    return _ios_cache["version"]


# ── Android ────────────────────────────────────────────────────────────────────


def _parse_android_version(html: str) -> str | None:
    """Intenta extraer la versión del HTML de Play Store usando varios patrones."""
    for pattern in _ANDROID_VERSION_PATTERNS:
        matches = pattern.findall(html)
        # Filtrar matches que parezcan versiones reales (≥ 2 segmentos numéricos)
        for match in matches:
            parts = match.split(".")
            if len(parts) >= 2 and all(p.isdigit() for p in parts):
                return match
    return None


def get_latest_android_version() -> str | None:
    """
    Retorna la última versión publicada en Google Play Store.
    Usa scraping del HTML de la página pública del app.

    Nota: Google no ofrece una API oficial para esto. Si Google cambia
    el formato del HTML, el scraping puede fallar silenciosamente y se
    retornará el último valor cacheado (o None si nunca se obtuvo uno).
    """
    now = time.time()

    if (
        _android_cache["version"] is not None
        and (now - _android_cache["fetched_at"]) < CACHE_TTL
    ):
        return _android_cache["version"]

    try:
        response = requests.get(
            PLAY_STORE_URL,
            timeout=8,
            headers={"User-Agent": _CHROME_UA},
        )
        response.raise_for_status()
        version = _parse_android_version(response.text)
        if version:
            _android_cache["version"] = version
            _android_cache["fetched_at"] = now
            logger.info("Android store version actualizada: %s", version)
            return version
        logger.warning(
            "No se pudo extraer la versión de Play Store para %s "
            "(el formato del HTML puede haber cambiado)",
            ANDROID_PACKAGE_ID,
        )
    except requests.exceptions.Timeout:
        logger.warning("Timeout al consultar Play Store (Android version)")
    except requests.exceptions.RequestException as exc:
        logger.warning("Error consultando Play Store: %s", exc)
    except Exception as exc:
        logger.warning("Error inesperado en get_latest_android_version: %s", exc)

    return _android_cache["version"]
