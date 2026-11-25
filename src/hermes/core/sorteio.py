"""Aleatoriedade reproduzível: a mesma semente e as mesmas partes dão sempre o mesmo sorteio.

`hash()` de texto muda a cada processo do Python, por isso a semente sai de um sha256.
"""

from __future__ import annotations

from hashlib import sha256

import numpy as np


def semente_derivada(semente: int, *partes: object) -> int:
    texto = "|".join(map(str, (semente, *partes)))
    return int.from_bytes(sha256(texto.encode("utf-8")).digest()[:8], "big")


def rng(semente: int, *partes: object) -> np.random.Generator:
    return np.random.default_rng(semente_derivada(semente, *partes))
