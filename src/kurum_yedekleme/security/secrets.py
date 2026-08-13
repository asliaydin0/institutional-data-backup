"""Güvenlik yardımcıları (parola hard-code edilmez)."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_credential_target(target: Optional[str]) -> Optional[str]:
    """
    Kimlik bilgisi hedef adını döner.

    Gerçek parola burada tutulmaz; Windows Credential Manager / DPAPI
    entegrasyonu sonraki aşamada eklenecektir.
    """
    if not target:
        return None
    # Hedef adı loglanır; parola / secret asla yazılmaz
    logger.debug("Kimlik bilgisi hedefi referansı kullanılıyor (değer yok)")
    return target
