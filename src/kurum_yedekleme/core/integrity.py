"""SHA-256 bütünlük doğrulama."""

from __future__ import annotations

import hashlib
from pathlib import Path

from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("IntegrityService")

CHUNK_SIZE = 1024 * 1024


class IntegrityError(Exception):
    """Bütünlük doğrulama hatası."""


class IntegrityChecker:
    """Dosya özet (hash) hesaplama ve karşılaştırma."""

    def __init__(self, algorithm: str = "sha256", chunk_size: int = CHUNK_SIZE) -> None:
        algo = algorithm.lower().strip()
        if algo != "sha256":
            raise IntegrityError(
                f"Desteklenmeyen algoritma: {algorithm}. Yalnızca sha256."
            )
        self.algorithm = algo
        self.chunk_size = chunk_size

    def sha256_file(self, path: Path) -> str:
        """Dosyanın SHA-256 özetini (hex) döner. Dosya yalnızca okunur."""
        path = Path(path)
        if not path.is_file():
            raise IntegrityError(f"Hash için dosya bulunamadı: {path}")

        digest = hashlib.sha256()
        logger.debug("SHA-256 hesaplanıyor: %s", path)
        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(self.chunk_size)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError as exc:
            raise IntegrityError(f"Hash okuma hatası: {path} ({exc})") from exc

        hex_digest = digest.hexdigest()
        logger.info("SHA-256 (%s): %s", path.name, hex_digest, operation="hash")
        return hex_digest

    def verify(self, path: Path, expected_hex: str) -> bool:
        """Hash eşleşmesini kontrol eder."""
        actual = self.sha256_file(path)
        expected = expected_hex.strip().lower()
        matched = actual.lower() == expected
        if matched:
            logger.info(
                "SHA-256 doğrulaması başarılı: %s",
                path,
                operation="verify",
            )
        else:
            logger.error(
                "Hash uyuşmazlığı: dosya=%s beklenen=%s gerçek=%s",
                path,
                expected,
                actual,
                operation="verify",
            )
        return matched
