"""Tudo o que falta para fechar a tesouraria, na ordem em que deve ser perguntado."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .modelo import DIVERGENCIA, PENDENTE, Lancamento, nome_mes_extenso, reais
from .transcricoes import id_da_foto


@dataclass
class Pendencia:
    id: str            # L00123, F0298-1, P2, FOTO-0298, SALDO
    cor: str           # 🔴 | 🟡
    mes: str           # "2025-06" ou "" quando não é de um mês
    titulo: str
    detalhe: str


def montar(lancamentos: list[Lancamento], perguntas: dict, respondidas: dict, ilegiveis: dict,
           saldo_inicial_informado: bool) -> list[Pendencia]:
    """🔴 primeiro, depois 🟡; dentro de cada cor, por mês."""
    lista: list[Pendencia] = []
    if not saldo_inicial_informado:
        lista.append(Pendencia("SALDO", "🟡", "", "Saldo inicial",
                               "Qual era o saldo (banco + espécie) antes do primeiro lançamento?"))
    for lanc in sorted(lancamentos, key=lambda l: (l.mes, l.data or l.mes, l.id)):
        if lanc.status in (DIVERGENCIA, PENDENTE):
            lista.append(Pendencia(lanc.id, lanc.status[0], lanc.mes, _titulo(lanc), lanc.observacao))
    for id_, pergunta in perguntas.items():
        if id_ not in respondidas:
            lista.append(Pendencia(id_, "🟡", "", pergunta["titulo"], pergunta["texto"]))
    for arquivo, foto in ilegiveis.items():
        lista.append(Pendencia(f"FOTO-{id_da_foto(arquivo)}", "🟡", "", f"Foto ilegível {arquivo}",
                               foto.get("observacao") or "Não foi possível ler a foto."))
    return sorted(lista, key=lambda p: (p.cor != "🔴", p.id != "SALDO", p.mes == "", p.mes))


def _titulo(lanc: Lancamento) -> str:
    data = lanc.data.strftime("%d/%m/%Y") if lanc.data else "sem data"
    return f"{data} · {lanc.tipo} · {lanc.descricao} · {reais(lanc.valor)}"


def fotos_por_mes(fotos: list[dict]) -> dict[str, list[str]]:
    grupos: dict[str, list[str]] = defaultdict(list)
    for foto in fotos:
        mes = foto["data"].strftime("%Y-%m") if foto.get("data") else "sem data"
        grupos[mes].append(id_da_foto(foto["arquivo"]))
    return dict(sorted(grupos.items()))


def texto_fotos_por_mes(fotos: list[dict]) -> list[tuple[str, str]]:
    return [(nome_mes_extenso(m) if m != "sem data" else m, f"{len(ids)} foto(s): {', '.join(ids)}")
            for m, ids in fotos_por_mes(fotos).items()]
