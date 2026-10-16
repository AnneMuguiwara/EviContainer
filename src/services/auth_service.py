# -*- coding: utf-8 -*-
import requests
import logging
from config import settings

logger = logging.getLogger("AuthService")

# Centralizamos los headers requeridos por la API
HEADERS = {
    "X-Container-Token": settings.CONTAINER_TOKEN,
    "Accept": "application/json"
}

def identify_user(code_identity):
    """
    Identifica al usuario mediante su código (QR/NFC).
    Retorna un diccionario con el estado y los datos del usuario.
    """
    url = f"{settings.API_BASE_URL}/scans/identify"
    payload = {"code_identity": code_identity}
    
    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        
        # Bloqueo crítico: Contenedor inactivo o token inválido
        if response.status_code in (401, 403):
            logger.critical("CONTENEDOR FUERA DE SERVICIO (Error 401/403).")
            return {"status": "OUT_OF_SERVICE", "message": "Fuera de servicio"}
            
        # Código no existe en la base de datos
        if response.status_code == 404:
            logger.warning(f"Código no encontrado: {code_identity}")
            return {"status": "NOT_FOUND", "message": "Código no reconocido"}
            
        body = response.json()
        
        # Errores de lógica (ej. 422 Cuenta desactivada)
        if not body.get("success"):
            logger.warning(f"Validación rechazada: {body.get('message')}")
            return {"status": "ERROR", "message": body.get("message")}
            
        logger.info(f"Usuario validado: {body['data']['user']['name']}")
        return {"status": "OK", "data": body["data"]}
        
    except requests.RequestException as e:
        logger.error(f"Fallo de conexión en validación: {e}")
        return {"status": "NETWORK_ERROR", "message": "Error de red"}