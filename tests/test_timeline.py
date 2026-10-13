"""python -m tests.test_timeline"""
import json
import random
import tempfile
from pathlib import Path

import cv2

import boardwise.core.timeline as core

from boardwise.core.pipeline import list_videos, run_videos
from boardwise.core.timeline import Timeline, durations as cached_durations, seek, video_duration

AREA = [(320, 180), (960, 180), (960, 540), (320, 540)]

folder = Path(__file__).resolve().parents[1] / "data" / "sample_folder"
paths = list_videos(folder)
durations = []
for path in paths:
    capture = cv2.VideoCapture(str(path))
    expected = capture.get(cv2.CAP_PROP_FRAME_COUNT) / capture.get(cv2.CAP_PROP_FPS)
    duration = video_duration(path)
    assert abs(duration - expected) < 0.5, (path.name, duration, expected)
    durations.append(duration)
assert video_duration(folder / "no_existe.mp4") == 0.0

timeline = Timeline(paths, durations)
assert abs(timeline.total - sum(durations)) < 1e-9
for i, path in enumerate(paths):
    offset = timeline.offsets[i]
    assert timeline.locate(offset) == (path, 0.0)  # el borde pertenece al archivo que empieza
    assert timeline.to_global(path, 0.0) == offset
    if i:
        before, local = timeline.locate(offset - 1e-6)  # justo antes: final del archivo anterior
        assert before == paths[i - 1] and abs(local - durations[i - 1]) < 1e-3, (before, local)
        assert abs(timeline.to_global(before, local) - offset) < 1e-3
    middle = offset + durations[i] / 2
    assert abs(timeline.to_global(*timeline.locate(middle)) - middle) < 1e-9
assert timeline.locate(-5) == (paths[0], 0.0)
last, local = timeline.locate(timeline.total + 5)
assert last == paths[-1] and abs(local - durations[-1]) < 1e-9

# cada subida trae su segundo dentro del archivo
video = paths[0]
marks = []
for _, _, _, count, _, seconds, new_ids in run_videos([video], AREA):
    marks += [seconds] * len(new_ids)
assert len(marks) == count and all(0 <= t <= durations[0] for t in marks), (marks, count)
# seek(): cae en el primer cuadro >= t (±1 cuadro) en tiempos al azar, también hacia atrás
capture = cv2.VideoCapture(str(paths[0]))
fps = capture.get(cv2.CAP_PROP_FPS)
random.seed(1)
for t in [0.0, durations[0] - 0.5] + [random.uniform(0, durations[0] - 0.5) for _ in range(8)]:
    real = seek(capture, t)
    assert real is not None and t - 1e-3 <= real <= t + 1.5 / fps, (t, real)
    assert capture.retrieve()[0]
seek(capture, durations[0] + 60)  # más allá del final no revienta

# caché de duraciones: la segunda vez no abre ningún video; si cambia el archivo, se recalcula; JSON corrupto se ignora
calls = []
real_duration = core.video_duration
core.video_duration = lambda path: calls.append(path) or 7.5
try:
    with tempfile.TemporaryDirectory() as tmp:
        cache_file, copy = Path(tmp) / "durations.json", Path(tmp) / "a.mp4"
        copy.write_bytes(b"x" * 10)
        assert cached_durations([copy], cache_file=cache_file) == [7.5] and len(calls) == 1
        assert cached_durations([copy], cache_file=cache_file) == [7.5] and len(calls) == 1  # de la caché
        copy.write_bytes(b"x" * 11)
        assert cached_durations([copy], cache_file=cache_file) == [7.5] and len(calls) == 2  # cambió el tamaño
        cache_file.write_text("{ no es json")
        assert cached_durations([copy], cache_file=cache_file) == [7.5] and len(calls) == 3
        assert json.loads(cache_file.read_text())  # se reescribió válido
        assert cached_durations([copy, copy.with_name("falta.mp4")], cache_file=cache_file) == [7.5, 0.0]
        assert cached_durations([copy], stop=lambda: True, cache_file=cache_file) is None
finally:
    core.video_duration = real_duration
print("ok")
