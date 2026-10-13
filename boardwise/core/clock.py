"""Lee la hora impresa por el DVR (Hikvision, 1280x720) arriba a la izquierda: "DD-MM-YYYY Ddd hh:mm:ss AM/PM".
Template matching por carácter (fuente fija, posiciones fijas) con plantillas de models/clock_glyphs.png.
Devuelve None si no reconoce el texto: mejor None que una hora inventada."""
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

GLYPHS = "0123456789PMA"  # orden de las plantillas en el PNG
X0, PITCH, Y0, W, H = 15, 8, 1, 8, 12  # origen y celda de cada carácter en el cuadro
# índice de carácter en "DD-MM-YYYY Ddd hh:mm:ss AM/PM"
DAY, MONTH, YEAR, HOUR, MIN, SEC, AP, M = (0, 1), (3, 4), (6, 7, 8, 9), (15, 16), (18, 19), (21, 22), 24, 25
MIN_SCORE, MIN_MARGIN = 0.6, 0.1  # correlación mínima y ventaja sobre el 2.º mejor glifo

_glyphs = []


def glyph_path():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "models" / "clock_glyphs.png"


def cell(gray, i):
    """Ventana del carácter i con 1 px de margen para tolerar desfase."""
    x = X0 + PITCH * i
    return gray[Y0 - 1:Y0 + H + 1, x - 1:x + W + 1]


def _scores(gray, i):
    win = cell(gray, i)
    return np.array([cv2.matchTemplate(win, g, cv2.TM_CCOEFF_NORMED).max() for g in _glyphs])


def _number(gray, idxs):
    n = 0
    for i in idxs:
        s = _scores(gray, i)[:10]
        top = np.sort(s)[-2:]
        if top[1] < MIN_SCORE or top[1] - top[0] < MIN_MARGIN:
            return None
        n = n * 10 + int(s.argmax())
    return n


def read_clock(frame_bgr):
    if not _glyphs:
        strip = cv2.imread(str(glyph_path()), cv2.IMREAD_GRAYSCALE)
        _glyphs.extend(strip[:, k * W:(k + 1) * W] for k in range(len(GLYPHS)))
    if frame_bgr is None or frame_bgr.ndim != 3 or frame_bgr.shape[0] < 16 or frame_bgr.shape[1] < 232:
        return None
    gray = cv2.cvtColor(frame_bgr[:16, :232], cv2.COLOR_BGR2GRAY)
    d, mo, y, h, mi, s = (_number(gray, f) for f in (DAY, MONTH, YEAR, HOUR, MIN, SEC))
    if None in (d, mo, y, h, mi, s) or not 1 <= h <= 12 or mi > 59 or s > 59:
        return None
    if _scores(gray, M)[11] < MIN_SCORE:  # la 'M' de AM/PM confirma que es este OSD
        return None
    sc = _scores(gray, AP)
    pm, am = sc[10], sc[12]
    if max(pm, am) < MIN_SCORE or abs(pm - am) < MIN_MARGIN:
        return None
    pm = pm > am
    try:
        return datetime(y, mo, d, h % 12 + 12 * pm, mi, s)
    except ValueError:
        return None
