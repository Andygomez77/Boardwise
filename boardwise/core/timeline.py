import json
from pathlib import Path

import cv2

from ..paths import data_dir

MAX_SECONDS = 4 * 3600  # tope de la búsqueda: un segmento de cámara no pasa de ~1 h; 24 h tardaba 60% más en los saltos fallidos
PRECISION = 0.25
LANDING = 2.0  # segundos que puede caer el cuadro leído antes de lo pedido


def video_duration(path, precision=PRECISION):
    """Duración real en segundos: el mayor instante que se puede leer, por búsqueda binaria."""
    # ponytail: CAP_PROP_FRAME_COUNT, ffprobe y PyAV dan duraciones falsas en los .mp4 (MPEG-PS) de Hikvision; saltar por tiempo sí es exacto.
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened() or not capture.read()[0]:
            return 0.0
        low, high = 0.0, float(MAX_SECONDS)
        while high - low > precision:
            mid = (low + high) / 2
            capture.set(cv2.CAP_PROP_POS_MSEC, mid * 1000)
            ok = capture.read()[0]
            # pasado el final real algunos archivos "saltan" al final del índice falso (cuadro leído mucho antes de lo pedido);
            # caer más adelante es normal (índice disperso, marcas de tiempo con saltos)
            if ok and capture.get(cv2.CAP_PROP_POS_MSEC) / 1000 >= mid - LANDING:
                low = mid
            else:
                high = mid
        return high
    finally:
        capture.release()


def seek(cap, t, back=5.0):
    """Deja `cap` con el primer cuadro de pts >= t ya decodificado (usar cap.retrieve()); devuelve su segundo real, None si no hay."""
    # ponytail: las grabaciones tienen huecos reales (pts que saltan) y el índice del MPEG-PS es impreciso: set(POS_MSEC, t) a veces cae
    # muy lejos. Se salta antes de t (duplicando el margen si cae después) y se avanza con grab(); típico 0.2 s, peor caso ~5 s.
    while True:
        start = max(t - back, 0.0)
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        if not cap.grab():
            return None
        pos = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if pos <= t or start == 0:
            break
        back *= 2
    while pos < t:
        if not cap.grab():
            return pos
        pos = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
    return pos


def durations(paths, stop=lambda: False, cache_file=None):
    """Duración de cada video; las ya calculadas (misma ruta, tamaño y fecha) salen de la caché. None si `stop()`."""
    cache_file = cache_file or data_dir() / "durations.json"
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):  # no existe o corrupta: se recalcula
        cache = {}
    result = []
    try:
        for path in paths:
            if stop():
                return None
            try:
                info = Path(path).stat()
            except OSError:
                result.append(0.0)
                continue
            key, signature = str(Path(path).resolve()), [info.st_size, info.st_mtime_ns]
            entry = cache.get(key)
            if not (isinstance(entry, dict) and entry.get("signature") == signature and isinstance(entry.get("seconds"), (int, float))):
                entry = cache[key] = {"signature": signature, "seconds": video_duration(path)}
            result.append(float(entry["seconds"]))
        return result
    finally:
        try:
            cache_file.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass


class Timeline:
    """Los videos uno detrás de otro como un solo día continuo."""

    def __init__(self, paths, durations):
        self.paths = list(paths)
        self.durations = list(durations)
        self.offsets = [sum(self.durations[:i]) for i in range(len(self.paths))]
        self.total = sum(self.durations)

    def locate(self, t):
        """Tiempo global -> (archivo, segundos dentro del archivo)."""
        t = min(max(t, 0.0), self.total)
        for path, offset, duration in zip(self.paths, self.offsets, self.durations):
            if t < offset + duration:
                return path, t - offset
        return self.paths[-1], self.durations[-1]  # t == total

    def to_global(self, path, t):
        return self.offsets[self.paths.index(path)] + t
