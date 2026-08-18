"""Tablo hücrelerinde ortadan kısaltılmış dosya yolu."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedPathLabel(QLabel):
    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_path = path
        self.setToolTip(path)
        self.setObjectName("TablePathLabel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(160)
        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._apply_elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        width = max(40, self.width() - 8)
        self.setText(
            self.fontMetrics().elidedText(
                self._full_path, Qt.TextElideMode.ElideMiddle, width
            )
        )
