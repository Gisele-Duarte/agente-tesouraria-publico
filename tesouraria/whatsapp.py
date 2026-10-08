"""ZIPs exportados do WhatsApp: índice dos anexos e extração das fotos para leitura.

Aceita a exportação do iPhone ("[04/05/2025, 21:47:08] Maria: <anexado: 0000…jpg>")
e a do Android ("04/05/2025 21:47 - Maria: IMG-…jpg (arquivo anexado)").
"""
from __future__ import annotations

import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from .dados import Congregacao, USO_PENDENTE_FOTO

_INVISIVEIS = dict.fromkeys(map(ord, "‎‏‪‬﻿"), None)
_MSG_IPHONE = re.compile(r"^\[(\d{2}/\d{2}/\d{2,4}),? (\d{1,2}:\d{2}(?::\d{2})?)\] ([^:]+): (.*)$")
_MSG_ANDROID = re.compile(r"^(\d{2}/\d{2}/\d{2,4}),? (\d{1,2}:\d{2}) - ([^:]+): (.*)$")
_ANEXO_IPHONE = re.compile(r"<(?:anexado|attached): ([^>]+)>")
_ANEXO_ANDROID = re.compile(r"^(.+?) \((?:arquivo anexado|file attached)\)$")
EXTENSOES_FOTO = (".jpg", ".jpeg", ".png", ".heic")
# Figurinhas, áudios e contatos não são comprovante.
_NAO_E_COMPROVANTE = re.compile(r"^(STK|PTT|AUD|VID)-|\.(webp|opus|vcf|mp4)$", re.IGNORECASE)
# Nome que o iPhone dá à foto: "00000298-PHOTO-2025-08-03-15-38-22.jpg" (data e hora do envio).
_FOTO_IPHONE = re.compile(r"^\d{8}-PHOTO-(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-\d{2}\.")


def mensagens(texto: str) -> list[dict]:
    """Quebra o _chat.txt em mensagens (texto de várias linhas fica junto)."""
    lista: list[dict] = []
    for linha in texto.translate(_INVISIVEIS).splitlines():
        achado = _MSG_IPHONE.match(linha) or _MSG_ANDROID.match(linha)
        if achado:
            dia, hora, autor, corpo = achado.groups()
            lista.append({"quando": _quando(dia, hora), "autor": autor.strip(), "texto": corpo})
        elif lista:
            lista[-1]["texto"] += "\n" + linha
    return lista


def _quando(dia: str, hora: str) -> datetime:
    formato_dia = "%d/%m/%Y" if len(dia) == 10 else "%d/%m/%y"
    formato_hora = "%H:%M:%S" if hora.count(":") == 2 else "%H:%M"
    return datetime.strptime(f"{dia} {hora}", f"{formato_dia} {formato_hora}")


def anexos(zip_path: Path) -> list[dict]:
    with zipfile.ZipFile(zip_path) as zf:
        chats = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not chats:
            raise ValueError(f"{zip_path.name}: não há conversa (.txt) dentro do ZIP")
        texto = zf.read(chats[0]).decode("utf-8", errors="replace")
    encontrados = []
    for msg in mensagens(texto):
        primeira, _, resto = msg["texto"].partition("\n")
        iphone = _ANEXO_IPHONE.search(msg["texto"])
        android = _ANEXO_ANDROID.match(primeira.strip())
        if iphone:
            arquivo, legenda = iphone.group(1).strip(), _ANEXO_IPHONE.sub("", msg["texto"]).strip()
        elif android:
            arquivo, legenda = android.group(1).strip(), resto.strip()
        else:
            continue
        encontrados.append({"data": msg["quando"].date(), "quando": msg["quando"], "enviado_por": msg["autor"],
                            "arquivo": arquivo, "mensagem": legenda, "zip": zip_path.name})
    return encontrados


def zips(cong: Congregacao) -> list[Path]:
    return sorted(cong.entrada("whatsapp").glob("*.zip"))


