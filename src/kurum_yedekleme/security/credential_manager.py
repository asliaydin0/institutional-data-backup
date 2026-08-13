"""Windows Credential Manager — modüler iskelet (parola saklanmaz)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CredentialRef:
    """
    Kimlik bilgisi referansı.

    Gerçek parola burada tutulmaz; yalnızca hedef adı / kullanıcı adı.
    """

    target_name: str
    username: Optional[str] = None


class CredentialStore(Protocol):
    """Credential Manager soyutlaması."""

    def get_reference(self, target_name: str) -> Optional[CredentialRef]:
        """Hedef adına göre referans döner (parola yok)."""

    def has_credential(self, target_name: str) -> bool:
        """Hedef kayıtlı mı?"""


class NullCredentialStore:
    """
    Varsayılan: UNC mevcut Windows oturumu ile erişilir.

    Farklı kullanıcı gerektiğinde WinCredentialStore ile değiştirilir.
    """

    def get_reference(self, target_name: str) -> Optional[CredentialRef]:
        if not target_name:
            return None
        logger.debug(
            "Credential referansı istendi (parola okunmadı): hedef=%s",
            target_name,
        )
        return CredentialRef(target_name=target_name)

    def has_credential(self, target_name: str) -> bool:
        return bool(target_name)


class WinCredentialStore:
    """
    İleride: Windows Credential Manager (win32cred / keyring) entegrasyonu.

    Şimdilik parola okumaz/yazmaz; yalnızca arayüz hazırdır.
    """

    def get_reference(self, target_name: str) -> Optional[CredentialRef]:
        if not target_name:
            return None
        # TODO: win32cred.CredRead — parola belleğe alınmadan yalnızca varlık kontrolü
        logger.info(
            "WinCredentialStore: hedef referansı (henüz CredRead yok): %s",
            target_name,
        )
        return CredentialRef(target_name=target_name)

    def has_credential(self, target_name: str) -> bool:
        # Gerçek sorgu sonraki aşamada
        return bool(target_name)


def default_credential_store() -> CredentialStore:
    """Mevcut oturum varsayımı — Null store."""
    return NullCredentialStore()
