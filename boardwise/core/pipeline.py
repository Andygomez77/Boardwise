from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import cv2
import numpy as np
import supervision as sv

from .detector import Detector


VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov")
MIN_FRAMES_INSIDE = 3


def list_videos(folder):
    return sorted(path for path in Path(folder).iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS)


def _model_path():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "models" / "yolo11n.onnx"


class Counter:
    """Cuenta personas (IDs del tracker) cuyos pies estuvieron dentro del área al menos MIN_FRAMES_INSIDE cuadros."""

    def __init__(self, polygon):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            self.tracker = sv.ByteTrack()
        self.zone = sv.PolygonZone(np.array(polygon), triggering_anchors=(sv.Position.BOTTOM_CENTER,))
        self.frames_inside = {}
        self.counted = set()

    @property
    def count(self):
        return len(self.counted)

    def update(self, detections):
        detections = self.tracker.update_with_detections(detections)
        inside = self.zone.trigger(detections)
        for track_id in detections.tracker_id[inside]:
            self.frames_inside[track_id] = self.frames_inside.get(track_id, 0) + 1
            if self.frames_inside[track_id] >= MIN_FRAMES_INSIDE:
                self.counted.add(track_id)
        # ponytail: si el tracker pierde a alguien y le da otro ID, puede contarse doble; subir MIN_FRAMES_INSIDE o ReID si estorba.
        return detections


def _frames(paths, counter, detector, skip_bad=False, on_skip=None):
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
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                detections = counter.update(detector.detect(frame))
                yield video_path, frame, detections, counter.count
        finally:
            capture.release()


def run(video_path, polygon, model_path=None, detector=None):
    counter = Counter(polygon)
    detector = detector or Detector(model_path or _model_path())
    for _, frame, detections, count in _frames([video_path], counter, detector):
        yield frame, detections, count


def run_videos(paths, polygon, model_path=None, detector=None, on_skip=None):
    counter = Counter(polygon)
    detector = detector or Detector(model_path or _model_path())
    yield from _frames(paths, counter, detector, skip_bad=True, on_skip=on_skip)


def run_folder(folder, polygon, model_path=None, detector=None, on_skip=None):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"No se pudo abrir la carpeta: {folder}")
    yield from run_videos(list_videos(folder), polygon, model_path, detector, on_skip)


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
    args = parser.parse_args()
    polygon = args.zone
    source = Path(args.video)
    folder = source.is_dir()
    detector = Detector(_model_path())
    print(f"provider: {detector.provider}")
    generator = run_folder(source, polygon, detector=detector) if folder else run(source, polygon, detector=detector)
    frames = 0
    started = time.perf_counter()
    show = args.show and "GUI: NONE" not in cv2.getBuildInformation()
    current = None
    counts = {}
    try:
        for item in generator:
            if folder:
                current, frame, detections, count = item
            else:
                frame, detections, count = item
                current = source
            counts[current] = count
            frames += 1
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
