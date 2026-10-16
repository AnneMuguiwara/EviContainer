# -*- coding: utf-8 -*-
"""
Avisa a Evi (backend de RenovaAvatar en la misma máquina) lo que pasa en el
contenedor: usuario identificado, envase escaneado y fin de sesión. Así Evi
saluda al usuario por su nombre y reacciona a cada envase.

Los avisos se mandan en un hilo aparte y en orden. Si Evi no está corriendo,
solo se registra una advertencia: el contenedor nunca se detiene por esto.
"""
import queue
import threading
import logging
import requests
from config import settings

logger = logging.getLogger("EviNotifier")

_events: "queue.Queue[dict]" = queue.Queue()
_worker = None
_warned_offline = False


def _send(event: dict) -> None:
    global _warned_offline
    url = f"{settings.EVI_URL}/avatar/container-event"
    headers = {"Accept": "application/json"}
    if settings.EVI_BRIDGE_KEY:
        headers["X-Bridge-Key"] = settings.EVI_BRIDGE_KEY

    try:
        response = requests.post(url, json=event, headers=headers, timeout=settings.EVI_TIMEOUT)
        if response.status_code >= 400:
            logger.warning(f"Evi rechazó el evento {event['type']}: HTTP {response.status_code} {response.text[:200]}")
            return
        body = response.json()
        if not body.get("delivered"):
            logger.warning(f"Evi recibió {event['type']} pero no hay kiosko abierto ({body.get('reason')}).")
        _warned_offline = False
    except requests.RequestException as e:
        # Se avisa una vez por racha de fallos para no llenar el log.
        if not _warned_offline:
            logger.warning(f"Evi no responde en {url} ({e}). El contenedor sigue sin avatar.")
            _warned_offline = True


def _run() -> None:
    while True:
        event = _events.get()
        _send(event)
        _events.task_done()


def notify(event_type: str, code_identity: str, **data) -> None:
    """Encola un evento para Evi. No bloquea."""
    global _worker
    if not settings.EVI_NOTIFY_ENABLED:
        return
    if _worker is None:
        _worker = threading.Thread(target=_run, daemon=True)
        _worker.start()

    event = {"type": event_type, "code_identity": code_identity, **data}
    if settings.CONTAINER_SERIAL_NUMBER:
        event.setdefault("container_serial_number", settings.CONTAINER_SERIAL_NUMBER)
    _events.put(event)


def flush(timeout: float = 5.0) -> None:
    """Espera (con límite) a que se manden los avisos pendientes, p. ej. al apagar."""
    if _worker is None:
        return
    done = threading.Event()

    def _wait():
        _events.join()
        done.set()

    threading.Thread(target=_wait, daemon=True).start()
    done.wait(timeout)
