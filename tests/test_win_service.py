"""Windows Service kurulum doğrulama testleri."""

from __future__ import annotations

import sys

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
        "_service_util",
        lambda: (_FakeService, _FakeUtil()),
    )
    monkeypatch.setattr(win_service, "_configure_installed_service", lambda: None)
    monkeypatch.setattr(
        "kurum_yedekleme.services.windows_service.query_service",
        lambda: _NotInstalled(),
    )

    with pytest.raises(RuntimeError, match="kaydedilemedi"):
        win_service.install_win32_service()


def test_service_class_is_importable_on_windows() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows only")
    assert win_service.KurumYedeklemeWinService is not None
    assert (
        win_service.KurumYedeklemeWinService.__name__ == "KurumYedeklemeWinService"
    )


class _FakeService:
    pass


class _FakeUtil:
    @staticmethod
    def HandleCommandLine(_cls) -> None:
        return None


class _NotInstalled:
    state = "not_installed"
