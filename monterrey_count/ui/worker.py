import threading
import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from monterrey_count.core.detector import Detector
from monterrey_count.core.pipeline import Counter, _model_path, run_videos

FRAME_INTERVAL = 1 / 15  # el proceso va a ~80 fps; la vista no necesita tanto


def to_qimage(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


class Worker(QThread):
    frame = Signal(QImage)
    counts = Signal(int)
    file_changed = Signal(int, int, str)
    file_skipped = Signal(str)
    provider = Signal(str)
    fps = Signal(float)
    done = Signal(list)  # [(nombre, subidas)]; (nombre, None) si no se pudo abrir
    error = Signal(str)

    def __init__(self, paths, polygon):
        super().__init__()
        self.paths = list(paths)
        self.polygon = polygon
        self.counter = Counter(polygon)
        self._go = threading.Event()  # apagado = en pausa; el hilo duerme en wait()
        self._go.set()

    def pause(self):
        self._go.clear()

    def resume(self):
        self._go.set()

    def stop(self):
        self.requestInterruption()
        self._go.set()  # despierta el hilo si está en pausa

    def _annotate(self, frame, detections):
        # gris: fuera del área · amarillo: dentro, aún sin contar · verde: ya contada
        if detections.tracker_id is None:
            return frame
        for box, track_id in zip(detections.xyxy.astype(int), detections.tracker_id):
            if track_id in self.counter.counted:
                color = (0, 200, 0)
            elif track_id in self.counter.inside_ids:
                color = (0, 220, 255)
            else:
                color = (160, 160, 160)
            x1, y1, x2, y2 = box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, ((x1 + x2) // 2, (y1 + y2) // 2), 6, color, -1)
            cv2.putText(frame, f"#{track_id}", (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return frame

    def run(self):
        rows = []  # [nombre, subidas acumuladas]

        def skip(path):
            rows.append([path.name, None])
            self.file_skipped.emit(path.name)

        try:
            detector = Detector(_model_path())
            self.provider.emit(detector.provider)
            paths = self.paths
            items = run_videos(paths, self.polygon, detector=detector, on_skip=skip, counter=self.counter)
            current = None
            count = frames = 0
            started = last = time.perf_counter()
            try:
                for path, frame, detections, count, advanced in items:
                    if path != current:
                        current = path
                        rows.append([path.name, 0])
                        self.file_changed.emit(paths.index(path) + 1, len(paths), path.name)
                    rows[-1][1] = count
                    frames += advanced  # fps = cuadros de VIDEO por segundo (incluye los saltados)
                    now = time.perf_counter()
                    if now - last >= FRAME_INTERVAL:
                        last = now
                        self.frame.emit(to_qimage(self._annotate(frame, detections)))
                        self.counts.emit(count)
                        self.fps.emit(frames / (now - started))
                    if not self._go.is_set():
                        paused = time.perf_counter()
                        self._go.wait()
                        started += time.perf_counter() - paused  # el fps no cuenta la pausa
                    if self.isInterruptionRequested():
                        break
            finally:
                items.close()  # suelta el video aunque se detenga a medias
            self.counts.emit(count)
        except Exception as e:
            self.error.emit(str(e))
            return
        result = []
        previous = 0
        for name, total in rows:
            if total is None:
                result.append((name, None))
            else:
                result.append((name, total - previous))
                previous = total
        self.done.emit(result)
