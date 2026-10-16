# -*- coding: utf-8 -*-

import time
import logging
import unicodedata
import sys

# Importamos nuestras configuraciones globales
from config import settings

# Importamos nuestras capas modulares
from src.hardware.camera import setup_camera, take_photo
from src.hardware.arduino import ArduinoManager
from src.hardware.qr_scanner import QRScanner
#from src.ml.classifier import WasteClassifier

# Importamos nuestros NUEVOS servicios de red
from src.services.auth_service import identify_user
from src.services.api_client import registrar_escaneo

# ============================================================================
# ⚙️ CONFIGURACIÓN DEL LOGGING GLOBAL
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("contenedor_inteligente.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Main")

def strip_accents(s: str) -> str:
    """Elimina los acentos de un string para que el Arduino LCD lo lea sin basura."""
    if not s:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

def mapear_ia_a_api(predicted_class, confidence):
    """
    Traduce la salida local de la IA a los slugs estrictos que acepta la API.
    Si el modelo no está seguro (< 0.60), se envía 'other' para registrar el intento sin puntos.
    """
    if confidence < 0.60:
        return "other"
        
    clase_limpia = strip_accents(predicted_class).upper()
    
    if "PLASTICO" in clase_limpia:
        return "plastic"
    elif "METAL" in clase_limpia or "ALUMINIO" in clase_limpia:
        return "aluminum"
    elif "CARTON" in clase_limpia:
        return "cardboard"
    elif "VIDRIO" in clase_limpia:
        return "glass"
        
    return "other"

