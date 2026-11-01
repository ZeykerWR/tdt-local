"""HTTP routes of the settings dialog: read/save settings, test the connections, manage Whisper models.

Changing settings is more powerful than anything else the server does (``whisper_bin`` is a program that gets
executed), so every route that changes something or contacts a configured address only accepts requests that
come from the machine the server runs on, even with ``--lan``.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import urllib.error
from typing import TYPE_CHECKING, Any

from .ads import embed_verdict
from .ai import ModelError
from .net import Blocked
from .settings import BY_NAME
from .stt import diagnose
from .whisper_models import catalogue, installed_models

if TYPE_CHECKING:
    from .server import Handler

WRITE_PREFIXES = ("/api/settings", "/api/whisper/download")


def _from_this_machine(handler: Handler) -> bool:
    try:
        return ipaddress.ip_address(handler.client_address[0].split("%")[0]).is_loopback
    except ValueError:
        return False


def handle_get(handler: Handler, path: str) -> bool:
    """Answer the read-only settings routes. Returns ``False`` if ``path`` is not one of them."""
    app = handler.app
    if path == "/api/settings":
        handler._json(200, app.settings.snapshot())
    elif path == "/api/whisper/models":
        models_dir = app.config.models_dir
        handler._json(
            200,
            {
                "installed": installed_models(models_dir),
                "catalog": catalogue(models_dir),
                "models_dir": str(models_dir),
                "download": app.models.status(),
            },
        )
    elif path == "/api/whisper/download":
        handler._json(200, app.models.status())
    else:
        return False
    return True


def handle_post(handler: Handler, path: str) -> bool:
    """Answer the settings routes that change something or test something. ``False`` if not ours."""
    if not (path.startswith(WRITE_PREFIXES) or path.startswith("/api/settings/test/")):
        return False
    if not _from_this_machine(handler):
        handler._json(403, {"error": "los ajustes solo se pueden cambiar desde el propio equipo"})
        return True
    body = handler._body()
    app = handler.app
    if path == "/api/settings":
        changed, errors = app.settings.update(body)
        if errors:
            handler._json(400, {"ok": False, "errors": errors})
            return True
        app.apply_settings(changed)
        handler._json(200, {"ok": True, "changed": changed, "settings": app.settings.snapshot()})
    elif path == "/api/settings/reset":
        section = body.get("section")
        changed = app.settings.reset(section if isinstance(section, str) else None)
        app.apply_settings(changed)
        handler._json(200, {"ok": True, "changed": changed, "settings": app.settings.snapshot()})
    elif path == "/api/settings/test/ai":
        handler._json(200, _test_ai(app, body))
    elif path == "/api/settings/test/stt":
        handler._json(200, _test_stt(app, body))
    elif path == "/api/settings/test/web":
        handler._json(200, _test_web(app, body, f"http://{handler.headers.get('Host', '')}"))
    elif path == "/api/whisper/download":
        try:
            started = app.models.start(str(body.get("name") or ""))
        except ValueError as exc:
            handler._json(400, {"ok": False, "error": str(exc)})
            return True
        handler._json(200 if started else 409, {"ok": started, "download": app.models.status()})
    elif path == "/api/whisper/download/cancel":
        app.models.cancel()
        handler._json(200, {"ok": True})
    else:
        handler._json(404, {"error": "no existe"})
    return True


def _test_ai(app: Any, body: dict[str, Any]) -> dict[str, Any]:
    """Ask the endpoint for its models, with the values typed in the dialog (saved or not)."""
    url, key = body.get("url"), body.get("api_key")
    try:
        url = BY_NAME["llm_url"].validate(url) if url is not None else None
        key = BY_NAME["llm_api_key"].validate(key) if key is not None else None
        return {"ok": True, "models": app.assistant.list_models(url, key)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except ModelError as exc:
        return {"ok": False, "error": str(exc)}
    except urllib.error.HTTPError as exc:
        hint = " (hace falta una clave de API)" if exc.code in (401, 403) else ""
        return {"ok": False, "error": f"el servidor contestó HTTP {exc.code}{hint}"}
    except OSError:
        return {"ok": False, "error": f"no responde en {url or app.config.llm_url}"}


def _test_web(app: Any, body: dict[str, Any], our_origin: str) -> dict[str, Any]:
    """Whether the web typed in the dialog answers and lets itself be shown inside our page."""
    try:
        url = BY_NAME["ad_web_url"].validate(body.get("url"))
        if not url:
            return {"ok": False, "error": "escribe primero una dirección"}
        with app.net.open(url, None, False, 10) as response:
            ok, why = embed_verdict(response.headers, our_origin)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Blocked as exc:
        return {"ok": False, "error": f"no se puede abrir esa dirección ({exc})"}
    except urllib.error.HTTPError as exc:
        exc.close()
        return {"ok": False, "error": f"la web contestó HTTP {exc.code}"}
    except OSError:
        return {"ok": False, "error": "la web no responde"}
    return {"ok": ok, "error": why}


def _test_stt(app: Any, body: dict[str, Any]) -> dict[str, Any]:
    """What would happen with the Whisper values typed in the dialog (saved or not)."""
    values: dict[str, Any] = {}
    try:
        for name in ("whisper_url", "whisper_bin", "whisper_model"):
            if name in body:
                values[name] = BY_NAME[name].validate(body[name])
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **diagnose(dataclasses.replace(app.config, **values))}
