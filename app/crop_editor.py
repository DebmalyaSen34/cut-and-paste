from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.captured_frame import CropRect
from app.utils import clamp_crop


class CropImageView(QWidget):
    crop_changed = Signal(CropRect)

    def __init__(self, pixmap: QPixmap, initial_crop: CropRect | None = None) -> None:
        super().__init__()
        self.pixmap = pixmap
        self.image_width = pixmap.width()
        self.image_height = pixmap.height()
        self.crop = clamp_crop(
            initial_crop or CropRect(0, 0, self.image_width, self.image_height),
            self.image_width,
            self.image_height,
        )
        self._drag_mode: str | None = None
        self._drag_start = QPoint()
        self._start_crop = self.crop
        self.setMinimumSize(720, 460)
        self.setMouseTracking(True)

    def reset_crop(self) -> None:
        self.crop = CropRect(0, 0, self.image_width, self.image_height)
        self.crop_changed.emit(self.crop)
        self.update()

    def set_crop(self, crop: CropRect) -> None:
        self.crop = clamp_crop(crop, self.image_width, self.image_height)
        self.crop_changed.emit(self.crop)
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#15171c"))
        target = self._image_rect()
        painter.drawPixmap(target.toRect(), self.pixmap)

        crop_rect = self._image_to_widget_rect(self.crop)
        overlay = QColor(0, 0, 0, 120)
        painter.fillRect(QRect(0, 0, self.width(), crop_rect.top()), overlay)
        painter.fillRect(QRect(0, crop_rect.bottom(), self.width(), self.height() - crop_rect.bottom()), overlay)
        painter.fillRect(QRect(0, crop_rect.top(), crop_rect.left(), crop_rect.height()), overlay)
        painter.fillRect(QRect(crop_rect.right(), crop_rect.top(), self.width() - crop_rect.right(), crop_rect.height()), overlay)
        painter.setPen(QPen(QColor("#5eead4"), 2))
        painter.drawRect(crop_rect)
        painter.setBrush(QColor("#5eead4"))
        for handle in self._handles(crop_rect):
            painter.drawRect(handle)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position().toPoint()
        crop_rect = self._image_to_widget_rect(self.crop)
        self._drag_mode = self._hit_test(position, crop_rect)
        if self._drag_mode:
            self._drag_start = position
            self._start_crop = self.crop

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        position = event.position().toPoint()
        if not self._drag_mode:
            mode = self._hit_test(position, self._image_to_widget_rect(self.crop))
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if mode and mode != "move" else Qt.CursorShape.SizeAllCursor if mode == "move" else Qt.CursorShape.ArrowCursor)
            return

        image_start = self._widget_to_image_point(self._drag_start)
        image_position = self._widget_to_image_point(position)
        dx = image_position.x() - image_start.x()
        dy = image_position.y() - image_start.y()
        c = self._start_crop

        if self._drag_mode == "move":
            next_crop = CropRect(c.x + dx, c.y + dy, c.width, c.height)
        elif self._drag_mode == "tl":
            next_crop = CropRect(c.x + dx, c.y + dy, c.width - dx, c.height - dy)
        elif self._drag_mode == "tr":
            next_crop = CropRect(c.x, c.y + dy, c.width + dx, c.height - dy)
        elif self._drag_mode == "bl":
            next_crop = CropRect(c.x + dx, c.y, c.width - dx, c.height + dy)
        else:
            next_crop = CropRect(c.x, c.y, c.width + dx, c.height + dy)

        self.crop = clamp_crop(next_crop, self.image_width, self.image_height)
        self.crop_changed.emit(self.crop)
        self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_mode = None

    def _image_rect(self) -> QRectF:
        if self.pixmap.isNull():
            return QRectF()
        scale = min(self.width() / self.image_width, self.height() / self.image_height)
        width = self.image_width * scale
        height = self.image_height * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def _image_to_widget_rect(self, crop: CropRect) -> QRect:
        target = self._image_rect()
        scale = target.width() / self.image_width
        return QRect(
            int(target.left() + crop.x * scale),
            int(target.top() + crop.y * scale),
            max(1, int(crop.width * scale)),
            max(1, int(crop.height * scale)),
        )

    def _widget_to_image_point(self, point: QPoint) -> QPoint:
        target = self._image_rect()
        scale = self.image_width / target.width()
        x = int((point.x() - target.left()) * scale)
        y = int((point.y() - target.top()) * scale)
        return QPoint(max(0, min(x, self.image_width)), max(0, min(y, self.image_height)))

    def _handles(self, rect: QRect) -> list[QRect]:
        size = 12
        half = size // 2
        return [
            QRect(rect.left() - half, rect.top() - half, size, size),
            QRect(rect.right() - half, rect.top() - half, size, size),
            QRect(rect.left() - half, rect.bottom() - half, size, size),
            QRect(rect.right() - half, rect.bottom() - half, size, size),
        ]

    def _hit_test(self, point: QPoint, rect: QRect) -> str | None:
        names = ["tl", "tr", "bl", "br"]
        for name, handle in zip(names, self._handles(rect), strict=True):
            if handle.contains(point):
                return name
        if rect.contains(point):
            return "move"
        return None


