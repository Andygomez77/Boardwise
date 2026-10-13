"""Regenera models/clock_glyphs.png (plantillas 0-9, P, M, A del reloj del DVR) promediando celdas de cuadros con hora conocida.
Uso: .venv/Scripts/python -m training.make_clock_glyphs   (necesita data/video test/983 06-10-2026/)"""
from pathlib import Path

import cv2
import numpy as np

from boardwise.core.clock import GLYPHS, H, PITCH, W, X0, Y0

REPO = Path(__file__).resolve().parent.parent
VIDEOS = REPO / "data" / "video test" / "983 06-10-2026"
# (archivo, ms del cuadro, "DD-MM-YYYY hh:mm:ss AP") — hora real del cuadro
SAMPLES = [(f"hiv000{n}.mp4", 0, f"06-10-2026 {t}") for n, t in zip(range(54, 67), (
    "01:37:40 PM", "02:32:32 PM", "02:55:43 PM", "03:17:33 PM", "03:43:10 PM", "04:07:36 PM", "04:33:50 PM",
    "04:59:55 PM", "05:31:43 PM", "05:59:17 PM", "06:36:43 PM", "07:11:03 PM", "07:44:31 PM"))] + [
    # la verdad conocida no tiene ningún 8; estas dos se leyeron a ojo del cuadro
    ("hiv00054.mp4", 8000, "06-10-2026 01:37:48 PM"),
    ("hiv00054.mp4", 18000, "06-10-2026 01:37:58 PM"),
    # cuadros AM (el DVR pasa de medianoche en hiv00066), leídos a ojo
    ("hiv00066.mp4", 1500000, "07-10-2026 05:34:45 AM"),
    ("hiv00066.mp4", 1510000, "07-10-2026 05:34:55 AM"),
    ("hiv00066.mp4", 1530000, "07-10-2026 05:35:15 AM")]


def frame_at(name, msec):
    cap = cv2.VideoCapture(str(VIDEOS / name))
    cap.set(cv2.CAP_PROP_POS_MSEC, msec)
    ok, f = cap.read()
    assert ok, (name, msec)
    return f


if __name__ == "__main__":
    acc = {g: [] for g in GLYPHS}
    for name, msec, text in SAMPLES:
        gray = cv2.cvtColor(frame_at(name, msec)[:16, :232], cv2.COLOR_BGR2GRAY)
        s = text[:10] + " " * 5 + text[11:19] + " " + text[20:]  # alinea con los índices de carácter
        for i, ch in enumerate(s):
            if ch in acc:
                x = X0 + PITCH * i
                acc[ch].append(gray[Y0:Y0 + H, x:x + W].astype(np.float32))
    assert all(acc.values()), [g for g in GLYPHS if not acc[g]]
    strip = np.hstack([np.mean(acc[g], axis=0) for g in GLYPHS]).round().astype(np.uint8)
    cv2.imwrite(str(REPO / "models" / "clock_glyphs.png"), strip)
    print("ok", {g: len(v) for g, v in acc.items()})
