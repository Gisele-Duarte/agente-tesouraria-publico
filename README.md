# Agente de Tesouraria

Organiza o livro caixa de uma congregação juntando três fontes: o **livro caixa** escrito à
mão, os **comprovantes do WhatsApp** e os **extratos do banco**. Gera uma planilha Excel com
uma aba por mês, a divisão **20% sede · 20% prebenda · 60% igreja local**, os saldos e uma
lista de pendências para a tesouraria responder.

Cada lançamento recebe uma marca:

- 🟢 **CONFIRMADO**: data, valor e identificação suficientes.
- 🟡 **PENDENTE**: a movimentação existiu, mas falta informação.
- 🔴 **DIVERGÊNCIA**: não bate com extrato ou comprovante, ou parece duplicado.

## Instalação (uma vez por computador)

Precisa de Python 3.10 ou mais novo. Na pasta do projeto:

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

No macOS e no Linux, use `.venv/bin/python` no lugar de `.venv/Scripts/python.exe`.

Para ler extratos em PDF, o `pdftotext` (Poppler) precisa estar instalado. No Windows ele
já vem com o Git for Windows. Tesseract e ImageMagick **não** são necessários: as fotos
manuscritas são lidas pelo Claude Code (skill `/tesouraria`), que entende letra de mão
melhor que OCR.

## Onde ficam os dados

Os dados de cada congregação ficam em `congregacoes/<nome>/` e **nunca vão para o Git**,
porque têm nome de membros e valores (veja o `.gitignore`). Só `congregacoes/exemplo/` é
versionada, como modelo.

```
congregacoes/<nome>/
  config.yaml          regras (porcentagens) e nome
  entrada/whatsapp/    ZIPs exportados (1_gestao_contas.zip, 2_outros_comprovantes.zip)
  entrada/extratos/    PDFs do banco
  entrada/livro/       PDF do livro caixa (referência)
  dados/               lançamentos, extrato, índice do WhatsApp (gerados ao importar)
  transcricoes.yaml    fotos da agenda já lidas
  respostas.yaml       respostas da tesouraria às pendências
  rascunho/            planilha de conferência (refeita a cada `executar`)
  saida/               revisões oficiais REV03, REV04… (nunca sobrescritas)
  cache/               fotos extraídas, texto dos extratos e backups (nunca apagar)
```

## Uso

**1. Começar a partir de uma planilha já organizada** (uma vez):

```bash
.venv/Scripts/python.exe agente.py importar-planilha congregacoes/minha_congregacao "C:/Users/.../Livro_Caixa_REV04.xlsx"
```

Para trocar a base por uma revisão mais nova, acrescente `--substituir`. Os dados atuais vão
para `cache/backup_dados_<data>/` antes.

**2. Conferir o estado atual** (sempre que chegar arquivo novo):

```bash
.venv/Scripts/python.exe agente.py executar congregacoes/minha_congregacao
```

Lê ZIPs e extratos novos, aplica transcrições e respostas, gera `rascunho/Livro_Caixa_RASCUNHO.xlsx`
e mostra o resumo: meses, extratos lidos, fotos pendentes, pendências e saldo.

**3. Outros comandos**

| Comando | Para quê |
|---|---|
| `pendencias <pasta>` | lista 🔴 e 🟡 com o código de cada uma (L00123, P2, SALDO…) |
| `fotos <pasta> --proximas 10 --extrair` | próximas fotos da agenda, copiadas para `cache/fotos/` |
| `buscar <pasta> --mes 2025-07 --valor 45` | procura lançamento parecido, para não lançar em dobro |
| `resumo <pasta>` | saldo mês a mês no terminal |
| `gerar-revisao <pasta>` | grava a próxima revisão oficial em `saida/` |

## Como as respostas entram

Nada é corrigido direto na planilha gerada: a próxima revisão sairia sem a correção. Cada
resposta vai para `respostas.yaml` com o texto do que a pessoa disse. Veja o formato
comentado em [congregacoes/exemplo/respostas.yaml](congregacoes/exemplo/respostas.yaml).
As fotos lidas vão para `transcricoes.yaml`, no formato de
[congregacoes/exemplo/transcricoes.yaml](congregacoes/exemplo/transcricoes.yaml).

## Regras do cálculo

As mesmas da planilha REV02:

1. Entradas do mês = soma das linhas "Entrada", menos "Transferência interna…".
2. 20% sede e 20% prebenda sobre as entradas. O resto (60%) fica com a igreja local.
3. Despesas = saídas, menos as que começam com "Prebenda", "Repasse Sede" ou
   "Transferência interna", porque essas saem das partes de 20% ou são só troca de bolso.
4. Saldo total = 60% − despesas + saldo do mês anterior. O primeiro mês parte do saldo inicial.
5. Prebenda a pagar e sede a repassar são acumulados: devido − pago, mês a mês.

As porcentagens ficam em `config.yaml` (`regras:`). **Não mude sem pedido da tesouraria.**

## Testes

```bash
.venv/Scripts/python.exe -m pytest
```

Os testes usam só dados fictícios.

## Limitações conhecidas

- O leitor de extrato do Santander (`tesouraria/extrato.py`) foi escrito para o formato
  "data · histórico · valor · saldo" e **ainda não foi validado com um PDF real**. Se um
  extrato der "0 linhas lidas", o texto extraído fica em `cache/extratos_texto/` para ajustar
  o leitor.
- Linhas novas de extrato não viram lançamento sozinhas. Elas são marcadas "Conciliado
  (automático)" ou "Não lançado – conferir", e a decisão fica com quem confere.
