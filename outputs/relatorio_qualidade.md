# Relatório de qualidade de dados (ETL)

Gerado por `src/02_etl.py`.

| Tabela | Verificação | Quantidade |
|---|---|---:|
| frotas | linhas lidas do CSV | 79 |
| motoristas | linhas lidas do CSV | 87 |
| viagens | linhas lidas do CSV | 27.932 |
| abastecimentos | linhas lidas do CSV | 6.250 |
| pedagios | linhas lidas do CSV | 54.656 |
| abastecimentos | placas corrigidas (minúscula/hífen/espaço) | 188 |
| pedagios | placas corrigidas (minúscula/hífen/espaço) | 1.634 |
| pedagios | linhas duplicadas removidas (mesmo id_transacao) | 434 |
| pedagios | centro de custo vazio preenchido pelo cadastro | 1.084 |
| abastecimentos | placas fora do cadastro de frota | 0 |
| pedagios | placas fora do cadastro de frota | 0 |
| viagens | placas fora do cadastro de frota | 0 |
| abastecimentos | litros acima da capacidade do tanque (flag) | 15 |
| abastecimentos | hodômetro inconsistente (flag) | 40 |
| abastecimentos | células nulas após tratamento | 0 |
| pedagios | células nulas após tratamento | 0 |
| viagens | células nulas após tratamento | 0 |
| motoristas | linhas gravadas no banco | 87 |
| frotas | linhas gravadas no banco | 79 |
| viagens | linhas gravadas no banco | 27.932 |
| abastecimentos | linhas gravadas no banco | 6.250 |
| pedagios | linhas gravadas no banco | 54.222 |
| banco | violações de chave estrangeira | 0 |
