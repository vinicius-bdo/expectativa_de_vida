from decimal import Decimal

import pytest

from painel import DOLAR, INTERGER, MEDIAS


@pytest.mark.parametrize(
    ("formatar", "valor", "resultado"),
    [
        (DOLAR, Decimal("1003862.14"), "USD$ 1.003.862,14"),
        (INTERGER, 96470, "96.470"),
        (MEDIAS, Decimal("70.55"), "70,55"),
    ],
)
def test_formatadores_usam_separadores_pt_br(formatar, valor, resultado):
    assert formatar(valor) == resultado


def test_formatadores_representam_valor_ausente():
    assert DOLAR(None) == "USD$ —"
    assert INTERGER(None) == "—"
    assert MEDIAS(None) == "—"
