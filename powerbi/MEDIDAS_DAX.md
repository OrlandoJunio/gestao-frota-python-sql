# Montando o painel no Power BI

## 1. Importar
Obter dados > Texto/CSV > selecione os 6 arquivos desta pasta. Eles já estão em `;` com vírgula decimal (padrão pt-BR), então o Power BI reconhece os números sem ajuste.

## 2. Relacionamentos (modelo estrela)

| De (fato, lado N) | Para (dimensão, lado 1) |
|---|---|
| fato_viagens[placa] | dim_veiculo[placa] |
| fato_abastecimentos[placa] | dim_veiculo[placa] |
| fato_pedagios[placa] | dim_veiculo[placa] |
| fato_viagens[id_motorista] | dim_motorista[id_motorista] |
| fato_abastecimentos[id_motorista] | dim_motorista[id_motorista] |
| fato_viagens[data] | dim_calendario[data] |
| fato_abastecimentos[data] | dim_calendario[data] |
| fato_pedagios[data] | dim_calendario[data] |

Marque `dim_calendario` como tabela de datas. Deixe `fato_pedagios[id_motorista]` sem relacionamento ativo (evita ambiguidade) e use `USERELATIONSHIP` quando precisar.

## 3. Medidas DAX

```dax
KM Rodado = SUM ( fato_viagens[km_rodado] )

Litros = SUM ( fato_abastecimentos[litros] )

Custo Combustível = SUM ( fato_abastecimentos[valor_total] )

Custo Pedágio = SUM ( fato_pedagios[valor_transacao] )

Custo Total = [Custo Combustível] + [Custo Pedágio]

Custo por KM = DIVIDE ( [Custo Total], [KM Rodado] )

-- km/l pelo método do tanque cheio (só registros com km calculado)
KM/L Real =
DIVIDE (
    SUM ( fato_abastecimentos[km_desde_ultimo] ),
    CALCULATE ( SUM ( fato_abastecimentos[litros] ), NOT ISBLANK ( fato_abastecimentos[km_desde_ultimo] ) )
)

-- km/l esperado ponderado pelos km de cada veículo
KM/L Esperado =
DIVIDE (
    SUM ( fato_abastecimentos[km_desde_ultimo] ),
    SUMX (
        FILTER ( fato_abastecimentos, NOT ISBLANK ( fato_abastecimentos[km_desde_ultimo] ) ),
        fato_abastecimentos[km_desde_ultimo] / RELATED ( dim_veiculo[km_l_referencia] )
    )
)

Desvio KM/L % = DIVIDE ( [KM/L Real], [KM/L Esperado] ) - 1

Perda Eixo Não Suspenso = SUM ( fato_pedagios[perda_eixo_nao_suspenso] )

Cobrança Duplicada R$ =
CALCULATE ( [Custo Pedágio], fato_pedagios[flag_cobranca_duplicada] = 1 )

-- Conformidade: % das passagens em retorno vazio (veículos com eixo suspensível) em que o eixo subiu
% Conformidade Eixo =
VAR VaziasElegiveis =
    CALCULATE (
        COUNTROWS ( fato_pedagios ),
        fato_pedagios[status_carga] = "VAZIO",
        dim_veiculo[eixos_suspensiveis] > 0
    )
VAR SemSuspender =
    CALCULATE ( COUNTROWS ( fato_pedagios ), fato_pedagios[perda_eixo_nao_suspenso] > 0 )
RETURN DIVIDE ( VaziasElegiveis - SemSuspender, VaziasElegiveis )

Abastecimentos para Auditoria =
CALCULATE ( COUNTROWS ( fato_abastecimentos ), fato_abastecimentos[prioridade_auditoria] = "Alta" )

Custo Total Mês Anterior =
CALCULATE ( [Custo Total], DATEADD ( dim_calendario[data], -1, MONTH ) )

Variação Custo MoM % = DIVIDE ( [Custo Total] - [Custo Total Mês Anterior], [Custo Total Mês Anterior] )
```

## 4. Sugestão de páginas
1. **Visão geral**: cartões (Custo Total, Custo por KM, KM/L Real x Esperado), coluna empilhada de custo mensal por tipo, segmentação por filial e centro de custo.
2. **Pedágio**: matriz por praça/concessionária, perda por eixo por filial e motorista, tabela de cobranças duplicadas para contestação.
3. **Combustível**: desvio de km/l por modelo, ranking de motoristas, tabela de auditoria filtrada por `prioridade_auditoria = "Alta"`.

Os números do painel devem bater com `outputs/consultas/q01_visao_geral.csv` e `q10_saving_potencial.csv`: é uma boa forma de validar o modelo.
