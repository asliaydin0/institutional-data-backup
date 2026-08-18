"""Hakkında sayfası."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from kurum_yedekleme import __app_name__, __version__
from kurum_yedekleme.ui.widgets.page_header import PageHeader
from kurum_yedekleme.ui.widgets.section_panel import SectionPanel


class AboutPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "Hakkında",
                "Kurum birimlerinin dosya yedekleme ve arşivleme uygulaması.",
            )
        )

        info = SectionPanel("Uygulama Bilgisi")
        version = QLabel(f"{__app_name__}")
        version.setObjectName("AboutVersion")
        info.add_widget(version)
        subtitle = QLabel(f"Sürüm {__version__}")
        subtitle.setObjectName("Muted")
        info.add_widget(subtitle)
        desc = QLabel(
            "Kurum birimlerinin paylaşımlı klasörlerini ZIP arşivi olarak "
            "güvenli biçimde yedekler. Kaynak dosyalar yalnızca okunur; "
            "yedekler kurum politikasına uygun hedef dizinde saklanır."
        )
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        info.add_widget(desc)
        layout.addWidget(info)

        features = SectionPanel("Özellikler")
        body = QLabel(
            "• Her birim için ayrı yedekleme alanı tanımlanır\n"
            "• Manuel ve otomatik (zamanlanmış) yedekleme desteği\n"
            "• Windows Service ile arka planda kesintisiz çalışma\n"
            "• Yedekleme geçmişi ve denetim kayıtları\n"
            "• Eski yedekler için saklama süresi politikası\n"
            "• Yarım kalan arşivler nihai dosya olarak görünmez"
        )
        body.setWordWrap(True)
        features.add_widget(body)
        layout.addWidget(features)

        layout.addStretch(1)
        credit = QLabel("Geliştirici: Aslı AYDIN")
        credit.setObjectName("AboutCredit")
        layout.addWidget(credit)
