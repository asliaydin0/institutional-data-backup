"""Windows Service kurulum doğrulama testleri."""

from __future__ import annotations

import pytest

from kurum_yedekleme import win_service


def test_install_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kurum_yedekleme.services.windows_service.is_user_admin",
        lambda: False,
    )

    with pytest.raises(RuntimeError, match="yönetici yetkisi"):
        win_service.install_win32_service()


def test_install_verifies_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kurum_yedekleme.services.windows_service.is_user_admin",
        lambda: True,
    )
    monkeypatch.setattr(
        win_service,
        "_ensure_service_class",
        lambda: (_FakeService, _FakeUtil()),
    )
    monkeypatch.setattr(
        "kurum_yedekleme.services.windows_service.query_service",
        lambda: _NotInstalled(),
    )

    with pytest.raises(RuntimeError, match="kaydedilemedi"):
        win_service.install_win32_service()


class _FakeService:
    pass


class _FakeUtil:
    @staticmethod
    def HandleCommandLine(_cls) -> None:
        return None


class _NotInstalled:
    state = "not_installed"
