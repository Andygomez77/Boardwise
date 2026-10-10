from __future__ import annotations

import cv2
import numpy as np
import onnxruntime as ort
import supervision as sv

ort.set_default_logger_severity(3)


class Detector:
    def __init__(self, model_path, conf=0.35):
        providers = ort.get_available_providers()
        self.provider = next(
            (name for name in ("CoreMLExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider") if name in providers),
            providers[0],
        )
        self.session = ort.InferenceSession(str(model_path), providers=[self.provider])
        self.input_name = self.session.get_inputs()[0].name
        self.conf = conf

    def detect(self, frame_bgr):
        height, width = frame_bgr.shape[:2]
        scale = min(640 / width, 640 / height)
        resized = cv2.resize(frame_bgr, (round(width * scale), round(height * scale)))
        top = (640 - resized.shape[0]) // 2
        left = (640 - resized.shape[1]) // 2
        image = cv2.copyMakeBorder(resized, top, 640 - resized.shape[0] - top, left, 640 - resized.shape[1] - left, cv2.BORDER_CONSTANT, value=(114, 114, 114))
        blob = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None].astype(np.float32) / 255
        output = self.session.run(None, {self.input_name: blob})[0][0]
        if output.ndim != 2 or output.shape[1] != 6:
            raise ValueError("el modelo debe exportarse con nms=True, ver training/export.py")
        rows = output[(output[:, 4] >= self.conf) & (output[:, 5] == 0)]
        if not len(rows):
            return sv.Detections.empty()
        boxes = rows[:, :4].copy()
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - left) / scale
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - top) / scale
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, width)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, height)
        return sv.Detections(xyxy=boxes, confidence=rows[:, 4], class_id=rows[:, 5].astype(int))
