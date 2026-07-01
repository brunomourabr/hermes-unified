#!/usr/bin/env python3
"""
PREPARAÇÃO DOS DATASETS DE MARKETING CAUSAL
Consolida todos os datasets encontrados e prepara para análise comparativa.
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from pathlib import Path

OUTPUT = Path("/opt/projetos/hermes-unified/datasets")
OUTPUT.mkdir(parents=True, exist_ok=True)

print("=" * 70)
print("PREPARAÇÃO DE DATASETS - MARKETING CAUSAL")
print("=" * 70)

datasets = {}

# ============================================================
# 1. SHENZHEN MMM (Dados reais de TV Manufacturing)
# ============================================================
print("\n[1/5] Shenzhen MMM (China - TV Manufacturing)")
df_sz = pd.read_excel("/tmp/shenzhen_mmm.xlsx")
print(f"  Shape: {df_sz.shape}")
print(f"  Periodo: {df_sz['DATE'].min()} a {df_sz['DATE'].max()}")
print(f"  Marcas: {df_sz['TV Manufacturing Brand'].nunique()}")

# Renomear colunas para padrao
df_sz = df_sz.rename(columns={
    "DATE": "date",
    "SALES ($)": "sales",
    "DEMAND ": "demand",
    "Advertising Expenses (SMS)": "spend_sms",
    "Advertising Expenses(Newspaper ads)": "spend_newspaper",
    "Advertising Expenses(Radio)": "spend_radio",
    "Advertising Expenses(TV)": "spend_tv",
    "Advertising Expenses(Internet)": "spend_internet",
    "GRP(SMS)": "grp_sms",
    "GRP (NewPaper ads)": "grp_newspaper",
    "GRP(Radio": "grp_radio",
    "GRP(Internet)": "grp_internet",
    "GRP(TV)": "grp_tv",
    "TV Manufacturing Brand": "brand",
    "Consumer Price Index (CPI)": "cpi",
    "Consumer Confidence Index(CCI)": "cci",
    "Producer Price Index (PPI)": "ppi",
    "Unit Price ($)": "unit_price",
    "POS/ Supply Data": "pos_supply",
})
df_sz["date"] = pd.to_datetime(df_sz["date"])

# Filtrar apenas uma marca para simplicidade (a principal)
brand_main = df_sz["brand"].value_counts().index[0]
df_sz_main = df_sz[df_sz["brand"] == brand_main].copy()
print(f"  Marca principal: {brand_main} ({len(df_sz_main)} linhas)")

# Agregar para weekly (dados sao diarios)
df_sz_main = df_sz_main.set_index("date")
df_sz_weekly = df_sz_main.resample("W-MON").agg({
    "sales": "sum",
    "demand": "sum",
    "spend_sms": "sum",
    "spend_newspaper": "sum",
    "spend_radio": "sum",
    "spend_tv": "sum",
    "spend_internet": "sum",
    "grp_sms": "mean",
    "grp_newspaper": "mean",
    "grp_radio": "mean",
    "grp_internet": "mean",
    "grp_tv": "mean",
    "cpi": "last",
    "cci": "last",
    "ppi": "last",
    "unit_price": "mean",
    "pos_supply": "sum",
}).dropna()
print(f"  Weekly aggregation: {len(df_sz_weekly)} semanas")

df_sz_weekly.to_csv(OUTPUT / "shenzhen_mmm_weekly.csv")
datasets["shenzhen"] = {"df": df_sz_weekly, "desc": f"Dados reais de TV Manufacturing ({len(df_sz_weekly)} semanas, 5 canais de mídia)", "n_rows": len(df_sz_weekly), "n_channels": 5}

# ============================================================
# 2. OBSERVED MMM (deejayrusso - TV + Search)
# ============================================================
print("\n[2/5] Observed MMM (deejayrusso)")
df_obs = pd.read_csv("/tmp/observed_mmm.csv")
print(f"  Shape: {df_obs.shape}")

df_obs = df_obs.rename(columns={
    "time.index": "time",
    "tv.spend": "spend_tv",
    "search.spend": "spend_search",
    "total.spend": "spend_total",
    "brand.sales": "sales_brand",
    "revenue": "revenue",
    "profit": "profit",
    "competitor.sales": "sales_competitor",
})
df_obs["date"] = pd.date_range("2020-01-06", periods=len(df_obs), freq="W-MON")
df_obs.to_csv(OUTPUT / "observed_mmm_weekly.csv", index=False)
datasets["observed"] = {"df": df_obs, "desc": f"Dados de TV + Search com revenue e profit ({len(df_obs)} semanas)", "n_rows": len(df_obs), "n_channels": 2}

# ============================================================
# 3. GOOGLE MERIDIAN - Dados sintéticos (via gerador)
# ============================================================
print("\n[3/5] Google Meridian - Dados sintéticos replicados")
# Replicar a estrutura do Meridian demo: 104 semanas, 3 canais
np.random.seed(42)
n_weeks = 104
dates = pd.date_range("2023-01-02", periods=n_weeks, freq="W-MON")
t = np.arange(n_weeks)

meridian_data = pd.DataFrame({
    "date": dates,
    "spend_tv": np.random.uniform(5000, 50000, n_weeks),
    "spend_search": np.random.uniform(2000, 30000, n_weeks),
    "spend_social": np.random.uniform(1000, 20000, n_weeks),
    "spend_display": np.random.uniform(500, 10000, n_weeks),
    "revenue": np.random.normal(500000, 100000, n_weeks),
})

# Adicionar sazonalidade realista
meridian_data["revenue"] = meridian_data["revenue"] * (1 + 0.3 * np.sin(2 * np.pi * t / 52))
meridian_data["spend_tv"] *= (1 + 0.5 * np.sin(2 * np.pi * t / 52 + 0.5))

meridian_data.to_csv(OUTPUT / "meridian_style_synthetic.csv", index=False)
datasets["meridian_style"] = {"df": meridian_data, "desc": f"Dados estilo Google Meridian ({n_weeks} semanas, 4 canais)", "n_rows": n_weeks, "n_channels": 4}

# ============================================================
# 4. PyMC-Marketing - Dados do tutorial oficial
# ============================================================
print("\n[4/5] PyMC-Marketing - Dados do tutorial oficial (replicados)")
n2 = 179
dates2 = pd.date_range("2018-04-01", periods=n2, freq="W-MON")
rng = np.random.default_rng(42)

x1 = np.array([rng.uniform(0.05, 0.3) if rng.random() < 0.7 else rng.uniform(0.6, 1.0) for _ in range(n2)])
x2 = np.array([rng.uniform(0, 0.1) if rng.random() < 0.5 else rng.uniform(0.5, 1.0) for _ in range(n2)])

tt = np.arange(n2)
trend = 0.005 * tt
seas = 0.1 * np.sin(2 * np.pi * tt / 52) + 0.05 * np.sin(4 * np.pi * tt / 52)
event_1 = np.isin(tt % 52, [10, 11]).astype(float)
event_2 = np.isin(tt % 52, [15, 16]).astype(float)

# Parametros verdadeiros conhecidos
alpha_true = [0.4, 0.2]
lam_true = [4.0, 3.0]
beta_true = [3.0, 2.0]

def geo_adstock(x, a, l=8):
    w = np.array([a**i for i in range(l+1)])
    return np.convolve(x, w/w.sum(), mode="same")
def log_sat(x, l):
    return (1 - np.exp(-l * x)) / (1 - np.exp(-l))

x1_a = geo_adstock(x1, alpha_true[0])
x2_a = geo_adstock(x2, alpha_true[1])
x1_s = log_sat(x1_a, lam_true[0])
x2_s = log_sat(x2_a, lam_true[1])
y = 100 * (0.5 + trend + seas + 1.5*event_1 + 2.5*event_2 + beta_true[0]*x1_s + beta_true[1]*x2_s + rng.normal(0, 0.05, n2))

df_pymc = pd.DataFrame({
    "date_week": dates2, "spend_social": x1 * 100000, "spend_tv": x2 * 500000,
    "x1": x1, "x2": x2, "y": y,
    "event_1": event_1, "event_2": event_2, "t": tt
})
df_pymc.to_csv(OUTPUT / "pymc_tutorial_synthetic.csv", index=False)
datasets["pymc_tutorial"] = {"df": df_pymc, "desc": f"Dados do tutorial PyMC-Marketing ({n2} semanas, 2 canais, parametros verdadeiros conhecidos)", "n_rows": n2, "n_channels": 2, "true_params": {"adstock": alpha_true, "saturation": lam_true, "beta": beta_true}}

# ============================================================
# 5. CausalPy - Dados para Synthetic Control
# ============================================================
print("\n[5/5] CausalPy - Dados para Synthetic Control")
np.random.seed(42)
np_pre, np_post = 100, 50
tp = np.arange(np_pre + np_post)

data = {"time": tp}
data["treated"] = [10 + 0.02*t + np.random.normal(0, 0.5) for t in tp[:np_pre]] + \
                  [10 + 0.02*t + 3.0 + np.random.normal(0, 0.5) for t in range(np_post)]
for i in range(10):
    data[f"control_{i}"] = [10 + 0.02*t + np.random.normal(0, 1) + i*0.3 for t in tp]

# Diferentes niveis de efeito
for eff, label in [(0, "zero_effect"), (1, "small_effect"), (5, "large_effect")]:
    y = [10 + 0.02*t + np.random.normal(0, 0.5) for t in tp[:np_pre]] + \
        [10 + 0.02*t + eff + np.random.normal(0, 0.5) for t in range(np_post)]
    data[f"treated_{label}"] = y

df_sc = pd.DataFrame(data)
df_sc.to_csv(OUTPUT / "causalpy_synthetic_control.csv", index=False)
datasets["causalpy_sc"] = {"df": df_sc, "desc": f"Dados para Synthetic Control (150 periodos, 10 controles, 4 cenarios de efeito)", "n_rows": len(df_sc), "n_controls": 10}

# ============================================================
# RELATÓRIO FINAL
# ============================================================
print("\n" + "=" * 70)
print("DATASETS PRONTOS")
print("=" * 70)

for name, info in datasets.items():
    print(f"\n📊 {name}")
    print(f"   {info['desc']}")
    print(f"   Arquivo: {OUTPUT / name}.csv")
    if "n_channels" in info:
        print(f"   Canais: {info['n_channels']}")
    if "true_params" in info:
        print(f"   Parâmetros verdadeiros: {info['true_params']}")

# Salvar indice
index_df = pd.DataFrame([{
    "dataset": name,
    "desc": info["desc"],
    "n_rows": info.get("n_rows", info["df"].shape[0]),
    "file": f"{name}.csv",
} for name, info in datasets.items()])
index_df.to_csv(OUTPUT / "_dataset_index.csv", index=False)

print(f"\n✅ Todos os datasets em: {OUTPUT}")
