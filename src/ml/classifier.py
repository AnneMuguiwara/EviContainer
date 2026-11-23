import os
import time
import logging
import numpy as np
from PIL import Image
import tensorflow as tf
from config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# ⚙️ CONFIGURACIÓN DEL MODELO A USAR (EL SWITCH QUE PEDISTE)
# Cambia esta variable a 'TFLITE' o 'KERAS' para alternar entre modelos.
# ============================================================================
MODEL_TYPE = 'TFLITE'  # <-- ¡CAMBIA ESTO PARA PROBAR EL OTRO MODELO!

# Ajusta estas clases según el orden exacto en el que entrenaste tu modelo.
# Ej: Si la salida 0 es Aluminio, la 1 es Plastico, etc.
# --- CONFIGURACIÓN FIJA ---
# Actualiza esta lista con el orden exacto de tu entrenamiento
# crushed_metal, crushed_plastic, metal, no_reciclable, plastic
CLASS_NAMES = [
    "aluminio",      # Índice 0 (o "metal")
    "carton",        # Índice 1
    "no reciclable", # Índice 2 (o "otro" / "basura")
    "plastico",      # Índice 3
    "vidrio"         # Índice 4
]

# Tamaño de imagen que espera tu modelo (Típicamente 224x224)
TARGET_IMAGE_SIZE = (224, 224) 

class WasteClassifier:
    """Carga el modelo de IA y ejecuta inferencia sobre las fotos."""
    
    def __init__(self):
        self.model_type = MODEL_TYPE
        self.keras_model = None
        self.tflite_interpreter = None
        self.input_details = None
        self.output_details = None
        # Ranking [(clase, prob)] de la última predicción, para el top-3 de Evi.
        self.last_ranking = []
        
        self._load_model()

    def _load_model(self):
        """Carga en RAM exclusivamente el modelo seleccionado."""
        logger.info(f"Inicializando motor de IA en modo: {self.model_type}")
        inicio = time.time()
        
        try:
            if self.model_type == 'KERAS':
                # --- CARGA DEL MODELO .KERAS ---
                model_path = os.path.join(settings.MODELS_DIR, "modelo_residuos_rpi_V3_05.keras")
                self.keras_model = tf.keras.models.load_model(model_path)
                logger.info(f"Modelo KERAS cargado en {time.time() - inicio:.2f} segundos.")
                
            elif self.model_type == 'TFLITE':
                # --- CARGA DEL MODELO .TFLITE ---
                model_path = os.path.join(settings.MODELS_DIR, "modelo_residuos_rpi_V3_05.tflite")
                self.tflite_interpreter = tf.lite.Interpreter(model_path=model_path)
                self.tflite_interpreter.allocate_tensors()
                
                self.input_details = self.tflite_interpreter.get_input_details()
                self.output_details = self.tflite_interpreter.get_output_details()
                logger.info(f"Modelo TFLITE cargado en {time.time() - inicio:.2f} segundos.")
            else:
                logger.error("Tipo de modelo no reconocido. Usa 'KERAS' o 'TFLITE'.")
                
        except Exception as e:
            logger.critical(f"Error fatal al cargar el modelo de IA: {e}")

    def _preprocess_image(self, image_path: str) -> np.ndarray:
        """Prepara la imagen recortándola al centro y redimensionándola."""
        # 1. Abrir la imagen
        img = Image.open(image_path).convert('RGB')
        
        # 2. Recorte Central (Center Crop) para evitar deformación
        width, height = img.size
        new_size = min(width, height) # Tomamos el lado más corto (720)
        
        left = (width - new_size) / 2
        top = (height - new_size) / 2
        right = (width + new_size) / 2
        bottom = (height + new_size) / 2
        
        # Recortamos a un cuadrado perfecto (720x720 en este caso)
        img = img.crop((left, top, right, bottom))
        
        # 3. Redimensionar a 224x224
        img = img.resize(TARGET_IMAGE_SIZE)
        
        # 4. Convertir a Array de Numpy (píxeles crudos 0-255)
        # NO normalizar aquí: MobileNetV3 incluye su propia capa Rescaling
        # interna que convierte 0-255 a [-1, 1]. Normalizar aquí la duplica.
        img_array = np.array(img, dtype=np.float32)

        # 5. Añadir la dimensión del batch (1, 224, 224, 3)
        img_array = np.expand_dims(img_array, axis=0)
        return img_array

    def predict(self, image_path: str) -> tuple[str, float]:
        """
        Ejecuta la inferencia en la imagen dada.
        Retorna una tupla: (Nombre_del_Material, Porcentaje_de_Confianza)
        """
        self.last_ranking = []
        if not os.path.exists(image_path):
            logger.error(f"La imagen {image_path} no existe.")
            return "Desconocido", 0.0

        try:
            input_data = self._preprocess_image(image_path)
            inicio_inferencia = time.time()
            
            # --- INFERENCIA ---
            if self.model_type == 'KERAS':
                predictions = self.keras_model.predict(input_data, verbose=0)
                probs = predictions[0]
                
            elif self.model_type == 'TFLITE':
                self.tflite_interpreter.set_tensor(self.input_details[0]['index'], input_data)
                self.tflite_interpreter.invoke()
                probs = self.tflite_interpreter.get_tensor(self.output_details[0]['index'])[0]

            tiempo_inferencia = time.time() - inicio_inferencia
            logger.debug(f"Inferencia ({self.model_type}) completada en {tiempo_inferencia:.4f}s")
            
            # --- INTERPRETAR RESULTADOS ---
            # Obtenemos el índice con la probabilidad más alta
            class_index = np.argmax(probs)
            confidence = probs[class_index]
            
            predicted_class = CLASS_NAMES[class_index] if class_index < len(CLASS_NAMES) else "Otro"
            self.last_ranking = sorted(
                ((name, float(p)) for name, p in zip(CLASS_NAMES, probs)),
                key=lambda x: -x[1],
            )
            
            return predicted_class, float(confidence)

        except Exception as e:
            logger.error(f"Error durante la predicción: {e}")
            self.last_ranking = []
            return "Error de IA", 0.0

    def is_recyclable(self, predicted_label: str, confidence: float, threshold: float = 0.60) -> bool:
        """Determina si se aprueba el depósito del residuo basado en confianza y material."""
        if confidence < threshold:
            logger.warning(f"Confianza insuficiente ({confidence:.2f}). Rechazado.")
            return False
            
        # Clases que el contenedor está programado para aceptar (las 4 que dan puntos)
        label_upper = predicted_label.upper()
        clases_validas = ["ALUMINIO", "METAL", "PLASTICO", "CARTON", "VIDRIO"]
        
        return any(valid in label_upper for valid in clases_validas)