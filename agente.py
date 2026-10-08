"""Agente de Tesouraria — linha de comando.

    python agente.py importar-planilha congregacoes/minha_congregacao "C:/…/Livro_Caixa_REV04.xlsx"
    python agente.py executar         congregacoes/minha_congregacao     # rascunho + relatório
    python agente.py fotos            congregacoes/minha_congregacao --proximas 10 --extrair
    python agente.py buscar           congregacoes/minha_congregacao --mes 2025-07 --valor 45
    python agente.py pendencias       congregacoes/minha_congregacao
    python agente.py gerar-revisao    congregacoes/minha_congregacao     # nova REVnn em saida/
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from tesouraria import extrato, incorporar, planilha
from tesouraria.dados import Congregacao
from tesouraria.importar_planilha import ErroImportacao, importar
from tesouraria.modelo import dinheiro, nome_mes_extenso, reais
from tesouraria.processar import montar_livro, proxima_revisao, sincronizar_entradas
from tesouraria.respostas import ErroResposta
from tesouraria.transcricoes import ErroTranscricao, id_da_foto
from tesouraria.whatsapp import extrair

ERROS_DE_DADOS = (ErroImportacao, ErroResposta, ErroTranscricao, extrato.ErroExtrato, ValueError)


def _congregacao(caminho: str, precisa_dados: bool = True) -> Congregacao:
    cong = Congregacao(Path(caminho).resolve())
    if precisa_dados and not cong.dados("lancamentos.csv").exists():
        sys.exit(f"{cong.pasta}: ainda não há dados. Rode primeiro: python agente.py importar-planilha "
                 f"{caminho} <planilha.xlsx>")
    return cong


def cmd_importar(args) -> None:
    cong = _congregacao(args.pasta, precisa_dados=False)
    resultado = importar(cong, Path(args.planilha), substituir=args.substituir)
    print(f"Importados {resultado['lancamentos']} lançamentos de {resultado['meses']} meses "
          f"(base: REV{resultado['revisao_base']:02d}).")
    for aviso in resultado["avisos"]:
        print(f"  aviso: {aviso}")


def cmd_executar(args) -> None:
    cong = _congregacao(args.pasta)
    entradas = sincronizar_entradas(cong)
    livro = montar_livro(cong)
    destino = planilha.gerar(livro, cong.pasta / "rascunho" / "Livro_Caixa_RASCUNHO.xlsx")

    zips = entradas["whatsapp"]["zips"]
    print(f"== {livro.nome}")
    print(f"Livro caixa: {len(livro.meses)} meses ({nome_mes_extenso(livro.meses[0])} a "
          f"{nome_mes_extenso(livro.meses[-1])}), {len(livro.lancamentos)} lançamentos.")
    meses_extrato = extrato.meses_cobertos(livro.extrato)
    print(f"Extratos: {len(meses_extrato)} meses com movimento no extrato "
          f"({', '.join(nome_mes_extenso(m) for m in meses_extrato) or 'nenhum'}).")
    sem_extrato = [m for m in livro.meses if m not in meses_extrato]
    if sem_extrato:
        print(f"  sem nenhum movimento no extrato: {', '.join(nome_mes_extenso(m) for m in sem_extrato)}")
    lidos = entradas["extratos"]
    if lidos["pdfs"]:
        print(f"  PDFs oficiais conferidos com os totais do banco: {len(lidos['meses'])} de {len(lidos['pdfs'])}")
    for pdf, motivo in lidos["recusados"].items():
        print(f"  PDF RECUSADO {pdf}: {motivo} (texto em cache/extratos_texto/)")
    situacoes = Counter(l.get("situacao") for l in livro.extrato)
    for situacao in (extrato.SITUACAO_NAO_LANCADO, extrato.SITUACAO_FORA_DO_OFICIAL):
        if situacoes[situacao]:
            print(f"  {situacoes[situacao]} linha(s) de extrato \"{situacao}\"")
    print(f"WhatsApp: {len(zips)} ZIP(s) em entrada/whatsapp"
          + (f", {entradas['whatsapp']['casados']} itens do índice ligados ao ZIP agora,"
             f" {entradas['whatsapp']['novos']} anexos novos." if zips else
             " — sem ZIPs, as fotos pendentes não podem ser abertas."))
    print(f"Fotos manuscritas pendentes: {len(livro.fotos_pendentes)}")
    vermelhas = sum(p.cor == "🔴" for p in livro.pendencias)
    print(f"Pendências: {vermelhas} 🔴 e {len(livro.pendencias) - vermelhas} 🟡")
    if livro.removidos:
        print(f"Removidos por resposta: {len(livro.removidos)}")
    if livro.saldo_inicial is None:
        print("Saldo inicial: NÃO INFORMADO (a planilha usa R$ 0,00 até ser respondido)")
    else:
        print(f"Saldo inicial: {reais(livro.saldo_inicial)}")
    ultimo = livro.resumos[-1]
    print(f"Saldo total em {nome_mes_extenso(ultimo.mes)}: {reais(ultimo.saldo_total)} · prebenda a pagar "
          f"{reais(ultimo.prebenda_a_pagar)} · sede a repassar {reais(ultimo.sede_a_repassar)}")
    print(f"Rascunho: {destino}")


def cmd_resumo(args) -> None:
    livro = montar_livro(_congregacao(args.pasta))
    print(f"{'Mês':<16}{'Entradas':>14}{'Despesas':>14}{'Saldo mês':>14}{'SALDO TOTAL':>14}  🟢/🟡/🔴")
    for r in livro.resumos:
        print(f"{nome_mes_extenso(r.mes):<16}{r.entradas:>14,.2f}{r.despesas:>14,.2f}{r.saldo_mes:>14,.2f}"
              f"{r.saldo_total:>14,.2f}  {r.confirmados}/{r.pendentes}/{r.divergencias}")


def cmd_pendencias(args) -> None:
    livro = montar_livro(_congregacao(args.pasta))
    if args.json:
        print(json.dumps([p.__dict__ for p in livro.pendencias], ensure_ascii=False, indent=1))
        return
    for n, p in enumerate(livro.pendencias, start=1):
        print(f"{n:>3}. {p.cor} [{p.id}] {p.titulo}")
        if p.detalhe:
            print(f"       {p.detalhe}")
    print(f"\nFotos da agenda ainda não lidas: {len(livro.fotos_pendentes)}")
    for mes, texto in livro.fotos_pendentes_por_mes:
        print(f"  {mes}: {texto}")


def cmd_fotos(args) -> None:
    cong = _congregacao(args.pasta)
    livro = montar_livro(cong)
    fila = livro.fotos_pendentes[: args.proximas] if args.proximas else livro.fotos_pendentes
    por_nome, faltando = extrair(cong, [f["arquivo"] for f in fila]) if args.extrair else ({}, [])
    print(f"{len(livro.fotos_pendentes)} fotos pendentes; mostrando {len(fila)}.")
    for foto in fila:
        data = foto["data"].strftime("%d/%m/%Y") if foto.get("data") else "sem data"
        legenda = " ".join(str(foto.get("mensagem") or "").split())
        print(f"- {id_da_foto(foto['arquivo'])} · {data} · {foto.get('enviado_por', '')} · {foto['arquivo']}")
        if legenda:
            print(f"    legenda: {legenda}")
        if foto["arquivo"] in por_nome:
            print(f"    arquivo: {por_nome[foto['arquivo']]}")
    if faltando:
        print(f"\nNão encontradas nos ZIPs de entrada/whatsapp: {len(faltando)} "
              f"({', '.join(id_da_foto(a) for a in faltando[:10])}{'…' if len(faltando) > 10 else ''})")


def cmd_buscar(args) -> None:
    livro = montar_livro(_congregacao(args.pasta))
    valor = dinheiro(args.valor) if args.valor else None
    achados = [l for l in livro.lancamentos
               if (not args.mes or l.mes == args.mes)
               and (valor is None or (l.valor is not None and abs(l.valor - valor) <= Decimal(args.tolerancia)))
               and (not args.texto or args.texto.casefold() in f"{l.descricao} {l.observacao}".casefold())]
    for l in achados:
        data = l.data.strftime("%d/%m/%Y") if l.data else "sem data"
        print(f"[{l.id}] {data} {l.tipo:<7} {reais(l.valor):>13}  {l.status[0]} {l.descricao}  ({l.comprovante})")
    print(f"{len(achados)} lançamento(s).")


def cmd_incorporar_extrato(args) -> None:
    cong = _congregacao(args.pasta)
    sincronizar_entradas(cong)
    livro = montar_livro(cong)
    novos = incorporar.propor(cong, livro.extrato, livro.lancamentos, args.mes)
    for l in novos:
        print(f"[{l.id}] {l.data:%d/%m/%Y} {l.tipo:<7} {reais(l.valor):>13}  {l.status[0]} {l.descricao}")
    entradas = sum(l.valor for l in novos if l.tipo == "Entrada")
    saidas = sum(l.valor for l in novos if l.tipo == "Saída")
    print(f"{len(novos)} movimento(s) de {args.mes}: entradas {reais(Decimal(entradas))}, "
          f"saídas {reais(Decimal(saidas))}.")
    if novos and args.gravar:
        incorporar.gravar(cong, novos)
        print("Gravado em dados/lancamentos.csv (versão anterior em cache/).")
    elif novos:
        print("Prévia: nada foi gravado. Para gravar, repita com --gravar.")


def cmd_gerar_revisao(args) -> None:
    cong = _congregacao(args.pasta)
    sincronizar_entradas(cong)
    livro = montar_livro(cong)
    destino = proxima_revisao(cong)
    planilha.gerar(livro, destino)
    vermelhas = sum(p.cor == "🔴" for p in livro.pendencias)
    print(f"Revisão gerada: {destino}")
    print(f"Ainda abertas: {vermelhas} 🔴, {len(livro.pendencias) - vermelhas} 🟡, "
          f"{len(livro.fotos_pendentes)} fotos sem leitura.")


def main(argv=None) -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")  # emojis no terminal do Windows
    parser = argparse.ArgumentParser(description="Agente de Tesouraria")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("importar-planilha", help="usa uma revisão da planilha como base de dados")
    p.add_argument("pasta"), p.add_argument("planilha")
    p.add_argument("--substituir", action="store_true", help="troca os dados atuais (backup em cache/)")
    p.set_defaults(func=cmd_importar)

    for nome, func, ajuda in (("executar", cmd_executar, "lê entradas novas, gera rascunho e relatório"),
                              ("resumo", cmd_resumo, "saldo mês a mês"),
                              ("gerar-revisao", cmd_gerar_revisao, "grava a próxima REVnn em saida/")):
        p = sub.add_parser(nome, help=ajuda)
        p.add_argument("pasta")
        p.set_defaults(func=func)

    p = sub.add_parser("pendencias", help="lista 🔴 e 🟡 com o código de cada uma")
    p.add_argument("pasta"), p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pendencias)

    p = sub.add_parser("fotos", help="fotos da agenda ainda não lidas")
    p.add_argument("pasta")
    p.add_argument("--proximas", type=int, default=0, help="mostra só as N próximas")
    p.add_argument("--extrair", action="store_true", help="copia as fotos dos ZIPs para cache/fotos/")
    p.set_defaults(func=cmd_fotos)

    p = sub.add_parser("incorporar-extrato", help="lança os movimentos do extrato que ainda não têm lançamento")
    p.add_argument("pasta"), p.add_argument("--mes", required=True, help="AAAA-MM")
    p.add_argument("--gravar", action="store_true", help="sem isto, só mostra a prévia")
    p.set_defaults(func=cmd_incorporar_extrato)

    p = sub.add_parser("buscar", help="procura lançamentos (para não lançar em dobro)")
    p.add_argument("pasta")
    p.add_argument("--mes"), p.add_argument("--valor"), p.add_argument("--texto")
    p.add_argument("--tolerancia", default="0.00", help="diferença aceita no valor (ex.: 0.50)")
    p.set_defaults(func=cmd_buscar)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ERROS_DE_DADOS as erro:
        sys.exit(f"ERRO: {erro}")


if __name__ == "__main__":
    main()
