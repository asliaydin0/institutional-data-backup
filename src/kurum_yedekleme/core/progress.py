"""Yedekleme ilerleme olayları (GUI ↔ motor ayrımı)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


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
    area_name: str = ""

    @property
    def stage_label(self) -> str:
        mapping = {
            "basladi": "Başlatılıyor",
            "tarama": "Dosyalar taranıyor",
            "zip": "ZIP oluşturuluyor",
            "tamamlandi": "Tamamlandı",
            "iptal": "İptal edildi",
            "hata": "Hata",
        }
        return mapping.get(self.stage, self.stage)


ProgressEmitter = Callable[[BackupProgressEvent], None]
