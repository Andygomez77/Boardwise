import threading
import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from boardwise.core.clock import read_clock
from boardwise.core.pipeline import PARALLEL_VIDEOS, run_parallel

FRAME_INTERVAL = 1 / 15  # el proceso va a ~80 fps; la vista no necesita tanto


def to_qimage(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


class Worker(QThread):
    frame = Signal(QImage)
    counts = Signal(int)
    mark = Signal(object, float, object)  # (video, segundo en el video, hora real o None) de cada subida contada
    file_started = Signal(int)  # posición en la lista
    file_finished = Signal(int)
    file_skipped = Signal(str)
    provider = Signal(str)
    fps = Signal(float)
    done = Signal(list)  # [(nombre, subidas)]; (nombre, None) si no se pudo abrir
    error = Signal(str)

    def __init__(self, paths, polygon):
        super().__init__()
        self.paths = list(paths)
        self.polygon = polygon
        self._lock = threading.Lock()  # los callbacks de run_parallel llegan desde varios hilos
        self._running = set()  # posiciones de los videos en curso
        self._counters = {}  # video -> su Counter (para colorear las cajas)
        self._go = threading.Event()  # apagado = en pausa; el hilo duerme en wait()
        self._go.set()

    def pause(self):
        self._go.clear()

    def resume(self):
        self._go.set()

    def stop(self):
        self.requestInterruption()
        self._go.set()  # despierta el hilo si está en pausa

    def _annotate(self, frame, detections, counter):
        # gris: fuera del área · amarillo: dentro, aún sin contar · verde: ya contada
        if detections.tracker_id is None:
            return frame
        for box, track_id in zip(detections.xyxy.astype(int), detections.tracker_id):
            if track_id in counter.counted:
                color = (0, 200, 0)
            elif track_id in counter.inside_ids:
                color = (0, 220, 255)
            else:
                color = (160, 160, 160)
            x1, y1, x2, y2 = box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, ((x1 + x2) // 2, (y1 + y2) // 2), 6, color, -1)
            cv2.putText(frame, f"#{track_id}", (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return frame

    def run(self):
        paths = self.paths
        index = {path: i for i, path in enumerate(paths)}
        final = {}  # video -> conteo final (o el último); solo lo escribe este hilo
        skipped = []

        def skip(path):
            skipped.append(path)
            self.file_finished.emit(index[path])
            self.file_skipped.emit(path.name)

        def start(path, counter, detector):
            with self._lock:
                if not self._counters:
                    self.provider.emit(detector.provider)
                self._counters[path] = counter
                self._running.add(index[path])
            self.file_started.emit(index[path])

        def finish(path):
            with self._lock:
                self._running.discard(index[path])
            self.file_finished.emit(index[path])

        try:
            items = run_parallel(paths, self.polygon, PARALLEL_VIDEOS, on_skip=skip, on_start=start, on_done=finish)
            frames = 0
            started = last = time.perf_counter()
            try:
                for path, frame, detections, count, advanced, seconds, new_ids in items:
                    final[path] = count
                    if new_ids:
                        wall = read_clock(frame)  # el cuadro aún está limpio (se anota más abajo)
                        for _ in new_ids:
                            self.mark.emit(path, seconds, wall)
                    frames += advanced  # fps = cuadros de VIDEO por segundo (todos los hilos, incluye los saltados)
                    now = time.perf_counter()
                    if now - last >= FRAME_INTERVAL:
                        with self._lock:
                            preview = min(self._running, default=None)
                        if index[path] == preview:  # la vista sigue al video en curso de menor posición
                            last = now
                            self.frame.emit(to_qimage(self._annotate(frame, detections, self._counters[path])))
                            self.counts.emit(sum(final.values()))
                            self.fps.emit(frames / (now - started))
                    if not self._go.is_set():
                        paused = time.perf_counter()
                        self._go.wait()
                        started += time.perf_counter() - paused  # el fps no cuenta la pausa
                    if self.isInterruptionRequested():
                        break
            finally:
                items.close()  # termina los hilos aunque se detenga a medias
            self.counts.emit(sum(final.values()))
        except Exception as e:
            self.error.emit(str(e))
            return
        self.done.emit([(path.name, final.get(path)) for path in paths if path in final or path in skipped])
