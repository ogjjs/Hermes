# Hermes — fase 1 (back-end): desenho

Data: 23/11/2026 · Estado: rascunho para aprovação

## 1. Intenção

Hermes é um projeto de **portfólio para o GitHub**. Ele mostra uma pipeline de dados de ponta a ponta
num negócio fictício: uma **distribuidora de filmes em DVD/CD que trabalha em consignação** com lojas
parceiras.

A ideia nasce de dois sistemas que o autor construiu no trabalho (um que **emite** documentos e
acompanha a saída, e outro que **recebe e lê o retorno** e confere contra o que foi emitido). Aqui o
padrão é refeito do zero, num domínio que não tem nada a ver com a empresa.

O que quem abrir o repositório precisa entender:
- dados chegam de terceiros em formatos bagunçados e diferentes entre si;
- a pipeline os guarda como chegaram, padroniza, **concilia contra o que a distribuidora emitiu** e
  aponta as divergências;
- no fim sai o fechamento do mês (faturamento real, repasse, custo, lucro), pronto para um painel.

## 2. Metas, não metas e anti-metas

**Metas da fase 1**
- Emitir remessas (notas fiscais fictícias) mensais para as lojas parceiras.
- Gerar, por script, os relatórios mensais que as lojas "devolvem", em CSV, Excel e PDF, com erros
  de propósito.
- Importar esses arquivos, padronizar, conciliar e registrar divergências.
- Conferência do acerto: aceitar ou contestar cada divergência.
- Fechamento mensal por loja e geral, em tabelas que o Power BI lerá na fase 3.
- Testes automatizados e um README que conte a história.

**Não metas (fases seguintes)**
- Tela (fase 2 ou depois).
- Leitura de relatório escrito à mão / OCR (fase 2).
- Power BI (fase 3).
- dbt (possível migração futura das transformações SQL).
- Promoções, preço variável, frete separado, impostos reais.

**Anti-metas (falharia mesmo funcionando)**
- Qualquer código, regra, nome ou dado copiado do Argus, do Octopus ou da empresa.
- Nota fiscal que pareça documento real (SEFAZ, chave de acesso válida, CNPJ real).
- Senha no repositório ou no histórico do git.
- Alterar as tabelas do Pagila.
- Dados gerados ao acaso a cada execução: o mesmo comando precisa dar o mesmo resultado.

## 3. Restrições

- PostgreSQL 18 local, banco `pagila` já carregado (1.000 filmes, 500 lojas cadastradas, histórico
  de aluguéis de 02/2022 a 07/2026).
- Python (o autor usa 3.13/3.14 no Windows).
- Credenciais só em `.env` (fora do git), lidas pelo código. `.env.example` no repositório sem valor.
- Windows é o ambiente principal; os comandos devem rodar também em Linux (CI do GitHub).

## 4. O negócio

### Contrato
Cada loja parceira tem **um contrato**, com:
- **tabela de preço fixa** por faixa, vinda do `rental_rate` do Pagila:
  0,99 → **R$ 19,90** · 2,99 → **R$ 29,90** · 4,99 → **R$ 39,90**;
- **comissão de 30%** sobre a venda, que fica com a loja;
- **custo** do produto para a distribuidora: **40% do preço** de tabela;
- **frete embutido** no contrato: não aparece como linha nem como despesa separada.

Os valores ficam numa tabela de contratos (com vigência), não no código, para a fase 3 poder simular
outro contrato.

### Consignação, mês a mês
1. No início do mês a distribuidora **emite uma remessa** (nota fiscal fictícia) para cada loja:
   reposição até um **estoque-alvo** por título.
2. Durante o mês a loja vende ao consumidor.
3. Até o dia **10 do mês seguinte** a loja manda o **relatório do mês**: por título, quantidade
   **vendida**, **devolvida** (volta para a distribuidora) e **em estoque** no fim do mês, e o
   **valor do repasse** que ela calculou.
4. A distribuidora concilia, aponta divergências, decide (aceita/contesta) e fecha o mês.

Exemplo: 10 enviados, 2 devolvidos, 8 vendidos a R$ 29,90 → venda R$ 239,20; comissão (30%)
R$ 71,76; repasse R$ 167,44; custo 8 × R$ 11,96 = R$ 95,68; **lucro R$ 71,76**.

### A regra central da conciliação (por loja, título e mês)
```
estoque_inicial + recebido_no_mes = vendido + devolvido + estoque_final
```
`estoque_inicial` é o `estoque_final` conferido do mês anterior (zero no primeiro mês).

### Calendário do mês (decisão do desenho, para a conta fechar)
A remessa de um mês depende do estoque conferido do mês anterior, que só chega no dia 10. Por isso,
na simulação: o relatório do mês M−1 chega até o dia 10 de M, o fechamento de M−1 acontece no dia
10, e a **remessa de M é emitida no dia 11**, repondo até o estoque-alvo a partir desse estoque.
As vendas de M contam de 1 a 31 de M. No primeiro mês (08/2025) a remessa sai no dia 1, com estoque
zero.