def main():
    logger.info("=== INICIANDO SISTEMA DEL CONTENEDOR INTELIGENTE ===")
    
    # 1. Inicialización de Hardware e IA
    camera = setup_camera()
    if not camera:
        logger.critical("Abortando inicio: Sin cámara el sistema no puede operar.")
        #return

    #ia_classifier = WasteClassifier() # Aquí se carga el modelo .tflite o .keras

    sensores = ArduinoManager(settings.ARDUINO_SENSORES_PORT, settings.BAUD_RATE, "Arduino Sensores")
    motores = ArduinoManager(settings.ARDUINO_MOTORES_PORT, settings.BAUD_RATE, "Arduino Motores")
    escaner_qr = QRScanner(settings.QR_SCANNER_PORT, settings.BAUD_RATE)

    # Intentamos conectar
    if not sensores.connect():
        logger.critical("Abortando: El Arduino de Sensores/Pantalla es crítico y no conectó.")
        #return
        
    motores.connect() # Si falla, ArduinoManager ya maneja el modo simulación
    escaner_qr.connect()

    fuera_de_servicio = False

    try:
        # ============================================================================
        # 🔄 BUCLE PRINCIPAL DEL SISTEMA (MÁQUINA DE ESTADOS)
        # ============================================================================
        while not fuera_de_servicio:
            logger.info("--- FASE 1: ESPERANDO USUARIO (QR) ---")
            escaner_qr.flush()
            code_identity = None
            
            # Esperar lectura de código (QR, Barras, NFC)
            while not code_identity:
                code_identity = escaner_qr.read_token()
                time.sleep(0.2)
            
            logger.info(f"Código detectado: '{code_identity}'. Identificando...")
            sensores.send_command("VALIDANDO")
            
            # --- VALIDACIÓN CON LA NUEVA API ---
            auth_response = identify_user(code_identity)

            # Si el contenedor está bloqueado desde la plataforma web
            if auth_response["status"] == "OUT_OF_SERVICE":
                logger.critical("Contenedor bloqueado desde el servidor (401/403).")
                sensores.send_command("FUERA_SERVICIO") # Necesitas agregar este case en tu Arduino
                fuera_de_servicio = True
                break

            # Si el QR no existe o la cuenta está desactivada
            if auth_response["status"] != "OK":
                logger.warning("Usuario inválido o no reconocido.")
                sensores.send_command("ERROR_SESION")
                time.sleep(1)
                continue # Regresa a esperar otro QR
                
            user_data = auth_response["data"]["user"]
            first_name_simple = strip_accents(user_data["name"].split()[0])
            sensores.send_command(f"SESION_OK:{first_name_simple}")
            
            # --- FASE 2: SESIÓN DE RECICLAJE ACTIVA ---
            logger.info(f"--- FASE 2: SESIÓN ACTIVA PARA {user_data['name']} ---")
            session_active = True
            
            while session_active:
                arduino_msg = sensores.read_line()
                if not arduino_msg:
                    time.sleep(0.1)
                    continue

                if "Info:" in arduino_msg:
                    logger.info(f"[Sensores] {arduino_msg}")
                
                # --- EVENTO: EL USUARIO INGRESÓ UN OBJETO ---
                elif arduino_msg == "FOTO":
                    logger.info("Objeto detectado. Capturando y procesando...")
                    filepath = take_photo(camera)
                
                    if filepath:
                        # 🧠 INFERENCIA LOCAL DE IA
                        predicted_class, confidence = ia_classifier.predict(filepath)
                        logger.info(f"IA Predice: {predicted_class} (Confianza: {confidence:.2f})")
                        
                        clase_limpia = strip_accents(predicted_class).upper()
                        
                        # Mapeo estricto a los slugs de la nueva API
                        material_api = mapear_ia_a_api(predicted_class, confidence)
                        
                        # 🌐 REGISTRO EN LA API (Incluye generación de UUID y reintentos)
                        api_result = registrar_escaneo(code_identity, material_api, filepath)
                        
                        if api_result["status"] == "OUT_OF_SERVICE":
                            sensores.send_command("FUERA_SERVICIO")
                            session_active = False
                            fuera_de_servicio = True
                            break

                        if api_result["status"] == "OK":
                            scan_data = api_result["data"]["scan"]
                            logger.info(f"API registró el envase. Puntos otorgados: {scan_data['points_awarded']}")
                        else:
                            logger.error("La API no pudo registrar el envase por fallos de red o validación.")

                        # ⚙️ COMPORTAMIENTO FÍSICO (Idéntico a tu lógica original)
                        # --- CASO 1: RECHAZO FÍSICO (Baja Confianza) ---
                        if confidence < 0.60:
                            logger.warning(f"-> RECHAZADO (Baja Confianza): {clase_limpia}")
                            sensores.send_command("RECHAZADO")
                            # La banda no se mueve, obligando al usuario a sacar el objeto con la mano.

                        # --- CASO 2: CLASIFICACIÓN EXITOSA (Reciclable o Basura) ---
                        else:
                            logger.info(f"-> APROBADO: {clase_limpia}")
                            
                            # La pantalla del Arduino Sensores mostrará la clase exacta (ej. METAL APLASTADO)
                            sensores.send_command(f"APROBADO:{clase_limpia}")
                            
                            # --- MAPEO FÍSICO A MOTORES ---
                            if material_api == "aluminum":
                                motores.send_command("ALUMINIO") 
                            elif material_api == "plastic":
                                motores.send_command("PLASTICO")
                            else:
                                motores.send_command("OTRO") # Todo lo demás (vidrio, cartón, o basura) va a OTRO
                    else:
                        logger.error("Fallo al capturar foto.")
                        sensores.send_command("RECHAZADO")

                # --- EVENTO: EL USUARIO O EL TIMEOUT FINALIZÓ LA SESIÓN ---
                elif arduino_msg == "TERMINAR":
                    logger.info("El Arduino de sensores ha terminado la sesión.")
                    session_active = False 

    except KeyboardInterrupt:
        logger.info("Programa detenido manualmente por el operador (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Error inesperado en el bucle principal: {e}", exc_info=True)
    finally:
        # Limpieza rigurosa de recursos
        logger.info("Limpiando recursos y cerrando puertos...")
        sensores.close()
        motores.close()
        escaner_qr.close()
        if camera:
            camera.close()
        logger.info("=== SISTEMA APAGADO CORRECTAMENTE ===")

if __name__ == "__main__":
    main()