"""Tipos básicos: lançamento, status de conferência e conversões de dinheiro/data/mês."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ENTRADA = "Entrada"
SAIDA = "Saída"
TIPOS = (ENTRADA, SAIDA)

CONFIRMADO = "🟢 CONFIRMADO"
PENDENTE = "🟡 PENDENTE"
DIVERGENCIA = "🔴 DIVERGÊNCIA"
STATUS = (CONFIRMADO, PENDENTE, DIVERGENCIA)

# Apelidos aceitos em respostas.yaml / transcricoes.yaml.
STATUS_APELIDOS = {
    "confirmado": CONFIRMADO, "verde": CONFIRMADO, "🟢": CONFIRMADO,
    "pendente": PENDENTE, "amarelo": PENDENTE, "🟡": PENDENTE,
    "divergencia": DIVERGENCIA, "divergência": DIVERGENCIA, "vermelho": DIVERGENCIA, "🔴": DIVERGENCIA,
}

FORMAS = ("Dinheiro", "Cartão", "Pix", "Débito em conta", "Transferência", "Não informado")

MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


@dataclass
class Lancamento:
    id: str
    mes: str                      # "2025-06" — mês da aba onde o lançamento fica
    data: date | None
    tipo: str                     # Entrada | Saída
    descricao: str
    valor: Decimal | None
    forma: str = "Não informado"
    comprovante: str = ""
    status: str = PENDENTE
    observacao: str = ""
    extras: dict = field(default_factory=dict)  # colunas além da H (texto livre), preservadas

    def copia(self, **mudancas) -> "Lancamento":
        return replace(self, **mudancas)


def dinheiro(valor) -> Decimal | None:
    """Converte 1234.5, '1.234,50', 'R$ 1.234,50' ou '1234.50' em Decimal com 2 casas."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, Decimal):
        return valor.quantize(Decimal("0.01"))
    if isinstance(valor, (int, float)):
        return Decimal(str(round(float(valor), 2))).quantize(Decimal("0.01"))
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    negativo = texto.startswith("-") or texto.endswith("-")
    texto = texto.strip("-+")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto).quantize(Decimal("0.01"))
    except InvalidOperation as erro:
        raise ValueError(f"valor em dinheiro inválido: {valor!r}") from erro
    return -numero if negativo else numero


def reais(valor: Decimal | None) -> str:
    """Decimal('1234.5') → 'R$ 1.234,50'."""
    if valor is None:
        return "sem valor"
    valor = Decimal(valor).quantize(Decimal("0.01")) + 0   # "+ 0" tira o sinal de -0,00
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def para_data(valor) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    raise ValueError(f"data inválida: {valor!r} (use AAAA-MM-DD ou DD/MM/AAAA)")


def normalizar_status(valor) -> str:
    if valor in STATUS:
        return valor
    chave = str(valor or "").strip().lower()
    if chave in STATUS_APELIDOS:
        return STATUS_APELIDOS[chave]
    raise ValueError(f"status inválido: {valor!r} (use confirmado, pendente ou divergencia)")


def normalizar_tipo(valor) -> str:
    chave = str(valor or "").strip().lower()
    if chave in ("entrada", "e"):
        return ENTRADA
    if chave in ("saída", "saida", "s"):
        return SAIDA
    raise ValueError(f"tipo inválido: {valor!r} (use Entrada ou Saída)")


def mes_de(data: date) -> str:
    return f"{data.year:04d}-{data.month:02d}"


def validar_mes(mes: str) -> str:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(mes)):
        raise ValueError(f"mês inválido: {mes!r} (use AAAA-MM)")
    return str(mes)


def nome_aba(mes: str) -> str:
    ano, m = mes.split("-")
    return f"{MESES_ABREV[int(m) - 1]}-{ano}"


def mes_da_aba(titulo: str) -> str | None:
    achado = re.fullmatch(r"([A-Za-z]{3})-(\d{4})", titulo.strip())
    if not achado or achado.group(1).capitalize() not in MESES_ABREV:
        return None
    return f"{achado.group(2)}-{MESES_ABREV.index(achado.group(1).capitalize()) + 1:02d}"


def nome_mes_extenso(mes: str) -> str:
    ano, m = mes.split("-")
    return f"{MESES_PT[int(m) - 1]}/{ano}"


def proximo_mes(mes: str) -> str:
    ano, m = (int(x) for x in mes.split("-"))
    return f"{ano + (m == 12):04d}-{(m % 12) + 1:02d}"


def meses_entre(inicio: str, fim: str) -> list[str]:
    meses, atual = [], inicio
    while atual <= fim:
        meses.append(atual)
        atual = proximo_mes(atual)
    return meses