### Divergências que a conciliação aponta
| Código | Quando |
|---|---|
| `SALDO_NAO_FECHA` | a equação acima não fecha |
| `TITULO_NAO_ENVIADO` | a loja relata um título que nunca recebeu |
| `TITULO_AUSENTE` | título com estoque na loja que não aparece no relatório |
| `REPASSE_DIVERGENTE` | o repasse declarado difere do calculado (tolerância R$ 0,01) |
| `PRECO_DIVERGENTE` | a loja usou preço diferente da tabela do contrato |
| `RELATORIO_ATRASADO` | chegou depois do dia 10 |
| `RELATORIO_FALTANDO` | loja com remessa no mês e sem relatório até o fechamento |
| `DUPLICADO` | mesmo título duas vezes no relatório |

Cada divergência nasce **aberta** e é decidida como **aceita** (vale o que a loja disse) ou
**contestada** (vale o que a distribuidora calculou), com motivo. É o equivalente da conferência de
pagamento: o mês de uma loja só fecha sem divergência aberta.

O que cada decisão faz com os números (decisão do desenho):
- **Saldo que não fecha, aceito:** vale o estoque final que a loja disse; a diferença vira um
  **ajuste de estoque** (perda ou sobra) registrado, sem cobrança.
- **Saldo que não fecha, contestado:** vendido e devolvido declarados valem, e o estoque final passa
  a ser o calculado pela equação; a diferença é **cobrada da loja a preço de custo**.
- **Repasse ou preço divergente:** aceito, vale o valor da loja; contestado, vale o do contrato.
- **Título não enviado:** contestado, a linha é descartada; aceito, entra como venda de título
  avulso (raro, mas possível).
- **Relatório faltando:** a loja fecha o mês **sem relatório**, sem venda, e o estoque passa igual
  para o mês seguinte. Se o relatório chegar depois, ele reabre o mês dela.
- **Devolução:** a distribuidora confia na quantidade devolvida que o relatório informa (não há
  conferência física na fase 1).

## 5. Dados

- **Pagila (schema `public`) é só leitura.** Dele saem:
  - o **catálogo**: `film` (título, `rental_rate` → faixa de preço, categoria);
  - as **lojas parceiras**: das 500 lojas cadastradas, as **24 que ficam no Brasil** (endereço e
    cidade do Pagila);
  - a **popularidade** de cada título: contagem de aluguéis em `rental`, usada como peso de quanto
    cada título vende. (Só 2 lojas têm aluguéis no Pagila; a popularidade é do título, não da loja.)
- **Tudo do Hermes fica em schemas próprios no mesmo banco**, em camadas:
  - `hermes` — cadastro e operação: lojas parceiras, contratos, remessas/notas e seus itens,
    arquivos recebidos, divergências e decisões;
  - `bruto` — o conteúdo dos arquivos como chegou, uma linha por linha do arquivo, com a origem;
  - `padronizado` — linhas limpas: loja, título, mês, vendido, devolvido, estoque, preço, repasse;
  - `conferido` — a conciliação por loja/título/mês e o resultado das decisões;
  - `relatorio` — o fechamento: por loja e mês, por título e mês, geral do mês. É o que o Power BI lê.
- **Período simulado:** 12 meses, **08/2025 a 07/2026** (os últimos 12 meses com histórico no Pagila).

## 6. Abordagens consideradas

1. **Pipeline em camadas no Postgres (escolhida).** Python lê os arquivos e grava em `bruto`; SQL
   faz `padronizado` → `conferido` → `relatorio`. É o formato que vagas de dados esperam ver, a regra
   de negócio fica legível em SQL, e o Power BI lê a última camada direto.
2. **Tudo em Python, banco só guarda o resultado** (no estilo dos sistemas originais). Mais familiar,
   mas a regra fica escondida no Python e o Power BI recebe menos coisa pronta.
3. **Abordagem 1 com dbt.** Bem visto em vagas, mas é mais uma ferramenta antes do primeiro
   resultado. Fica como migração possível: os SQL da abordagem 1 viram modelos dbt depois.

Escolhida pelo autor em 23/11/2026: **1**.

## 7. Como funciona

### Um projeto, quatro partes
Um só repositório, com o papel de cada sistema original como módulo:

| Módulo | Papel |
|---|---|
| `emissao` | contratos, remessas e notas fiscais fictícias (o lado que emite) |
| `simulador` | gera, de forma reproduzível, o que as lojas fazem e os arquivos que mandam, com erros |
| `retorno` | recebe e lê os arquivos, grava em `bruto`, padroniza (o lado que lê o retorno) |
| `conferencia` | concilia, aponta divergências, registra decisões, fecha o mês |

