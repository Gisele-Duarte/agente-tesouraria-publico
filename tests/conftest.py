"""Congregação fictícia para os testes. Nenhum dado real entra no repositório."""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tesouraria.dados import Congregacao, gravar_yaml  # noqa: E402
from tesouraria.modelo import CONFIRMADO, DIVERGENCIA, ENTRADA, PENDENTE, SAIDA, Lancamento  # noqa: E402


def lanc(id_, mes, dia, tipo, descricao, valor, status=CONFIRMADO, comprovante="Livro caixa – pág. 1"):
    ano, m = (int(x) for x in mes.split("-"))
    return Lancamento(id=id_, mes=mes, data=date(ano, m, dia), tipo=tipo, descricao=descricao,
                      valor=None if valor is None else Decimal(str(valor)), forma="Pix",
                      comprovante=comprovante, status=status)


LANCAMENTOS = [
    lanc("L00001", "2025-01", 5, ENTRADA, "Dízimo – Fulano", 1000),
    lanc("L00002", "2025-01", 6, ENTRADA, "Oferta – culto (Pix)", 500),
    lanc("L00003", "2025-01", 7, SAIDA, "Luz – conta de janeiro", 200),
    lanc("L00004", "2025-01", 8, SAIDA, "Prebenda – Pr. Teste", 100),
    lanc("L00005", "2025-01", 9, SAIDA, "Transferência interna – banco para caixa", 300),
    lanc("L00006", "2025-01", 9, ENTRADA, "Transferência interna – caixa recebe", 300),
    lanc("L00007", "2025-02", 2, ENTRADA, "Oferta – culto (Pix)", None, PENDENTE),
    lanc("L00008", "2025-02", 3, ENTRADA, "Dízimo – Beltrano", 400, DIVERGENCIA),
    lanc("L00009", "2025-02", 4, SAIDA, "Repasse Sede – janeiro", 300),
    lanc("L00010", "2025-02", 5, SAIDA, "Água", 50),
]


@pytest.fixture
def cong(tmp_path) -> Congregacao:
    c = Congregacao(tmp_path / "igreja_teste")
    c.criar_pastas()
    c.salvar_config({"nome": "Igreja Teste", "regras": {"repasse_sede": 0.2, "prebenda": 0.2},
                     "saldo_inicial": None, "revisao_base": 2})
    c.salvar_lancamentos(LANCAMENTOS)
    c.salvar_notas({"titulo": "LIVRO CAIXA – Igreja Teste", "meses": {"2025-01": "Fonte: teste"},
                    "livro_totais": {"2025-01": {"entradas": 1500, "saidas": 200, "observacao": "ok"}},
                    "perguntas": {"P1": {"titulo": "Saldo inicial", "texto": "Qual era?"},
                                  "P2": {"titulo": "Pix de R$ 500", "texto": "Prebenda ou despesa?"}},
                    "avisos": [{"secao": "1. EXTRATOS", "titulo": "Jan/2025", "texto": "Sem extrato"}]})
    c.salvar_comprovantes([
        {"data": date(2025, 2, 1), "enviado_por": "Pastor", "tipo": "Manuscrito/foto (ler)",
         "arquivo": "00000010-PHOTO-2025-02-01-10-00-00.jpg", "uso": "Pendente – Etapa 3", "mensagem": "entradas"},
        {"data": date(2025, 2, 8), "enviado_por": "Pastor", "tipo": "Manuscrito/foto (ler)",
         "arquivo": "00000011-PHOTO-2025-02-08-10-00-00.jpg", "uso": "Pendente – Etapa 3"},
        {"data": date(2025, 2, 9), "enviado_por": "Tesoureira", "tipo": "Comprovante Pix (outro)",
         "arquivo": "00000012-doc.pdf", "uso": "Conciliado com o livro", "valor": Decimal("400")},
    ])
    return c


def escrever(cong: Congregacao, arquivo: str, conteudo: dict) -> None:
    gravar_yaml(cong.pasta / arquivo, conteudo)
