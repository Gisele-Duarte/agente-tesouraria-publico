"""Respostas da tesouraria e transcrições das fotos."""
from decimal import Decimal

import pytest

from tesouraria import respostas, transcricoes
from tesouraria.modelo import CONFIRMADO, PENDENTE
from tesouraria.processar import montar_livro
from conftest import escrever


def test_resposta_corrige_remove_e_acrescenta(cong):
    escrever(cong, "respostas.yaml", {
        "base_revisao": 2, "saldo_inicial": 250,
        "lancamentos": {
            "L00007": {"resposta": "Foram R$ 80 no Pix", "valor": 80, "status": "confirmado"},
            "L00008": {"resposta": "Lançado em dobro", "remover": True},
        },
        "novos": [{"resposta": "Teve oferta em dinheiro", "data": "2025-02-10", "tipo": "Entrada",
                   "descricao": "Oferta – culto (dinheiro)", "valor": "50,00", "forma": "Dinheiro"}],
        "perguntas": {"P2": "Foi prebenda"},
    })
    livro = montar_livro(cong)
    por_id = {l.id: l for l in livro.lancamentos}

    assert por_id["L00007"].valor == Decimal("80.00") and por_id["L00007"].status == CONFIRMADO
    assert "Resposta da tesouraria: Foram R$ 80 no Pix" in por_id["L00007"].observacao
    assert "L00008" not in por_id and [l.id for l in livro.removidos] == ["L00008"]
    assert por_id["R0001"].valor == Decimal("50.00")
    assert livro.saldo_inicial == Decimal("250.00")
    assert livro.perguntas_respondidas == {"P2": "Foi prebenda"}
    assert [p.id for p in livro.pendencias] == []  # P1 (saldo) some quando o saldo é informado


def test_novo_removido_sai_do_livro_sem_mudar_o_codigo_dos_seguintes(cong):
    item = {"resposta": "x", "data": "2025-02-10", "tipo": "Entrada", "descricao": "Oferta – culto",
            "valor": 10, "forma": "Dinheiro"}
    escrever(cong, "respostas.yaml", {"base_revisao": 2, "saldo_inicial": 0,
                                      "novos": [{**item, "remover": True}, {**item, "valor": 20}]})
    livro = montar_livro(cong)
    por_id = {l.id: l for l in livro.lancamentos}
    assert "R0001" not in por_id and por_id["R0002"].valor == Decimal("20.00")
    assert [l.id for l in livro.removidos] == ["R0001"]


def test_resposta_sem_texto_ou_com_id_inexistente_e_recusada(cong):
    escrever(cong, "respostas.yaml", {"base_revisao": 2, "lancamentos": {"L00007": {"valor": 80}}})
    with pytest.raises(respostas.ErroResposta, match="resposta"):
        montar_livro(cong)
    escrever(cong, "respostas.yaml", {"base_revisao": 2, "lancamentos": {"L99999": {"resposta": "x", "valor": 1}}})
    with pytest.raises(respostas.ErroResposta, match="não existe"):
        montar_livro(cong)


def test_pendencias_vermelhas_primeiro_e_saldo_em_seguida(cong):
    ids = [p.id for p in montar_livro(cong).pendencias]
    assert ids == ["L00008", "SALDO", "L00007", "P2"]


def test_foto_transcrita_vira_lancamento_e_sai_da_fila(cong):
    escrever(cong, "transcricoes.yaml", {"fotos": {
        "00000010-PHOTO-2025-02-01-10-00-00.jpg": {"situacao": "transcrita", "lancamentos": [
            {"data": "2025-02-01", "tipo": "Entrada", "descricao": "Oferta – culto (dinheiro)",
             "valor": 45, "forma": "Dinheiro", "certeza": "alta"},
            {"data": "2025-02-01", "tipo": "Saída", "descricao": "Lanche – evento", "valor": 12.5,
             "forma": "Dinheiro", "certeza": "baixa"},
        ]},
        "00000011-PHOTO-2025-02-08-10-00-00.jpg": {"situacao": "ilegivel", "observacao": "foto tremida"},
    }})
    livro = montar_livro(cong)
    por_id = {l.id: l for l in livro.lancamentos}

    assert por_id["F0010-1"].status == CONFIRMADO and por_id["F0010-1"].comprovante == "Agenda – foto 0010"
    assert por_id["F0010-2"].status == PENDENTE and "Leitura incerta" in por_id["F0010-2"].observacao
    assert livro.fotos_pendentes == []
    assert "FOTO-0011" in [p.id for p in livro.pendencias]
    usos = {c["arquivo"]: c["uso"] for c in livro.comprovantes}
    assert usos["00000010-PHOTO-2025-02-01-10-00-00.jpg"] == "Transcrita (agenda)"


