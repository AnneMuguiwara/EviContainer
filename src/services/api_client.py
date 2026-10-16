# -*- coding: utf-8 -*-
import time
import uuid
import requests
import logging
from config import settings

logger = logging.getLogger("ApiClient")

HEADERS = {
    "X-Container-Token": settings.CONTAINER_TOKEN,
    "Accept": "application/json"
}

def registrar_escaneo(code_identity, material, image_path=None, max_intentos=4):
    """
    Envía la clasificación del envase a la API con sistema de reintentos seguro.
    """
    url = f"{settings.API_BASE_URL}/scans"
    
    # 1. Generación del UUID ÚNICO para este envase físico
    event_id = str(uuid.uuid4())
    logger.info(f"Iniciando registro para envase. Evento: {event_id} | Material: {material}")
    
    datos = {
        "event_id": event_id,
        "code_identity": code_identity,
        "material": material
    }
    
    for intento in range(max_intentos):
        try:
            # 2. Envío de petición (soporta multipart/form-data si hay imagen)
            if image_path:
                with open(image_path, "rb") as f:
                    # requests maneja automáticamente el Content-Type para multipart
                    files = {"image": ("captura.jpg", f, "image/jpeg")}
                    response = requests.post(url, headers=HEADERS, data=datos, files=files, timeout=10)
            else:
                response = requests.post(url, headers=HEADERS, json=datos, timeout=10)
                
            # 3. Manejo de Errores Críticos (No reintentar)
            if response.status_code in (401, 403):
                logger.critical("CONTENEDOR FUERA DE SERVICIO (401/403). Abortando registro.")
                return {"status": "OUT_OF_SERVICE"}
                
            # 4. Manejo de Errores de Negocio o Cliente (404, 409, 422 - No reintentar)
            if response.status_code in (404, 409, 422):
                logger.error(f"Error {response.status_code} al registrar: {response.text}")
                return {"status": "ERROR", "message": "Datos inválidos o conflicto."}

            # 5. Fallos del Servidor (5xx - Requieren reintento)
            if response.status_code >= 500:
                logger.warning(f"Error 5xx del servidor. Reintento {intento + 1}/{max_intentos}...")
                time.sleep(2 ** intento)
                continue
                
            # 6. Éxito (200 Duplicado procesado o 201 Creado)
            body = response.json()
            if not body.get("success"):
                return {"status": "ERROR", "message": body.get("message")}
                
            scan_data = body["data"]["scan"]
            logger.info(f"Registro exitoso. Status: {scan_data['status_label']} | Puntos: {scan_data['points_awarded']}")
            
            return {"status": "OK", "data": body["data"]}
                
        except requests.RequestException as e:
            # Fallos de red (Timeouts, DNS - Requieren reintento)
            logger.warning(f"Fallo de red ({e}). Reintento {intento + 1}/{max_intentos}...")
            time.sleep(2 ** intento)
            continue
            
    logger.error(f"Se agotaron los reintentos para el evento {event_id}.")
    return {"status": "NETWORK_ERROR"}