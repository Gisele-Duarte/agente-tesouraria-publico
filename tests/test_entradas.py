"""Leitura dos ZIPs do WhatsApp e do texto dos extratos."""
import zipfile
from datetime import date
from decimal import Decimal

from tesouraria import extrato, whatsapp
from conftest import LANCAMENTOS

CHAT_IPHONE = (
    "[01/02/2025, 10:00:00] Pastor: ‎<anexado: 00000010-PHOTO-2025-02-01-10-00-00.jpg>\n"
    "[01/03/2025, 09:15:30] Pastor: Segue as entradas do dia\n"
    "[01/03/2025, 09:16:00] Pastor: ‎<anexado: 00000099-PHOTO-2025-03-01-09-16-00.jpg>\n"
    "legenda na linha de baixo\n"
)
CHAT_ANDROID = "05/03/2025 20:01 - Tesoureira: IMG-20250305-WA0001.jpg (arquivo anexado)\nOferta\n"


def _zip(pasta, nome, chat, fotos):
    with zipfile.ZipFile(pasta / nome, "w") as zf:
        zf.writestr("_chat.txt", chat)
        for foto in fotos:
            zf.writestr(foto, b"jpg")


def test_anexos_iphone_e_android(tmp_path):
    _zip(tmp_path, "a.zip", CHAT_IPHONE, [])
    _zip(tmp_path, "b.zip", CHAT_ANDROID, [])
    iphone = whatsapp.anexos(tmp_path / "a.zip")
    android = whatsapp.anexos(tmp_path / "b.zip")
    assert [a["arquivo"] for a in iphone] == ["00000010-PHOTO-2025-02-01-10-00-00.jpg",
                                              "00000099-PHOTO-2025-03-01-09-16-00.jpg"]
    assert iphone[1]["mensagem"] == "legenda na linha de baixo" and iphone[1]["data"] == date(2025, 3, 1)
    assert {k: v for k, v in android[0].items() if k != "quando"} == {
        "data": date(2025, 3, 5), "enviado_por": "Tesoureira", "arquivo": "IMG-20250305-WA0001.jpg",
        "mensagem": "Oferta", "zip": "b.zip"}


def test_sincronizar_acrescenta_so_o_novo_e_extrai_fotos(cong):
    _zip(cong.entrada("whatsapp"), "1_gestao_contas.zip", CHAT_IPHONE,
         ["00000010-PHOTO-2025-02-01-10-00-00.jpg", "00000099-PHOTO-2025-03-01-09-16-00.jpg"])
    resultado = whatsapp.sincronizar(cong)
    assert resultado["novos"] == 1
    novo = next(c for c in cong.comprovantes() if c["arquivo"].startswith("00000099"))
    assert novo["uso"] == "Pendente – Etapa 3" and novo["zip"] == "1_gestao_contas.zip"

    caminhos, faltando = whatsapp.extrair(cong, ["00000010-PHOTO-2025-02-01-10-00-00.jpg", "nao-existe.jpg"])
    assert list(caminhos) == ["00000010-PHOTO-2025-02-01-10-00-00.jpg"]
    assert faltando == ["nao-existe.jpg"]
    assert caminhos["00000010-PHOTO-2025-02-01-10-00-00.jpg"].read_bytes() == b"jpg"


# Mesmo grupo exportado no Android: o índice (feito com a exportação do iPhone) tem outros nomes.
CHAT_ANDROID_DO_INDICE = (
    "01/02/2025 10:00 - Pastor: ‎IMG-20250201-WA0000.jpg (arquivo anexado)\n"
    "08/02/2025 10:00 - Pastor: ‎IMG-20250208-WA0000.jpg (arquivo anexado)\n"
    "09/02/2025 11:00 - Tesoureira: ‎doc.pdf (arquivo anexado)\n"
    "09/02/2025 11:01 - Tesoureira: ‎STK-20250209-WA0000.webp (arquivo anexado)\n"
    "10/02/2025 12:00 - Tesoureira: ‎IMG-20250210-WA0000.jpg (arquivo anexado)\n"
)


def test_indice_do_iphone_casa_com_zip_do_android_pelo_horario(cong):
    _zip(cong.entrada("whatsapp"), "1_gestao_contas.zip", CHAT_ANDROID_DO_INDICE,
         ["IMG-20250201-WA0000.jpg", "IMG-20250208-WA0000.jpg", "doc.pdf", "IMG-20250210-WA0000.jpg"])
    resultado = whatsapp.sincronizar(cong)
    no_zip = {c["arquivo"]: c.get("arquivo_zip") for c in cong.comprovantes()}
    assert no_zip["00000010-PHOTO-2025-02-01-10-00-00.jpg"] == "IMG-20250201-WA0000.jpg"
    assert no_zip["00000011-PHOTO-2025-02-08-10-00-00.jpg"] == "IMG-20250208-WA0000.jpg"
    assert no_zip["00000012-doc.pdf"] == "doc.pdf"
    assert resultado == {"zips": ["1_gestao_contas.zip"], "novos": 1, "casados": 3, "total": 4}  # figurinha fora
    caminhos, faltando = whatsapp.extrair(cong, ["00000011-PHOTO-2025-02-08-10-00-00.jpg"])
    assert caminhos["00000011-PHOTO-2025-02-08-10-00-00.jpg"].name == "IMG-20250208-WA0000.jpg" and not faltando


