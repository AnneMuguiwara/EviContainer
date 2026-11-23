"""
CNN simulada para el modo simulación.

Cuando se elige el material con una tecla, aquí se arma una salida con la
misma forma que la de WasteClassifier: la clase ganadora, su confianza y el
ranking de las 5 clases. No usa TensorFlow, así corre en cualquier laptop.
Las probabilidades son inventadas; la regla de aceptación (0.60) es la real.
"""
import random

# Mismos nombres y orden que CLASS_NAMES en classifier.py.
CLASS_NAMES = ["aluminio", "carton", "no reciclable", "plastico", "vidrio"]

_rng = random.Random()


def simulate(seen: str) -> tuple[str, float, list[tuple[str, float]]]:
    """
    seen: una de CLASS_NAMES, o "desconocido" para una foto confusa.
    Devuelve (clase, confianza, [(clase, prob), ...] de mayor a menor).
    """
    if seen in CLASS_NAMES:
        raw = [_rng.uniform(0.0, 0.08) for _ in CLASS_NAMES]
        raw[CLASS_NAMES.index(seen)] = _rng.uniform(0.82, 0.97)
    else:
        # Ninguna clase convence: la más alta queda por debajo de 0.60.
        raw = [_rng.uniform(0.10, 0.40) for _ in CLASS_NAMES]

    total = sum(raw)
    ranking = sorted(((c, p / total) for c, p in zip(CLASS_NAMES, raw)), key=lambda x: -x[1])
    predicted_class, confidence = ranking[0]
    return predicted_class, confidence, ranking
