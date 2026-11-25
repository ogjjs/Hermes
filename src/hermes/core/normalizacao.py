"""Normalização de texto (mesmo critério da função SQL hermes.normalizar)."""

from __future__ import annotations

import re
import unicodedata

_ESPACOS = re.compile(r"\s+")


def normalizar_texto(texto: str) -> str:
    """NFKC desfaz ligaduras de PDF ("ﬁ" -> "fi")."""
    return unicodedata.normalize("NFKC", texto or "")


def normalizar_titulo(texto: str) -> str:
    return _ESPACOS.sub(" ", normalizar_texto(texto)).strip().upper()
