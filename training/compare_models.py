from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import supervision as sv

REPO = Path(__file__).resolve().parent.parent
VIDEO = REPO / "data" / "video test" / "983 06-10-2026" / "hiv00054.mp4"
OUT_DIR = REPO / "training" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    ("yolo11n", OUT_DIR / "yolo11n.onnx"),
    ("yolo11s", OUT_DIR / "yolo11s.onnx"),
    ("yolo11m", OUT_DIR / "yolo11m.onnx"),
]

# Import Detector from app (uses app venv)
sys.path.insert(0, str(REPO))
try:
    from boardwise.core.detector import Detector
except Exception as e:
    print(f"Error importando Detector: {e}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    # Pre-cargar detectores
    dets = []
    for name, path in MODELS:
        if not path.exists():
            raise FileNotFoundError(f"Falta {path}. Exporta con training/export.py")
        dets.append((name, Detector(str(path), conf=0.35)))

    cap = cv2.VideoCapture(str(VIDEO))
    if not cap.isOpened():
        raise RuntimeError(f"No se puede abrir {VIDEO}")

    fps_video = cap.get(cv2.CAP_PROP_FPS) or 15.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_ms = int(frame_count / fps_video * 1000.0) if fps_video > 0 else 0

    # Tomar ~600 cuadros cada 5 s (POS_MSEC) - permite override por env/arg
    interval_ms = 5000
    samples = int(sys.argv[1]) if len(sys.argv) > 1 and str(sys.argv[1]).isdigit() else 600
    # Calcular tiempos
    times = []
    t = 0
    while t <= duration_ms and len(times) < samples:
        times.append(t)
        t += interval_ms
    # Si quedaron pocos, ajustar? pero tarea pide ~600

    results = {name: {"fps_list": [], "people": [], "door": 0} for name, _ in dets}
    sample_data = []  # almacenar para generar comparativas

    for i, t_ms in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t_ms))
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        sample = {"frame": frame.copy(), "dets": {}}
        h, w = frame.shape[:2]
        mid_x = w // 2
        for name, det in dets:
            start = time.perf_counter()
            d = det.detect(frame)
            end = time.perf_counter()
            dt = end - start
            fps_d = 1.0 / dt if dt > 0 else 0.0
            results[name]["fps_list"].append(fps_d)
            n = len(d)
            results[name]["people"].append(n)
            sample["dets"][name] = d
            if n > 0:
                xyxy = d.xyxy
                cx = (xyxy[:, 0] + xyxy[:, 2]) / 2.0
                if np.any(cx >= mid_x):
                    results[name]["door"] += 1
        sample_data.append(sample)


    cap.release()

    # Calcular estadísticas
    stats = {}
    for name, _ in dets:
        r = results[name]
        fps_list = r["fps_list"]
        people_list = r["people"]
        stats[name] = {
            "fps_mean": float(np.mean(fps_list)) if fps_list else 0.0,
            "people_mean": float(np.mean(people_list)) if people_list else 0.0,
            "door_count": int(r["door"]),
            "n_samples": len(fps_list),
        }

    # Calcular scores y elegir mejores para comparar
    scored = []
    for i, s in enumerate(sample_data):
        pn = len(s["dets"].get("yolo11n", sv.Detections.empty()))
        ps = len(s["dets"].get("yolo11s", sv.Detections.empty()))
        pm = len(s["dets"].get("yolo11m", sv.Detections.empty()))
        score = abs(pn - ps) + abs(pn - pm) + abs(ps - pm)
        scored.append((score, i))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = [i for _, i in scored[:6]] if len(scored) >= 6 else list(range(min(6, len(scored))))

    box_annotator = sv.BoxAnnotator(thickness=2)
    label_annotator = sv.LabelAnnotator(text_scale=0.4, text_thickness=1)

    for k, idx in enumerate(chosen):
        s = sample_data[idx] if idx < len(sample_data) else None
        if s is None:
            continue
        frame = s["frame"]
        h, w = frame.shape[:2]
        panels = []
        for name in ("yolo11n", "yolo11s", "yolo11m"):
            d = s["dets"].get(name, sv.Detections.empty())
            f = frame.copy()
            if len(d) > 0:
                try:
                    labels = [f"{name}: {conf:.2f}" for conf in d.confidence]
                    f = box_annotator.annotate(f, d)
                    f = label_annotator.annotate(f, d, labels=labels)
                except Exception:
                    pass
            cv2.line(f, (w // 2, 0), (w // 2, h), (0, 255, 255), 1)
            panels.append(f)
        comp = np.hstack(panels)
        cv2.imwrite(str(OUT_DIR / f"compare_{k:02d}.jpg"), comp)

    # Escribir resumen
    summary_path = OUT_DIR / "compare_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("modelo | tamaño MB | fps | personas/cuadro | cuadros con persona en la puerta\n")
        for name in ("yolo11n", "yolo11s", "yolo11m"):
            st = stats.get(name, {})
            p = OUT_DIR / f"{name}.onnx"
            mb = p.stat().st_size / 1e6 if p.exists() else 0.0
            line = f"{name} | {mb:.1f} | {st.get('fps_mean', 0.0):.1f} | {st.get('people_mean', 0.0):.2f} | {st.get('door_count', 0)}/{st.get('n_samples', 0)}\n"
            f.write(line)
        f.write("\nImágenes: " + ", ".join(str(OUT_DIR / f"compare_{k:02d}.jpg") for k in range(min(len(chosen), 6))) + "\n")


if __name__ == "__main__":
    main()
