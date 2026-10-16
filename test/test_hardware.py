import os
from picamera2 import Picamera2

# --- CONFIGURACIÓN DE PICAMERA2 ---
try:
    picam2 = Picamera2()
    # Configuración para fotografía estática. Ajusta la resolución si lo necesitas.
    config = picam2.create_still_configuration(main={"size": (1920, 1080)})
    picam2.configure(config)
    picam2.start()
    print("Módulo de cámara iniciado correctamente.")
except Exception as e:
    print(f"Error al acceder a la cámara Picamera2: {e}")
    exit()

# --- PREPARACIÓN DE DIRECTORIO ---
carpeta_destino = "dataset_capturas"
if not os.path.exists(carpeta_destino):
    os.makedirs(carpeta_destino)

contador_fotos = 0
print("\n--- MODO DE CAPTURA MANUAL ---")
print(f"Las imágenes se guardarán en la carpeta: {carpeta_destino}")

# --- BUCLE PRINCIPAL ---
try:
    while True:
        # Esperar la entrada del usuario en la terminal
        tecla = input("\n¿Capturar imagen? ('y' para sí / 'n' para salir): ").strip().lower()
        
        if tecla == 'y':
            nombre_archivo = os.path.join(carpeta_destino, f"captura_{contador_fotos}.jpg")
            
            try:
                # Tomar la foto y guardarla
                picam2.capture_file(nombre_archivo)
                print(f"✅ Foto {contador_fotos} guardada con éxito: {nombre_archivo}")
                contador_fotos += 1
            except Exception as e:
                print(f"❌ Error al guardar la fotografía: {e}")
                
        elif tecla == 'n':
            print("\nFinalizando la sesión de capturas...")
            break
            
        else:
            print("⚠️ Entrada no reconocida. Por favor, escribe solo 'y' o 'n'.")

except KeyboardInterrupt:
    print("\nPrograma detenido manualmente mediante el teclado (Ctrl+C).")

finally:
    # --- LIMPIEZA DE RECURSOS ---
    # Detenemos y cerramos la cámara de forma segura
    picam2.stop()
    picam2.close()
    print("Hardware de cámara liberado correctamente. ¡Nos vemos!")