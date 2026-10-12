"""
ETAPA 0 - GERAÇÃO DE DADOS FICTÍCIOS
====================================

Este script cria os arquivos CSV "brutos" do projeto, imitando o que chegaria
de três sistemas diferentes numa transportadora:

    frotas.csv          -> cadastro de veículos (planilha da gestão de frota)
    motoristas.csv      -> cadastro de motoristas (RH)
    viagens.csv         -> viagens registradas no TMS (sistema de transporte)
    abastecimentos.csv  -> extrato do cartão combustível
    pedagios.csv        -> extrato da operadora de TAG de pedágio

Nenhum dado aqui é real. A empresa "TransLog Fictícia" não existe.

Para deixar o projeto realista, o script também injeta PROBLEMAS que
aparecem no mundo real e que as próximas etapas precisam encontrar:

    * placas digitadas fora do padrão ("abc-1d23" em vez de "ABC1D23")
    * linhas duplicadas na exportação do extrato de pedágio
    * centro de custo vazio em parte das transações de pedágio
    * hodômetro digitado errado no abastecimento
    * abastecimentos "inflados" (litros a mais do que o caminhão consumiu)
    * cobrança de pedágio em duplicidade (mesma praça, minutos depois)
    * retorno vazio sem suspender o eixo (paga pedágio a mais)

Como rodar:  python src/01_gerar_dados.py
"""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Semente fixa: toda vez que rodar, os "números aleatórios" saem iguais.
# Isso deixa o projeto reprodutível (quem clonar o repositório vê os mesmos números).
rng = np.random.default_rng(42)

PASTA_RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
PASTA_RAW.mkdir(parents=True, exist_ok=True)

DATA_INICIO = datetime(2025, 10, 1)
DATA_FIM = datetime(2026, 9, 30, 23, 59)

# ---------------------------------------------------------------------------
# 1. Tabelas de referência (o "conhecimento do negócio")
# ---------------------------------------------------------------------------

# Cada tipo de veículo tem: eixos totais, eixos que podem ser suspensos,
# consumo esperado (km/l) e capacidade de tanque (litros).
TIPOS_VEICULO = {
    "Toco":                 {"eixos": 2, "suspensiveis": 0, "km_l": 4.6, "tanque": 275},
    "Truck":                {"eixos": 3, "suspensiveis": 1, "km_l": 3.7, "tanque": 300},
    "Carreta 2 eixos":      {"eixos": 5, "suspensiveis": 1, "km_l": 2.7, "tanque": 640},
    "Carreta 3 eixos":      {"eixos": 6, "suspensiveis": 1, "km_l": 2.4, "tanque": 640},
    "Bitrem":               {"eixos": 7, "suspensiveis": 2, "km_l": 2.1, "tanque": 900},
    "Rodotrem":             {"eixos": 9, "suspensiveis": 2, "km_l": 1.8, "tanque": 1000},
}

# Modelo de cavalo/caminhão possível para cada tipo
MODELOS = {
    "Toco":            [("Volkswagen", "Delivery 11.180"), ("Mercedes-Benz", "Accelo 1316")],
    "Truck":           [("Volkswagen", "Constellation 24.280"), ("Mercedes-Benz", "Atego 2430")],
    "Carreta 2 eixos": [("Volvo", "FH 460"), ("Scania", "R 450"), ("Mercedes-Benz", "Actros 2546")],
    "Carreta 3 eixos": [("Volvo", "FH 540"), ("Scania", "R 450"), ("DAF", "XF 480")],
    "Bitrem":          [("Volvo", "FH 540"), ("Scania", "R 540")],
    "Rodotrem":        [("Volvo", "FH 540"), ("Scania", "R 560")],
}

FILIAIS = {
    "Jundiaí-SP":        {"cc": "CC-1010", "cc_nome": "Distribuição Grande SP", "uf": "SP"},
    "Ribeirão Preto-SP": {"cc": "CC-1020", "cc_nome": "Transferência Interior SP", "uf": "SP"},
    "Belo Horizonte-MG": {"cc": "CC-2010", "cc_nome": "Distribuição MG", "uf": "MG"},
    "Curitiba-PR":       {"cc": "CC-3010", "cc_nome": "Distribuição PR/SC", "uf": "PR"},
}

