-- =============================================================================
-- 02_consultas_negocio.sql
-- Perguntas de negócio da gestão de frota respondidas em SQL (dialeto SQLite).
--
-- Cada consulta começa com uma linha "-- @consulta: nome". O script
-- src/03_rodar_consultas.py usa essa marcação para separar as consultas,
-- executar uma a uma e salvar o resultado em outputs/consultas/<nome>.csv.
--
-- Recursos de SQL usados (e onde aparecem):
--   JOIN / LEFT JOIN ............ todas
--   GROUP BY + agregações ....... q01, q02, q03, q06, q09
--   CASE WHEN ................... q02, q04, q05, q08, q09
--   CTE (WITH ... AS) ........... q01, q03, q04, q05, q06, q09, q10
--   UNION ALL ................... q02, q10
--   Window functions:
--      RANK / DENSE_RANK ........ q03, q06
--      LAG ...................... q05, q07
--      AVG(...) OVER (ROWS ...) . q05 (média móvel)
--      NTILE .................... q09 (quartis)
--      SUM(...) OVER () ......... q03, q10 (% do total)
--   JOIN por intervalo de datas . q04 (pedágio dentro da janela da viagem)
-- =============================================================================


-- @consulta: q01_visao_geral
-- PERGUNTA: Qual o tamanho da operação no período e quanto custa cada km rodado?
-- Cada CTE resume uma tabela; no final juntamos tudo numa linha só.
WITH km AS (
    SELECT SUM(km_rodado) AS km_total, COUNT(*) AS qtd_viagens
    FROM viagens
),
comb AS (
    SELECT SUM(litros) AS litros_total, SUM(valor_total) AS custo_combustivel
    FROM abastecimentos
),
ped AS (
    SELECT SUM(valor_transacao) AS custo_pedagio, COUNT(*) AS qtd_passagens
    FROM pedagios
)
SELECT
    (SELECT COUNT(*) FROM frotas)                                   AS qtd_veiculos,
    km.qtd_viagens,
    ROUND(km.km_total, 0)                                           AS km_total,
    ROUND(comb.litros_total, 0)                                     AS litros_total,
    ROUND(km.km_total / comb.litros_total, 2)                       AS km_l_medio_frota,
    ROUND(comb.custo_combustivel, 2)                                AS custo_combustivel,
    ROUND(ped.custo_pedagio, 2)                                     AS custo_pedagio,
    ROUND((comb.custo_combustivel + ped.custo_pedagio) / km.km_total, 3) AS custo_por_km
FROM km, comb, ped;


-- @consulta: q02_custo_mensal_centro_custo
-- PERGUNTA: Quanto cada centro de custo gastou por mês com combustível e pedágio?
-- Técnica: empilhar as duas fontes com UNION ALL e depois "pivotar" com CASE WHEN
-- (é o mesmo que uma matriz no Power BI com Tipo de Custo nas colunas).
WITH custos AS (
    SELECT strftime('%Y-%m', a.data_hora) AS mes,
           f.centro_custo,
           'COMBUSTIVEL'                  AS tipo_custo,
           a.valor_total                  AS valor
    FROM abastecimentos a
    JOIN frotas f ON f.placa = a.placa
    UNION ALL
    SELECT strftime('%Y-%m', p.data_hora_passagem),
           p.centro_custo,
           'PEDAGIO',
           p.valor_transacao
    FROM pedagios p
)
SELECT
    mes,
    centro_custo,
    ROUND(SUM(CASE WHEN tipo_custo = 'COMBUSTIVEL' THEN valor ELSE 0 END), 2) AS combustivel,
    ROUND(SUM(CASE WHEN tipo_custo = 'PEDAGIO'     THEN valor ELSE 0 END), 2) AS pedagio,
    ROUND(SUM(valor), 2)                                                       AS total
FROM custos
GROUP BY mes, centro_custo
ORDER BY mes, centro_custo;


