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
from src.hardware.console_input import ConsoleInput

# Importamos nuestros NUEVOS servicios de red
from src.services.auth_service import identify_user
from src.services.api_client import registrar_escaneo
from src.services import evi_notifier

# La IA depende de TensorFlow, que puede no estar disponible (p. ej. en una
# laptop con una versión de Python sin soporte). En ese caso, en modo
# simulación el material se elige desde la terminal.
try:
    from src.ml.classifier import WasteClassifier
except Exception as e:  # noqa: BLE001 - cualquier fallo de import deja la IA desactivada
    WasteClassifier = None
    CLASSIFIER_IMPORT_ERROR = e

# En Windows la consola no siempre es UTF-8; evita errores con acentos en el log.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    if settings.SIMULATION_MODE:
        logger.warning("MODO SIMULACIÓN ACTIVO: los escaneos se registran en la API real con el CONTAINER_TOKEN configurado.")

    # 1. Inicialización de Hardware e IA
    camera = setup_camera()
    if not camera:
        logger.critical("Sin cámara: todos los objetos se rechazarán hasta que se conecte.")

    ia_classifier = None
    if WasteClassifier:
        ia_classifier = WasteClassifier() # Aquí se carga el modelo .tflite o .keras
    elif settings.SIMULATION_MODE:
        logger.warning(f"IA no disponible ({CLASSIFIER_IMPORT_ERROR}). Usa 'f <material>' para clasificar a mano.")
    else:
        logger.critical(f"No se pudo cargar la IA ({CLASSIFIER_IMPORT_ERROR}). Los objetos se rechazarán.")

    sensores = ArduinoManager(settings.ARDUINO_SENSORES_PORT, settings.BAUD_RATE, "Arduino Sensores")
    motores = ArduinoManager(settings.ARDUINO_MOTORES_PORT, settings.BAUD_RATE, "Arduino Motores")
    escaner_qr = QRScanner(settings.QR_SCANNER_PORT, settings.BAUD_RATE)

    # Intentamos conectar
    if not sensores.connect() and not settings.SIMULATION_MODE:
        logger.critical("El Arduino de Sensores/Pantalla es crítico y no conectó.")

    motores.connect() # Si falla, ArduinoManager ya maneja el modo simulación
    escaner_qr.connect()

    # En simulación, la terminal sustituye al lector QR y al Arduino de sensores.
    consola = None
    if settings.SIMULATION_MODE:
        consola = ConsoleInput()
        consola.start()

    fuera_de_servicio = False

    try:
        # ============================================================================
        # 🔄 BUCLE PRINCIPAL DEL SISTEMA (MÁQUINA DE ESTADOS)
        # ============================================================================
        while not fuera_de_servicio:
            logger.info("--- FASE 1: ESPERANDO USUARIO (QR) ---")
            escaner_qr.flush()
            code_identity = None

            # Esperar lectura de código (QR, Barras, NFC) o, en simulación, de la terminal
            while not code_identity:
                code_identity = escaner_qr.read_token()
                if not code_identity and consola:
                    code_identity = consola.read_code()
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

            identity_data = auth_response["data"]
            user_data = identity_data["user"]
            first_name_simple = strip_accents(user_data["name"].split()[0])
            sensores.send_command(f"SESION_OK:{first_name_simple}")

            # Evi saluda al usuario en el kiosko
            evi_notifier.notify(
                "session_start",
                code_identity,
                user={"name": user_data.get("name"), "last_name": user_data.get("last_name")},
                total_points=identity_data.get("total_points"),
                points_month=identity_data.get("points_month"),
                valid_scans=identity_data.get("valid_scans"),
                streak=identity_data.get("streak"),
            )

            # --- FASE 2: SESIÓN DE RECICLAJE ACTIVA ---
            logger.info(f"--- FASE 2: SESIÓN ACTIVA PARA {user_data['name']} ---")
            session_active = True

            while session_active:
                forced_class = None
                forced_confidence = None
                arduino_msg = sensores.read_line()
                if not arduino_msg and consola:
                    console_event = consola.read_event()
                    if console_event:
                        arduino_msg, forced_class, forced_confidence = console_event
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
                        # 🧠 INFERENCIA LOCAL DE IA (o material forzado desde la terminal)
                        if forced_class:
                            predicted_class, confidence = forced_class, forced_confidence
                            logger.info(f"[Simulación] Material forzado: {predicted_class} (Confianza: {confidence:.2f})")
                        elif ia_classifier:
                            predicted_class, confidence = ia_classifier.predict(filepath)
                            logger.info(f"IA Predice: {predicted_class} (Confianza: {confidence:.2f})")
                        else:
                            hint = " Usa 'f <material>' (plastico, aluminio, carton, vidrio, basura)." if consola else ""
                            logger.error(f"IA no disponible.{hint}")
                            sensores.send_command("RECHAZADO")
                            continue

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

                        scan_info = {}
                        if api_result["status"] == "OK":
                            scan_data = api_result["data"]["scan"]
                            logger.info(f"API registró el envase. Puntos otorgados: {scan_data['points_awarded']}")
                            scan_info = {
                                "points_awarded": scan_data.get("points_awarded", 0),
                                "total_points": api_result["data"].get("total_points"),
                                "points_month": api_result["data"].get("points_month"),
                                "streak": api_result["data"].get("streak"),
                            }
                        else:
                            logger.error("La API no pudo registrar el envase por fallos de red o validación.")

                        # Evi reacciona al envase
                        if confidence < 0.60:
                            reason = "low_confidence"
                        elif material_api == "other":
                            reason = "not_recyclable"
                        else:
                            reason = None
                        evi_notifier.notify(
                            "scan",
                            code_identity,
                            material=material_api,
                            accepted=reason is None,
                            reason=reason,
                            registered=api_result["status"] == "OK",
                            **scan_info,
                        )

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
                    # Evi se despide y guarda el resumen de la visita
                    evi_notifier.notify("session_end", code_identity)

    except KeyboardInterrupt:
        logger.info("Programa detenido manualmente por el operador (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Error inesperado en el bucle principal: {e}", exc_info=True)
    finally:
        # Limpieza rigurosa de recursos
        logger.info("Limpiando recursos y cerrando puertos...")
        evi_notifier.flush()
        sensores.close()
        motores.close()
        escaner_qr.close()
        if camera:
            camera.close()
        logger.info("=== SISTEMA APAGADO CORRECTAMENTE ===")

if __name__ == "__main__":
    main()
