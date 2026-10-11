from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
import warnings
from pathlib import Path

import cv2
import numpy as np
import supervision as sv

from .detector import Detector


VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov")
MIN_FRAMES_INSIDE = 3
ANALYZE_FPS = 8  # cuadros analizados por segundo de video


def list_videos(folder):
    return sorted(path for path in Path(folder).iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS)


def _model_path():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "models" / "yolo11n.onnx"


class Counter:
    """Cuenta personas (IDs del tracker) cuyo centro estuvo dentro del área al menos MIN_FRAMES_INSIDE cuadros."""

    def __init__(self, polygon):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            self.tracker = sv.ByteTrack(frame_rate=ANALYZE_FPS)  # el buffer de pérdida sigue siendo ~1 s real
        self.zone = sv.PolygonZone(np.array(polygon), triggering_anchors=(sv.Position.CENTER,))
        self.frames_inside = {}
        self.counted = set()
        self.inside_ids = set()  # IDs dentro del área en el último cuadro

    @property
    def count(self):
        return len(self.counted)

    def update(self, detections):
        detections = self.tracker.update_with_detections(detections)
        inside = self.zone.trigger(detections)
        self.inside_ids = set(detections.tracker_id[inside])
        for track_id in detections.tracker_id[inside]:
            self.frames_inside[track_id] = self.frames_inside.get(track_id, 0) + 1
            if self.frames_inside[track_id] >= MIN_FRAMES_INSIDE:
                self.counted.add(track_id)
        # ponytail: si el tracker pierde a alguien y le da otro ID, puede contarse doble; subir MIN_FRAMES_INSIDE o ReID si estorba.
        return detections


def _read(capture, stride, frames, stop):
    """Hilo productor: lee un cuadro, salta stride-1 con grab() y lo pone en la cola (None = fin)."""

    def put(item):
        while not stop.is_set():
            try:
                frames.put(item, timeout=0.1)  # cola llena (consumidor en pausa) = espera sin consumir memoria
                return
            except queue.Full:
                pass

    end = None
    try:
        while not stop.is_set():
            ok, frame = capture.read()
            if not ok:
                break
            advanced = 1
            while advanced < stride and capture.grab():
                advanced += 1
            put((frame, advanced))
    except Exception as error:
        end = error
    put(end)


def _frames(paths, counter, detector, skip_bad=False, on_skip=None, stride=None):
    for video_path in paths:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            message = f"No se pudo abrir el video: {video_path}"
            if skip_bad:
                warnings.warn(message, RuntimeWarning)
                if on_skip:
                    on_skip(video_path)
                continue
            raise ValueError(message)
        fps = capture.get(cv2.CAP_PROP_FPS)
        # ponytail: si la gente se mueve muy rápido entre cuadros analizados el tracker puede perderla; bajar el stride (--stride) si pasa.
        fps_used = fps if fps > 0 else 25  # fps 0/NaN -> 25
        step = stride or max(1, round(fps_used / ANALYZE_FPS))
        counter.tracker.max_time_lost = max(1, round(fps_used / step))  # ~1 s real aunque se fuerce el stride
        frames = queue.Queue(maxsize=16)
        stop = threading.Event()
        reader = threading.Thread(target=_read, args=(capture, step, frames, stop), daemon=True)
        reader.start()
        try:
            while True:
                item = frames.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                frame, advanced = item
                detections = counter.update(detector.detect(frame))
                yield video_path, frame, detections, counter.count, advanced
        finally:
            stop.set()
            reader.join()
            capture.release()


def run(video_path, polygon, model_path=None, detector=None, stride=None):
    counter = Counter(polygon)
    detector = detector or Detector(model_path or _model_path())
    for _, frame, detections, count, advanced in _frames([video_path], counter, detector, stride=stride):
        yield frame, detections, count, advanced


def run_videos(paths, polygon, model_path=None, detector=None, on_skip=None, counter=None, stride=None):
    counter = counter or Counter(polygon)
    detector = detector or Detector(model_path or _model_path())
    yield from _frames(paths, counter, detector, skip_bad=True, on_skip=on_skip, stride=stride)


def run_folder(folder, polygon, model_path=None, detector=None, on_skip=None, stride=None):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"No se pudo abrir la carpeta: {folder}")
    yield from run_videos(list_videos(folder), polygon, model_path, detector, on_skip, stride=stride)


def _zone(value):
    try:
        numbers = list(map(int, value.split(",")))
        if len(numbers) < 6 or len(numbers) % 2:
            raise ValueError
        return list(zip(numbers[::2], numbers[1::2]))
    except ValueError as error:
        raise argparse.ArgumentTypeError("El área debe ser x1,y1,x2,y2,x3,y3[,...] (mínimo 3 puntos)") from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--zone", required=True, type=_zone)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--stride", type=int)  # por defecto automático
    args = parser.parse_args()
    polygon = args.zone
    source = Path(args.video)
    folder = source.is_dir()
    detector = Detector(_model_path())
    print(f"provider: {detector.provider}")
    generator = run_folder(source, polygon, detector=detector, stride=args.stride) if folder else run(source, polygon, detector=detector, stride=args.stride)
    frames = 0
    started = time.perf_counter()
    show = args.show and "GUI: NONE" not in cv2.getBuildInformation()
    current = None
    counts = {}
    try:
        for item in generator:
            if folder:
                path, frame, detections, count, advanced = item
            else:
                frame, detections, count, advanced = item
                path = source
            if path != current:
                current = path
                print(f"{path.name}: stride {advanced}")  # lo avanzado en el primer cuadro = stride usado
            counts[current] = count
            frames += advanced
            if show:
                frame = sv.BoxAnnotator().annotate(frame, detections)
                labels = [str(track_id) for track_id in detections.tracker_id] if detections.tracker_id is not None else None
                frame = sv.LabelAnnotator().annotate(frame, detections, labels=labels)
                cv2.polylines(frame, [np.array(polygon)], True, (0, 255, 0), 2)
                cv2.imshow("Boardwise", frame)
                if cv2.waitKey(1) == 27:
                    break
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if show:
        cv2.destroyAllWindows()
    elapsed = time.perf_counter() - started
    print(f"fps: {frames / elapsed:.2f}")
    if folder:
        previous = 0
        for path, count in counts.items():
            print(f"{path.name}: subidas: {count - previous}")
            previous = count
    print(f"total subidas: {next(reversed(counts.values()), 0)}")


if __name__ == "__main__":
    main()
