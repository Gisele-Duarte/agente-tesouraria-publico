# CLAUDE.md — Agente de Tesouraria

Ferramenta que organiza o livro caixa de congregações (livro manuscrito + WhatsApp + extrato).
Leia o `README.md` antes de mudar código. O fluxo de trabalho com a tesouraria está na skill
`/tesouraria` (`.claude/skills/tesouraria/SKILL.md`).

## Quem usa

Quem pede as mudanças é programadora, mas não costuma usar o Claude Code: explique cada passo
em português simples antes de executar, e peça confirmação antes de instalar qualquer coisa
no sistema (fora do `.venv`).

## Regras que não podem quebrar

- **Porcentagens 20% sede · 20% prebenda · 60% local**: só mudam a pedido da tesouraria, e
  só no `config.yaml` da congregação, nunca no código.
- **Nunca apagar nada em `cache/` nem em `saida/`.** Revisões em `saida/` nunca são
  sobrescritas (`proxima_revisao` sempre pega o número seguinte).
- **Dados da igreja nunca vão para o Git**: `congregacoes/*` está no `.gitignore`, exceto
  `exemplo/`. Nome de membro, valor, foto, PDF ou planilha real não entra em código, teste,
  commit nem issue. Testes usam dados fictícios (`tests/conftest.py`).
- **Correção é registrada, não editada à mão**: toda resposta da tesouraria vai para
  `respostas.yaml` com o campo `resposta` (o que a pessoa disse). Toda foto lida vai para
  `transcricoes.yaml`. A planilha é sempre regenerada a partir dos dados.
- **Com dúvida, perguntar antes de gerar a revisão final** (`gerar-revisao`). O `executar`
  gera só o rascunho e pode rodar à vontade.
- Lançamento sem certeza fica 🟡, nunca 🟢. Não invente valor que não está escrito.

## Código

- `agente.py`: linha de comando.
- `tesouraria/regras.py`: cálculo do mês. Precisa bater com as fórmulas de `planilha.py`.
  Se mudar um, mude o outro e rode os testes.
- `tesouraria/importar_planilha.py`: lê qualquer revisão REVnn como base.
- `tesouraria/processar.py`: monta o livro (dados + transcrições + respostas).
- Checks: `.venv/Scripts/python.exe -m pytest`.
