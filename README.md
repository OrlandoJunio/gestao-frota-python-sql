# Gestão de Frota: combustível, pedágio e eixo suspenso com Python + SQL

Projeto de portfólio que resolve, fora do Power BI, um problema real de gestão de frotas: **quanto a operação gasta com combustível e pedágio, onde está o desperdício e quais abastecimentos merecem auditoria.**

**[Ver o painel online](https://orlandojunio.github.io/gestao-frota-python-sql/)**

O pipeline usa **Python (pandas, scikit-learn)**, **SQL (SQLite)**, **HTML/JavaScript** para o painel e entrega um **modelo estrela pronto para Power BI**.

> Todos os dados são fictícios. A "TransLog Fictícia", as placas, os motoristas e as tarifas foram gerados por `src/01_gerar_dados.py`.

---

## O problema de negócio

Uma transportadora com 79 veículos (Toco, Truck, Carretas, Bitrem e Rodotrem) em 4 filiais recebe dados de três fontes que não conversam entre si:

| Fonte | O que traz | O que falta |
|---|---|---|
| Cartão combustível | litros, valor, hodômetro | não sabe se o consumo faz sentido |
| Operadora de TAG de pedágio | placa, praça, eixos cobrados, valor | não sabe se o caminhão estava carregado |
| TMS (viagens) | origem, destino, km, carregado/vazio | não sabe quanto foi pago |

Perguntas que o gestor faz e que este projeto responde:

1. Quanto custa cada km rodado, por centro de custo e por mês?
2. **Retorno vazio sem suspender o eixo**: o caminhão volta vazio e paga pedágio por eixos que deveriam estar levantados. Quanto isso custa e quais motoristas mais esquecem?
3. O **km/l real** de cada modelo e de cada motorista está dentro do esperado?
4. A operadora **cobrou duas vezes** a mesma passagem?
5. Quais abastecimentos parecem **inflados** (desvio de combustível) e devem ir para auditoria?

## Resultados (dados fictícios, out/2025 a set/2026)

| Indicador | Valor |
|---|---|
| Custo total (combustível + pedágio) | R$ 19,67 milhões |
| Custo por km | R$ 2,95 |
| km/l da frota | 2,33 (esperado 2,46, ou seja, 5,3% abaixo) |
| **Saving identificado** | **R$ 124 mil** |

O saving se divide em três frentes (consulta `q10`):

| Frente | Ocorrências | R$ |
|---|---:|---:|
| Combustível acima do consumo esperado | 98 abastecimentos | 67.245 |
| Retorno vazio sem suspender eixo | 4.916 passagens | 50.060 |
| Pedágio cobrado em duplicidade | 202 cobranças | 7.309 |

A filial de Ribeirão Preto concentra metade da perda com eixo (conformidade de 67%, contra 72% a 78% nas demais).

**Machine Learning.** Três métodos foram comparados contra um gabarito de 96 abastecimentos inflados de propósito:

| Método | Apontados | Precisão | Recall |
|---|---:|---:|---:|
| Regra fixa em SQL (`q08`) | 100 | 74% | 77% |
| Z-score por veículo | 79 | 63% | 52% |
| Isolation Forest | 86 | 70% | 63% |
| **Consenso (2 ou mais métodos)** | **76** | **90%** | **71%** |

Nenhum método sozinho é o melhor. Quando dois concordam, 9 em cada 10 casos enviados para auditoria são fraude de verdade, o que poupa o tempo do auditor.

---

## Arquitetura

```
 data/raw/*.csv            src/02_etl.py              data/frotas.db
 (3 sistemas "sujos")  ──► pandas: limpa, valida ──►  SQLite com PK, FK
                           e gera relatório           e índices
                                                           │
                    ┌──────────────────────────────────────┼─────────────────────────┐
                    ▼                                      ▼                         ▼
        sql/02_consultas_negocio.sql         src/04_analise_ml.py        src/05_exportar_powerbi.py
        10 perguntas de negócio              z-score + Isolation Forest   modelo estrela (CSV pt-BR)
        → outputs/consultas/*.csv            → gráficos + auditoria       → powerbi/
                                                           │
                                                           ▼
                                             src/06_gerar_dashboard.py
                                             → dashboard/painel_frota.html
```

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
python rodar_pipeline.py         # roda as 6 etapas, ~20 segundos
```

Depois abra `dashboard/painel_frota.html` no navegador. Para explorar o banco com SQL na mão, use o [DB Browser for SQLite](https://sqlitebrowser.org/) e abra `data/frotas.db`.

## Estrutura

```
projeto-frotas/
├── rodar_pipeline.py              roda tudo na ordem
├── requirements.txt
├── src/
│   ├── 01_gerar_dados.py          dados fictícios + sujeira proposital
│   ├── 02_etl.py                  ETL em pandas → SQLite + relatório de qualidade
│   ├── 03_rodar_consultas.py      executa o .sql e salva cada resultado em CSV
│   ├── 04_analise_ml.py           z-score, Isolation Forest, gráficos
│   ├── 05_exportar_powerbi.py     modelo estrela para o Power BI
│   ├── 06_gerar_dashboard.py      monta o painel HTML
│   ├── dashboard_template.html    layout do painel (HTML/CSS/JS + Chart.js)
│   └── utils.py                   caminhos e leitura do arquivo .sql
├── sql/
│   ├── 01_criar_tabelas.sql       schema com chaves e índices
│   └── 02_consultas_negocio.sql   as 10 consultas comentadas
├── data/
│   ├── raw/                       CSVs brutos
│   ├── frotas.db                  banco SQLite
│   └── gabarito_fraudes.csv       só para medir o ML
├── outputs/
│   ├── relatorio_qualidade.md     o que o ETL encontrou e corrigiu
│   ├── consultas/                 resultado de cada consulta
│   ├── graficos/                  PNGs da análise
│   ├── anomalias_abastecimento.csv
│   └── comparacao_metodos.csv
├── powerbi/                       dimensões, fatos e MEDIDAS_DAX.md
├── dashboard/painel_frota.html     painel para abrir localmente
└── docs/index.html                mesma página, publicada pelo GitHub Pages
```

## O que cada parte demonstra

### Qualidade de dados (`02_etl.py`)
Os dados brutos chegam com problemas inseridos de propósito, como acontece na vida real. O ETL:

- padroniza placas digitadas como `abc-1d23` ou ` ABC1D23 ` (1.822 correções);
- lê o extrato do cartão no padrão brasileiro (`;` e vírgula decimal);
- remove 434 linhas duplicadas na exportação do pedágio;
- preenche 1.084 centros de custo vazios a partir do cadastro (equivalente a um PROCV);
- marca 40 hodômetros inconsistentes e 15 abastecimentos acima da capacidade do tanque;
- confere as chaves estrangeiras no banco e grava tudo em `outputs/relatorio_qualidade.md`.

### SQL (`sql/02_consultas_negocio.sql`)

| Consulta | Pergunta | Técnicas |
|---|---|---|
| q01 | Tamanho da operação e custo por km | CTE, subconsulta |
| q02 | Custo mensal por centro de custo | UNION ALL, CASE WHEN para pivotar, strftime |
| q03 | Ranking de pedágio por km | LEFT JOIN, RANK() OVER (PARTITION BY), % do total com SUM() OVER () |
| q04 | Retorno vazio sem eixo suspenso | **JOIN por intervalo de datas** (pedágio dentro da janela da viagem) |
| q05 | km/l de cada abastecimento | **LAG()**, média móvel com AVG() OVER (ROWS BETWEEN 2 PRECEDING) |
| q06 | km/l por modelo vs. referência | DENSE_RANK() |
| q07 | Pedágio cobrado em duplicidade | LAG() por placa + praça, julianday() |
| q08 | Abastecimentos que quebram regras | CASE WHEN com motivo |
| q09 | Ranking de motoristas | NTILE(4) em quartis, km/l esperado ponderado |
| q10 | Saving potencial total | consolidação das três frentes |

O ponto mais interessante é a **q04**: o extrato da TAG não diz se o caminhão estava carregado. A ligação entre pedágio e viagem é feita por `placa` e por `data_hora_passagem BETWEEN saída AND chegada`, um tipo de JOIN que o Power BI não faz nativamente.

### Machine Learning (`04_analise_ml.py`)
- **Engenharia de variáveis**: km/l relativo à referência, % do tanque abastecido e % da autonomia usada, para que um Toco e um Rodotrem possam ser comparados.
- **Z-score** por veículo (estatística clássica).
- **Isolation Forest** (não supervisionado: não precisa de exemplos rotulados de fraude).
- **Avaliação** com precisão e recall contra o gabarito, e um consenso entre métodos.

### Power BI (`powerbi/`)
Modelo estrela com `dim_veiculo`, `dim_motorista`, `dim_calendario`, `fato_viagens`, `fato_abastecimentos` e `fato_pedagios`. O pedágio já vem ligado à viagem e com a perda por eixo calculada. O arquivo `MEDIDAS_DAX.md` traz os relacionamentos, as medidas (Custo por KM, KM/L Real, % Conformidade Eixo, variação mês a mês) e uma sugestão de páginas.

## Decisões e limitações

- **SQLite** foi escolhido porque não precisa de servidor. As consultas usam SQL padrão e funcionam no PostgreSQL com poucas trocas (`strftime` vira `to_char`, `julianday` vira subtração de timestamps).
- **km/l pelo método do tanque cheio**: km desde o abastecimento anterior divididos pelos litros do abastecimento atual. Só é correto se o tanque for completado em todo abastecimento, o que a simulação garante.
- O **gabarito de fraudes** só existe porque os dados são simulados. Num caso real, os casos apontados iriam para auditoria e o resultado viraria rótulo para um modelo supervisionado.
- A referência de km/l é otimista de propósito (como as de fabricante), por isso toda a frota aparece um pouco abaixo dela.

## Próximos passos

- Trocar o SQLite por PostgreSQL e agendar o pipeline (cron ou Airflow).
- Modelo supervisionado (Random Forest) treinado com o resultado das auditorias.
- Previsão de custo do mês seguinte por centro de custo.
- Testes automáticos das regras de qualidade com `pytest`.
