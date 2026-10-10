"""Descarga yolo11n.pt (preentrenado COCO) y lo exporta a models/yolo11n.onnx imgsz=640."""
from pathlib import Path
import shutil

from ultralytics import YOLO

REPO = Path(__file__).resolve().parent.parent          # raíz del repo, funcione desde donde se ejecute
WEIGHTS = REPO / "training" / "yolo11n.pt"            # queda en training/ (gitignored: *.pt)
OUT = REPO / "models" / "yolo11n.onnx"

model = YOLO(WEIGHTS)  # descarga los pesos si no existen

# NMS embebido si la versión lo soporta; si no, exporta crudo.
try:
    exported = model.export(format="onnx", imgsz=640, nms=True)
    nms_ok = True
except Exception as e:  # noqa: BLE001
    print(f"[export] nms=True fallo ({e}); se exporta sin NMS")
    exported = model.export(format="onnx", imgsz=640, nms=False)
    nms_ok = False

OUT.unlink(missing_ok=True)  # export deterministico entre corridas
OUT.parent.mkdir(parents=True, exist_ok=True)
shutil.move(str(exported), str(OUT))

import onnxruntime as ort

sess = ort.InferenceSession(str(OUT), providers=["CPUExecutionProvider"])
print(f"[export] archivo: {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
for i in sess.get_inputs():
    print(f"[export] input : name={i.name} shape={i.shape} type={i.type}")
for o in sess.get_outputs():
    print(f"[export] output: name={o.name} shape={o.shape} type={o.type}")
print(f"[export] nms embebido: {nms_ok}")