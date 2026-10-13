import cv2
from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from boardwise.core.clock import read_clock
from boardwise.core.timeline import durations as cached_durations

PAD = 8
NEAR_PX = 5  # distancia al clic para tomarlo como clic en una marca


def hms(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def clock_text(moment, date=True):
    """Hora real del DVR; AM/PM propio para no depender del idioma del sistema."""
    return (f"{moment:%d/%m/%Y} " if date else "") + f"{moment:%I:%M:%S} " + ("PM" if moment.hour >= 12 else "AM")


def start_time(path):
    """Hora real impresa en el primer cuadro del archivo, None si no hay reloj."""
    capture = cv2.VideoCapture(str(path))
    ok, frame = capture.read()
    capture.release()
    return read_clock(frame) if ok else None


class DurationWorker(QThread):
    done = Signal(list, list)  # duraciones y hora real de inicio de cada archivo

    def __init__(self, paths, parent):
        super().__init__(parent)
        self.paths = list(paths)

    def run(self):
        durations = cached_durations(self.paths, self.isInterruptionRequested)
        if durations is None:
            return
        starts = []
        for path in self.paths:
            if self.isInterruptionRequested():
                return
            starts.append(start_time(path))
        self.done.emit(durations, starts)


class TimelineBar(QWidget):
    """Barra de toda la carpeta: posición, separadores entre archivos y una marca por subida."""

    seek = Signal(float, bool)  # tiempo global; True = soltó el ratón
    mark_clicked = Signal(float)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self.setMouseTracking(True)
        self.timeline = None
        self.starts = []  # hora real de inicio de cada archivo (None = sin reloj)
        self.position = 0.0
        self.wall = None  # hora real del cuadro mostrado
        self.marks = []  # (video, segundo en el video, hora real o None)
        self._drag = False

    def set_timeline(self, timeline, starts=None):
        self.timeline = timeline
        self.starts = starts or [None] * (len(timeline.paths) if timeline else 0)
        self.update()

    def set_position(self, seconds, wall=None):
        self.position, self.wall = seconds, wall
        self.update()

    def clear_marks(self):
        self.marks = []
        self.update()

    def add_mark(self, path, seconds, wall=None):
        self.marks.append((path, seconds, wall))
        self.update()

    def sorted_marks(self):
        """[(tiempo global, número de subida, video, hora real)] en orden de tiempo."""
        if not self.timeline:
            return []
        rows = sorted(((self.timeline.to_global(path, seconds), path, wall) for path, seconds, wall in self.marks), key=lambda row: row[0])
        return [(t, n, path, wall) for n, (t, path, wall) in enumerate(rows, 1)]

    def x_of(self, seconds):
        return PAD + seconds / self.timeline.total * (self.width() - 2 * PAD)

    def _time_at(self, x):
        return min(max((x - PAD) / (self.width() - 2 * PAD), 0.0), 1.0) * self.timeline.total

    def _mark_near(self, x):
        near = [mark for mark in self.sorted_marks() if abs(self.x_of(mark[0]) - x) <= NEAR_PX]
        return min(near, key=lambda mark: abs(self.x_of(mark[0]) - x), default=None)

    def label(self):
        t = self.timeline
        parts = [clock_text(self.wall)] if self.wall else []
        return " · ".join(parts + [t.locate(self.position)[0].stem, f"{hms(self.position)} / {hms(t.total)}"])

    def tooltip_at(self, x):
        mark = self._mark_near(x)
        if mark:
            return " · ".join(filter(None, [f"Subida {mark[1]}", mark[3] and clock_text(mark[3], False), mark[2].stem]))
        for path, offset, start in list(zip(self.timeline.paths, self.timeline.offsets, self.starts))[1:]:
            if abs(self.x_of(offset) - x) <= NEAR_PX:
                return " · ".join(filter(None, [path.stem, start and clock_text(start)]))

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.window())
        if not self.timeline:
            return
        timeline = self.timeline
        painter.setPen(palette.text().color())
        painter.drawText(PAD, 14, self.label())
        painter.fillRect(QRectF(PAD, 28, self.width() - 2 * PAD, 6), palette.mid())
        painter.fillRect(QRectF(PAD, 28, self.x_of(self.position) - PAD, 6), palette.highlight())
        separator = QColor(palette.text().color())
        separator.setAlpha(70)
        painter.setPen(separator)
        for offset in timeline.offsets[1:]:
            x = self.x_of(offset)
            painter.drawLine(int(x), 24, int(x), 38)
        painter.setPen(QPen(QColor(220, 40, 40), 2))
        for t, *_ in self.sorted_marks():
            x = int(self.x_of(t))
            painter.drawLine(x, 22, x, 40)
        painter.setPen(QPen(palette.text().color(), 1))
        painter.setBrush(palette.base())
        painter.drawEllipse(QRectF(self.x_of(self.position) - 5, 26, 10, 10))

    def mousePressEvent(self, event):
        if not self.timeline or event.button() != Qt.MouseButton.LeftButton:
            return
        mark = self._mark_near(event.position().x())
        if mark:
            return self.mark_clicked.emit(mark[0])
        self._drag = True
        self.seek.emit(self._time_at(event.position().x()), False)

    def mouseMoveEvent(self, event):
        if not self.timeline:
            return
        x = event.position().x()
        if self._drag:
            return self.seek.emit(self._time_at(x), False)
        tip = self.tooltip_at(x)
        if tip:
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        if self._drag:
            self._drag = False
            self.seek.emit(self._time_at(event.position().x()), True)
