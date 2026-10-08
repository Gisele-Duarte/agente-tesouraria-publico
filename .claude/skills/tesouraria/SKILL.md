---
name: tesouraria
description: Continua a organização do livro caixa de uma congregação — lê as fotos manuscritas da agenda em lotes, apresenta as pendências 🔴 e 🟡 uma de cada vez, registra as respostas e gera a próxima revisão da planilha. Use quando pedirem para "continuar a tesouraria", "ler as fotos", "ver as pendências", "responder pendência" ou "gerar nova revisão".
---

# /tesouraria

Comandos sempre com o Python do projeto: `.venv/Scripts/python.exe agente.py …` (Windows)
ou `.venv/bin/python agente.py …` (macOS/Linux). `<pasta>` é a da congregação, por exemplo
`congregacoes/minha_congregacao`.

## 0. Situação

Rode `agente.py executar <pasta>` e conte à pessoa, em 3 ou 4 linhas: meses no livro,
meses com extrato, fotos pendentes, quantas 🔴 e 🟡, e o saldo do último mês. Se o saldo
estiver muito negativo por falta das entradas em espécie, diga isso, para ninguém se assustar.

## 1. Fotos da agenda, em lotes de 10

1. `agente.py fotos <pasta> --proximas 10 --extrair` copia as próximas 10 para `cache/fotos/`.
   Se disser que não encontrou, os ZIPs não estão em `entrada/whatsapp/`: peça os arquivos e pare.
2. Abra cada foto com a ferramenta Read e leia a legenda que o comando mostrou (ela costuma
   dizer o dia e se é entrada ou saída).
3. Antes de lançar, verifique duplicidade com `agente.py buscar <pasta> --mes AAAA-MM --valor N`.
   Fotos de mai–jul/2025 cobrem meses que o livro caixa já tem: se o lançamento já existe,
   marque a foto como `ja_lancada`.
4. Registre a foto em `transcricoes.yaml` (formato em `congregacoes/exemplo/transcricoes.yaml`):
   - `transcrita`: um item por linha da agenda. Use `certeza: baixa` quando qualquer dígito
     ou nome for duvidoso. **Nunca adivinhe valor.**
   - `ilegivel`: explique em `observacao` o que não deu para ler.
   - `sem_lancamento`: foto sem movimento de dinheiro.
   - Descrição sempre começando pela categoria: "Oferta – culto (dinheiro)", "Dízimo – Nome",
     "Transporte – Uber Pr. …". Pagamento de prebenda começa com "Prebenda", repasse à sede
     com "Repasse Sede", e dinheiro do banco para o caixa com "Transferência interna".
5. Rode `agente.py executar <pasta>`. Se der ERRO, corrija o YAML e rode de novo.
6. Mostre o progresso: "Lote 3: 10 fotos (8 transcritas, 1 ilegível, 1 já lançada) ·
   faltam 212". Siga para o próximo lote, a menos que a pessoa peça para parar.

## 2. Pendências, uma de cada vez

1. `agente.py pendencias <pasta>`: as 🔴 vêm primeiro.
2. Apresente **uma** por vez, em linguagem simples: o que se sabe, o que falta e a pergunta.
   Exemplo: "Em 29/06/2025 aparece um dízimo de R$ 211,00 no Pix sem nome, marcado como
   divergência. Você sabe de quem é? Ele deveria estar no extrato de junho?"
   Quando várias pendências têm a mesma causa (ex.: ofertas Pix sem valor que dependem do
   extrato), agrupe numa pergunta só e diga quantas são.
3. Registre a resposta **antes** de passar para a próxima, em `respostas.yaml` (formato em
   `congregacoes/exemplo/respostas.yaml`). O campo `resposta` guarda o que a pessoa disse,
   com as palavras dela.
   - "Não sei" não resolve: deixe como está (🟡) e siga.
   - Resposta que muda regra (ex.: "o repasse à sede foi abonado") **não** altera as
     porcentagens. Registre a resposta e, se precisar, lance o abono como lançamento.
4. Rode `agente.py executar <pasta>` a cada resposta para validar o YAML.

## 3. Revisão final

Com dúvida, pergunte **antes** de gerar. Quando a pessoa confirmar, rode
`agente.py gerar-revisao <pasta>` e informe o caminho da nova `saida/Livro_Caixa_REVnn.xlsx`
e o que ainda ficou aberto.

## Nunca

- Apagar ou sobrescrever nada em `cache/` ou `saida/`.
- Mudar 20% / 20% / 60% sem pedido explícito.
- Colocar dado da igreja (nome, valor, foto) em código, teste, commit ou issue.
- Editar à mão a planilha gerada para "consertar": a correção some na revisão seguinte.