-- @consulta: q03_ranking_pedagio_por_km
-- PERGUNTA: Quais veículos têm o maior custo de pedágio por km rodado?
-- O ranking é feito DENTRO de cada tipo de veículo (PARTITION BY), porque não é
-- justo comparar um Toco de 2 eixos com um Rodotrem de 9 eixos.
WITH km_veiculo AS (
    SELECT placa, SUM(km_rodado) AS km
    FROM viagens
    GROUP BY placa
),
pedagio_veiculo AS (
    SELECT placa, SUM(valor_transacao) AS valor, COUNT(*) AS passagens
    FROM pedagios
    GROUP BY placa
)
SELECT
    f.placa,
    f.tipo_veiculo,
    f.filial,
    ROUND(k.km, 0)                                     AS km_rodado,
    COALESCE(p.passagens, 0)                           AS passagens,
    ROUND(COALESCE(p.valor, 0), 2)                     AS custo_pedagio,
    ROUND(COALESCE(p.valor, 0) / k.km, 3)              AS pedagio_por_km,
    RANK() OVER (PARTITION BY f.tipo_veiculo
                 ORDER BY COALESCE(p.valor, 0) / k.km DESC) AS ranking_no_tipo,
    ROUND(100.0 * COALESCE(p.valor, 0) / SUM(COALESCE(p.valor, 0)) OVER (), 2) AS pct_do_total_pedagio
FROM frotas f
JOIN km_veiculo k           ON k.placa = f.placa
LEFT JOIN pedagio_veiculo p ON p.placa = f.placa   -- LEFT: veículo sem pedágio também aparece
ORDER BY f.tipo_veiculo, ranking_no_tipo;


-- @consulta: q04_retorno_vazio_sem_eixo_suspenso
-- PERGUNTA: Em quais passagens de pedágio o caminhão voltava VAZIO e mesmo assim
--           pagou pelos eixos que deveriam estar suspensos? Quanto isso custou?
-- O extrato da TAG não diz se o caminhão estava carregado. Essa informação está
-- no TMS (viagens). Por isso ligamos as duas tabelas por PLACA + INTERVALO DE TEMPO:
-- a passagem pertence à viagem se aconteceu entre a saída e a chegada.
WITH passagem_viagem AS (
    SELECT
        p.id_transacao,
        p.data_hora_passagem,
        p.placa,
        p.praca,
        p.categoria_eixos,
        p.valor_transacao,
        v.id_viagem,
        v.id_motorista,
        v.status_carga,
        f.tipo_veiculo,
        f.qtd_eixos,
        f.eixos_suspensiveis,
        f.filial
    FROM pedagios p
    JOIN viagens v
      ON v.placa = p.placa
     AND p.data_hora_passagem BETWEEN v.data_hora_saida AND v.data_hora_chegada
    JOIN frotas f ON f.placa = p.placa
)
SELECT
    id_transacao,
    data_hora_passagem,
    placa,
    tipo_veiculo,
    filial,
    id_motorista,
    id_viagem,
    praca,
    qtd_eixos,
    categoria_eixos AS eixos_cobrados,
    valor_transacao,
    -- Valor de um eixo = valor pago / eixos cobrados. A perda é o que foi pago
    -- pelos eixos que deveriam estar levantados.
    ROUND(valor_transacao / categoria_eixos * eixos_suspensiveis, 2) AS perda_estimada,
    CASE
        WHEN categoria_eixos = qtd_eixos THEN 'NAO SUSPENDEU'
        ELSE 'SUSPENDEU'
    END AS situacao_eixo
FROM passagem_viagem
WHERE status_carga = 'VAZIO'
  AND eixos_suspensiveis > 0          -- Toco não tem eixo suspensível: fica de fora
  AND categoria_eixos = qtd_eixos     -- pagou todos os eixos = não suspendeu
ORDER BY data_hora_passagem;


