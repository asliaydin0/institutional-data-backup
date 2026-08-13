"""Hassas bilgi redaksiyonu — parola / token loglara yazılmaz."""

from __future__ import annotations

import logging
import re
from typing import Match

# Anahtar=değer veya JSON benzeri hassas alanlar
_SENSITIVE_KV = re.compile(
    r"(?i)\b("
    r"password|passwd|pwd|parola|sifre|şifre|"
    r"secret|token|api[_-]?key|access[_-]?key|"
    r"credential|auth(?:entication)?[_-]?key|"
    r"private[_-]?key|connection[_-]?string"
    r")\b(\s*[=:]\s*)([^\s,;\"']+)"
)

_SENSITIVE_JSON = re.compile(
    r'(?i)("(?:'
    r"password|passwd|pwd|parola|sifre|şifre|"
    r"secret|token|api[_-]?key|credential"
    r')"\s*:\s*")([^"]*)(")'
)

# UNC / URL kullanıcı:parola@
_SENSITIVE_URL = re.compile(
    r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)"
)

_REDACTED = "***"


def redact_sensitive_text(text: str) -> str:
    """Metindeki parola ve benzeri değerleri maskeler."""

    def _kv(match: Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}{_REDACTED}"

    def _json(match: Match[str]) -> str:
        return f"{match.group(1)}{_REDACTED}{match.group(3)}"

    def _url(match: Match[str]) -> str:
        return f"{match.group(1)}{_REDACTED}{match.group(3)}"

    out = _SENSITIVE_KV.sub(_kv, text)
    out = _SENSITIVE_JSON.sub(_json, out)
    out = _SENSITIVE_URL.sub(_url, out)
    return out


class SensitiveDataFilter(logging.Filter):
    """Logging kayıtlarında hassas alanları maskeler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_sensitive_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: redact_sensitive_text(v) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        redact_sensitive_text(a) if isinstance(a, str) else a
                        for a in record.args
                    )
        except Exception:  # noqa: BLE001 — log yolu asla uygulamayı düşürmez
            pass
        return True
