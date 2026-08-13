"""Hakkında sayfası."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from kurum_yedekleme import __app_name__, __version__


class AboutPage(QWidget):
    """Uygulama bilgisi."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel("Hakkında")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        body = QLabel(
            f"<b>{__app_name__}</b> v{__version__}<br><br>"
            "Kurumsal klasörleri ZIP olarak yedekler, SHA-256 ile doğrular "
            "ve Windows ağ paylaşımına güvenli aktarır.<br><br>"
            "• Kaynak dosyalar yalnızca okunur<br>"
            "• Yarım ZIP nihai adla bırakılmaz<br>"
            "• Parola bilgisi kod içine yazılmaz<br>"
            "• Arayüz yedekleme motorundan bağımsızdır"
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)
