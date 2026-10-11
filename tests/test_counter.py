"""python -m tests.test_counter"""
import numpy as np
import supervision as sv

from boardwise.core.pipeline import Counter

AREA = [(0, 50), (100, 50), (100, 100), (0, 100)]


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
print("ok")
