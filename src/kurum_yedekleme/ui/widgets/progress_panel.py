"""Yedekleme ilerleme paneli."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.utils.formatting import format_bytes


def _format_elapsed(seconds: float) -> str:
    total = int(max(0, seconds))
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


class ProgressPanel(QFrame):
    """Canlı yedekleme ilerlemesi."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        title = QLabel("Yedekleme İlerlemesi")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        self._stage = QLabel("Hazır")
        self._stage.setObjectName("CardValue")
        self._stage.setWordWrap(True)
        layout.addWidget(self._stage)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        meta = QHBoxLayout()
        meta.setSpacing(16)
        self._files = QLabel("Dosya: 0 / 0")
        self._elapsed = QLabel("Süre: 00:00")
        self._zip = QLabel("ZIP boyutu: —")
        for widget in (self._files, self._elapsed, self._zip):
            meta.addWidget(widget)
        meta.addStretch(1)
        layout.addLayout(meta)

        self._path = QLabel("")
        self._path.setObjectName("Muted")
        self._path.setWordWrap(True)
        layout.addWidget(self._path)

        self.reset()

    def reset(self) -> None:
        self._stage.setText("Hazır")
        self._bar.setValue(0)
        self._files.setText("Dosya: 0 / 0")
        self._elapsed.setText("Süre: 00:00")
        self._zip.setText("ZIP boyutu: —")
        self._path.setText("")
        self.setVisible(False)

    def show_idle(self) -> None:
        self.reset()

    def apply_event(self, event: BackupProgressEvent) -> None:
        self.setVisible(True)
        self._stage.setText(f"{event.stage_label} — {event.message}")
        self._bar.setValue(event.percent)
        self._files.setText(
            f"Dosya: {event.current_files} / {event.total_files}"
        )
        self._elapsed.setText(f"Süre: {_format_elapsed(event.elapsed_seconds)}")
        if event.zip_bytes > 0:
            self._zip.setText(f"ZIP boyutu: {format_bytes(event.zip_bytes)}")
        if event.current_path:
            self._path.setText(event.current_path)