def casar_nomes(comprovantes: list[dict], todos: list[dict]) -> int:
    """Liga cada item do índice ao arquivo do ZIP (coluna arquivo_zip). Devolve quantos casaram.

    A mesma conversa exportada no iPhone e no Android dá nomes diferentes ao mesmo anexo:
    - foto: "00000298-PHOTO-2025-08-03-15-38-22.jpg" (iPhone) x "IMG-20250803-WA0003.jpg"
      (Android) → casa pelo minuto do envio; no mesmo minuto, pela ordem de envio;
    - documento: "00000365-Comprovante_30-08-2025 193220.pdf" x "Comprovante_30-08-2025 193220.pdf".
    """
    por_nome = {a["arquivo"]: a for a in todos}
    por_minuto: dict[datetime, list[dict]] = {}
    for anexo in todos:
        if anexo["arquivo"].lower().endswith(EXTENSOES_FOTO):
            por_minuto.setdefault(anexo["quando"].replace(second=0), []).append(anexo)
    usados = {c["arquivo_zip"] for c in comprovantes if c.get("arquivo_zip")}
    casados = 0
    for item in sorted(comprovantes, key=lambda c: c["arquivo"]):
        if item.get("arquivo_zip"):
            continue
        nome = item["arquivo"]
        sem_prefixo = re.sub(r"^\d{8}-", "", nome)
        candidatos = [por_nome.get(n) for n in (nome, sem_prefixo, sem_prefixo.removesuffix(".pdf").rstrip("."))]
        achado = next((a for a in candidatos if a and a["arquivo"] not in usados), None)
        foto = _FOTO_IPHONE.match(nome)
        if achado is None and foto:
            minuto = datetime(*(int(x) for x in foto.groups()))
            for tentativa in (minuto, minuto - timedelta(minutes=1), minuto + timedelta(minutes=1)):
                achado = next((a for a in por_minuto.get(tentativa, []) if a["arquivo"] not in usados), None)
                if achado:
                    break
        if achado:
            item["arquivo_zip"], item["zip"] = achado["arquivo"], achado["zip"]
            usados.add(achado["arquivo"])
            casados += 1
    return casados


def sincronizar(cong: Congregacao) -> dict:
    """Liga o índice aos ZIPs e acrescenta os anexos novos. Nunca apaga nem reclassifica o que já existe."""
    if not zips(cong):
        return {"zips": [], "novos": 0, "casados": 0, "total": len(cong.comprovantes())}
    comprovantes = cong.comprovantes()
    todos = [a for z in zips(cong) for a in anexos(z) if not _NAO_E_COMPROVANTE.search(a["arquivo"])]
    casados = casar_nomes(comprovantes, todos)
    conhecidos = {c.get("arquivo_zip") or c["arquivo"] for c in comprovantes}
    novos = 0
    for anexo in todos:
        if anexo["arquivo"] in conhecidos:
            continue
        foto = anexo["arquivo"].lower().endswith(EXTENSOES_FOTO)
        comprovantes.append({**{k: v for k, v in anexo.items() if k != "quando"},
                             "arquivo_zip": anexo["arquivo"],
                             "tipo": "Foto nova (ler)" if foto else "Documento novo (ler)",
                             "valor": None, "pagador": "", "recebedor": "",
                             "uso": USO_PENDENTE_FOTO if foto else "Novo – conferir"})
        conhecidos.add(anexo["arquivo"])
        novos += 1
    comprovantes.sort(key=lambda c: (c["data"] or datetime.min.date(), c["arquivo"]))
    cong.salvar_comprovantes(comprovantes)
    return {"zips": [z.name for z in zips(cong)], "novos": novos, "casados": casados, "total": len(comprovantes)}


def extrair(cong: Congregacao, arquivos: list[str]) -> tuple[dict[str, Path], list[str]]:
    """Copia os anexos pedidos (nomes do índice) dos ZIPs para cache/fotos/, sem sobrescrever.

    Devolve ({nome no índice: caminho}, [nomes não encontrados])."""
    destino = cong.cache / "fotos"
    destino.mkdir(parents=True, exist_ok=True)
    no_zip = {c["arquivo"]: c.get("arquivo_zip") or c["arquivo"] for c in cong.comprovantes()}
    pedidos = {a: no_zip.get(a, a) for a in arquivos}
    caminhos = {a: destino / z for a, z in pedidos.items() if (destino / z).exists()}
    for zip_path in zips(cong):
        faltam = {z: a for a, z in pedidos.items() if a not in caminhos}
        if not faltam:
            break
        with zipfile.ZipFile(zip_path) as zf:
            for nome in zf.namelist():
                base = nome.rsplit("/", 1)[-1]
                if base in faltam:
                    (destino / base).write_bytes(zf.read(nome))
                    caminhos[faltam.pop(base)] = destino / base
    return caminhos, [a for a in arquivos if a not in caminhos]