### Arquivos que as lojas mandam
- Cada loja tem um **formato fixo**, sorteado uma vez (semente fixa): CSV com `;` ou `,`, Excel com
  cabeçalho em linhas diferentes, PDF com tabela em texto. Nomes de coluna variam entre lojas
  ("Qtd vendida", "VENDIDOS", "qtd_vend"…), e o mapeamento de cada loja fica em configuração.
- Ficam numa pasta de entrada (`entrada/<AAAA-MM>/`), com nome livre, como chegariam por e-mail.
- **Importar o mesmo arquivo duas vezes não duplica nada** (identificado pelo sha256). Um arquivo
  novo da mesma loja e mês **substitui** o anterior e reabre a conciliação daquela loja e mês.

### Erros que o simulador injeta
Em proporção configurável (padrão: cerca de 1 em cada 5 relatórios com algum erro): conta que não
fecha, título não enviado, título esquecido, repasse calculado errado, preço errado, linha duplicada,
relatório atrasado, loja que não manda. O simulador grava também um **gabarito** (que erro foi posto
onde), usado só pelos testes para provar que a conciliação acha cada um.

### Nota fiscal fictícia
Registrada no banco (número sequencial, loja, data, itens, valores) e com um **espelho em PDF**
simples. Marcada visivelmente como fictícia; sem chave de acesso, sem CNPJ real. Os valores da nota (número, loja, itens, total) também vão nos atributos do PDF, como gabarito para testar a leitura.

### Comandos (linha de comando)
```
hermes preparar                 # cria schemas e tabelas, carrega lojas e contratos
hermes emitir 2025-08           # remessas e notas do mês
hermes simular 2025-08          # vendas das lojas e arquivos em entrada/2025-08/
hermes importar 2025-08         # lê os arquivos -> bruto -> padronizado
hermes conferir 2025-08         # conciliação e divergências
hermes divergencias 2025-08     # lista as abertas
hermes decidir <id> aceitar|contestar "motivo"
hermes fechar 2025-08           # fechamento em relatorio (recusa se houver divergência aberta)
hermes rodar 2025-08 2026-07    # ciclo inteiro, decisões automáticas por regra, para a demonstração
```
`rodar` precisa decidir sozinho para fechar os 12 meses: aceita o que a loja disse quando a
diferença é pequena e contesta o resto (regra simples e configurável). Ele existe para alguém clonar
o repositório e ver tudo pronto com um comando.

## 8. Qualidade

- `pytest`, com um banco de teste separado (`hermes_teste`) recriado a cada rodada, e o Pagila
  carregado nele a partir dos arquivos `.sql` (no CI, baixados do repositório oficial do Pagila).
- Os testes usam o gabarito do simulador: cada erro injetado precisa virar a divergência certa, e um
  mês sem erro precisa fechar sem nenhuma.
- Mesma semente, mesmo resultado: dois `hermes rodar` seguidos dão o mesmo `relatorio`.
- GitHub Actions rodando os testes com um Postgres de serviço.
- README em português com: a história do negócio, o diagrama das camadas, como rodar, e exemplos do
  que a conciliação pega.

## 9. Ferramentas (decididas em 23/11/2026)

| Ferramenta | Uso |
|---|---|
| Python 3.14, PostgreSQL 18 + pgAdmin, SQL em arquivos `.sql` | base do projeto |
| pandas (com openpyxl) | ler e escrever CSV e Excel |
| NumPy | o sorteio reproduzível do simulador |
| PyMuPDF | gerar PDF e leitor principal de PDF (o que o autor já usa) |
| pdfplumber | leitor reserva: entra quando a leitura com PyMuPDF falha |
| psycopg 3, python-dotenv | banco e `.env` |
| pytest, pytest-cov, ruff | testes, cobertura e padrão de código |
| Git + GitHub Actions | histórico e testes a cada envio |
| Jupyter (opcional), Power BI | análise e painel (fase 3) |
| OCR (pytesseract ou parecido) | relatório à mão (fase 2) |

## 10. Fases

1. **Back-end** (este documento).
2. Leitura de relatório escrito à mão (OCR). Uma interface (HTML ou desktop) fica para a fase 2 ou 3, se fizer sentido.
3. Power BI em cima de `relatorio`: sell-in × sell-out, giro, estoque nas lojas, margem por loja e
   categoria. No GitHub vão o `.pbix` e imagens do painel.

## 11. O que fica para quem constrói

- Layout de pastas, nomes de tabelas e colunas, e se a CLI usa `argparse` ou `typer`.
- O estoque-alvo por título e quantos títulos cada loja trabalha (sugestão: 40 a 120 títulos por
  loja, estoque-alvo de 2 a 6).
- A regra exata de decisão automática do `rodar`.
- Formato do espelho da nota em PDF.