# Praças de pedágio: código -> (nome, rodovia, concessionária, tarifa por eixo R$)
# Nomes de concessionárias e tarifas são fictícios.
PRACAS = {
    "P01": ("Praça Campo Limpo",  "SP-348", "Rota das Bandeiras S.A.", 11.40),
    "P02": ("Praça Valinhos",     "SP-330", "Rota das Bandeiras S.A.", 10.90),
    "P03": ("Praça Limeira",      "SP-330", "Caminhos do Interior",     9.70),
    "P04": ("Praça Pirassununga", "SP-330", "Caminhos do Interior",     8.80),
    "P05": ("Praça Sertãozinho",  "SP-322", "Caminhos do Interior",     7.60),
    "P06": ("Praça Atibaia",      "BR-381", "Via Mineira Sul",          4.20),
    "P07": ("Praça Cambuí",       "BR-381", "Via Mineira Sul",          4.20),
    "P08": ("Praça Carmópolis",   "BR-381", "Via Mineira Sul",          4.20),
    "P09": ("Praça Itaperuçu",    "BR-476", "Rodovias do Paraná",       6.30),
    "P10": ("Praça Registro",     "BR-116", "Litoral Sul Rodovias",     3.90),
    "P11": ("Praça Juquitiba",    "BR-116", "Litoral Sul Rodovias",     3.90),
    "P12": ("Praça Garuva",       "BR-376", "Litoral Sul Rodovias",     3.10),
    "P13": ("Praça Itatiba",      "SP-065", "Rota das Bandeiras S.A.",  7.90),
    "P14": ("Praça Betim",        "BR-381", "Via Mineira Sul",          5.10),
}

# Rotas por filial: (destino, km de ida, [praças no caminho de ida], tipo de rota)
# "curta" é atendida por Toco/Truck, "longa" por carretas/bitrem/rodotrem.
ROTAS = {
    "Jundiaí-SP": [
        ("São Paulo-SP",        60, ["P01"],                      "curta"),
        ("Campinas-SP",         45, ["P02"],                      "curta"),
        ("Bragança Paulista-SP", 70, ["P13"],                     "curta"),
        ("Ribeirão Preto-SP",  265, ["P02", "P03", "P04"],        "longa"),
        ("Belo Horizonte-MG",  540, ["P13", "P06", "P07", "P08"], "longa"),
        ("Curitiba-PR",        460, ["P01", "P11", "P10"],        "longa"),
    ],
    "Ribeirão Preto-SP": [
        ("Sertãozinho-SP",      25, ["P05"],                      "curta"),
        ("Franca-SP",           90, [],                           "curta"),
        ("Campinas-SP",        220, ["P04", "P03"],               "longa"),
        ("São Paulo-SP",       315, ["P04", "P03", "P02", "P01"], "longa"),
    ],
    "Belo Horizonte-MG": [
        ("Contagem-MG",         25, [],                           "curta"),
        ("Betim-MG",            35, ["P14"],                      "curta"),
        ("São Paulo-SP",       585, ["P08", "P07", "P06"],        "longa"),
        ("Jundiaí-SP",         540, ["P08", "P07", "P06", "P13"], "longa"),
    ],
    "Curitiba-PR": [
        ("Ponta Grossa-PR",    115, ["P09"],                      "curta"),
        ("Joinville-SC",       130, ["P12"],                      "curta"),
        ("São Paulo-SP",       410, ["P10", "P11"],               "longa"),
        ("Jundiaí-SP",         460, ["P10", "P11", "P01"],        "longa"),
    ],
}

# ---------------------------------------------------------------------------
# 2. Funções auxiliares
# ---------------------------------------------------------------------------

LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def gerar_placa_mercosul() -> str:
    """Placa no padrão Mercosul: 3 letras, 1 número, 1 letra, 2 números (ex.: RTA4B21)."""
    l = rng.choice(LETRAS, 4)
    n = rng.integers(0, 10, 3)
    return f"{l[0]}{l[1]}{l[2]}{n[0]}{l[3]}{n[1]}{n[2]}"


def bagunca_placa(placa: str) -> str:
    """Simula digitação fora do padrão: minúsculas e/ou hífen."""
    opcao = rng.integers(0, 3)
    if opcao == 0:
        return placa.lower()
    if opcao == 1:
        return placa[:3] + "-" + placa[3:]
    return " " + placa.lower()[:3] + "-" + placa[3:] + " "


def preco_diesel(data: datetime, uf: str) -> float:
    """Preço do diesel S10 varia com o mês (tendência leve) e com o estado."""
    meses = (data.year - DATA_INICIO.year) * 12 + data.month - DATA_INICIO.month
    base = 6.05 + 0.025 * meses + 0.12 * np.sin(meses / 2)
    ajuste_uf = {"SP": 0.0, "MG": 0.09, "PR": -0.06}[uf]
    return round(base + ajuste_uf + rng.normal(0, 0.06), 2)


# ---------------------------------------------------------------------------
# 3. Cadastro de frota e motoristas
# ---------------------------------------------------------------------------

# Quantos veículos de cada tipo por filial
COMPOSICAO = {
    "Jundiaí-SP":        {"Toco": 4, "Truck": 6, "Carreta 2 eixos": 5, "Carreta 3 eixos": 7, "Bitrem": 4, "Rodotrem": 2},
    "Ribeirão Preto-SP": {"Toco": 2, "Truck": 4, "Carreta 3 eixos": 5, "Bitrem": 4, "Rodotrem": 3},
    "Belo Horizonte-MG": {"Toco": 3, "Truck": 4, "Carreta 2 eixos": 3, "Carreta 3 eixos": 5, "Bitrem": 2},
    "Curitiba-PR":       {"Toco": 3, "Truck": 4, "Carreta 2 eixos": 3, "Carreta 3 eixos": 4, "Bitrem": 2},
}

frotas = []
placas_usadas = set()
for filial, tipos in COMPOSICAO.items():
    for tipo, qtd in tipos.items():
        for _ in range(qtd):
            placa = gerar_placa_mercosul()
            while placa in placas_usadas:
                placa = gerar_placa_mercosul()
            placas_usadas.add(placa)
            marca, modelo = MODELOS[tipo][rng.integers(0, len(MODELOS[tipo]))]
            info = TIPOS_VEICULO[tipo]
            ano = int(rng.integers(2015, 2025))
            # Caminhões mais velhos consomem um pouco mais (fator de desgaste)
            desgaste = 1 - (2025 - ano) * 0.006
            frotas.append({
                "placa": placa,
                "tag": f"TAG{rng.integers(10**9, 10**10)}",
                "tipo_veiculo": tipo,
                "marca": marca,
                "modelo": modelo,
                "ano_fabricacao": ano,
                "qtd_eixos": info["eixos"],
                "eixos_suspensiveis": info["suspensiveis"],
                "km_l_referencia": info["km_l"],   # o que o fabricante/gestão espera
                "capacidade_tanque_l": info["tanque"],
                "filial": filial,
                "centro_custo": FILIAIS[filial]["cc"],
                "_desgaste": desgaste,              # coluna interna, não vai para o CSV
            })

df_frotas = pd.DataFrame(frotas)

PRIMEIROS = ["Carlos", "José", "Marcos", "Paulo", "Antônio", "Luiz", "Rafael", "Fernando", "Ricardo",
             "André", "Rodrigo", "Eduardo", "Sérgio", "Fábio", "Márcio", "Adriana", "Juliana", "Cláudio",
             "Roberto", "Wagner", "Edson", "Gilberto", "Valdir", "Renato", "Patrícia", "Leandro", "Diego"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Pereira", "Costa", "Rodrigues", "Almeida",
              "Nascimento", "Lima", "Araújo", "Fernandes", "Carvalho", "Gomes", "Martins", "Rocha", "Ribeiro"]