# Formato real do "Extrato Consolidado Inteligente" no modo raw (nomes e valores fictícios).
TEXTO_CONSOLIDADO = """EXTRATO CONSOLIDADO INTELIGENTE
fevereiro/2025
Resumo - fevereiro/2025
(+) Total de Créditos 1.600,00
(-) Total de Débitos 1.600,00
Movimentação
Data Descrição Nº Documento Movimentos (R$) Saldo (R$)
Créditos Débitos
SALDO EM 31/01 0,00
07/02 PIX RECEBIDO 11122233344 - 1.000,00
PIX RECEBIDO 55566677788 004855 300,00
APLICACAO CONTAMAX - 1.300,00- 0,00
EXTRATO CONSOLIDADO INTELIGENTE
fevereiro/2025
Pagina: 3/7
Data Descrição Nº Documento Movimentos (R$) Saldo (R$)
08/02 PIX ENVIADO
Fulano de Tal
- 200,00-
TARIFA MENSALIDADE PACOTE SERVICOS
JANEIRO / 2025
- 100,00-
RESGATE CONTAMAX AUTOMATICO - 300,00 0,00
Movimentação Mensal
"""

TEXTO_APLICATIVO = """Aplicativo Santander Empresas
Períodos: 01/09/2026 a 30/09/2026 Data/Hora: 01/10/2026 as 11h43
Data Histórico Documento Valor (R$) Saldo (R$)
30/09/2026 Pix Recebido 11122233344 10,00 1.077,26
28/09/2026
Pix Enviado MERCADO PAGO
INSTITUICAO
-22,74 1.067,26
1/4
02/09/2026 Pix Recebido 55566677788 90,00 1.090,00
"""


def test_extrato_consolidado_soma_bate_com_o_resumo_e_ignora_contamax():
    lido = extrato.ler_texto(TEXTO_CONSOLIDADO, "teste")
    assert lido.confere and lido.mes == "2025-02"
    assert [(l["data"], l["historico"], l["valor"]) for l in lido.linhas] == [
        (date(2025, 2, 7), "PIX RECEBIDO 11122233344", Decimal("1000.00")),
        (date(2025, 2, 7), "PIX RECEBIDO 55566677788", Decimal("300.00")),
        (date(2025, 2, 8), "PIX ENVIADO Fulano de Tal", Decimal("-200.00")),
        (date(2025, 2, 8), "TARIFA MENSALIDADE PACOTE SERVICOS JANEIRO / 2025", Decimal("-100.00")),
    ]


def test_extrato_consolidado_com_total_errado_e_recusado():
    lido = extrato.ler_texto(TEXTO_CONSOLIDADO.replace("Créditos 1.600,00", "Créditos 1.700,00"), "teste")
    assert not lido.confere


def test_extrato_do_aplicativo_valida_a_corrente_de_saldos():
    lido = extrato.ler_texto(TEXTO_APLICATIVO, "app")
    assert lido.confere and lido.mes == "2026-09"
    assert [(l["data"], l["historico"], l["valor"]) for l in lido.linhas] == [
        (date(2026, 9, 2), "Pix Recebido 55566677788", Decimal("90.00")),
        (date(2026, 9, 28), "Pix Enviado MERCADO PAGO INSTITUICAO", Decimal("-22.74")),
        (date(2026, 9, 30), "Pix Recebido 11122233344", Decimal("10.00")),
    ]
    assert not extrato.ler_texto(TEXTO_APLICATIVO.replace("1.067,26", "1.067,00"), "app").confere


def test_conciliacao_acha_lancamento_de_mesmo_valor_ate_3_dias():
    usados = set()
    entrada = {"data": date(2025, 1, 7), "valor": Decimal("1000.00")}
    assert extrato.conciliar(entrada, LANCAMENTOS, usados) == extrato.SITUACAO_AUTOMATICA
    assert extrato.conciliar(entrada, LANCAMENTOS, usados) == extrato.SITUACAO_NAO_LANCADO  # já usado
    saida = {"data": date(2025, 1, 20), "valor": Decimal("-200.00")}
    assert extrato.conciliar(saida, LANCAMENTOS, usados) == extrato.SITUACAO_NAO_LANCADO   # 13 dias


def test_releitura_recalcula_situacao_automatica_e_preserva_a_decidida(cong, monkeypatch):
    linhas = [{"data": date(2025, 2, 3), "historico": "PIX RECEBIDO 1", "valor": Decimal("400.00"),
               "arquivo": "Extrato x"},
              {"data": date(2025, 2, 5), "historico": "TARIFA", "valor": Decimal("-50.00"), "arquivo": "Extrato x"}]
    cong.salvar_extrato([{**linhas[0], "situacao": extrato.SITUACAO_NAO_LANCADO},
                         {**linhas[1], "situacao": "Decidido na REV03"}])
    (cong.entrada("extratos") / "Fev 2025.pdf").write_bytes(b"%PDF")
    lido = extrato.ExtratoLido("Fev 2025", "2025-02", linhas, Decimal("400"), Decimal("50"),
                               Decimal("400"), Decimal("50"))
    monkeypatch.setattr(extrato, "texto_do_pdf", lambda c, p: "")
    monkeypatch.setattr(extrato, "ler_texto", lambda t, a: lido)
    extrato.sincronizar(cong, cong.lancamentos())
    situacoes = [l["situacao"] for l in cong.extrato()]
    assert situacoes == [extrato.SITUACAO_AUTOMATICA, "Decidido na REV03"]   # L00008 = 400 em 03/02
