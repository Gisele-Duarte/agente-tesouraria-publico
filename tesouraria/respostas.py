"""Respostas da tesouraria às pendências → correções nos lançamentos.

Formato de respostas.yaml (toda resposta fica registrada, inclusive remoções):

    base_revisao: 4                   # REVnn importada: os códigos L… abaixo são dela
    saldo_inicial: 0                  # saldo (banco + espécie) antes do 1º lançamento

    lancamentos:                      # correções por id (veja `agente.py pendencias`)
      L00123:
        resposta: "Era oferta do culto de quarta, R$ 120 no Pix"   # obrigatória: o que a pessoa disse
        valor: 120.00
        status: confirmado            # confirmado | pendente | divergencia
        descricao: "Oferta – culto (Pix)"
        # também aceitos: data, tipo, forma, mes, comprovante, observacao
      L00456:
        resposta: "Lançado em dobro, o certo é o de 30/06"
        remover: true

    novos:                            # lançamentos que só a resposta revelou
      - resposta: "Teve oferta de R$ 50 em dinheiro no dia 04/06"
        data: 2025-06-04
        tipo: Entrada
        descricao: "Oferta – culto (dinheiro)"
        valor: 50
        forma: Dinheiro

    perguntas:                        # perguntas para a liderança (P1, P2… em `pendencias`)
      P2: "Os dois Pix de R$ 500 foram prebenda"

    extrato:                          # situação de linhas do extrato que não viram lançamento
      - data: 2025-02-07
        valor: 1000.00
        situacao: "Repasse da maquininha da sede (valores já lançados como dízimos/ofertas)"
        resposta: "Repasse da maquininha, somente saldo"

    para_a_agenda:                    # respostas sobre fotos ainda não transcritas (lembrete)
      - "05/10/25: dízimo da Fulana é R$ 60,00"

Em vez de `resposta`, uma correção pode trazer `conferencia`: a evidência que o agente
encontrou (ex.: "o extrato tem um único Pix de R$ 1.500 em 27/10; L00985 repete L00982").
Fica registrada como "Conferência: …", separada do que a tesouraria respondeu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dados import Congregacao, ler_yaml
from .modelo import (CONFIRMADO, FORMAS, Lancamento, dinheiro, para_data, normalizar_status,
                     normalizar_tipo, mes_de, validar_mes)

CAMPOS_EDITAVEIS = {"valor", "status", "descricao", "data", "tipo", "forma", "mes", "comprovante",
                    "observacao", "remover", "resposta", "conferencia"}


class ErroResposta(ValueError):
    pass


@dataclass
class Resultado:
    lancamentos: list[Lancamento]
    removidos: list[Lancamento] = field(default_factory=list)
    perguntas_respondidas: dict[str, str] = field(default_factory=dict)


def ler(cong: Congregacao) -> dict:
    return ler_yaml(cong.arquivo_respostas)


def aplicar(cong: Congregacao, lancamentos: list[Lancamento]) -> Resultado:
    respostas = ler(cong)
    conferir_base(cong, respostas)
    por_id = {l.id: l for l in lancamentos}
    removidos: set[str] = set()

    for id_, mudanca in (respostas.get("lancamentos") or {}).items():
        id_ = str(id_)
        if id_ not in por_id:
            raise ErroResposta(f"respostas.yaml: lançamento {id_} não existe (confira o id em `pendencias`)")
        if not isinstance(mudanca, dict):
            raise ErroResposta(f"respostas.yaml, {id_}: use campos (resposta:, valor:, status: …)")
        desconhecidos = set(mudanca) - CAMPOS_EDITAVEIS
        if desconhecidos:
            raise ErroResposta(f"respostas.yaml, {id_}: campos desconhecidos {sorted(desconhecidos)}")
        if not (mudanca.get("resposta") or mudanca.get("conferencia")):
            raise ErroResposta(f"respostas.yaml, {id_}: registre em 'resposta' o que a pessoa respondeu "
                               "(ou em 'conferencia' a evidência da correção)")
        if mudanca.get("remover"):
            removidos.add(id_)
            continue
        try:
            por_id[id_] = _corrigir(por_id[id_], mudanca)
        except ValueError as erro:
            raise ErroResposta(f"respostas.yaml, {id_}: {erro}") from erro

    editados = {str(i) for i in (respostas.get("lancamentos") or {})}
    for n, regra in enumerate(respostas.get("em_lote") or [], start=1):
        _em_lote(n, regra, por_id, editados | removidos)

    novos, novos_removidos = [], []
    for n, item in enumerate(respostas.get("novos") or [], start=1):
        try:
            novo = _novo(n, item)
        except ValueError as erro:
            raise ErroResposta(f"respostas.yaml, novos #{n}: {erro}") from erro
        # 'remover: true' tira o lançamento sem apagar o item: a posição (código R…) dos seguintes não muda.
        (novos_removidos if item.get("remover") else novos).append(novo)

    resultado = [por_id[l.id] for l in lancamentos if l.id not in removidos] + novos
    perguntas = {str(k): str(v) for k, v in (respostas.get("perguntas") or {}).items() if v}
    return Resultado(resultado, [l for l in lancamentos if l.id in removidos] + novos_removidos, perguntas)


def _em_lote(n: int, regra: dict, por_id: dict[str, Lancamento], ignorar: set[str]) -> None:
    """Uma resposta que vale para todos os lançamentos cuja descrição começa de um certo jeito.

        em_lote:
          - resposta: "marcar 🟢 como oferta/dízimo não identificado"
            descricao_comeca: ["Entrada Pix – a identificar", "Entrada Pix – provável"]
            nova_descricao: "Entrada Pix – oferta/dízimo não identificado ({resto})"
            status: confirmado

    {resto} = o que vinha depois do começo, sem "(dízimo/oferta a confirmar)" e sem parênteses
    (ex.: "CPF final 1234", "provável Pr. Fulano"). Lançamentos com resposta individual não mudam.
    """
    local = f"respostas.yaml, em_lote #{n}"
    comecos = regra.get("descricao_comeca") or []
    if isinstance(comecos, str):
        comecos = [comecos]
    if not comecos or not (regra.get("resposta") or regra.get("conferencia")):
        raise ErroResposta(f"{local}: informe 'descricao_comeca' e 'resposta'")
    for id_, lanc in por_id.items():
        if id_ in ignorar:
            continue
        comeco = next((c for c in comecos if lanc.descricao.startswith(c)), None)
        if comeco is None:
            continue
        mudanca = {k: v for k, v in regra.items() if k in ("status", "forma", "resposta", "conferencia")}
        if regra.get("nova_descricao"):
            resto = lanc.descricao.removeprefix("Entrada Pix – ").replace("(dízimo/oferta a confirmar)", "")
            resto = re.sub(r"\s+", " ", resto.replace("a identificar", "").replace("(", "").replace(")", "")).strip()
            mudanca["descricao"] = regra["nova_descricao"].replace("{resto}", resto)
        try:
            por_id[id_] = _corrigir(lanc, mudanca)
        except ValueError as erro:
            raise ErroResposta(f"{local}: {erro}") from erro


def conferir_base(cong: Congregacao, respostas: dict) -> None:
    """Os códigos L00123 mudam a cada planilha importada: respostas de outra base não valem."""
    base = respostas.get("base_revisao")
    atual = cong.config().get("revisao_base")
    if respostas.get("lancamentos") and base is None:
        raise ErroResposta("respostas.yaml: informe 'base_revisao' (a REVnn importada cujos códigos L… "
                           "as respostas usam)")
    if base is not None and int(base) != int(atual or 0):
        raise ErroResposta(f"respostas.yaml foi escrito para a REV{int(base):02d}, mas a base importada é a "
                           f"REV{int(atual or 0):02d}: os códigos L… não correspondem mais. Refaça as respostas.")


def registro(item: dict) -> str:
    partes = []
    if item.get("resposta"):
        partes.append(f"Resposta da tesouraria: {item['resposta']}")
    if item.get("conferencia"):
        partes.append(f"Conferência: {item['conferencia']}")
    return "; ".join(partes)


def aplicar_extrato(cong: Congregacao, extrato: list[dict]) -> list[dict]:
    """Cópia do extrato com a situação das linhas indicadas em respostas.yaml (chave: data + valor)."""
    ajustes = ler(cong).get("extrato") or []
    resultado = [dict(l) for l in extrato]
    ajustadas: set[int] = set()
    for n, ajuste in enumerate(ajustes, start=1):
        local = f"respostas.yaml, extrato #{n}"
        if not (ajuste.get("resposta") or ajuste.get("conferencia")) or not ajuste.get("situacao"):
            raise ErroResposta(f"{local}: informe 'situacao' e 'resposta' (ou 'conferencia')")
        data, valor = para_data(ajuste.get("data")), dinheiro(ajuste.get("valor"))
        alvos = [i for i, l in enumerate(resultado) if l.get("data") == data and l.get("valor") is not None
                 and abs(l["valor"]) == abs(valor)
                 and (not ajuste.get("historico") or l.get("historico") == ajuste["historico"])]
        livres = [i for i in alvos if i not in ajustadas]
        # Linhas idênticas (mesmo dia, valor e histórico) são marcadas uma por ajuste.
        identicas = len({(resultado[i].get("historico"), resultado[i]["valor"]) for i in alvos}) == 1
        if not livres or (len(livres) > 1 and not identicas):
            raise ErroResposta(f"{local}: esperava 1 linha do extrato em {data} de {valor}, achei {len(livres)} "
                               "(informe também 'historico')")
        ajustadas.add(livres[0])
        resultado[livres[0]]["situacao"] = f"{ajuste['situacao']} — {registro(ajuste)}"
    return resultado


def _corrigir(lanc: Lancamento, mudanca: dict) -> Lancamento:
    novo = lanc.copia()
    if "valor" in mudanca:
        novo.valor = dinheiro(mudanca["valor"])
    if "status" in mudanca:
        novo.status = normalizar_status(mudanca["status"])
    if "descricao" in mudanca:
        novo.descricao = str(mudanca["descricao"]).strip()
    if "data" in mudanca:
        novo.data = para_data(mudanca["data"])
    if "tipo" in mudanca:
        novo.tipo = normalizar_tipo(mudanca["tipo"])
    if "forma" in mudanca:
        if mudanca["forma"] not in FORMAS:
            raise ValueError(f"forma {mudanca['forma']!r} inválida, use uma de {FORMAS}")
        novo.forma = mudanca["forma"]
    if "mes" in mudanca:
        novo.mes = validar_mes(str(mudanca["mes"]))
    if "comprovante" in mudanca:
        novo.comprovante = str(mudanca["comprovante"])
    base = str(mudanca["observacao"]) if "observacao" in mudanca else lanc.observacao
    novo.observacao = "; ".join(filter(None, [base, registro(mudanca)]))
    return novo


def _novo(n: int, item: dict) -> Lancamento:
    if not isinstance(item, dict) or not (item.get("resposta") or item.get("conferencia")):
        raise ValueError("registre em 'resposta' o que a pessoa respondeu (ou em 'conferencia' a evidência)")
    data = para_data(item.get("data"))
    if data is None:
        raise ValueError("data é obrigatória")
    forma = item.get("forma") or "Não informado"
    if forma not in FORMAS:
        raise ValueError(f"forma {forma!r} inválida, use uma de {FORMAS}")
    descricao = str(item.get("descricao") or "").strip()
    if not descricao:
        raise ValueError("descricao é obrigatória")
    return Lancamento(
        id=f"R{n:04d}", mes=validar_mes(str(item["mes"])) if item.get("mes") else mes_de(data),
        data=data, tipo=normalizar_tipo(item.get("tipo")), descricao=descricao,
        valor=dinheiro(item.get("valor")), forma=forma,
        comprovante=str(item.get("comprovante") or "Resposta da tesouraria"),
        status=normalizar_status(item.get("status", CONFIRMADO)),
        observacao="; ".join(filter(None, [str(item.get("observacao") or ""), registro(item)])))