-- @consulta: q05_km_por_litro_por_abastecimento
-- PERGUNTA: Qual foi o km/l real de cada abastecimento?
-- Método do tanque cheio: km rodados desde o abastecimento ANTERIOR (LAG) divididos
-- pelos litros colocados AGORA. Também calculamos a média móvel dos últimos 3
-- abastecimentos do veículo, que suaviza a variação e mostra a tendência.
WITH base AS (
    SELECT
        a.id_abastecimento,
        a.data_hora,
        a.placa,
        a.id_motorista,
        a.litros,
        a.valor_total,
        a.hodometro,
        a.flag_hodometro_inconsistente,
        f.tipo_veiculo,
        f.modelo,
        f.km_l_referencia,
        LAG(a.hodometro) OVER (PARTITION BY a.placa ORDER BY a.data_hora)                    AS hodometro_anterior,
        LAG(a.flag_hodometro_inconsistente) OVER (PARTITION BY a.placa ORDER BY a.data_hora) AS flag_anterior
    FROM abastecimentos a
    JOIN frotas f ON f.placa = a.placa
),
calculo AS (
    SELECT
        *,
        hodometro - hodometro_anterior                    AS km_desde_ultimo,
        ROUND((hodometro - hodometro_anterior) / litros, 3) AS km_l_real
    FROM base
    WHERE hodometro_anterior IS NOT NULL                -- 1º abastecimento não tem anterior
      AND flag_hodometro_inconsistente = 0              -- descarta erros de digitação
      AND flag_anterior = 0
)
SELECT
    id_abastecimento,
    data_hora,
    placa,
    tipo_veiculo,
    modelo,
    id_motorista,
    litros,
    valor_total,
    km_desde_ultimo,
    km_l_real,
    km_l_referencia,
    ROUND(100.0 * (km_l_real / km_l_referencia - 1), 1) AS desvio_pct,
    ROUND(AVG(km_l_real) OVER (PARTITION BY placa ORDER BY data_hora
                               ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 3) AS km_l_media_movel_3,
    CASE
        WHEN km_l_real < km_l_referencia * 0.80 THEN 'CRITICO'
        WHEN km_l_real < km_l_referencia * 0.92 THEN 'ATENCAO'
        ELSE 'OK'
    END AS faixa_consumo
FROM calculo
ORDER BY placa, data_hora;


-- @consulta: q06_km_l_por_modelo
-- PERGUNTA: Cada modelo de veículo entrega o km/l esperado?
-- Usa a mesma lógica da q05 (repetida aqui porque o SQLite não guarda CTE entre
-- consultas; num banco "de verdade" isso viraria uma VIEW).
WITH base AS (
    SELECT a.placa, a.litros, a.hodometro, a.flag_hodometro_inconsistente AS flag,
           LAG(a.hodometro) OVER (PARTITION BY a.placa ORDER BY a.data_hora) AS hod_ant,
           LAG(a.flag_hodometro_inconsistente) OVER (PARTITION BY a.placa ORDER BY a.data_hora) AS flag_ant
    FROM abastecimentos a
),
valido AS (
    SELECT placa, hodometro - hod_ant AS km, litros
    FROM base
    WHERE hod_ant IS NOT NULL AND flag = 0 AND flag_ant = 0
)
SELECT
    f.tipo_veiculo,
    f.marca,
    f.modelo,
    COUNT(DISTINCT f.placa)                         AS qtd_veiculos,
    ROUND(SUM(v.km) / SUM(v.litros), 3)             AS km_l_real,
    MAX(f.km_l_referencia)                          AS km_l_referencia,
    ROUND(100.0 * (SUM(v.km) / SUM(v.litros) / MAX(f.km_l_referencia) - 1), 1) AS desvio_pct,
    DENSE_RANK() OVER (PARTITION BY f.tipo_veiculo
                       ORDER BY SUM(v.km) / SUM(v.litros) DESC) AS ranking_eficiencia_no_tipo
FROM valido v
JOIN frotas f ON f.placa = v.placa
GROUP BY f.tipo_veiculo, f.marca, f.modelo
ORDER BY f.tipo_veiculo, ranking_eficiencia_no_tipo;


-- @consulta: q07_cobranca_duplicada_pedagio
-- PERGUNTA: A operadora cobrou duas vezes a mesma passagem?
-- Com LAG olhamos a passagem anterior da MESMA placa na MESMA praça. Se foi há
-- menos de 10 minutos, é cobrança em duplicidade: candidata a contestação.
WITH ordenado AS (
    SELECT
        p.*,
        LAG(p.data_hora_passagem) OVER (PARTITION BY p.placa, p.codigo_praca
                                        ORDER BY p.data_hora_passagem) AS passagem_anterior,
        LAG(p.id_transacao)       OVER (PARTITION BY p.placa, p.codigo_praca
                                        ORDER BY p.data_hora_passagem) AS transacao_anterior
    FROM pedagios p
)
SELECT
    id_transacao,
    transacao_anterior,
    placa,
    praca,
    concessionaria,
    passagem_anterior,
    data_hora_passagem,
    ROUND((julianday(data_hora_passagem) - julianday(passagem_anterior)) * 24 * 60, 1) AS minutos_entre,
    valor_transacao AS valor_a_contestar
FROM ordenado
WHERE passagem_anterior IS NOT NULL
  AND (julianday(data_hora_passagem) - julianday(passagem_anterior)) * 24 * 60 < 10
ORDER BY data_hora_passagem;


-- @consulta: q08_abastecimentos_suspeitos_regra
-- PERGUNTA: Quais abastecimentos quebram regras simples de negócio?
-- (Na etapa de Python vamos comparar essas regras com um modelo de Machine Learning.)
WITH kml AS (
    SELECT a.id_abastecimento,
           (a.hodometro - LAG(a.hodometro) OVER (PARTITION BY a.placa ORDER BY a.data_hora)) / a.litros AS km_l_real,
           LAG(a.flag_hodometro_inconsistente) OVER (PARTITION BY a.placa ORDER BY a.data_hora) AS flag_ant
    FROM abastecimentos a
)
SELECT
    a.id_abastecimento,
    a.data_hora,
    a.placa,
    a.id_motorista,
    m.nome AS motorista,
    a.cidade_posto,
    a.litros,
    f.capacidade_tanque_l,
    ROUND(k.km_l_real, 2) AS km_l_real,
    f.km_l_referencia,
    a.valor_total,
    CASE
        WHEN a.litros > f.capacidade_tanque_l              THEN 'LITROS ACIMA DO TANQUE'
        WHEN k.km_l_real < f.km_l_referencia * 0.80        THEN 'KM/L MUITO ABAIXO DO ESPERADO'
    END AS motivo
FROM abastecimentos a
JOIN frotas f      ON f.placa = a.placa
JOIN kml k         ON k.id_abastecimento = a.id_abastecimento
LEFT JOIN motoristas m ON m.id_motorista = a.id_motorista
WHERE a.flag_hodometro_inconsistente = 0
  AND COALESCE(k.flag_ant, 0) = 0
  AND (a.litros > f.capacidade_tanque_l OR k.km_l_real < f.km_l_referencia * 0.80)
ORDER BY a.data_hora;


-- @consulta: q09_ranking_motoristas
-- PERGUNTA: Quais motoristas são mais eficientes e mais disciplinados com o eixo?
-- NTILE(4) divide os motoristas em 4 grupos (quartis) pelo desvio de km/l:
-- quartil 1 = os 25% mais econômicos, quartil 4 = os 25% que mais gastam.
WITH kml AS (
    SELECT a.id_motorista, a.placa, a.litros, a.flag_hodometro_inconsistente AS flag,
           a.hodometro - LAG(a.hodometro) OVER (PARTITION BY a.placa ORDER BY a.data_hora) AS km,
           LAG(a.flag_hodometro_inconsistente) OVER (PARTITION BY a.placa ORDER BY a.data_hora) AS flag_ant
    FROM abastecimentos a
),
consumo AS (
    SELECT k.id_motorista,
           SUM(k.km)                                     AS km,
           SUM(k.litros)                                 AS litros,
           -- km/l esperado ponderado pelos km rodados em cada tipo de veículo
           SUM(k.km) / SUM(k.km / f.km_l_referencia)     AS km_l_esperado
    FROM kml k
    JOIN frotas f ON f.placa = k.placa
    WHERE k.km IS NOT NULL AND k.flag = 0 AND k.flag_ant = 0
    GROUP BY k.id_motorista
),
eixo AS (
    -- Retornos vazios com eixo suspensível: quantos o motorista suspendeu?
    SELECT v.id_motorista,
           COUNT(DISTINCT v.id_viagem) AS viagens_vazias,
           COUNT(DISTINCT CASE WHEN p.categoria_eixos < f.qtd_eixos THEN v.id_viagem END) AS viagens_com_eixo_suspenso
    FROM viagens v
    JOIN frotas f   ON f.placa = v.placa
    JOIN pedagios p ON p.placa = v.placa
                   AND p.data_hora_passagem BETWEEN v.data_hora_saida AND v.data_hora_chegada
    WHERE v.status_carga = 'VAZIO' AND f.eixos_suspensiveis > 0
    GROUP BY v.id_motorista
)
SELECT
    m.id_motorista,
    m.nome,
    m.filial,
    ROUND(c.km, 0)                                         AS km_abastecido,
    ROUND(c.km / c.litros, 3)                              AS km_l_real,
    ROUND(c.km_l_esperado, 3)                              AS km_l_esperado,
    ROUND(100.0 * ((c.km / c.litros) / c.km_l_esperado - 1), 1) AS desvio_consumo_pct,
    e.viagens_vazias,
    ROUND(100.0 * e.viagens_com_eixo_suspenso / e.viagens_vazias, 1) AS pct_conformidade_eixo,
    NTILE(4) OVER (ORDER BY (c.km / c.litros) / c.km_l_esperado DESC) AS quartil_eficiencia
FROM motoristas m
JOIN consumo c   ON c.id_motorista = m.id_motorista
LEFT JOIN eixo e ON e.id_motorista = m.id_motorista
WHERE c.km > 5000            -- ignora quem rodou pouco (amostra pequena)
ORDER BY desvio_consumo_pct DESC;


-- @consulta: q10_saving_potencial
-- PERGUNTA: Quanto dinheiro está na mesa? (o "saving" que a gestão pode buscar)
-- Junta as três frentes de perda numa tabela só, com o % de cada uma.
WITH eixo AS (
    SELECT SUM(p.valor_transacao / p.categoria_eixos * f.eixos_suspensiveis) AS valor,
           COUNT(*) AS ocorrencias
    FROM pedagios p
    JOIN frotas f  ON f.placa = p.placa
    JOIN viagens v ON v.placa = p.placa
                  AND p.data_hora_passagem BETWEEN v.data_hora_saida AND v.data_hora_chegada
    WHERE v.status_carga = 'VAZIO' AND f.eixos_suspensiveis > 0
      AND p.categoria_eixos = f.qtd_eixos
),
duplicidade AS (
    SELECT SUM(valor_transacao) AS valor, COUNT(*) AS ocorrencias
    FROM (
        SELECT valor_transacao, data_hora_passagem,
               LAG(data_hora_passagem) OVER (PARTITION BY placa, codigo_praca
                                             ORDER BY data_hora_passagem) AS anterior
        FROM pedagios
    )
    WHERE (julianday(data_hora_passagem) - julianday(anterior)) * 1440 < 10
),
combustivel AS (
    -- Litros "a mais": o que passou do que o km/l de referência justificaria (com 10% de folga)
    SELECT SUM((a.litros - k.km / (f.km_l_referencia * 0.90)) * a.preco_litro) AS valor,
           COUNT(*) AS ocorrencias
    FROM (
        SELECT id_abastecimento, flag_hodometro_inconsistente AS flag,
               hodometro - LAG(hodometro) OVER (PARTITION BY placa ORDER BY data_hora) AS km,
               LAG(flag_hodometro_inconsistente) OVER (PARTITION BY placa ORDER BY data_hora) AS flag_ant
        FROM abastecimentos
    ) k
    JOIN abastecimentos a ON a.id_abastecimento = k.id_abastecimento
    JOIN frotas f         ON f.placa = a.placa
    WHERE k.flag = 0 AND k.flag_ant = 0
      AND k.km / a.litros < f.km_l_referencia * 0.80
),
frentes AS (
    SELECT 'Retorno vazio sem suspender eixo' AS frente, valor, ocorrencias FROM eixo
    UNION ALL
    SELECT 'Pedágio cobrado em duplicidade', valor, ocorrencias FROM duplicidade
    UNION ALL
    SELECT 'Combustível acima do consumo esperado', valor, ocorrencias FROM combustivel
)
SELECT
    frente,
    ocorrencias,
    ROUND(valor, 2)                                  AS valor_rs,
    ROUND(100.0 * valor / SUM(valor) OVER (), 1)     AS pct_do_saving
FROM frentes
ORDER BY valor_rs DESC;
