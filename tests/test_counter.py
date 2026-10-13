"""python -m tests.test_counter"""
import threading
from pathlib import Path

import cv2
import numpy as np
import supervision as sv

from boardwise.core.pipeline import Counter, run_parallel, run_videos

AREA = [(0, 35), (100, 35), (100, 85), (0, 85)]  # se cuenta el centro de la caja (pies - 15)


def boxes(*people):  # cada persona: (x, y de los pies); caja de 20x30
    return sv.Detections(
        xyxy=np.array([[x - 10, y - 30, x + 10, y] for x, y in people], dtype=np.float32),
        confidence=np.full(len(people), 0.9),
        class_id=np.zeros(len(people), dtype=int),
    )


def feed(counter, path):  # path: lista de cuadros, cada uno con las posiciones de las personas
    for people in path:
        counter.update(boxes(*people))


# (a) entra al área y se queda
counter = Counter(AREA)
feed(counter, [[(50, y)] for y in range(30, 70, 5)] + [[(50, 70)]] * 5)
assert counter.count == 1, counter.count

# (b) pasa siempre por fuera
counter = Counter(AREA)
feed(counter, [[(x, 40)] for x in range(10, 90, 3)])
assert counter.count == 0, counter.count

# (c) cae dentro solo 1 cuadro
counter = Counter(AREA)
feed(counter, [[(50, 44)]] * 5 + [[(50, 54)]] + [[(50, 44)]] * 5)
assert counter.count == 0, counter.count

# (d) afuera en un segmento, entra en el siguiente con el mismo Counter
counter = Counter(AREA)
feed(counter, [[(50, 30 + y)] for y in range(0, 15, 3)])
assert counter.count == 0, counter.count
feed(counter, [[(50, 45 + y)] for y in range(0, 25, 3)] + [[(50, 70)]] * 3)
assert counter.count == 1, counter.count

# (e) dos personas distintas entran
counter = Counter(AREA)
feed(counter, [[(20, y), (80, y)] for y in range(30, 70, 5)] + [[(20, 70), (80, 70)]] * 5)
assert counter.count == 2, counter.count

# (f) el centro entra al área pero los pies quedan fuera: cuenta
counter = Counter(AREA)
feed(counter, [[(50, 95)]] * 5)
assert counter.count == 1, counter.count

# (g) lectura en paralelo: stride, cuadros avanzados y cerrar a mitad sin hilos colgados
class Empty:
    detect = staticmethod(lambda frame: sv.Detections.empty())


video = Path(__file__).resolve().parents[1] / "data" / "sample_folder" / "segment_00.mp4"
total = int(cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FRAME_COUNT))
for stride in (1, 3):
    advanced = [item[4] for item in run_videos([video], AREA, detector=Empty(), stride=stride)]
    assert advanced[0] == stride and abs(sum(advanced) - total) <= stride, (stride, sum(advanced), total)
threads = threading.active_count()
items = run_videos([video], AREA, detector=Empty(), stride=1)
for _ in range(20):
    next(items)
items.close()
assert threading.active_count() == threads, threading.enumerate()
missing = []
assert list(run_videos([video.with_name("no_existe.mp4"), video], AREA, detector=Empty(), on_skip=missing.append, stride=30))
assert len(missing) == 1 and threading.active_count() == threads

# (h) run_parallel: cerrar a mitad no deja hilos; sin cerrar, cada video cuenta igual que solo
folder = video.parent
videos = sorted(folder.glob("*.mp4"))
items = run_parallel(videos, AREA, workers=3)
for _ in range(30):
    next(items)
items.close()
assert threading.active_count() == threads, threading.enumerate()
started, done = [], []
last = {}
for path, _, _, count, *_ in run_parallel(videos, AREA, workers=2, on_start=lambda p, c, d: started.append(p), on_done=done.append):
    last[path] = count
alone = {path: list(run_videos([path], AREA))[-1][3] for path in videos}
assert last == alone and sorted(started) == sorted(done) == videos, (last, alone)
assert threading.active_count() == threads
print("ok")
