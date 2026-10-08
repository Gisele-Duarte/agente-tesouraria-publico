"""Pastas e arquivos de uma congregação, e leitura/gravação das tabelas de dados.

Estrutura (tudo fora do Git, ver .gitignore):

    congregacoes/<nome>/
        config.yaml            regras (porcentagens), saldo inicial, nome
        entrada/livro|whatsapp|extratos|planilha_base/
        dados/lancamentos.csv  fonte da verdade dos lançamentos
        dados/extrato.csv      linhas de extrato bancário já conferidas
        dados/comprovantes.csv índice dos anexos do WhatsApp
        dados/notas.yaml       textos da planilha (fonte de cada mês, perguntas, avisos)
        transcricoes.yaml      fotos manuscritas já lidas
        respostas.yaml         respostas da tesouraria às pendências
        cache/                 arquivos extraídos (nunca apagar)
        saida/                 planilhas geradas (nunca apagar)
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from .modelo import Lancamento, dinheiro, para_data, normalizar_status, normalizar_tipo, validar_mes
from .regras import Abono, Regras

CAMPOS_LANCAMENTO = ["id", "mes", "data", "tipo", "descricao", "valor", "forma",
                     "comprovante", "status", "observacao", "extras"]
CAMPOS_EXTRATO = ["data", "historico", "valor", "situacao", "arquivo"]
CAMPOS_COMPROVANTE = ["data", "enviado_por", "tipo", "valor", "pagador", "recebedor",
                      "mensagem", "uso", "arquivo", "zip", "arquivo_zip"]

USO_PENDENTE_FOTO = "Pendente – Etapa 3"


@dataclass
class Congregacao:
    pasta: Path

    # --- caminhos -------------------------------------------------------
    @property
    def nome(self) -> str:
        return self.config().get("nome") or self.pasta.name

    def entrada(self, *partes: str) -> Path:
        return self.pasta.joinpath("entrada", *partes)

    def dados(self, arquivo: str) -> Path:
        return self.pasta / "dados" / arquivo

    @property
    def cache(self) -> Path:
        return self.pasta / "cache"

    @property
    def saida(self) -> Path:
        return self.pasta / "saida"

    @property
    def arquivo_transcricoes(self) -> Path:
        return self.pasta / "transcricoes.yaml"

    @property
    def arquivo_respostas(self) -> Path:
        return self.pasta / "respostas.yaml"

    def criar_pastas(self) -> None:
        for sub in ("entrada/livro", "entrada/whatsapp", "entrada/extratos", "entrada/planilha_base",
                    "dados", "cache", "saida"):
            (self.pasta / sub).mkdir(parents=True, exist_ok=True)

    # --- config ---------------------------------------------------------
    def config(self) -> dict:
        return ler_yaml(self.pasta / "config.yaml")

    def salvar_config(self, config: dict) -> None:
        gravar_yaml(self.pasta / "config.yaml", config)

    def regras(self) -> Regras:
        cfg = self.config().get("regras", {})
        regras = Regras(
            repasse_sede=Decimal(str(cfg.get("repasse_sede", "0.20"))),
            prebenda=Decimal(str(cfg.get("prebenda", "0.20"))),
            abonos_sede=tuple(Abono(de=validar_mes(str(a["de"])), ate=validar_mes(str(a["ate"])),
                                    motivo=str(a.get("motivo") or ""),
                                    valor=dinheiro(a["valor"]) if a.get("valor") is not None else None)
                              for a in cfg.get("abonos_sede") or []),
            prebenda_no_saldo=str(cfg.get("prebenda_no_saldo") or "mensal"),
            na_sede_desde=(validar_mes(str(cfg["valores_na_sede"]["desde"]))
                           if (cfg.get("valores_na_sede") or {}).get("desde") else None),
            na_sede_motivo=str((cfg.get("valores_na_sede") or {}).get("motivo") or ""),
        )
        regras.validar()
        return regras

    def saldo_inicial(self) -> Decimal | None:
        """Respostas têm prioridade sobre o config; None = ainda não informado."""
        resposta = ler_yaml(self.arquivo_respostas).get("saldo_inicial")
        if resposta is not None:
            return dinheiro(resposta)
        valor = self.config().get("saldo_inicial")
        return None if valor is None else dinheiro(valor)

    # --- tabelas --------------------------------------------------------
    def lancamentos(self) -> list[Lancamento]:
        return [_lancamento_de_linha(l) for l in ler_csv(self.dados("lancamentos.csv"))]

    def salvar_lancamentos(self, lancamentos: list[Lancamento]) -> None:
        gravar_csv(self.dados("lancamentos.csv"), CAMPOS_LANCAMENTO,
                   [_linha_de_lancamento(l) for l in lancamentos])

    def extrato(self) -> list[dict]:
        linhas = ler_csv(self.dados("extrato.csv"))
        for l in linhas:
            l["data"], l["valor"] = para_data(l["data"]), dinheiro(l["valor"])
        return linhas

    def salvar_extrato(self, linhas: list[dict]) -> None:
        gravar_csv(self.dados("extrato.csv"), CAMPOS_EXTRATO, linhas)

    def comprovantes(self) -> list[dict]:
        linhas = ler_csv(self.dados("comprovantes.csv"))
        for l in linhas:
            l["data"], l["valor"] = para_data(l["data"]), dinheiro(l["valor"])
        return linhas

    def salvar_comprovantes(self, linhas: list[dict]) -> None:
        gravar_csv(self.dados("comprovantes.csv"), CAMPOS_COMPROVANTE, linhas)

    def notas(self) -> dict:
        return ler_yaml(self.dados("notas.yaml"))

    def gestao_anterior(self) -> dict:
        """Registro à parte do período anterior à tesouraria atual (não entra no livro). Opcional."""
        return ler_yaml(self.pasta / "gestao_anterior.yaml")

    def salvar_notas(self, notas: dict) -> None:
        gravar_yaml(self.dados("notas.yaml"), notas)


# --- conversões linha <-> Lancamento -----------------------------------
def _lancamento_de_linha(linha: dict) -> Lancamento:
    return Lancamento(
        id=linha["id"],
        mes=validar_mes(linha["mes"]),
        data=para_data(linha["data"]),
        tipo=normalizar_tipo(linha["tipo"]),
        descricao=linha["descricao"],
        valor=dinheiro(linha["valor"]),
        forma=linha.get("forma") or "Não informado",
        comprovante=linha.get("comprovante", ""),
        status=normalizar_status(linha["status"]),
        observacao=linha.get("observacao", ""),
        extras=json.loads(linha["extras"]) if linha.get("extras") else {},
    )


def _linha_de_lancamento(l: Lancamento) -> dict:
    return {
        "id": l.id, "mes": l.mes, "data": l.data.isoformat() if l.data else "",
        "tipo": l.tipo, "descricao": l.descricao,
        "valor": "" if l.valor is None else f"{l.valor:.2f}",
        "forma": l.forma, "comprovante": l.comprovante, "status": l.status,
        "observacao": l.observacao,
        "extras": json.dumps(l.extras, ensure_ascii=False) if l.extras else "",
    }


# --- arquivos -----------------------------------------------------------
def ler_csv(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    with caminho.open(encoding="utf-8-sig", newline="") as arq:
        return list(csv.DictReader(arq))


def gravar_csv(caminho: Path, campos: list[str], linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8-sig", newline="") as arq:
        escritor = csv.DictWriter(arq, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow({c: _texto(linha.get(c)) for c in campos})
    temporario.replace(caminho)


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, Decimal):
        return f"{valor:.2f}"
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor)


def ler_yaml(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8") as arq:
        conteudo = yaml.safe_load(arq)
    if conteudo is None:
        return {}
    if not isinstance(conteudo, dict):
        raise ValueError(f"{caminho.name}: o arquivo precisa ser um mapa (chave: valor)")
    return conteudo


def gravar_yaml(caminho: Path, conteudo: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arq:
        yaml.safe_dump(conteudo, arq, allow_unicode=True, sort_keys=False, width=110)
    temporario.replace(caminho)
