from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Media Studio")
    app.setOrganizationName("MediaStudio")

    window = MainWindow(initial_tab=0)
    window.resize(1340, 850)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

