"""Extratos mensais do Santander PJ ("Extrato Consolidado Inteligente") em PDF.

Usa `pdftotext -raw` (Poppler); o texto fica em cache/extratos_texto/ para conferência.
No modo raw cada movimento sai numa linha, assim:

    01/06 PIX ENVIADO MARIA DA SILVA SOUZA 123456 30,00-     ← data só no 1º movimento do dia
    PIX RECEBIDO 12345678900 - 70,00                          ← "-" = sem nº de documento
    PIX ENVIADO                                               ← descrição em várias linhas…
    Joao de Oliveira Santo
    - 1.500,00-                                               ← …e o valor sozinho no fim
    RESGATE CONTAMAX AUTOMATICO - 1.470,96 0,00               ← último valor = saldo do dia

Débito termina em "-". Cada PDF só é aceito se a soma dos créditos e dos débitos lidos
bater, centavo a centavo, com o "Total de Créditos/Débitos" do resumo do próprio extrato.

Aplicação/resgate ContaMax é o banco guardando o saldo parado: entra na conferência dos
totais, mas não é entrada nem saída da igreja e não vai para a aba do extrato.

Linhas de extrato NÃO viram lançamento sozinhas: ficam como "Conciliado (automático)"
quando há lançamento de mesmo valor e tipo até 3 dias de diferença, ou "Não lançado –
conferir" quando não há.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .dados import Congregacao
from .modelo import ENTRADA, MESES_PT, SAIDA, Lancamento, dinheiro, mes_de

_VALOR = r"\d{1,3}(?:\.\d{3})*,\d{2}-?"
_MOVIMENTO = re.compile(rf"^(?:(\d{{2}}/\d{{2}})\s+)?(?:(.*?)\s+)?(-|\d{{3,}})\s+({_VALOR})(?:\s+(-?{_VALOR}))?$")
_SO_DATA = re.compile(r"^(\d{2}/\d{2})\s+(.*)$")
_MES_ANO = re.compile(r"^(" + "|".join(m.lower() for m in MESES_PT) + r")/(\d{4})$")
_TOTAL = re.compile(rf"\(([+-])\) Total de (Créditos|Débitos)\s+({_VALOR})")
_INICIO = "Movimentação"
_FIM = ("Movimentação Mensal", "Saldos por Período", "Índices Econômicos")
_CABECALHO = re.compile(r"^(Data Descrição|Créditos Débitos|EXTRATO CONSOLIDADO|Extrato_PJ|BALP_|Pagina:)")
_INTERNO = re.compile(r"contamax", re.IGNORECASE)
# Formato do aplicativo Santander Empresas.
_PERIODO_APP = re.compile(r"Períodos: (\d{2}/\d{2}/\d{4}) a (\d{2}/\d{2}/\d{4})")
_APP_COMPLETO = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})$")
_APP_VALOR = re.compile(r"^(-?\d{1,3}(?:\.\d{3})*,\d{2})\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})$")
_APP_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_APP_IGNORAR = re.compile(r"^(\d+/\d+|Data Histórico.*)$")

SITUACAO_AUTOMATICA = "Conciliado (automático)"
SITUACAO_NAO_LANCADO = "Não lançado – conferir"
SITUACAO_FORA_DO_OFICIAL = "Não consta no extrato oficial – conferir"
SITUACAO_ANTES_DO_INICIO = "Anterior ao início da tesouraria"
# Situações que o próprio agente calcula e recalcula a cada leitura.
SITUACOES_AUTOMATICAS = (SITUACAO_AUTOMATICA, SITUACAO_NAO_LANCADO, SITUACAO_FORA_DO_OFICIAL,
                         SITUACAO_ANTES_DO_INICIO)


class ErroExtrato(RuntimeError):
    pass


@dataclass
class ExtratoLido:
    arquivo: str
    mes: str | None
    linhas: list[dict] = field(default_factory=list)       # movimentos da igreja
    creditos: Decimal = Decimal("0")                        # inclui ContaMax, para bater com o resumo
    debitos: Decimal = Decimal("0")
    creditos_resumo: Decimal | None = None
    debitos_resumo: Decimal | None = None
    saldos_encadeados: bool | None = None                   # só no formato do aplicativo

    @property
    def confere(self) -> bool:
        if self.mes is None:
            return False
        if self.saldos_encadeados is not None:
            return self.saldos_encadeados and bool(self.linhas)
        return self.creditos == self.creditos_resumo and self.debitos == self.debitos_resumo


def pdftotext() -> str:
    caminho = shutil.which("pdftotext")
    if not caminho:
        raise ErroExtrato("pdftotext (Poppler) não encontrado. Veja a seção de instalação do README.")
    return caminho


def texto_do_pdf(cong: Congregacao, pdf: Path) -> str:
    destino = cong.cache / "extratos_texto" / f"{pdf.stem}.raw.txt"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([pdftotext(), "-raw", "-enc", "UTF-8", str(pdf), str(destino)],
                       check=True, capture_output=True)
    return destino.read_text(encoding="utf-8", errors="replace")


def ler_texto(texto: str, arquivo: str) -> ExtratoLido:
    if _PERIODO_APP.search(texto):
        return ler_texto_aplicativo(texto, arquivo)
    linhas_texto = [l.strip() for l in texto.splitlines()]
    mes = next((f"{m.group(2)}-{[x.lower() for x in MESES_PT].index(m.group(1)) + 1:02d}"
                for l in linhas_texto if (m := _MES_ANO.match(l))), None)
    lido = ExtratoLido(arquivo=arquivo, mes=mes)
    for sinal, tipo, valor in _TOTAL.findall(texto):
        if tipo == "Créditos" and lido.creditos_resumo is None:
            lido.creditos_resumo = dinheiro(valor)
        elif tipo == "Débitos" and lido.debitos_resumo is None:
            lido.debitos_resumo = dinheiro(valor)
    if lido.creditos_resumo is None and lido.debitos_resumo is None and "Resumo - " in texto:
        # Mês sem nenhum movimento: o banco não imprime os totais.
        lido.creditos_resumo = lido.debitos_resumo = Decimal("0")
    if mes is None:
        return lido
    ano = int(mes[:4])

    dentro, dia, descricao = False, None, []
    for linha in linhas_texto:
        if not dentro:
            dentro = linha == _INICIO
            continue
        if linha.startswith(_FIM):
            break
        if not linha or _CABECALHO.match(linha) or _MES_ANO.match(linha) or linha.startswith("SALDO EM"):
            continue
        achado = _MOVIMENTO.match(linha)
        if not achado:
            so_data = _SO_DATA.match(linha)
            if so_data:
                dia, linha = so_data.group(1), so_data.group(2)
            descricao.append(linha)
            continue
        if achado.group(1):
            dia = achado.group(1)
        if dia is None:
            raise ErroExtrato(f"{arquivo}: movimento antes da primeira data: {linha!r}")
        historico = " ".join(descricao + [achado.group(2) or ""]).strip()
        descricao = []
        valor = dinheiro(achado.group(4))      # "1.500,00-" → -1500.00
        if valor > 0:
            lido.creditos += valor
        else:
            lido.debitos += -valor
        if _INTERNO.search(historico):
            continue
        dd, mm = (int(x) for x in dia.split("/"))
        lido.linhas.append({"data": date(ano, mm, dd), "historico": historico, "valor": valor,
                            "arquivo": f"Extrato {arquivo}"})
    return lido


def ler_texto_aplicativo(texto: str, arquivo: str) -> ExtratoLido:
    """Extrato exportado pelo app Santander Empresas: mais recente primeiro, saldo após cada movimento.

        30/09/2026 Pix Recebido 98765432100 10,00 1.250,00
        28/09/2026                                ← data sozinha…
        Pix Enviado MERCADO PAGO                  ← …descrição em várias linhas…
        -22,74 1.240,00                           ← …e valor + saldo no fim

    Validação: o saldo de cada linha menos o seu valor tem de ser o saldo da linha seguinte.
    """
    periodo = _PERIODO_APP.search(texto)
    inicio = datetime.strptime(periodo.group(1), "%d/%m/%Y").date()
    lido = ExtratoLido(arquivo=arquivo, mes=mes_de(inicio))
    movimentos, dia, descricao = [], None, []
    for linha in (l.strip() for l in texto.splitlines()):
        completo = _APP_COMPLETO.match(linha)
        if completo:
            dia, descricao = completo.group(1), [completo.group(2)]
            valor, saldo = completo.group(3), completo.group(4)
        elif (so_valor := _APP_VALOR.match(linha)) and dia:
            valor, saldo = so_valor.group(1), so_valor.group(2)
        else:
            if _APP_DATA.match(linha):
                dia, descricao = linha, []
            elif dia and linha and not _APP_IGNORAR.match(linha):
                descricao.append(linha)
            continue
        movimentos.append({"data": datetime.strptime(dia, "%d/%m/%Y").date(),
                           "historico": " ".join(descricao).strip(), "valor": dinheiro(valor),
                           "saldo": dinheiro(saldo), "arquivo": f"Extrato {arquivo}"})
        dia, descricao = None, []
    lido.saldos_encadeados = all(a["saldo"] - a["valor"] == b["saldo"]
                                 for a, b in zip(movimentos, movimentos[1:]))
    for mov in reversed(movimentos):
        if mov["valor"] > 0:
            lido.creditos += mov["valor"]
        else:
            lido.debitos += -mov["valor"]
        if not _INTERNO.search(mov["historico"]):
            lido.linhas.append({k: v for k, v in mov.items() if k != "saldo"})
    return lido


def _casa(linha: dict, lanc: Lancamento, dias: int) -> bool:
    tipo = ENTRADA if linha["valor"] > 0 else SAIDA
    return (lanc.tipo == tipo and lanc.valor == abs(linha["valor"]) and lanc.data is not None
            and abs(lanc.data - linha["data"]) <= timedelta(days=dias))


def conciliar(linha: dict, lancamentos: list[Lancamento], usados: set[str]) -> str:
    """Procura primeiro no mesmo dia, depois até 3 dias de diferença."""
    for dias in (0, 3):
        for lanc in lancamentos:
            if lanc.id not in usados and _casa(linha, lanc, dias):
                usados.add(lanc.id)
                return SITUACAO_AUTOMATICA
    return SITUACAO_NAO_LANCADO


def sincronizar(cong: Congregacao, lancamentos: list[Lancamento]) -> dict:
    """Troca, mês a mês, o extrato guardado pelo extrato oficial em PDF (quando os totais batem).

    Linhas antigas que não aparecem no PDF oficial não são apagadas: ficam marcadas
    "Não consta no extrato oficial – conferir". A versão anterior vai para cache/.
    """
    pdfs = sorted(cong.entrada("extratos").glob("*.pdf"))
    if not pdfs:
        return {"pdfs": {}, "recusados": {}, "meses": []}
    lidos = [ler_texto(texto_do_pdf(cong, pdf), pdf.stem) for pdf in pdfs]
    aceitos = {l.mes: l for l in lidos if l.confere}
    recusados = {l.arquivo: _motivo(l) for l in lidos if not l.confere}

    antigo = cong.extrato()
    inicio = min((l.data for l in lancamentos if l.data), default=None)
    novo = [l for l in antigo if l.get("data") is None or mes_de(l["data"]) not in aceitos]
    usados: set[str] = set()
    for mes, lido in sorted(aceitos.items()):
        restantes = [l for l in antigo if l.get("data") and mes_de(l["data"]) == mes]
        for linha in lido.linhas:
            igual = next((r for r in restantes if r["data"] == linha["data"] and r["valor"] == linha["valor"]), None)
            if igual:
                restantes.remove(igual)
            if inicio and linha["data"] < inicio:
                situacao = SITUACAO_ANTES_DO_INICIO
            elif igual and igual.get("situacao") and igual["situacao"] not in SITUACOES_AUTOMATICAS:
                situacao = igual["situacao"]   # decidida numa revisão anterior: preservar
            else:
                situacao = conciliar(linha, lancamentos, usados)
            novo.append({**linha, "situacao": situacao})
        novo += [{**r, "situacao": SITUACAO_FORA_DO_OFICIAL} for r in restantes]
    novo.sort(key=lambda l: (l.get("data") or date.min, str(l.get("historico"))))

    if _chaves(novo) != _chaves(antigo):
        backup = cong.cache / f"extrato_antes_{datetime.now():%Y%m%d_%H%M%S}.csv"
        if cong.dados("extrato.csv").exists():
            shutil.copy2(cong.dados("extrato.csv"), backup)
        cong.salvar_extrato(novo)
    return {"pdfs": {l.arquivo: len(l.linhas) for l in lidos}, "recusados": recusados,
            "meses": sorted(aceitos)}


def _chaves(linhas: list[dict]) -> list[tuple]:
    return [(l.get("data"), l.get("valor"), l.get("historico"), l.get("situacao")) for l in linhas]


def _motivo(lido: ExtratoLido) -> str:
    if lido.mes is None:
        return "mês/ano do extrato não encontrado"
    return (f"totais não batem: créditos lidos {lido.creditos} x resumo {lido.creditos_resumo}; "
            f"débitos lidos {lido.debitos} x resumo {lido.debitos_resumo}")


def meses_cobertos(extrato: list[dict]) -> list[str]:
    return sorted({mes_de(l["data"]) for l in extrato if l.get("data")})
