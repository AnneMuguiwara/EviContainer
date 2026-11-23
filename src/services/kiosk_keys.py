# -*- coding: utf-8 -*-
"""
Teclas del kiosko de Evi para el modo simulación.

En la Pi el navegador con Evi tiene el foco, así que las teclas de material
(1-5, 0, t...) y lo que «teclea» un lector QR USB llegan al kiosko y no a esta
terminal. El kiosko se las pasa al backend de Evi y aquí se recogen con
GET {EVI_URL}/avatar/container-keys, cada pocas décimas de segundo.

Si Evi no está corriendo solo se avisa una vez; la terminal sigue funcionando.
"""
import logging
import threading
import time
from typing import Callable

import requests

from config import settings

logger = logging.getLogger("KioskKeys")

POLL_SECONDS = 0.15


def _run(feed: Callable[[str, float], None]) -> None:
    url = f"{settings.EVI_URL}/avatar/container-keys"
    headers = {"Accept": "application/json"}
    if settings.EVI_BRIDGE_KEY:
        headers["X-Bridge-Key"] = settings.EVI_BRIDGE_KEY

    warned = False
    connected = False
    while True:
        try:
            response = requests.get(url, headers=headers, timeout=2)
            if response.status_code >= 400:
                if not warned:
                    logger.warning(
                        f"Evi no entrega las teclas del kiosko: HTTP {response.status_code} "
                        f"{response.text[:120]} (revisa EVI_BRIDGE_KEY)."
                    )
                    warned = True
                time.sleep(2)
                continue
            if not connected:
                logger.info("Recibiendo teclas desde el kiosko de Evi (el navegador puede tener el foco).")
                connected, warned = True, False
            for item in response.json().get("keys", []):
                key, at = item.get("key"), item.get("t")
                if isinstance(key, str) and len(key) == 1:
                    feed(key, (at / 1000.0) if isinstance(at, (int, float)) else time.time())
        except requests.RequestException:
            if not warned:
                logger.warning(f"Evi no responde en {url}: por ahora solo funcionan las teclas de esta terminal.")
                warned = True
            connected = False
            time.sleep(2)
            continue
        time.sleep(POLL_SECONDS)


def start(feed: Callable[[str, float], None]) -> None:
    """Empieza a recoger teclas del kiosko en un hilo aparte."""
    threading.Thread(target=_run, args=(feed,), daemon=True).start()
