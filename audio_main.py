from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.common import get_resource_path
from app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Media Studio")
    app.setOrganizationName("MediaStudio")
    app.setWindowIcon(QIcon(str(get_resource_path("assets/cutandpaste-logo-1.png"))))

    window = MainWindow(initial_tab=1)
    window.resize(1340, 850)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