motoristas = []
for i, row in df_frotas.iterrows():
    motoristas.append({
        "id_motorista": f"M{i + 1:03d}",
        "nome": f"{rng.choice(PRIMEIROS)} {rng.choice(SOBRENOMES)}",
        "filial": row["filial"],
        "data_admissao": (datetime(2012, 1, 1) + timedelta(days=int(rng.integers(0, 4700)))).date(),
        # Perfil de condução (escondido): eficiência no consumo e disciplina com o eixo
        "_eficiencia": float(np.clip(rng.normal(1.0, 0.05), 0.85, 1.10)),
        "_disciplina_eixo": float(rng.beta(6, 2)),
    })
# 8 motoristas reservas (cobrem folgas)
for j, filial in enumerate(list(FILIAIS) * 2):
    motoristas.append({
        "id_motorista": f"M{len(df_frotas) + j + 1:03d}",
        "nome": f"{rng.choice(PRIMEIROS)} {rng.choice(SOBRENOMES)}",
        "filial": filial,
        "data_admissao": (datetime(2018, 1, 1) + timedelta(days=int(rng.integers(0, 2500)))).date(),
        "_eficiencia": float(np.clip(rng.normal(0.97, 0.05), 0.85, 1.10)),
        "_disciplina_eixo": float(rng.beta(4, 3)),
    })
df_motoristas = pd.DataFrame(motoristas)
df_frotas["id_motorista_titular"] = df_motoristas["id_motorista"].iloc[: len(df_frotas)].values

# ---------------------------------------------------------------------------
# 4. Simulação da operação: viagens, abastecimentos e pedágios
# ---------------------------------------------------------------------------

viagens, abastecimentos, pedagios = [], [], []
id_viagem = id_abast = id_pedagio = 0

# Alguns motoristas "problema" inflam abastecimentos com frequência (desvio de combustível)
motoristas_suspeitos = set(rng.choice(df_motoristas["id_motorista"], 4, replace=False))

