"""Movimentos do extrato oficial ainda sem lançamento → lançamentos novos, no padrão da REV03.

- Pix recebido: "Entrada Pix – provável <nome>" quando o mesmo CPF já foi ligado a uma
  pessoa em outro lançamento; senão "Entrada Pix – a identificar (CPF final NNNN)". Sempre 🟡:
  dízimo ou oferta, e de quem, só a tesouraria confirma.
- Pix enviado sem comprovante: "A identificar – Pix enviado a <nome>" 🟡.
- Tarifa bancária: 🟢 (o próprio extrato é o comprovante).
- Qualquer outro movimento: "A identificar – <histórico>" 🟡.
"""
from __future__ import annotations

import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from .dados import Congregacao
from .extrato import SITUACAO_NAO_LANCADO
from .modelo import CONFIRMADO, ENTRADA, PENDENTE, SAIDA, Lancamento, mes_de

_PIX_RECEBIDO = re.compile(r"^pix recebido\s+(\d{11,14})", re.IGNORECASE)
_PIX_ENVIADO = re.compile(r"^pix enviado\s*(.*)$", re.IGNORECASE)
_TARIFA = re.compile(r"^tarifa", re.IGNORECASE)
# Nome da pessoa dentro da descrição de um lançamento já identificado.
_NOME = re.compile(r"^(?:Dízimo|Oferta)\s+–\s+(.+)$|^Entrada Pix – provável (.+?) \(")
_NAO_E_PESSOA = re.compile(r"identificar|sem nome|culto|evento|ofertas|aniversário|\(", re.IGNORECASE)
# Um valor pequeno coincide por acaso; o CPF só ganha nome se casou com ele ao menos 2 vezes.
MINIMO_DE_COINCIDENCIAS = 2

OBS_PIX_RECEBIDO = "Pix recebido na conta; identificar se é dízimo ou oferta e quem enviou"
OBS_SEM_COMPROVANTE = "Consta no extrato sem comprovante/descrição no WhatsApp"


def _cpf(historico: str) -> str | None:
    achado = _PIX_RECEBIDO.match(historico.strip())
    return achado.group(1) if achado else None


def nomes_por_cpf(extrato: list[dict], lancamentos: list[Lancamento]) -> dict[str, str]:
    """CPF → nome, a partir dos Pix recebidos que já casam com um lançamento identificado.

    Só vale quando o CPF aparece sempre com o mesmo nome (sem empate)."""
    contagem: dict[str, Counter] = defaultdict(Counter)
    por_chave = defaultdict(list)
    for lanc in lancamentos:
        if lanc.tipo == ENTRADA and lanc.valor is not None and lanc.data:
            por_chave[lanc.valor].append(lanc)
    for linha in extrato:
        cpf = _cpf(str(linha.get("historico") or ""))
        if not cpf or not linha.get("data") or linha["valor"] is None or linha["valor"] <= 0:
            continue
        candidatos = [l for l in por_chave[linha["valor"]] if abs(l.data - linha["data"]) <= timedelta(days=3)]
        if len(candidatos) != 1:
            continue
        achado = _NOME.match(candidatos[0].descricao)
        nome = (achado.group(1) or achado.group(2)).strip() if achado else ""
        if nome and not _NAO_E_PESSOA.search(nome):
            contagem[cpf][nome] += 1
    mapa = {}
    for cpf, nomes in contagem.items():
        (primeiro, n1), *resto = nomes.most_common(2)
        if n1 >= MINIMO_DE_COINCIDENCIAS and (not resto or resto[0][1] < n1):
            mapa[cpf] = primeiro
    return mapa


def propor(cong: Congregacao, extrato: list[dict], lancamentos: list[Lancamento], mes: str) -> list[Lancamento]:
    nomes = nomes_por_cpf(extrato, lancamentos)
    proximo = max((int(l.id[1:]) for l in lancamentos if re.fullmatch(r"L\d+", l.id)), default=0)
    novos = []
    for linha in extrato:
        if linha.get("situacao") != SITUACAO_NAO_LANCADO or not linha.get("data") or mes_de(linha["data"]) != mes:
            continue
        proximo += 1
        novos.append(_lancamento(f"L{proximo:05d}", linha, nomes))
    return novos


def _lancamento(id_: str, linha: dict, nomes: dict[str, str]) -> Lancamento:
    historico = " ".join(str(linha["historico"]).split())
    data, valor = linha["data"], abs(linha["valor"])
    tipo = ENTRADA if linha["valor"] > 0 else SAIDA
    base = dict(id=id_, mes=mes_de(data), data=data, tipo=tipo, valor=valor,
                comprovante=f"Extrato {data:%d/%m/%Y}")
    if tipo == ENTRADA and (cpf := _cpf(historico)):
        if cpf in nomes:
            descricao = f"Entrada Pix – provável {nomes[cpf]} (dízimo/oferta a confirmar)"
        else:
            descricao = f"Entrada Pix – a identificar (CPF final {cpf[-4:]})"
        return Lancamento(**base, descricao=descricao, forma="Pix", status=PENDENTE, observacao=OBS_PIX_RECEBIDO)
    if _TARIFA.match(historico):
        return Lancamento(**base, descricao=f"Tarifa bancária – {historico.upper()}", forma="Débito em conta",
                          status=CONFIRMADO)
    if tipo == SAIDA and (enviado := _PIX_ENVIADO.match(historico)):
        destino = enviado.group(1).strip().title() or "(sem nome no extrato)"
        return Lancamento(**base, descricao=f"A identificar – Pix enviado a {destino}", forma="Pix",
                          status=PENDENTE, observacao=OBS_SEM_COMPROVANTE)
    return Lancamento(**base, descricao=f"A identificar – {historico}",
                      forma="Pix" if "pix" in historico.lower() else "Débito em conta",
                      status=PENDENTE, observacao=OBS_SEM_COMPROVANTE)


def gravar(cong: Congregacao, novos: list[Lancamento]) -> None:
    """Acrescenta aos dados (backup do arquivo anterior em cache/)."""
    atual = cong.dados("lancamentos.csv")
    shutil.copy2(atual, cong.cache / f"lancamentos_antes_{datetime.now():%Y%m%d_%H%M%S}.csv")
    cong.salvar_lancamentos(cong.lancamentos() + novos)
