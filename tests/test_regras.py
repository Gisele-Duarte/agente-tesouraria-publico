from decimal import Decimal

from tesouraria.regras import Regras, resumir
from conftest import LANCAMENTOS


def test_resumo_aplica_20_20_60_e_ignora_transferencias_prebenda_e_repasse():
    jan, fev = resumir(LANCAMENTOS, ["2025-01", "2025-02"], Regras(), Decimal("100"))

    assert jan.entradas == Decimal("1500")          # transferência interna não é entrada
    assert jan.sede == jan.prebenda == Decimal("300")
    assert jan.local == Decimal("900")
    assert jan.despesas == Decimal("200")           # sem prebenda e sem transferência
    assert jan.saldo_total == Decimal("100") + Decimal("700")
    assert jan.prebenda_paga == Decimal("100")
    assert jan.prebenda_a_pagar == Decimal("200")

    assert fev.entradas == Decimal("400")           # lançamento sem valor não soma
    assert fev.despesas == Decimal("50")            # repasse à sede não é despesa dos 60%
    assert fev.saldo_anterior == jan.saldo_total
    assert fev.sede_a_repassar == Decimal("300") + Decimal("80") - Decimal("300")
    assert (fev.pendentes, fev.divergencias, fev.sem_valor) == (1, 1, 1)


def test_regras_recusam_porcentagens_acima_de_100():
    import pytest
    with pytest.raises(ValueError):
        Regras(repasse_sede=Decimal("0.6"), prebenda=Decimal("0.5")).validar()


def test_abono_da_sede_deixa_80_por_cento_com_a_igreja_local():
    from tesouraria.regras import Abono
    regras = Regras(abonos_sede=(Abono("2025-02", "2025-02", "abonado pela sede"),))
    jan, fev = resumir(LANCAMENTOS, ["2025-01", "2025-02"], regras, Decimal("0"))
    assert jan.sede == Decimal("300") and jan.local == Decimal("900")
    assert fev.sede == Decimal("0") and fev.local == Decimal("400") * Decimal("0.8")
    assert fev.sede_a_repassar == Decimal("300") - Decimal("300")   # repasse pago em fev quita janeiro


def test_prebenda_quando_paga_so_debita_o_que_foi_pago_e_abono_parcial():
    from tesouraria.regras import Abono
    regras = Regras(prebenda_no_saldo="quando_paga",
                    abonos_sede=(Abono("2025-01", "2025-01", "parcial", valor=Decimal("100")),))
    jan, fev = resumir(LANCAMENTOS, ["2025-01", "2025-02"], regras, Decimal("0"))
    assert jan.sede == Decimal("200")                       # 20% de 1500 − 100 abonados
    assert jan.local == Decimal("1300")                     # entradas − sede
    assert jan.saldo_mes == Decimal("1300") - Decimal("200") - Decimal("100")   # − despesas − prebenda paga
    assert jan.prebenda_a_pagar == Decimal("200")           # continua sinalizado
    assert fev.saldo_mes == Decimal("400") - Decimal("80") - Decimal("50")      # sem prebenda paga em fev