for _, v in df_frotas.iterrows():
    filial = v["filial"]
    uf = FILIAIS[filial]["uf"]
    curta = v["tipo_veiculo"] in ("Toco", "Truck")
    rotas_possiveis = [r for r in ROTAS[filial] if (r[3] == "curta") == curta]
    reservas = df_motoristas[(df_motoristas["filial"] == filial) &
                             (df_motoristas["id_motorista"] > df_motoristas["id_motorista"].iloc[len(df_frotas) - 1])]

    relogio = DATA_INICIO + timedelta(hours=int(rng.integers(5, 9)))
    hodometro = int(rng.integers(80_000, 650_000))
    tanque = v["capacidade_tanque_l"] * rng.uniform(0.6, 1.0)  # litros no tanque agora

    while relogio < DATA_FIM:
        destino, km_ida, pracas_ida, _ = rotas_possiveis[rng.integers(0, len(rotas_possiveis))]
        # Motorista titular na maioria das viagens, reserva em ~10%
        if rng.random() < 0.10 and len(reservas):
            mot = reservas.sample(1, random_state=int(rng.integers(0, 10**6))).iloc[0]
        else:
            mot = df_motoristas[df_motoristas["id_motorista"] == v["id_motorista_titular"]].iloc[0]

        # Ida carregado, volta vazia (75% das vezes) ou com carga de retorno
        for perna in ("ida", "volta"):
            origem, dest = (filial, destino) if perna == "ida" else (destino, filial)
            status_carga = "CARREGADO" if perna == "ida" or rng.random() < 0.25 else "VAZIO"
            km = km_ida * rng.uniform(0.97, 1.06)
            velocidade = rng.uniform(52, 68) if not curta else rng.uniform(35, 48)
            saida = relogio
            chegada = saida + timedelta(hours=km / velocidade + rng.uniform(0.2, 1.0))
            id_viagem += 1

            # Eixo suspenso? Só faz sentido em retorno vazio e se o veículo tiver eixo suspensível
            if status_carga == "VAZIO" and v["eixos_suspensiveis"] > 0:
                suspendeu = rng.random() < mot["_disciplina_eixo"]
            else:
                suspendeu = False

            viagens.append({
                "id_viagem": f"V{id_viagem:06d}",
                "placa": v["placa"],
                "id_motorista": mot["id_motorista"],
                "origem": origem,
                "destino": dest,
                "data_hora_saida": saida,
                "data_hora_chegada": chegada,
                "km_rodado": round(km, 1),
                "status_carga": status_carga,
                "peso_carga_kg": int(rng.uniform(0.55, 1.0) * v["qtd_eixos"] * 5200) if status_carga == "CARREGADO" else 0,
            })

            # Pedágios no trajeto
            pracas = pracas_ida if perna == "ida" else list(reversed(pracas_ida))
            for k, cod in enumerate(pracas):
                nome, rodovia, conc, tarifa = PRACAS[cod]
                eixos_cobrados = v["qtd_eixos"] - (v["eixos_suspensiveis"] if suspendeu else 0)
                passagem = saida + (chegada - saida) * (k + 1) / (len(pracas) + 1)
                id_pedagio += 1
                registro = {
                    "id_transacao": f"T{id_pedagio:07d}",
                    "data_hora_passagem": passagem,
                    "placa": v["placa"],
                    "tag": v["tag"],
                    "codigo_praca": cod,
                    "praca": nome,
                    "rodovia": rodovia,
                    "concessionaria": conc,
                    "categoria_eixos": int(eixos_cobrados),
                    "valor_transacao": round(tarifa * eixos_cobrados, 2),
                    "centro_custo": v["centro_custo"],
                }
                pedagios.append(registro)
                # 0,4% de chance de a operadora cobrar duas vezes a mesma passagem
                if rng.random() < 0.004:
                    id_pedagio += 1
                    dup = dict(registro)
                    dup["id_transacao"] = f"T{id_pedagio:07d}"
                    dup["data_hora_passagem"] = passagem + timedelta(minutes=int(rng.integers(1, 6)))
                    pedagios.append(dup)

            # Consumo real da perna (o "verdadeiro" km/l, que ninguém vê diretamente)
            fator_carga = 0.93 if status_carga == "CARREGADO" else 1.12
            km_l_real = v["km_l_referencia"] * v["_desgaste"] * mot["_eficiencia"] * fator_carga * rng.normal(1, 0.03)
            tanque -= km / km_l_real
            hodometro += km
            relogio = chegada

            # Abastece no destino se o tanque estiver abaixo de 40% (método tanque cheio)
            if tanque < 0.40 * v["capacidade_tanque_l"]:
                litros = v["capacidade_tanque_l"] - max(tanque, 0)
                tanque = v["capacidade_tanque_l"]
                litros_informados = litros
                fraude = 0
                # Fraude: litros a mais lançados no cartão (abasteceu galão/outro veículo)
                chance_fraude = 0.18 if mot["id_motorista"] in motoristas_suspeitos else 0.006
                if rng.random() < chance_fraude:
                    litros_informados = litros * rng.uniform(1.18, 1.45)
                    fraude = 1
                hod_digitado = int(hodometro)
                if rng.random() < 0.004:  # erro de digitação do frentista
                    hod_digitado = int(str(hod_digitado)[:-1] + "0" + str(hod_digitado)[-1])
                posto_uf = dest.split("-")[-1]
                preco = preco_diesel(chegada, posto_uf if posto_uf in ("SP", "MG", "PR") else uf)
                id_abast += 1
                abastecimentos.append({
                    "id_abastecimento": f"A{id_abast:06d}",
                    "data_hora": chegada + timedelta(minutes=int(rng.integers(10, 50))),
                    "placa": v["placa"],
                    "id_motorista": mot["id_motorista"],
                    "cidade_posto": dest,
                    "combustivel": "Diesel S10",
                    "litros": round(litros_informados, 2),
                    "preco_litro": preco,
                    "valor_total": round(litros_informados * preco, 2),
                    "hodometro": hod_digitado,
                    "_fraude": fraude,
                })

            # Tempo parado entre as pernas (descarga, carga, descanso)
            relogio += timedelta(hours=float(rng.uniform(2, 10) if curta else rng.uniform(6, 20)))

        # Folga entre viagens; às vezes manutenção (vários dias parado)
        relogio += timedelta(hours=float(rng.uniform(4, 30)))
        if rng.random() < 0.03:
            relogio += timedelta(days=int(rng.integers(3, 10)))

