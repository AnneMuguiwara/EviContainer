"""
Teclado de la terminal en modo simulación.

- Esperando usuario: solo el lector QR identifica. Un lector serial lo lee
  QRScanner; uno USB tipo teclado «escribe» el código y Enter aquí mismo.
- En sesión: una sola tecla, sin Enter, simula lo que vería la CNN.
"""
import atexit
import logging
import queue
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Tecla -> objeto que la CNN simulada «ve» (ver src/ml/simulated_cnn.py).
MATERIAL_KEYS = {
    "1": "plastico",
    "2": "aluminio",
    "3": "carton",
    "4": "vidrio",
    "5": "no reciclable",
    "0": "desconocido",  # foto confusa: baja confianza
}
# Un lector USB tipo teclado escribe todo el código en milisegundos. Si entre
# dos teclas pasa más que esto, lo anterior era una persona tecleando y se tira.
SCANNER_KEY_GAP = 0.25
PHOTO_KEYS = {"f", " "}  # foto real + IA (si está cargada)
END_KEYS = {"t"}
QUIT_KEYS = {"q", "\x03"}  # q o Ctrl+C

HELP_TEXT = """
=== MODO SIMULACIÓN (teclas, sin Enter) ===
  Esperando usuario:  escanea el QR del usuario (lector serial o USB)
  En sesión:          1 plástico   2 aluminio   3 cartón   4 vidrio
                      5 no reciclable           0 no reconocido
                      f o espacio -> foto real + IA
                      t -> terminar sesión      h -> esta ayuda
  En cualquier momento: q o Ctrl+C -> apagar el contenedor
"""


def _read_keys_windows(put) -> None:
    import msvcrt

    while True:
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):  # flechas y teclas de función: se descartan
            msvcrt.getwch()
            continue
        put(key)


def _read_keys_posix(put) -> None:
    import termios
    import tty

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    tty.setcbreak(fd)  # tecla por tecla, sin eco; Ctrl+C sigue funcionando
    atexit.register(termios.tcsetattr, fd, termios.TCSADRAIN, previous)
    while True:
        key = sys.stdin.read(1)
        if not key:
            return
        put(key)


def _read_lines(put) -> None:
    # Sin terminal interactiva (p. ej. entrada redirigida): línea por línea.
    for line in sys.stdin:
        for key in line.rstrip("\r\n"):
            put(key)
        put("\n")


class ConsoleInput:
    """Lee el teclado en un hilo aparte y lo entrega al bucle principal."""

    def __init__(self):
        self.keys: "queue.Queue[tuple[str, float]]" = queue.Queue()
        self.code_buffer = ""
        self.last_code_key_at = 0.0
        self.thread = threading.Thread(target=self._reader, daemon=True)

    def start(self) -> None:
        print(HELP_TEXT, flush=True)
        self.thread.start()

    def _reader(self) -> None:
        try:
            put = lambda key: self.keys.put((key, time.monotonic()))  # noqa: E731
            if not sys.stdin or not sys.stdin.isatty():
                _read_lines(put)
            elif sys.platform == "win32":
                _read_keys_windows(put)
            else:
                _read_keys_posix(put)
        except Exception as e:  # noqa: BLE001 - el contenedor sigue sin teclado
            logger.error(f"No se pudo leer el teclado: {e}")

    def _next_key(self, with_time: bool = False):
        try:
            key, at = self.keys.get_nowait()
        except queue.Empty:
            return (None, 0.0) if with_time else None
        return (key, at) if with_time else key

    def clear(self) -> None:
        """Descarta teclas pendientes (al empezar o terminar una sesión)."""
        self.code_buffer = ""
        while self._next_key() is not None:
            pass

    def read_code(self) -> Optional[str]:
        """
        Fase 1: junta lo que «teclea» un lector QR USB hasta el Enter. Lo que
        se teclee a mano (con pausas) se descarta: solo identifica el lector.
        """
        while True:
            key, at = self._next_key(with_time=True)
            if key is None:
                return None
            if self.code_buffer and at - self.last_code_key_at > SCANNER_KEY_GAP:
                self.code_buffer = ""
            self.last_code_key_at = at
            if key in ("\r", "\n"):
                code, self.code_buffer = self.code_buffer.strip(), ""
                if code:
                    print(flush=True)
                    return code
                continue
            if key in ("\b", "\x7f"):
                self.code_buffer = self.code_buffer[:-1]
                continue
            if key == "\x03" or (key == "q" and not self.code_buffer):
                raise KeyboardInterrupt
            if key.isprintable():
                self.code_buffer += key

    def read_event(self):
        """
        Fase 2: devuelve ("FOTO", objeto|None), ("TERMINAR", None) o None.
        objeto es la clave de MATERIAL_KEYS; None significa foto real + IA.
        """
        while True:
            key = self._next_key()
            if key is None:
                return None
            key = key.lower()
            if key in QUIT_KEYS:
                raise KeyboardInterrupt
            if key in END_KEYS:
                return ("TERMINAR", None)
            if key in PHOTO_KEYS:
                return ("FOTO", None)
            if key in MATERIAL_KEYS:
                return ("FOTO", MATERIAL_KEYS[key])
            if key == "h":
                print(HELP_TEXT, flush=True)
            # Cualquier otra tecla (Enter, letras sueltas) se ignora.
