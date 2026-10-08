"""Junta dados importados + fotos transcritas + respostas num livro pronto para virar planilha."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from . import extrato as extrato_mod
from . import respostas as respostas_mod
from . import transcricoes as transcricoes_mod
from . import whatsapp
from .dados import Congregacao
from .modelo import Lancamento, meses_entre
from .pendencias import Pendencia, montar, texto_fotos_por_mes
from .regras import Regras, ResumoMes, resumir


@dataclass
class Livro:
    nome: str
    titulo: str
    regras: Regras
    saldo_inicial: Decimal | None
    situacao: str
    meses: list[str]
    fontes: dict[str, str]
    lancamentos: list[Lancamento]
    removidos: list[Lancamento]
    livro_totais: dict
    observacao_resumo: str
    extrato: list[dict]
    extrato_titulo: str
    extrato_periodos: str
    comprovantes: list[dict]
    perguntas: dict
    perguntas_respondidas: dict
    avisos: list[dict]
    fotos_pendentes: list[dict]
    pendencias: list[Pendencia]
    resumos: list[ResumoMes] = field(default_factory=list)
    alteracoes: list[dict] = field(default_factory=list)   # em relação à planilha base importada
    gestao_anterior: dict = field(default_factory=dict)    # aba à parte, fora do cálculo do livro

    @property
    def cor_por_id(self) -> dict[str, str]:
        return {a["id"]: a["tipo"] for a in self.alteracoes if a["tipo"] in ("Novo", "Alterado")}

    @property
    def fotos_pendentes_por_mes(self) -> list[tuple[str, str]]:
        return texto_fotos_por_mes(self.fotos_pendentes)


def sincronizar_entradas(cong: Congregacao) -> dict:
    """Lê ZIPs e PDFs novos de entrada/ e acrescenta ao índice e ao extrato."""
    return {"whatsapp": whatsapp.sincronizar(cong),
            "extratos": extrato_mod.sincronizar(cong, cong.lancamentos())}


def montar_livro(cong: Congregacao) -> Livro:
    notas = cong.notas()
    fotos = transcricoes_mod.ler(cong)
    base = cong.lancamentos() + transcricoes_mod.lancamentos(cong)
    resultado = respostas_mod.aplicar(cong, base)
    lancamentos = resultado.lancamentos
    meses = meses_entre(min(l.mes for l in lancamentos), max(l.mes for l in lancamentos))
    saldo_inicial = cong.saldo_inicial()
    comprovantes = transcricoes_mod.atualizar_uso(cong.comprovantes(), fotos)
    perguntas = notas.get("perguntas") or {}
    respondidas = {k: v for k, v in resultado.perguntas_respondidas.items() if k in perguntas}
    regras = cong.regras()
    livro = Livro(
        nome=cong.nome, titulo=notas.get("titulo", ""), regras=regras, saldo_inicial=saldo_inicial,
        situacao=notas.get("situacao", ""), meses=meses, fontes=notas.get("meses") or {},
        lancamentos=lancamentos, removidos=resultado.removidos,
        livro_totais=notas.get("livro_totais") or {}, observacao_resumo=notas.get("observacao_resumo", ""),
        extrato=respostas_mod.aplicar_extrato(cong, cong.extrato()), extrato_titulo=notas.get("extrato_titulo", ""),
        extrato_periodos=notas.get("extrato_periodos", ""), comprovantes=comprovantes,
        perguntas=perguntas, perguntas_respondidas=respondidas,
        avisos=notas.get("avisos") or [],
        fotos_pendentes=transcricoes_mod.fotos_pendentes(cong, comprovantes),
        pendencias=montar(lancamentos, _sem_saldo_inicial(perguntas), respondidas,
                          transcricoes_mod.fotos_ilegiveis(cong), saldo_inicial is not None),
    )
    livro.resumos = resumir(lancamentos, meses, regras, saldo_inicial or Decimal("0"))
    livro.alteracoes = alteracoes(cong.lancamentos(), lancamentos, resultado.removidos)
    livro.gestao_anterior = cong.gestao_anterior()
    motivos = respostas_mod.ler(cong).get("lancamentos") or {}
    for item in livro.alteracoes:
        if item["tipo"] == "Removido" and item["id"] in motivos:
            item["motivo"] = respostas_mod.registro(motivos[item["id"]])
    return livro


CAMPOS_COMPARADOS = (("data", "Data"), ("tipo", "Entrada/Saída"), ("descricao", "Descrição"), ("valor", "Valor"),
                     ("forma", "Forma"), ("comprovante", "Comprovante"), ("status", "Conferência"))


def _motivo(antes: Lancamento | None, depois: Lancamento) -> str:
    """O que a observação ganhou: a resposta, a conferência ou a nota da transcrição."""
    if antes and depois.observacao.startswith(antes.observacao):
        return depois.observacao[len(antes.observacao):].lstrip("; ")
    return depois.observacao


def alteracoes(base: list[Lancamento], final: list[Lancamento], removidos: list[Lancamento]) -> list[dict]:
    """Diferença entre a planilha base importada e o livro de agora, linha a linha."""
    por_id = {l.id: l for l in base}
    lista = []
    for depois in final:
        antes = por_id.get(depois.id)
        if antes is None:
            lista.append({"tipo": "Novo", "id": depois.id, "lanc": depois, "mudou": "", "motivo": _motivo(None, depois)})
            continue
        mudou = [f"{nome}: {_fmt(getattr(antes, campo))} → {_fmt(getattr(depois, campo))}"
                 for campo, nome in CAMPOS_COMPARADOS if getattr(antes, campo) != getattr(depois, campo)]
        if mudou:
            lista.append({"tipo": "Alterado", "id": depois.id, "lanc": depois, "mudou": " | ".join(mudou),
                          "motivo": _motivo(antes, depois)})
    for antes in removidos:
        lista.append({"tipo": "Removido", "id": antes.id, "lanc": antes, "mudou": "removido da planilha",
                      "motivo": ""})
    return sorted(lista, key=lambda a: (a["lanc"].mes, a["lanc"].data or a["lanc"].mes, a["id"]))


def _fmt(valor) -> str:
    if valor is None:
        return "(vazio)"
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, Decimal):
        return f"{valor:.2f}".replace(".", ",")
    return str(valor)


def _sem_saldo_inicial(perguntas: dict) -> dict:
    """O saldo inicial tem pendência própria (SALDO); não repetir a pergunta importada."""
    return {k: v for k, v in perguntas.items() if not str(v.get("titulo", "")).lower().startswith("saldo inicial")}


def proxima_revisao(cong: Congregacao) -> Path:
    """saida/Livro_Caixa_REVnn.xlsx com nn maior que a base e que todas as revisões já geradas."""
    numeros = [int(cong.config().get("revisao_base") or 0)]
    for arquivo in cong.saida.glob("*.xlsx"):
        achado = re.search(r"REV0*(\d+)", arquivo.stem, re.IGNORECASE)
        if achado:
            numeros.append(int(achado.group(1)))
    return cong.saida / f"Livro_Caixa_REV{max(numeros) + 1:02d}.xlsx"
