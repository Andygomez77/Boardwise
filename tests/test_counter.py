"""python -m tests.test_counter"""
import numpy as np
import supervision as sv

from boardwise.core.pipeline import Counter


def detections(y):
    return sv.Detections(
        xyxy=np.array([[20, y, 50, y + 30], [55, 70 - y, 85, 100 - y]], dtype=np.float32),
        confidence=np.array([0.9, 0.9]),
        class_id=np.array([0, 0]),
    )


counter = Counter((0, 50), (100, 50))
for y in range(0, 71, 2):
    counter.update(detections(y))
assert counter.line_zone.in_count == 1
assert counter.line_zone.out_count == 1

# El mismo contador continúa entre segmentos consecutivos.
counter = Counter((0, 50), (100, 50))
for y in range(0, 40, 2):
    counter.update(detections(y)[[0]])
for y in range(40, 72, 2):
    counter.update(detections(y)[[0]])
assert counter.line_zone.in_count + counter.line_zone.out_count == 1
print("ok")