def test_transcricao_invalida_explica_onde_esta_o_erro(cong):
    escrever(cong, "transcricoes.yaml", {"fotos": {"x.jpg": {"situacao": "transcrita", "lancamentos": [
        {"data": "2025-02-01", "tipo": "Entrada", "descricao": "Oferta", "valor": 1, "forma": "Cheque"}]}}})
    with pytest.raises(transcricoes.ErroTranscricao, match="x.jpg, lançamento 1: forma"):
        montar_livro(cong)


def test_exemplo_de_transcricoes_do_repositorio_e_valido(cong):
    import shutil
    from pathlib import Path
    exemplo = Path(__file__).resolve().parents[1] / "congregacoes" / "exemplo" / "transcricoes.yaml"
    shutil.copy(exemplo, cong.arquivo_transcricoes)
    gerados = transcricoes.lancamentos(cong)
    assert [l.status for l in gerados] == [CONFIRMADO, PENDENTE]
    assert len(transcricoes.fotos_ilegiveis(cong)) == 1


def test_conferencia_tecnica_e_situacao_de_linha_do_extrato(cong):
    from datetime import date
    cong.salvar_extrato([{"data": date(2025, 1, 5), "historico": "PIX RECEBIDO 111", "valor": Decimal("1000.00"),
                          "situacao": "Conciliado", "arquivo": "x"}])
    escrever(cong, "respostas.yaml", {
        "base_revisao": 2, "lancamentos": {"L00006": {"conferencia": "repete o L00005 no extrato", "remover": True}},
        "extrato": [{"data": "2025-01-05", "valor": 1000, "situacao": "Repasse da maquininha",
                     "resposta": "somente saldo"}],
    })
    livro = montar_livro(cong)
    assert [l.id for l in livro.removidos] == ["L00006"]
    assert livro.extrato[0]["situacao"] == "Repasse da maquininha — Resposta da tesouraria: somente saldo"
    escrever(cong, "respostas.yaml", {"extrato": [{"data": "2025-01-06", "valor": 1000, "situacao": "x",
                                                   "resposta": "y"}]})
    with pytest.raises(respostas.ErroResposta, match="achei 0"):
        montar_livro(cong)


def test_respostas_de_outra_revisao_sao_recusadas(cong):
    escrever(cong, "respostas.yaml", {"base_revisao": 3, "lancamentos": {"L00007": {"resposta": "x", "valor": 1}}})
    with pytest.raises(respostas.ErroResposta, match="REV03"):
        montar_livro(cong)
    escrever(cong, "respostas.yaml", {"lancamentos": {"L00007": {"resposta": "x", "valor": 1}}})
    with pytest.raises(respostas.ErroResposta, match="base_revisao"):
        montar_livro(cong)


def test_resposta_em_lote_respeita_as_respostas_individuais(cong):
    from tesouraria.modelo import ENTRADA
    from conftest import lanc
    cong.salvar_lancamentos(cong.lancamentos() + [
        lanc("L00011", "2025-02", 6, ENTRADA, "Entrada Pix – a identificar (CPF final 8777)", 211, PENDENTE),
        lanc("L00012", "2025-02", 7, ENTRADA, "Entrada Pix – provável Pr. Teste (dízimo/oferta a confirmar)", 50, PENDENTE),
        lanc("L00013", "2025-02", 8, ENTRADA, "Entrada Pix – a identificar (CPF final 1111)", 10, PENDENTE),
    ])
    escrever(cong, "respostas.yaml", {
        "base_revisao": 2,
        "lancamentos": {"L00011": {"resposta": "é do Beltrano", "descricao": "Dízimo – Beltrano", "status": "confirmado"}},
        "em_lote": [{"resposta": "marcar 🟢 como não identificado", "status": "confirmado",
                     "descricao_comeca": ["Entrada Pix – a identificar", "Entrada Pix – provável"],
                     "nova_descricao": "Entrada Pix – oferta/dízimo não identificado ({resto})"}],
    })
    por_id = {l.id: l for l in montar_livro(cong).lancamentos}
    assert por_id["L00011"].descricao == "Dízimo – Beltrano"
    assert por_id["L00012"].descricao == "Entrada Pix – oferta/dízimo não identificado (provável Pr. Teste)"
    assert por_id["L00013"].descricao == "Entrada Pix – oferta/dízimo não identificado (CPF final 1111)"
    assert por_id["L00013"].status == CONFIRMADO and "não identificado" in por_id["L00013"].observacao
