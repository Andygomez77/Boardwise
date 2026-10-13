from PySide6.QtGui import QColor, QPalette

BG = "#0f1115"
SURFACE = "#171a21"
SURFACE2 = "#1f232c"
BORDER = "#2a2f3a"
TEXT = "#e6e8ec"
MUTED = "#8b93a1"
ACCENT = "#4f8cff"
SUCCESS = "#22c55e"
WARN = "#f59e0b"
DANGER = "#ef4444"
RUNNING = "#4a3a14"  # fila del video en proceso: ámbar oscuro
OFF = "#5b6270"  # texto deshabilitado

QSS = f"""
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#title {{ font-size: 22px; font-weight: bold; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#hint {{ color: {MUTED}; font-size: 12px; }}
QLabel#section {{ font-weight: bold; }}
QLabel#caption {{ color: {MUTED}; font-size: 12px; font-weight: bold; letter-spacing: 2px; }}
QLabel#count {{ color: {SUCCESS}; font-size: 48px; font-weight: bold; }}

QPushButton {{ background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 14px; }}
QPushButton:hover {{ background: #282d38; border-color: #3a4150; }}
QPushButton:pressed {{ background: #181b22; }}
QPushButton:disabled {{ background: {SURFACE}; color: {OFF}; border-color: #22262f; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: bold; padding: 10px 14px; }}
QPushButton#primary:hover {{ background: #6a9dff; border-color: #6a9dff; }}
QPushButton#primary:pressed {{ background: #3a74e0; }}
QPushButton#primary:disabled {{ background: #1f2a42; border-color: #1f2a42; color: #5f6c87; }}
QPushButton#danger {{ background: {DANGER}; border-color: {DANGER}; color: white; }}
QPushButton#danger:hover {{ background: #f26060; border-color: #f26060; }}
QPushButton#danger:pressed {{ background: #d03030; }}
QPushButton#danger:disabled {{ background: #3a2024; border-color: #3a2024; color: #7d5a5f; }}

QComboBox {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 10px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox:disabled {{ color: {OFF}; background: {SURFACE}; }}
QComboBox QAbstractItemView {{ background: {SURFACE2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; outline: 0; }}

QListWidget, QTableWidget {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 10px; outline: 0; }}
QListWidget {{ padding: 4px; }}
QListWidget::indicator {{ width: 14px; height: 14px; border: 1px solid {OFF}; border-radius: 4px; background: {SURFACE}; }}
QListWidget::indicator:checked {{ background: {SUCCESS}; border-color: {SUCCESS}; }}
QTableWidget {{ gridline-color: transparent; alternate-background-color: {SURFACE}; selection-background-color: {ACCENT}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {SURFACE}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER}; padding: 6px 8px; font-weight: bold; }}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a4150; border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #4a5266; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3a4150; border-radius: 3px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QStatusBar {{ background: {SURFACE}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
"""


def apply(app):
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSizeF(max(font.pointSizeF(), 10))
    app.setFont(font)
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
                        (QPalette.ColorRole.Base, SURFACE2), (QPalette.ColorRole.AlternateBase, SURFACE),
                        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, SURFACE2),
                        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.ToolTipBase, SURFACE2),
                        (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, MUTED),
                        (QPalette.ColorRole.Mid, BORDER), (QPalette.ColorRole.Highlight, ACCENT),
                        (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.Link, ACCENT)):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(OFF))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
