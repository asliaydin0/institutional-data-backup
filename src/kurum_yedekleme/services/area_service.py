"""Yedekleme alanı iş kuralları — CRUD, doğrulama, ortak alan tarama."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kurum_yedekleme.db.areas_repository import AreasRepository
from kurum_yedekleme.db.errors import DatabaseError
from kurum_yedekleme.db.models import BackupArea
from kurum_yedekleme.services.disk_space import can_read_directory
from kurum_yedekleme.utils.windows_paths import to_path


class AreaError(ValueError):
    """Alan doğrulama / işlem hatası."""


@dataclass(frozen=True)
class ScannedFolder:
    name: str
    path: Path


class AreaService:
    def __init__(self, repository: AreasRepository) -> None:
        self._repo = repository

    def list_areas(self) -> list[BackupArea]:
        return self._repo.list_alive()

    def list_enabled(self) -> list[BackupArea]:
        return self._repo.list_enabled()

    def get(self, area_id: int) -> BackupArea:
        area = self._repo.get_by_id(area_id, include_deleted=False)
        if area is None:
            raise AreaError(f"Alan bulunamadı: id={area_id}")
        return area

    def add_area(
        self,
        *,
        name: str,
        source_path: str,
        enabled: bool = True,
        require_source: bool = True,
    ) -> BackupArea:
        cleaned_name = self._validate_name(name)
        source = self._validate_source(source_path, require_exists=require_source)
        existing = self._repo.get_by_name(cleaned_name, include_deleted=False)
        if existing is not None:
            raise AreaError(f"Bu alan adı zaten kayıtlı: {cleaned_name}")
        try:
            return self._repo.insert(
                name=cleaned_name, source_path=str(source), enabled=enabled
            )
        except DatabaseError as exc:
            raise AreaError(str(exc)) from exc

    def update_area(
        self,
        area_id: int,
        *,
        name: str,
        source_path: str,
        enabled: bool,
        require_source: bool = True,
    ) -> BackupArea:
        self.get(area_id)
        cleaned_name = self._validate_name(name)
        source = self._validate_source(source_path, require_exists=require_source)
        other = self._repo.get_by_name(cleaned_name, include_deleted=False)
        if other is not None and other.id != area_id:
            raise AreaError(f"Bu alan adı zaten kayıtlı: {cleaned_name}")
        try:
            return self._repo.update(
                area_id,
                name=cleaned_name,
                source_path=str(source),
                enabled=enabled,
            )
        except DatabaseError as exc:
            raise AreaError(str(exc)) from exc

    def set_enabled(self, area_id: int, enabled: bool) -> BackupArea:
        try:
            return self._repo.set_enabled(area_id, enabled)
        except DatabaseError as exc:
            raise AreaError(str(exc)) from exc

    def delete_area(self, area_id: int) -> None:
        """Soft delete — fiziksel yedekler ve geçmiş silinmez."""
        self.get(area_id)
        try:
            self._repo.soft_delete(area_id)
        except DatabaseError as exc:
            raise AreaError(str(exc)) from exc

    def scan_common_root(self, common_root: str | Path) -> list[ScannedFolder]:
        root = to_path(common_root)
        if not root.exists():
            raise AreaError(f"Ortak alan klasörü bulunamadı: {root}")
        if not root.is_dir():
            raise AreaError(f"Ortak alan bir klasör değil: {root}")
        try:
            children = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            raise AreaError(f"Ortak alan okunamadı: {root} ({exc})") from exc
        folders: list[ScannedFolder] = []
        for child in children:
            if not child.is_dir() or child.name.startswith("."):
                continue
            folders.append(ScannedFolder(name=child.name, path=child))
        return folders

    def add_scanned(
        self,
        folders: list[ScannedFolder],
        *,
        enabled: bool = True,
    ) -> tuple[list[BackupArea], list[str]]:
        added: list[BackupArea] = []
        skipped: list[str] = []
        for folder in folders:
            try:
                added.append(
                    self.add_area(
                        name=folder.name,
                        source_path=str(folder.path),
                        enabled=enabled,
                    )
                )
            except AreaError as exc:
                skipped.append(str(exc))
        return added, skipped

    @staticmethod
    def _validate_name(name: str) -> str:
        cleaned = str(name or "").strip()
        if not cleaned:
            raise AreaError("Alan adı boş olamaz.")
        if len(cleaned) > 120:
            raise AreaError("Alan adı 120 karakteri aşamaz.")
        return cleaned

    @staticmethod
    def _validate_source(source_path: str, *, require_exists: bool) -> Path:
        raw = str(source_path or "").strip()
        if not raw:
            raise AreaError("Kaynak klasör boş olamaz.")
        path = to_path(raw)
        if not require_exists:
            return path
        ok, detail = can_read_directory(path)
        if not ok:
            raise AreaError(
                f"Kaynak klasöre erişilemiyor: {path} ({detail})"
            )
        return path
