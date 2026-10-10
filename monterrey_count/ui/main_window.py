from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow

from monterrey_count import updater

TITLE = "Monterrey Count"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{TITLE} v{updater.current_version()}")
        self.setCentralWidget(QLabel("Aquí va el contador.", alignment=Qt.AlignmentFlag.AlignCenter))
        self.resize(900, 600)
