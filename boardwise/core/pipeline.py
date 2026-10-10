from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import cv2
import supervision as sv

from .detector import Detector


VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov")


def list_videos(folder):
    return sorted(path for path in Path(folder).iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS)


def _model_path():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "models" / "yolo11n.onnx"


class Counter:
    def __init__(self, line_start, line_end):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            self.tracker = sv.ByteTrack()
        self.line_zone = sv.LineZone(sv.Point(*line_start), sv.Point(*line_end))

    def update(self, detections):
        detections = self.tracker.update_with_detections(detections)
        self.line_zone.trigger(detections)
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
                yield video_path, frame, detections, counter.line_zone.in_count, counter.line_zone.out_count
        finally:
            capture.release()


def run(video_path, line_start, line_end, model_path=None, detector=None):
    counter = Counter(line_start, line_end)
    detector = detector or Detector(model_path or _model_path())
    for _, frame, detections, in_count, out_count in _frames([video_path], counter, detector):
        yield frame, detections, in_count, out_count


def run_folder(folder, line_start, line_end, model_path=None, detector=None, on_skip=None):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"No se pudo abrir la carpeta: {folder}")
    paths = list_videos(folder)
    counter = Counter(line_start, line_end)
    detector = detector or Detector(model_path or _model_path())
    yield from _frames(paths, counter, detector, skip_bad=True, on_skip=on_skip)


def _line(value):
    try:
        points = tuple(map(int, value.split(",")))
        if len(points) != 4:
            raise ValueError
        return points[:2], points[2:]
    except ValueError as error:
        raise argparse.ArgumentTypeError("La línea debe ser x1,y1,x2,y2") from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--line", required=True, type=_line)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    start, end = args.line
    source = Path(args.video)
    folder = source.is_dir()
    detector = Detector(_model_path())
    print(f"provider: {detector.provider}")
    generator = run_folder(source, start, end, detector=detector) if folder else run(source, start, end, detector=detector)
    frames = 0
    started = time.perf_counter()
    show = args.show and "GUI: NONE" not in cv2.getBuildInformation()
    current = None
    counts = {}
    try:
        for item in generator:
            if folder:
                current, frame, detections, in_count, out_count = item
            else:
                frame, detections, in_count, out_count = item
                current = source
            counts[current] = (in_count, out_count)
            frames += 1
            if show:
                frame = sv.BoxAnnotator().annotate(frame, detections)
                labels = [str(track_id) for track_id in detections.tracker_id] if detections.tracker_id is not None else None
                frame = sv.LabelAnnotator().annotate(frame, detections, labels=labels)
                cv2.line(frame, start, end, (0, 255, 0), 2)
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
        previous = (0, 0)
        for path, (in_count, out_count) in counts.items():
            print(f"{path.name}: in: {in_count - previous[0]}, out: {out_count - previous[1]}")
            previous = in_count, out_count
    in_count, out_count = next(reversed(counts.values()), (0, 0))
    print(f"total in: {in_count}, out: {out_count}")


# in es el cruce desde el lado derecho al izquierdo del vector line_start → line_end.
if __name__ == "__main__":
    main()
