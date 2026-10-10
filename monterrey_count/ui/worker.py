import time
from pathlib import Path

import cv2
import supervision as sv
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from monterrey_count.core.detector import Detector
from monterrey_count.core.pipeline import _model_path, list_videos, run, run_folder

FRAME_INTERVAL = 1 / 15  # el proceso va a ~80 fps; la vista no necesita tanto


def to_qimage(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


class Worker(QThread):
    frame = Signal(QImage)
    counts = Signal(int, int)
    file_changed = Signal(int, int, str)
    file_skipped = Signal(str)
    provider = Signal(str)
    fps = Signal(float)
    done = Signal(list)  # [(nombre, entradas, salidas)]; (nombre, None, None) si no se pudo abrir
    error = Signal(str)

    def __init__(self, source, line_start, line_end):
        super().__init__()
        self.source = Path(source)
        self.line = (line_start, line_end)

    def _annotate(self, frame, detections):
        frame = sv.BoxAnnotator().annotate(frame, detections)
        if detections.tracker_id is not None:
            labels = [str(track_id) for track_id in detections.tracker_id]
            frame = sv.LabelAnnotator().annotate(frame, detections, labels=labels)
        cv2.line(frame, *self.line, (0, 255, 0), 2)
        return frame

    def run(self):
        rows = []  # [nombre, entradas acumuladas, salidas acumuladas]

        def skip(path):
            rows.append([path.name, None, None])
            self.file_skipped.emit(path.name)

        try:
            detector = Detector(_model_path())
            self.provider.emit(detector.provider)
            folder = self.source.is_dir()
            paths = list_videos(self.source) if folder else [self.source]
            if folder:
                items = run_folder(self.source, *self.line, detector=detector, on_skip=skip)
            else:
                items = ((self.source, *item) for item in run(self.source, *self.line, detector=detector))
            current = None
            in_count = out_count = frames = 0
            started = last = time.perf_counter()
            try:
                for path, frame, detections, in_count, out_count in items:
                    if path != current:
                        current = path
                        rows.append([path.name, 0, 0])
                        self.file_changed.emit(paths.index(path) + 1, len(paths), path.name)
                    rows[-1][1:] = in_count, out_count
                    frames += 1
                    now = time.perf_counter()
                    if now - last >= FRAME_INTERVAL:
                        last = now
                        self.frame.emit(to_qimage(self._annotate(frame, detections)))
                        self.counts.emit(in_count, out_count)
                        self.fps.emit(frames / (now - started))
                    if self.isInterruptionRequested():
                        break
            finally:
                items.close()  # suelta el video aunque se detenga a medias
            self.counts.emit(in_count, out_count)
        except Exception as e:
            self.error.emit(str(e))
            return
        result = []
        previous = (0, 0)
        for name, entered, left in rows:
            if entered is None:
                result.append((name, None, None))
            else:
                result.append((name, entered - previous[0], left - previous[1]))
                previous = entered, left
        self.done.emit(result)
