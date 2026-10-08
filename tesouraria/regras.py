"""Regras da tesouraria: como cada lançamento entra no cálculo do mês.

As porcentagens vêm do config.yaml da congregação. Não mude os valores padrão
sem pedido explícito de quem cuida da tesouraria.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from .modelo import ENTRADA, SAIDA, CONFIRMADO, PENDENTE, DIVERGENCIA, Lancamento

# Prefixos da descrição que mudam a classificação (mesma regra da planilha REV02).
PREFIXO_PREBENDA = "prebenda"
PREFIXO_REPASSE_SEDE = "repasse sede"
PREFIXO_TRANSFERENCIA = "transferência interna"


@dataclass(frozen=True)
class Abono:
    """Período em que a sede abriu mão do repasse: os 20% dela ficam com a igreja local."""
    de: str          # "2025-05"
    ate: str         # "2026-04" (inclusive)
    motivo: str = ""
    valor: Decimal | None = None   # abono parcial (R$ abatido do repasse); None = mês inteiro abonado

    def cobre(self, mes: str) -> bool:
        return self.de <= mes <= self.ate


@dataclass(frozen=True)
class Regras:
    repasse_sede: Decimal = Decimal("0.20")
    prebenda: Decimal = Decimal("0.20")
    abonos_sede: tuple[Abono, ...] = ()
    # "mensal": os 20% da prebenda saem do saldo todo mês; "quando_paga": o saldo só é debitado
    # pelo que foi pago (adiantamentos), e o restante fica apenas sinalizado como "a pagar".
    prebenda_no_saldo: str = "mensal"
    # A partir deste mês ("AAAA-MM"), cartão/QR code e Pix sem crédito no extrato da congregação são
    # tratados como valores que ficaram na conta da sede (não repassados). None = controle desligado.
    na_sede_desde: str | None = None
    na_sede_motivo: str = ""

    @property
    def igreja_local(self) -> Decimal:
        return Decimal("1") - self.repasse_sede - self.prebenda

    def sede_do_mes(self, mes: str) -> Decimal:
        abono = self.abono_do_mes(mes)
        return Decimal("0") if abono and abono.valor is None else self.repasse_sede

    def abono_do_mes(self, mes: str) -> Abono | None:
        return next((a for a in self.abonos_sede if a.cobre(mes)), None)

    def abono_parcial(self, mes: str) -> Decimal:
        abono = self.abono_do_mes(mes)
        return abono.valor if abono and abono.valor is not None else Decimal("0")

    @property
    def prebenda_quando_paga(self) -> bool:
        return self.prebenda_no_saldo == "quando_paga"

    def validar(self) -> None:
        if not (0 <= self.repasse_sede <= 1 and 0 <= self.prebenda <= 1 and self.igreja_local >= 0):
            raise ValueError("porcentagens inválidas no config.yaml: sede + prebenda não pode passar de 100%")
        if self.prebenda_no_saldo not in ("mensal", "quando_paga"):
            raise ValueError("config.yaml: regras.prebenda_no_saldo deve ser 'mensal' ou 'quando_paga'")
        for a in self.abonos_sede:
            if a.de > a.ate:
                raise ValueError(f"config.yaml: abono da sede com 'de' ({a.de}) depois de 'ate' ({a.ate})")


def _comeca(lanc: Lancamento, prefixo: str) -> bool:
    return lanc.descricao.strip().casefold().startswith(prefixo)


def eh_transferencia(lanc: Lancamento) -> bool:
    return _comeca(lanc, PREFIXO_TRANSFERENCIA)


_MAQUININHA = re.compile(r"qr ?code|maquininha|cart[aã]o|d[eé]bito|cr[eé]dito", re.IGNORECASE)
MOTIVO_CARTAO = "Cartão / QR code da maquininha (cai na conta da sede)"
MOTIVO_PIX_SEM_EXTRATO = "Pix sem crédito no extrato da congregação"


def motivo_na_sede(lanc: Lancamento, regras: Regras) -> str | None:
    """Por que esta entrada é tratada como valor que ficou na sede (None = está na congregação)."""
    if (regras.na_sede_desde is None or lanc.tipo != ENTRADA or lanc.valor is None
            or lanc.mes < regras.na_sede_desde or eh_transferencia(lanc) or lanc.forma == "Dinheiro"):
        return None
    if lanc.forma == "Cartão" or _MAQUININHA.search(lanc.descricao):
        return MOTIVO_CARTAO
    if lanc.forma == "Pix" and "extrato" not in lanc.comprovante.casefold():
        return MOTIVO_PIX_SEM_EXTRATO
    return None


def eh_prebenda(lanc: Lancamento) -> bool:
    return lanc.tipo == SAIDA and _comeca(lanc, PREFIXO_PREBENDA)


def eh_repasse_sede(lanc: Lancamento) -> bool:
    return lanc.tipo == SAIDA and _comeca(lanc, PREFIXO_REPASSE_SEDE)


def conta_como_entrada(lanc: Lancamento) -> bool:
    return lanc.tipo == ENTRADA and not eh_transferencia(lanc)


def conta_como_despesa(lanc: Lancamento) -> bool:
    return (lanc.tipo == SAIDA and not eh_transferencia(lanc)
            and not eh_prebenda(lanc) and not eh_repasse_sede(lanc))


@dataclass
class ResumoMes:
    mes: str
    entradas: Decimal
    sede: Decimal
    prebenda: Decimal
    local: Decimal
    despesas: Decimal
    saldo_mes: Decimal
    saldo_anterior: Decimal
    saldo_total: Decimal
    prebenda_paga: Decimal
    prebenda_a_pagar: Decimal     # acumulado
    sede_paga: Decimal
    sede_a_repassar: Decimal      # acumulado
    confirmados: int
    pendentes: int
    divergencias: int
    sem_valor: int


def _soma(lancs, filtro) -> Decimal:
    return sum((l.valor for l in lancs if l.valor is not None and filtro(l)), Decimal("0"))


def resumir(lancamentos: list[Lancamento], meses: list[str], regras: Regras,
            saldo_inicial: Decimal) -> list[ResumoMes]:
    """Reproduz em Python as fórmulas das abas mensais e do Resumo Geral."""
    resumos: list[ResumoMes] = []
    saldo_anterior, prebenda_acum, sede_acum = saldo_inicial, Decimal("0"), Decimal("0")
    for mes in meses:
        do_mes = [l for l in lancamentos if l.mes == mes]
        entradas = _soma(do_mes, conta_como_entrada)
        sede = entradas * regras.sede_do_mes(mes) - regras.abono_parcial(mes)
        prebenda = entradas * regras.prebenda
        despesas = _soma(do_mes, conta_como_despesa)
        prebenda_paga = _soma(do_mes, eh_prebenda)
        sede_paga = _soma(do_mes, eh_repasse_sede)
        if regras.prebenda_quando_paga:
            local = entradas - sede
            saldo_mes = local - despesas - prebenda_paga
        else:
            local = entradas - sede - prebenda
            saldo_mes = local - despesas
        prebenda_acum += prebenda - prebenda_paga
        sede_acum += sede - sede_paga
        resumo = ResumoMes(
            mes=mes, entradas=entradas, sede=sede, prebenda=prebenda, local=local,
            despesas=despesas, saldo_mes=saldo_mes, saldo_anterior=saldo_anterior,
            saldo_total=saldo_mes + saldo_anterior, prebenda_paga=prebenda_paga,
            prebenda_a_pagar=prebenda_acum, sede_paga=sede_paga, sede_a_repassar=sede_acum,
            confirmados=sum(l.status == CONFIRMADO for l in do_mes),
            pendentes=sum(l.status == PENDENTE for l in do_mes),
            divergencias=sum(l.status == DIVERGENCIA for l in do_mes),
            sem_valor=sum(l.valor is None for l in do_mes),
        )
        resumos.append(resumo)
        saldo_anterior = resumo.saldo_total
    return resumos