df_viagens = pd.DataFrame(viagens)
df_abast = pd.DataFrame(abastecimentos)
df_ped = pd.DataFrame(pedagios)

# Corta o que passou da data final do período
df_viagens = df_viagens[df_viagens["data_hora_saida"] <= DATA_FIM]
df_abast = df_abast[df_abast["data_hora"] <= DATA_FIM]
df_ped = df_ped[df_ped["data_hora_passagem"] <= DATA_FIM]

# ---------------------------------------------------------------------------
# 5. Sujeira de dados (o que o ETL vai ter que tratar)
# ---------------------------------------------------------------------------

# 5.1 Placas fora do padrão em ~3% das linhas de abastecimento e pedágio
for df in (df_abast, df_ped):
    idx = df.sample(frac=0.03, random_state=1).index
    df.loc[idx, "placa"] = df.loc[idx, "placa"].apply(bagunca_placa)

# 5.2 Centro de custo vazio em ~2% do pedágio
idx = df_ped.sample(frac=0.02, random_state=2).index
df_ped.loc[idx, "centro_custo"] = None

# 5.3 Linhas repetidas na exportação (mesmo id_transacao) em ~0,8% do pedágio
duplicadas = df_ped.sample(frac=0.008, random_state=3)
df_ped = pd.concat([df_ped, duplicadas]).sort_values("data_hora_passagem")

# Formata datas como texto, do jeito que viriam num CSV exportado
df_abast["data_hora"] = df_abast["data_hora"].dt.strftime("%d/%m/%Y %H:%M")
df_ped["data_hora_passagem"] = df_ped["data_hora_passagem"].dt.strftime("%d/%m/%Y %H:%M:%S")
for c in ("data_hora_saida", "data_hora_chegada"):
    df_viagens[c] = df_viagens[c].dt.strftime("%Y-%m-%d %H:%M")

# ---------------------------------------------------------------------------
# 6. Salva os CSVs (colunas que começam com "_" são internas e não vão para o arquivo)
# ---------------------------------------------------------------------------

def salvar(df: pd.DataFrame, nome: str, **kwargs) -> None:
    colunas = [c for c in df.columns if not c.startswith("_")]
    df[colunas].to_csv(PASTA_RAW / nome, index=False, **kwargs)
    print(f"  {nome:22s} {len(df):>7,} linhas")


print("Gerando CSVs em", PASTA_RAW)
salvar(df_frotas, "frotas.csv")
salvar(df_motoristas, "motoristas.csv")
salvar(df_viagens, "viagens.csv")
# O extrato do cartão combustível vem no padrão brasileiro: ";" e vírgula decimal
salvar(df_abast, "abastecimentos.csv", sep=";", decimal=",")
salvar(df_ped, "pedagios.csv")

# GABARITO: quais abastecimentos foram realmente inflados. No mundo real ninguém
# tem essa resposta pronta; aqui ela existe só para medir se o modelo de
# Machine Learning da etapa 4 acerta. O ETL NÃO lê este arquivo.
df_abast[["id_abastecimento", "_fraude"]].rename(columns={"_fraude": "fraude"}).to_csv(
    PASTA_RAW.parent / "gabarito_fraudes.csv", index=False)
print("Abastecimentos inflados (gabarito):", int(df_abast["_fraude"].sum()))
print("Motoristas com padrão suspeito (gabarito):", sorted(motoristas_suspeitos))
