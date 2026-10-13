"""Lee la hora del DVR. Uso: .venv/Scripts/python -m tests.test_clock"""
import time
from datetime import datetime

import cv2
import numpy as np

from boardwise.core.clock import read_clock
from training.make_clock_glyphs import SAMPLES, VIDEOS, frame_at

PEOPLE = VIDEOS.parents[1] / "people-walking.mp4"

if not VIDEOS.exists():
    print("sin data/video test: se omite test_clock")
    raise SystemExit(0)

# cuadros con hora conocida (13 primeros cuadros + 2 en el 8 + 3 AM): exactos
for name, msec, text in SAMPLES:
    got, want = read_clock(frame_at(name, msec)), datetime.strptime(text, "%d-%m-%Y %I:%M:%S %p")
    assert got == want, (name, msec, got, want)

# independiente de las plantillas: hora leída - hora del primer cuadro == pts del contenedor
first = {n: datetime.strptime(t, "%d-%m-%Y %I:%M:%S %p") for n, m, t in SAMPLES if m == 0}
for name in ("hiv00054.mp4", "hiv00057.mp4", "hiv00060.mp4"):
    for msec in (3000, 60000, 200000, 500000, 900000):
        cap = cv2.VideoCapture(str(VIDEOS / name))
        cap.set(cv2.CAP_PROP_POS_MSEC, msec)
        ok, frame = cap.read()
        got = read_clock(frame)
        assert ok and got, (name, msec)
        assert abs((got - first[name]).total_seconds() - cap.get(cv2.CAP_PROP_POS_MSEC) / 1000) <= 1.5, (name, msec, got)

# sin reloj -> None
assert read_clock(np.zeros((720, 1280, 3), np.uint8)) is None
assert read_clock(np.random.default_rng(0).integers(0, 255, (720, 1280, 3), dtype=np.uint8)) is None
assert read_clock(None) is None
frame = frame_at("hiv00054.mp4", 0)
frame[:30] = frame[400:430]  # mismo cuadro con el texto tapado
assert read_clock(frame) is None
if PEOPLE.exists():
    cap = cv2.VideoCapture(str(PEOPLE))
    for _ in range(5):
        ok, frame = cap.read()
        assert ok and read_clock(frame) is None
        for _ in range(30):
            cap.read()

frame = frame_at("hiv00054.mp4", 0)
t = time.perf_counter()
for _ in range(200):
    read_clock(frame)
ms = (time.perf_counter() - t) / 200 * 1000
assert ms < 5, ms
print(f"ok ({ms:.2f} ms por llamada)")
