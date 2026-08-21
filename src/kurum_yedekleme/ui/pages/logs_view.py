"""Log görüntüleme sayfası — logs/ klasörü, filtre, yenileme."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.utils.logging_setup import LOG_FILE_NAME, SERVICE_LOG_FILE_NAME
from kurum_yedekleme.ui.widgets.page_header import PageHeader
from kurum_yedekleme.ui.widgets.section_panel import SectionPanel


class LogsPage(QWidget):
    """Kurumsal log dosyalarını görüntüler (hassas bilgiler zaten maskelenmiş)."""

    def __init__(
        self,
        log_file: Path | None = None,
        log_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if log_dir is not None:
            self._log_dir = Path(log_dir)
        elif log_file is not None:
            self._log_dir = Path(log_file).parent
        else:
            self._log_dir = Path("logs")
        self._log_file = (
            Path(log_file)
            if log_file is not None
            else self._log_dir / LOG_FILE_NAME
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "Loglar",
                "Uygulama ve servis kayıtları. Hassas bilgiler maskelenmiştir.",
            )
        )

        hint = QLabel(
            "GUI: kurum_yedekleme.log — Servis: kurum_yedekleme_service.log "
            "ve service_boot.log. Servis yedek kayıtları her iki dosyaya da yazılır. "
            "Satır: Tarih Saat SEVİYE Modül İşlem - Mesaj"
        )
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)

        toolbar_panel = SectionPanel("Görüntüleme")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(QLabel("Dosya:"))
        self._file_combo = QComboBox()
        self._file_combo.setMinimumWidth(260)
        self._file_combo.currentIndexChanged.connect(self.reload)
        toolbar.addWidget(self._file_combo, stretch=1)

        toolbar.addWidget(QLabel("Seviye:"))
        self._level_combo = QComboBox()
        self._level_combo.addItems(
            ["Tümü", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        )
        self._level_combo.currentIndexChanged.connect(self.reload)
        toolbar.addWidget(self._level_combo)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Ara…")
        self._search.textChanged.connect(self.reload)
        toolbar.addWidget(self._search, stretch=1)

        refresh = QPushButton("Yenile")
        refresh.setObjectName("SecondaryButton")
        refresh.clicked.connect(self._refresh_file_list_and_reload)
        toolbar.addWidget(refresh)

        self._auto = QPushButton("Otomatik: Kapalı")
        self._auto.setObjectName("SecondaryButton")
        self._auto.setCheckable(True)
        self._auto.toggled.connect(self._on_auto_toggled)
        toolbar.addWidget(self._auto)
        toolbar_panel.add_layout(toolbar)
        layout.addWidget(toolbar_panel)

        viewer_panel = SectionPanel("Kayıt İçeriği")
        self._viewer = QTextEdit()
        self._viewer.setReadOnly(True)
        mono = QFont("Cascadia Mono")
        if not mono.exactMatch():
            mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._viewer.setFont(mono)
        viewer_panel.add_widget(self._viewer)
        layout.addWidget(viewer_panel, stretch=1)

        self._status = QLabel("")
        self._status.setObjectName("MutedLabel")
        layout.addWidget(self._status)

        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.reload)

        self._refresh_file_list_and_reload()

    def _on_auto_toggled(self, checked: bool) -> None:
        self._auto.setText("Otomatik: Açık" if checked else "Otomatik: Kapalı")
        if checked:
            self._timer.start()
        else:
            self._timer.stop()

    def _list_log_files(self) -> list[Path]:
        if not self._log_dir.is_dir():
            return []
        files = [
            p
            for p in self._log_dir.iterdir()
            if p.is_file()
            and (
                p.name == LOG_FILE_NAME
                or p.name == SERVICE_LOG_FILE_NAME
                or p.name == "service_boot.log"
                or p.name.startswith(f"{LOG_FILE_NAME}.")
                or p.name.startswith(f"{SERVICE_LOG_FILE_NAME}.")
                or (
                    p.suffix == ".log"
                    and "kurum_yedekleme" in p.name.lower()
                )
            )
        ]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def _refresh_file_list_and_reload(self) -> None:
        current = self._file_combo.currentData()
        self._file_combo.blockSignals(True)
        self._file_combo.clear()
        files = self._list_log_files()
        if not files and self._log_file:
            files = [self._log_file]
        for path in files:
            self._file_combo.addItem(path.name, path)
        # Önceki seçimi koru
        if current is not None:
            for i in range(self._file_combo.count()):
                if self._file_combo.itemData(i) == current:
                    self._file_combo.setCurrentIndex(i)
                    break
        self._file_combo.blockSignals(False)
        self.reload()

    def _selected_file(self) -> Path | None:
        data = self._file_combo.currentData()
        if isinstance(data, Path):
            return data
        if self._log_file and self._log_file.is_file():
            return self._log_file
        return None

    def reload(self) -> None:
        path = self._selected_file()
        if path is None or not path.is_file():
            self._viewer.setPlainText(
                "Log dosyası henüz oluşmadı. Klasör: logs/"
            )
            self._status.setText("")
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._viewer.setPlainText(f"Log okunamadı: {exc}")
            self._status.setText("")
            return

        lines = text.splitlines()
        level = self._level_combo.currentText()
        query = self._search.text().strip().lower()

        filtered: list[str] = []
        for line in lines:
            if level != "Tümü" and f" {level} " not in line:
                continue
            if query and query not in line.lower():
                continue
            filtered.append(line)

        # Son 800 satır (GUI performansı)
        shown = filtered[-800:]
        self._viewer.setPlainText("\n".join(shown) if shown else "(Eşleşen log yok)")
        self._viewer.moveCursor(QTextCursor.MoveOperation.End)
        self._status.setText(
            f"{path.name} — {len(shown)} / {len(filtered)} satır "
            f"(dosyada {len(lines)})"
        )

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_file_list_and_reload()
