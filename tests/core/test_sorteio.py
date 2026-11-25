from hermes.core.sorteio import rng, semente_derivada


def test_semente_derivada_e_estavel_entre_processos():
    # valor fixo do sha256 de "2026|5": o hash() do Python mudaria a cada processo
    esperado = int.from_bytes(__import__("hashlib").sha256(b"2026|5").digest()[:8], "big")
    assert semente_derivada(2026, 5) == esperado
    assert semente_derivada(2026, "loja", 5) == semente_derivada(2026, "loja", 5)
    assert semente_derivada(2026, 5) != semente_derivada(2026, 6)


def test_rng_reproduz_a_mesma_sequencia():
    assert list(rng(2026, "x").integers(0, 1000, 5)) == list(rng(2026, "x").integers(0, 1000, 5))
    assert list(rng(2026, "x").integers(0, 1000, 5)) != list(rng(2026, "y").integers(0, 1000, 5))
