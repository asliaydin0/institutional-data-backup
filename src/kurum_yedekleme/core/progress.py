"""Yedekleme ilerleme olayları (GUI ↔ motor ayrımı)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class BackupProgressEvent:
    """Arka plan işinden UI'ye iletilen ilerleme anlık görüntüsü."""

    stage: str
    message: str
    current_files: int = 0
    total_files: int = 0
    percent: int = 0
    elapsed_seconds: float = 0.0
    zip_bytes: int = 0
    current_path: str = ""

    @property
    def stage_label(self) -> str:
        mapping = {
            "basladi": "Başlatılıyor",
            "tarama": "Dosyalar taranıyor",
            "zip": "ZIP oluşturuluyor",
            "aktarim": "Sunucuya aktarılıyor",
            "dogrulama": "Bütünlük doğrulanıyor",
            "tamamlandi": "Tamamlandı",
            "hata": "Hata",
        }
        return mapping.get(self.stage, self.stage)


ProgressEmitter = Callable[[BackupProgressEvent], None]