class CropEditor(QDialog):
    def __init__(self, frame_path: Path, initial_crop: CropRect | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crop Frame")
        self.result_crop: CropRect | None = initial_crop

        pixmap = QPixmap(str(frame_path))
        self.view = CropImageView(pixmap, initial_crop)
        self.info_label = QLabel()
        self._updating_fields = False
        self.x_input = self._make_spin_box(self.view.image_width)
        self.y_input = self._make_spin_box(self.view.image_height)
        self.width_input = self._make_spin_box(self.view.image_width, minimum=1)
        self.height_input = self._make_spin_box(self.view.image_height, minimum=1)
        self._update_info(self.view.crop)

        reset_button = QPushButton("Reset Crop")
        reset_button.clicked.connect(self.view.reset_crop)
        self.view.crop_changed.connect(self._update_info)
        update_values_button = QPushButton("Update Crop")
        update_values_button.clicked.connect(self._manual_crop_changed)

        size_form = QFormLayout()
        size_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        size_form.addRow("X", self.x_input)
        size_form.addRow("Y", self.y_input)
        size_form.addRow("Width", self.width_input)
        size_form.addRow("Height", self.height_input)
        size_form.addRow("", update_values_button)

        buttons = QDialogButtonBox()
        apply_button = buttons.addButton("Apply Crop", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_button = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        apply_button.clicked.connect(self._apply)
        cancel_button.clicked.connect(self.reject)

        footer = QHBoxLayout()
        footer.addWidget(reset_button)
        footer.addWidget(self.info_label)
        footer.addStretch()
        footer.addLayout(size_form)
        footer.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)
        layout.addLayout(footer)

    def _update_info(self, crop: CropRect) -> None:
        self._updating_fields = True
        self.x_input.setValue(crop.x)
        self.y_input.setValue(crop.y)
        self.width_input.setValue(crop.width)
        self.height_input.setValue(crop.height)
        self._updating_fields = False
        self.info_label.setText(f"x {crop.x}  y {crop.y}  w {crop.width}  h {crop.height}")

    def _make_spin_box(self, maximum: int, minimum: int = 0) -> QSpinBox:
        spin_box = QSpinBox()
        spin_box.setRange(minimum, max(minimum, maximum))
        spin_box.setSingleStep(1)
        spin_box.setFixedWidth(92)
        return spin_box

    def _manual_crop_changed(self) -> None:
        if self._updating_fields:
            return
        crop = CropRect(
            x=self.x_input.value(),
            y=self.y_input.value(),
            width=self.width_input.value(),
            height=self.height_input.value(),
        )
        self.view.set_crop(crop)

    def _apply(self) -> None:
        full_image = CropRect(0, 0, self.view.image_width, self.view.image_height)
        self.result_crop = None if self.view.crop == full_image else self.view.crop
        self.accept()
