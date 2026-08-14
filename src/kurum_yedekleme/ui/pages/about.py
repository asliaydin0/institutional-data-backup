"""Hakkında sayfası."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from kurum_yedekleme import __app_name__, __version__


class AboutPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Hakkında")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        body = QLabel(
            f"<b>{__app_name__}</b> v{__version__}<br><br>"
            "Kurum birimlerinin klasörlerini ZIP olarak "
            "<b>E:\\Yedekler</b> altına yedekler.<br><br>"
            "• Her birim kendi klasöründe tutulur<br>"
            "• Kaynak dosyalar yalnızca okunur<br>"
            "• Yarım ZIP nihai .zip adıyla görünmez<br>"
            "• Otomatik yedekleme Windows Service ile çalışır<br>"
            "• Geçmiş SQLite üzerinde alan ve tür bilgisiyle tutulur"
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)
        credit = QLabel("Geliştirici: Aslı AYDIN")
        credit.setObjectName("Muted")
        credit.setStyleSheet("font-size: 11px; color: #94a3b8;")
        layout.addWidget(credit)
