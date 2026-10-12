-- =============================================================================
-- 01_criar_tabelas.sql
-- Estrutura (schema) do banco SQLite do projeto.
--
-- Por que escrever o schema na mão em vez de deixar o pandas criar?
--   * Definimos CHAVE PRIMÁRIA (PRIMARY KEY): garante que não entra linha repetida.
--   * Definimos CHAVE ESTRANGEIRA (FOREIGN KEY): garante que toda placa em
--     abastecimentos/pedagios/viagens existe no cadastro de frotas.
--   * Definimos tipos e índices, que deixam as consultas rápidas.
-- É o equivalente aos relacionamentos do modelo no Power BI, só que no banco.
-- =============================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS pedagios;
DROP TABLE IF EXISTS abastecimentos;
DROP TABLE IF EXISTS viagens;
DROP TABLE IF EXISTS frotas;
DROP TABLE IF EXISTS motoristas;

-- Dimensão: motoristas -------------------------------------------------------
CREATE TABLE motoristas (
    id_motorista    TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    filial          TEXT NOT NULL,
    data_admissao   TEXT            -- SQLite guarda data como texto ISO: 'AAAA-MM-DD'
);

-- Dimensão: frotas (cadastro de veículos) ------------------------------------
CREATE TABLE frotas (
    placa                 TEXT PRIMARY KEY,
    tag                   TEXT UNIQUE NOT NULL,
    tipo_veiculo          TEXT NOT NULL,
    marca                 TEXT,
    modelo                TEXT,
    ano_fabricacao        INTEGER,
    qtd_eixos             INTEGER NOT NULL,
    eixos_suspensiveis    INTEGER NOT NULL DEFAULT 0,
    km_l_referencia       REAL NOT NULL,
    capacidade_tanque_l   REAL NOT NULL,
    filial                TEXT NOT NULL,
    centro_custo          TEXT NOT NULL,
    id_motorista_titular  TEXT REFERENCES motoristas(id_motorista)
);

-- Fato: viagens (vindas do TMS) ----------------------------------------------
CREATE TABLE viagens (
    id_viagem          TEXT PRIMARY KEY,
    placa              TEXT NOT NULL REFERENCES frotas(placa),
    id_motorista       TEXT NOT NULL REFERENCES motoristas(id_motorista),
    origem             TEXT,
    destino            TEXT,
    data_hora_saida    TEXT NOT NULL,   -- 'AAAA-MM-DD HH:MM:SS'
    data_hora_chegada  TEXT NOT NULL,
    km_rodado          REAL,
    status_carga       TEXT CHECK (status_carga IN ('CARREGADO', 'VAZIO')),
    peso_carga_kg      INTEGER
);

-- Fato: abastecimentos (extrato do cartão combustível) -----------------------
CREATE TABLE abastecimentos (
    id_abastecimento   TEXT PRIMARY KEY,
    data_hora          TEXT NOT NULL,
    placa              TEXT NOT NULL REFERENCES frotas(placa),
    id_motorista       TEXT REFERENCES motoristas(id_motorista),
    cidade_posto       TEXT,
    combustivel        TEXT,
    litros             REAL NOT NULL CHECK (litros > 0),
    preco_litro        REAL,
    valor_total        REAL,
    hodometro          INTEGER,
    -- Flags de qualidade calculadas no ETL (1 = problema encontrado)
    flag_litros_acima_tanque   INTEGER DEFAULT 0,
    flag_hodometro_inconsistente INTEGER DEFAULT 0
);

-- Fato: pedágios (extrato da operadora de TAG) -------------------------------
CREATE TABLE pedagios (
    id_transacao        TEXT PRIMARY KEY,
    data_hora_passagem  TEXT NOT NULL,
    placa               TEXT NOT NULL REFERENCES frotas(placa),
    tag                 TEXT,
    codigo_praca        TEXT,
    praca               TEXT,
    rodovia             TEXT,
    concessionaria      TEXT,
    categoria_eixos     INTEGER,
    valor_transacao     REAL,
    centro_custo        TEXT
);

-- Índices: aceleram filtros e JOINs por placa e data ------------------------
CREATE INDEX idx_viagens_placa_saida   ON viagens (placa, data_hora_saida);
CREATE INDEX idx_abast_placa_data      ON abastecimentos (placa, data_hora);
CREATE INDEX idx_pedagios_placa_data   ON pedagios (placa, data_hora_passagem);
