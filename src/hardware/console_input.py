import queue
import sys
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Atajos de material para forzar la clasificación desde la terminal (f <material>).
FORCED_CLASSES = {
    "plastico": "plastico",
    "plástico": "plastico",
    "aluminio": "aluminio",
    "metal": "aluminio",
    "carton": "carton",
    "cartón": "carton",
    "vidrio": "vidrio",
    "basura": "no reciclable",
    "otro": "no reciclable",
}

HELP_TEXT = """
=== MODO SIMULACIÓN: controles por terminal ===
  Esperando usuario:  escribe el code_identity (QR) y Enter
                      (un lector QR USB tipo teclado también funciona)
  En sesión:          f              -> objeto detectado (foto + IA)
                      f plastico     -> forzar material: plastico, aluminio, carton, vidrio, basura
                      f ?            -> forzar objeto no reconocido (baja confianza)
                      t              -> terminar sesión
  En cualquier momento: salir        -> apagar el contenedor
"""


class ConsoleInput:
    """
    Lee líneas de la terminal en un hilo aparte para simular el lector QR y el
    Arduino de sensores cuando no están conectados (modo simulación).
    """

    def __init__(self):
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.thread = threading.Thread(target=self._reader, daemon=True)

    def start(self) -> None:
        print(HELP_TEXT, flush=True)
        self.thread.start()

    def _reader(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if line:
                self.lines.put(line)

    def _next_line(self) -> Optional[str]:
        try:
            return self.lines.get_nowait()
        except queue.Empty:
            return None

    def read_code(self) -> Optional[str]:
        """Fase 1: cualquier línea que no sea un comando se toma como code_identity."""
        line = self._next_line()
        if not line:
            return None
        if line.lower() == "salir":
            raise KeyboardInterrupt
        if line.lower() in ("f", "t") or line.lower().startswith("f "):
            print("Primero escanea o escribe el code_identity del usuario.", flush=True)
            return None
        return line

    def read_event(self):
        """
        Fase 2: devuelve ("FOTO", clase_forzada|None, confianza_forzada|None),
        ("TERMINAR", None, None) o None si no hay comando.
        """
        line = self._next_line()
        if not line:
            return None

        parts = line.lower().split()
        command = parts[0]
        if command == "salir":
            raise KeyboardInterrupt
        if command == "t":
            return ("TERMINAR", None, None)
        if command == "f":
            if len(parts) == 1:
                return ("FOTO", None, None)
            if parts[1] == "?":
                return ("FOTO", "no reciclable", 0.30)
            forced = FORCED_CLASSES.get(parts[1])
            if forced:
                return ("FOTO", forced, 0.99)
            print(f"Material no reconocido: '{parts[1]}'. Usa plastico, aluminio, carton, vidrio o basura.", flush=True)
            return None

        print("Comando no reconocido. Usa: f, f <material>, t o salir.", flush=True)
        return None
