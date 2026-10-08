"""Fotos manuscritas (agenda do pastor) já lidas → lançamentos.

Formato de transcricoes.yaml:

    fotos:
      00000001-PHOTO-2025-01-05-20-00-00.jpg:
        situacao: transcrita        # transcrita | ilegivel | sem_lancamento | ja_lancada
        observacao: "Página de 16/07 e 19/07"
        lancamentos:
          - data: 2025-07-16
            tipo: Entrada
            descricao: "Oferta – culto (dinheiro)"
            valor: 45.00
            forma: Dinheiro
            certeza: alta           # alta → 🟢 ; baixa → 🟡 (leitura incerta)
            observacao: ""

- ilegivel: nada vira lançamento; a foto entra nas pendências para alguém conferir.
- sem_lancamento: a foto não tem movimento de dinheiro (aviso, foto de evento…).
- ja_lancada: o conteúdo já está na planilha (ex.: mesmo dia do livro caixa).
"""
from __future__ import annotations

import re

from .dados import Congregacao, ler_yaml, USO_PENDENTE_FOTO
from .modelo import (CONFIRMADO, PENDENTE, FORMAS, Lancamento, dinheiro, para_data, normalizar_tipo,
                     mes_de)

SITUACOES = ("transcrita", "ilegivel", "sem_lancamento", "ja_lancada")


class ErroTranscricao(ValueError):
    pass


def ler(cong: Congregacao) -> dict[str, dict]:
    fotos = ler_yaml(cong.arquivo_transcricoes).get("fotos") or {}
    for arquivo, foto in fotos.items():
        if not isinstance(foto, dict) or foto.get("situacao") not in SITUACOES:
            raise ErroTranscricao(f"transcricoes.yaml, foto {arquivo}: situacao deve ser uma de {SITUACOES}")
    return fotos


def id_da_foto(arquivo: str) -> str:
    """'00000298-PHOTO-…jpg' → '0298'; outros nomes → nome sem extensão."""
    achado = re.match(r"0*(\d+)-", arquivo)
    return achado.group(1).zfill(4) if achado else arquivo.rsplit(".", 1)[0]


def lancamentos(cong: Congregacao) -> list[Lancamento]:
    gerados: list[Lancamento] = []
    for arquivo, foto in ler(cong).items():
        if foto["situacao"] != "transcrita":
            continue
        itens = foto.get("lancamentos") or []
        if not itens:
            raise ErroTranscricao(f"foto {arquivo}: situacao 'transcrita' sem nenhum lançamento")
        for n, item in enumerate(itens, start=1):
            local = f"transcricoes.yaml, foto {arquivo}, lançamento {n}"
            try:
                data = para_data(item.get("data"))
                if data is None:
                    raise ValueError("data é obrigatória")
                forma = item.get("forma") or "Não informado"
                if forma not in FORMAS:
                    raise ValueError(f"forma {forma!r} inválida, use uma de {FORMAS}")
                certeza = item.get("certeza", "alta")
                if certeza not in ("alta", "baixa"):
                    raise ValueError("certeza deve ser 'alta' ou 'baixa'")
                observacao = str(item.get("observacao") or "")
                if certeza == "baixa":
                    observacao = "; ".join(filter(None, ["Leitura incerta da foto", observacao]))
                gerados.append(Lancamento(
                    id=f"F{id_da_foto(arquivo)}-{n}", mes=mes_de(data), data=data,
                    tipo=normalizar_tipo(item.get("tipo")),
                    descricao=str(item.get("descricao") or "").strip(),
                    valor=dinheiro(item.get("valor")), forma=forma,
                    comprovante=f"Agenda – foto {id_da_foto(arquivo)}",
                    status=CONFIRMADO if certeza == "alta" else PENDENTE,
                    observacao=observacao))
            except ValueError as erro:
                raise ErroTranscricao(f"{local}: {erro}") from erro
            if not gerados[-1].descricao:
                raise ErroTranscricao(f"{local}: descricao é obrigatória")
    return gerados


def fotos_pendentes(cong: Congregacao, comprovantes: list[dict] | None = None) -> list[dict]:
    """Fotos do índice do WhatsApp marcadas para leitura e ainda sem transcrição."""
    lidas = ler(cong)
    comprovantes = cong.comprovantes() if comprovantes is None else comprovantes
    return [c for c in comprovantes if c.get("uso") == USO_PENDENTE_FOTO and c["arquivo"] not in lidas]


def fotos_ilegiveis(cong: Congregacao) -> dict[str, dict]:
    return {a: f for a, f in ler(cong).items() if f["situacao"] == "ilegivel"}


USO_POR_SITUACAO = {
    "transcrita": "Transcrita (agenda)",
    "ilegivel": "Ilegível – conferir",
    "sem_lancamento": "Lida – sem movimento",
    "ja_lancada": "Lida – já estava na planilha",
}


def atualizar_uso(comprovantes: list[dict], fotos: dict[str, dict]) -> list[dict]:
    """Cópia do índice com a coluna 'uso' refletindo as fotos já lidas."""
    return [{**c, "uso": USO_POR_SITUACAO[fotos[c["arquivo"]]["situacao"]]}
            if c.get("arquivo") in fotos else c for c in comprovantes]
