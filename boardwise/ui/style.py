import sys
from pathlib import Path
from string import Template

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

# Colores de la marca (logo): morado #2A1B5C, ámbar #FFB020, lavanda #EDE8FF
THEMES = {
    "dark": dict(
        BG="#120D24", SURFACE="#1B1436", SURFACE2="#251C47", BORDER="#342A5E", TEXT="#EDE8FF", MUTED="#A49CC4",
        OFF="#5E5688", ACCENT="#FFB020", ACCENT_HOVER="#FFC04D", ACCENT_PRESSED="#E89A00", ON_ACCENT="#2A1B5C",
        COUNT="#FFB020", DANGER="#EF4444", HOVER="#2E2457", HOVER_BORDER="#4A3D80", PRESSED="#171030",
        SEL="#4B3A9A", SEL_TEXT="#EDE8FF", RUNNING="#4D3A12", PROGRESS="#8B7BE0", KNOB_EDGE="#120D24",
    ),
    "light": dict(
        BG="#F6F4FC", SURFACE="#FFFFFF", SURFACE2="#F0ECFA", BORDER="#DDD6F3", TEXT="#2A1B5C", MUTED="#6B6390",
        OFF="#A59DC4", ACCENT="#FFB020", ACCENT_HOVER="#FFC04D", ACCENT_PRESSED="#E89A00", ON_ACCENT="#2A1B5C",
        COUNT="#C77700", DANGER="#DC2626", HOVER="#E7E1F7", HOVER_BORDER="#C9BFEA", PRESSED="#E0D9F3",
        SEL="#E3DCFF", SEL_TEXT="#2A1B5C", RUNNING="#FFE9B8", PROGRESS="#5B4BB5", KNOB_EDGE="#2A1B5C",
    ),
}
C = dict(THEMES["dark"])  # colores vigentes: apply() lo reemplaza en sitio, se lee al pintar
mode = "dark"

QSS = Template("""
QMainWindow, QDialog { background: $BG; }
QToolTip { background: $SURFACE2; color: $TEXT; border: 1px solid $BORDER; padding: 4px; }
QFrame#card { background: $SURFACE; border: 1px solid $BORDER; border-radius: 12px; }
QLabel#title { font-size: 22px; font-weight: bold; }
QLabel#muted { color: $MUTED; }
QLabel#hint { color: $MUTED; font-size: 12px; }
QLabel#section { font-weight: bold; }
QLabel#caption { color: $MUTED; font-size: 12px; font-weight: bold; letter-spacing: 2px; }
QLabel#count { color: $COUNT; font-size: 48px; font-weight: bold; }

QPushButton { background: $SURFACE2; color: $TEXT; border: 1px solid $BORDER; border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { background: $HOVER; border-color: $HOVER_BORDER; }
QPushButton:pressed { background: $PRESSED; }
QPushButton:disabled { background: $SURFACE; color: $OFF; border-color: $BORDER; }
QPushButton#primary { background: $ACCENT; border-color: $ACCENT; color: $ON_ACCENT; font-weight: bold; padding: 10px 14px; }
QPushButton#primary:hover { background: $ACCENT_HOVER; border-color: $ACCENT_HOVER; }
QPushButton#primary:pressed { background: $ACCENT_PRESSED; border-color: $ACCENT_PRESSED; }
QPushButton#danger { background: $DANGER; border-color: $DANGER; color: white; }
QPushButton#danger:hover { background: $DANGER; border-color: $TEXT; }
QPushButton#danger:pressed { background: $DANGER; border-color: $DANGER; }
QPushButton#primary:disabled, QPushButton#danger:disabled { background: $SURFACE; color: $OFF; border-color: $BORDER; }

QComboBox { background: $SURFACE2; border: 1px solid $BORDER; border-radius: 8px; padding: 6px 10px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox:disabled { color: $OFF; background: $SURFACE; }
QComboBox QAbstractItemView { background: $SURFACE2; border: 1px solid $BORDER; selection-background-color: $SEL; selection-color: $SEL_TEXT; outline: 0; }

QListWidget, QTableWidget { background: $SURFACE2; border: 1px solid $BORDER; border-radius: 10px; outline: 0; selection-background-color: $SEL; selection-color: $SEL_TEXT; }
QListWidget { padding: 4px; }
QListWidget::indicator { width: 14px; height: 14px; border: 1px solid $OFF; border-radius: 4px; background: $SURFACE; }
QListWidget::indicator:checked { background: $ACCENT; border-color: $ACCENT; }
QTableWidget { gridline-color: transparent; alternate-background-color: $SURFACE; }
QHeaderView { background: transparent; }
QHeaderView::section { background: $SURFACE; color: $MUTED; border: none; border-bottom: 1px solid $BORDER; padding: 6px 8px; font-weight: bold; }
QTableCornerButton::section { background: $SURFACE; border: none; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $BORDER; border-radius: 3px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: $OFF; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $BORDER; border-radius: 3px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: $OFF; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QProgressBar { background: $SURFACE2; border: 1px solid $BORDER; border-radius: 6px; text-align: center; }
QProgressBar::chunk { background: $PROGRESS; border-radius: 5px; }
QStatusBar { background: $SURFACE; color: $MUTED; border-top: 1px solid $BORDER; }
QStatusBar::item { border: none; }
""")


def asset(name):
    """Ruta de un archivo de assets/ (dentro del build o en el repo)."""
    return str(Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / name)


def initial_mode():
    """Modo guardado; la primera vez, el esquema del sistema (desconocido → oscuro)."""
    saved = QSettings("Boardwise", "Boardwise").value("theme")
    if saved in THEMES:
        return saved
    return "light" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light else "dark"


def apply(app, new_mode=None):
    global mode
    mode = new_mode or initial_mode()
    C.update(THEMES[mode])
    if not app.property("boardwise_styled"):
        app.setStyle("Fusion")
        font = app.font()
        font.setPointSizeF(max(font.pointSizeF(), 10))
        app.setFont(font)
        app.setProperty("boardwise_styled", True)
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, "BG"), (QPalette.ColorRole.WindowText, "TEXT"),
                        (QPalette.ColorRole.Base, "SURFACE2"), (QPalette.ColorRole.AlternateBase, "SURFACE"),
                        (QPalette.ColorRole.Text, "TEXT"), (QPalette.ColorRole.Button, "SURFACE2"),
                        (QPalette.ColorRole.ButtonText, "TEXT"), (QPalette.ColorRole.ToolTipBase, "SURFACE2"),
                        (QPalette.ColorRole.ToolTipText, "TEXT"), (QPalette.ColorRole.PlaceholderText, "MUTED"),
                        (QPalette.ColorRole.Mid, "BORDER"), (QPalette.ColorRole.Highlight, "SEL"),
                        (QPalette.ColorRole.HighlightedText, "SEL_TEXT"), (QPalette.ColorRole.Link, "ACCENT")):
        palette.setColor(role, QColor(C[color]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(C["OFF"]))
    app.setPalette(palette)
    app.setStyleSheet(QSS.substitute(C))
