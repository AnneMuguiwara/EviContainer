import time
import serial
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Si el lector no manda Enter al final, el código se da por completo cuando deja
# de llegar texto durante este tiempo.
QUIET_SECONDS = 0.3


class QRScanner:
    """Gestiona la lectura física del dispositivo escáner de códigos QR."""

    def __init__(self, port: str, baud_rate: int):
        self.port = port
        self.baud_rate = baud_rate
        self.connection: Optional[serial.Serial] = None
        self._buffer = ""
        self._last_rx = 0.0

    @property
    def connected(self) -> bool:
        return bool(self.connection and self.connection.is_open)

    def connect(self) -> bool:
        """Conecta con el lector QR serial."""
        try:
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"[OK] Lector QR conectado en {self.port}")
            return True
        except Exception as e:
            logger.error(f"[ERROR] Fallo al conectar Lector QR: {e}")
            return False

    def flush(self) -> None:
        """Limpia el buffer para evitar lecturas antiguas."""
        self._buffer = ""
        if self.connected:
            self.connection.reset_input_buffer()

    def read_token(self) -> Optional[str]:
        """
        Devuelve el código leído cuando está completo, o None.

        El puerto entrega el código en pedazos: se juntan hasta que llega el
        Enter (CR/LF) del lector o hasta que deja de llegar texto. Así nunca se
        manda a Ecosort un código cortado a la mitad.
        """
        if not self.connected:
            return None
        try:
            waiting = self.connection.in_waiting
            if waiting:
                self._buffer += self.connection.read(waiting).decode("utf-8", errors="ignore")
                self._last_rx = time.monotonic()
        except Exception as e:
            logger.error(f"Error de lectura en escáner QR: {e}")
            return None

        if not self._buffer.strip():
            self._buffer = ""
            return None
        complete = "\r" in self._buffer or "\n" in self._buffer
        if not complete and time.monotonic() - self._last_rx < QUIET_SECONDS:
            return None

        tokens = self._buffer.split()
        self._buffer = ""
        return tokens[-1] if tokens else None  # la lectura más reciente

    def close(self) -> None:
        """Cierra el puerto del escáner."""
        if self.connected:
            self.connection.close()
