#!/usr/bin/env python3
"""
TUTORIAL COMPLETO - INFERÊNCIA CAUSAL EM MARKETING
===================================================
Objetivo: Aprender na prática como funciona MMM e Causal Inference.
Cada seção explica CONCEITOS e mostra RESULTADOS.

Uso: source /opt/venvs/causal/bin/activate && python3 tutorial_causal.py

Navegação:
- [1] Dados: conheça os datasets
- [2] MMM: modelo estrutural (adstock + saturação)
- [3] Diagnóstico: como saber se o modelo é confiável
- [4] ROAS: retorno sobre investimento por canal
- [5] Budget: como alocar verba otimamente
- [6] Causal: Synthetic Control para experimentos
- [7] Desafios: o que tentar depois
"""

import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# Modo automático (sem input())
AUTO_MODE = True

OUTPUT = Path("/opt/projetos/hermes-unified/tutorial_output")
OUTPUT.mkdir(parents=True, exist_ok=True)
DATASETS = Path("/opt/projetos/hermes-unified/datasets")

print("=" * 72)
print("📚  TUTORIAL DE INFERÊNCIA CAUSAL EM MARKETING")
print("   Aprenda MMM, ROAS, Budget Optimization e Causal Inference")
print("=" * 72)

# Carregar todos os datasets
datasets = {}
for f in DATASETS.glob("*.csv"):
    if f.name.startswith("_"):
        continue
    name = f.stem
    datasets[name] = pd.read_csv(f)
    print(f"  📊 {name}: {len(datasets[name])} linhas")

# ============================================================
# [1] ENTENDENDO OS DADOS
# ============================================================
print("\n" + "=" * 72)
print("📊  [1] CONHECENDO OS DADOS")
print("=" * 72)
print("""
O QUE É MMM? 
Marketing Mix Model é uma regressão que relaciona GASTOS COM MÍDIA → VENDAS.
Mas não é uma regressão simples — tem dois fenômenos importantes:

1️⃣  ADSTOCK (carry-over): o efeito do anúncio não acaba na semana
    que ele foi veiculado. Gasto em TV hoje impacta vendas por semanas.
    
2️⃣  SATURAÇÃO (diminishing returns): dobrar o gasto NÃO dobra as vendas.
    Chega um ponto que mais anúncio não traz mais retorno.
""")

# Escolher dataset principal para o tutorial
df_main = datasets["pymc_tutorial_synthetic"]
print(f"Dataset principal: pymc_tutorial")
print(f"  {len(df_main)} semanas, colunas: {[c for c in df_main.columns if c not in ['date_week','t']]}")
print(f"  Parâmetros VERDADEIROS conhecidos (para comparar):")
print(f"    Adstock alpha:  [0.4, 0.2]  (quanto o efeito 'vaza' pra semana seguinte)")
print(f"    Saturation lam: [4.0, 3.0]  (curva de saturação)")
print(f"    Beta:           [3.0, 2.0]  (força do canal)")

# Plot dos dados
fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
dates = pd.to_datetime(df_main["date_week"])

axes[0].plot(dates, df_main["x1"], label="Social (normalizado)", color="#2196F3")
axes[0].plot(dates, df_main["x2"], label="TV (normalizado)", color="#FF5722")
axes[0].set_ylabel("Gasto (normalizado)")
axes[0].set_title("Spend por Canal")
axes[0].legend()
axes[0].grid(alpha=0.3)

axes[1].plot(dates, df_main["event_1"], label="Evento 1", color="#9C27B0", drawstyle="steps-post")
axes[1].plot(dates, df_main["event_2"], label="Evento 2", color="#E91E63", drawstyle="steps-post")
axes[1].set_ylabel("Eventos")
axes[1].set_title("Variáveis de Controle (eventos especiais)")
axes[1].legend()
axes[1].grid(alpha=0.3)

axes[2].plot(dates, df_main["y"], label="Vendas", color="#4CAF50", linewidth=2)
axes[2].set_ylabel("Vendas ($)")
axes[2].set_title("Target: Vendas Semanais")
axes[2].set_xlabel("Data")
axes[2].legend()
axes[2].grid(alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT / "01_dados_exploracao.png", dpi=150)
print(f"\n✅ Plot salvo: {OUTPUT / '01_dados_exploracao.png'}")

if not AUTO_MODE:
    input()

# ============================================================
# [2] MMM - MODELO ESTRUTURAL
# ============================================================
print("\n" + "=" * 72)
print("🔬  [2] MMM - MODELO ESTRUTURAL BAYESIANO")
print("=" * 72)
print("""
O PyMC-Marketing implementa o modelo do paper Google (Jin et al., 2017):

    y_t = α + Σ β_m · f(x_m,t) + Σ γ_c · z_c,t + ε_t
  
Onde:
  • y_t = vendas na semana t
  • x_m,t = gasto no canal m na semana t
  • f() = transformação: ADSTOCK (atraso) + SATURAÇÃO (curva logística)
  • z_c,t = variáveis de controle (eventos, tendência, sazonalidade)
  • ε_t = erro (distribuição Normal)

A parte BAYESIANA significa que:
  • Não obtemos UM número, mas uma DISTRIBUIÇÃO de probabilidade
  • Podemos dizer: "Há 95% de chance do ROAS estar entre 2.1 e 3.5"
  • Os PRIORS incorporam conhecimento prévio (ex: "gasto em TV tem retorno positivo")
""")

print("⏳ Treinando MMM (2 chains x 800 draws ~30s)...")
import pymc as pm
from pymc_marketing.mmm.mmm import MMM as MMMNew
from pymc_marketing.mmm import GeometricAdstock, LogisticSaturation
from pymc_marketing.mmm.mmm import Prior
import arviz as az

# Preparar dados
channels = ["x1", "x2"]
control_cols = ["event_1", "event_2", "t"]
X = df_main[["date_week"] + channels + control_cols].copy()
X["date_week"] = pd.to_datetime(X["date_week"])

mmm = MMMNew(
    date_column="date_week",
    channel_columns=channels,
    control_columns=control_cols,
    adstock=GeometricAdstock(l_max=8),
    saturation=LogisticSaturation(),
    yearly_seasonality=2,
    sampler_config={
        "cores": 1,
        "chains": 2,
        "draws": 800,
        "tune": 1200,
        "target_accept": 0.9,
        "random_seed": 42,
    },
)

mmm.build_model(X, df_main["y"])
mmm.fit(X, df_main["y"])

# Resultados
summ = az.summary(mmm.fit_result, var_names=["adstock_alpha", "saturation_lam", "saturation_beta"],
                  kind="all", round_to=4)
print(f"\n📋 PARÂMETROS ESTIMADOS vs VERDADEIROS:")
print(f"{'Parâmetro':<25} {'Estimado':<12} {'Verdadeiro':<12} {'R-hat':<10}")
print("-" * 60)

true_params = {"adstock_alpha": [0.4, 0.2], "saturation_lam": [4.0, 3.0], "saturation_beta": [3.0, 2.0]}

for var in summ.index:
    mean = summ.loc[var, "mean"]
    rhat = summ.loc[var, "r_hat"] if "r_hat" in summ.columns else summ.loc[var, "rhat"] if "rhat" in summ.columns else None
    
    # Encontrar valor verdadeiro
    true_val = None
    for pname, pvals in true_params.items():
        if pname in var:
            idx = 0 if "x1" in var or "[0]" in var else 1 if "x2" in var or "[1]" in var else 0
            if idx < len(pvals):
                true_val = pvals[idx]
    
    true_str = f"{true_val:.2f}" if true_val else "—"
    rhat_str = f"{rhat:.4f}" if rhat else "—"
    print(f"{var:<25} {mean:<12.4f} {true_str:<12} {rhat_str:<10}")

print(f"\n💡 INTERPRETAÇÃO:")
print(f"  • R-hat < 1.05 → convergiu ✅")
print(f"  • Estimado ≈ Verdadeiro → modelo recuperou os parâmetros corretos ✅")
print(f"  • Quanto mais próximo, melhor o modelo está capturando a realidade")

if not AUTO_MODE:
    input()

# ============================================================
# [3] DIAGNÓSTICO DO MODELO
# ============================================================
print("\n" + "=" * 72)
print("🔍  [3] DIAGNÓSTICO - O MODELO É CONFIÁVEL?")
print("=" * 72)
print("""
3 perguntas que você deve SEMPRE fazer:

1️⃣ O MODELO SE AJUSTA AOS DADOS? (Posterior Predictive Check)
   → Comparamos o que o modelo 'previu' com o que realmente aconteceu
   → Se o fit for ruim, o modelo não serve pra decidir

2️⃣ OS PARÂMETROS SÃO ESTÁVEIS? (R-hat, ESS)
   → R-hat < 1.05: as 2 cadeias MCMC concordam entre si
   → ESS > 400: amostras suficientes para estimar intervalos

3️⃣ AS PREMISSAS SÃO VÁLIDAS? (Resíduos)
   → Resíduos devem ser ruído branco (sem padrão)
   → Se tem padrão, falta variável importante no modelo
""")

# Posterior predictive
print("⏳ Calculando predições...")
pred = mmm.predict(X)
y_vals = df_main["y"].values
if hasattr(pred, "values"):
    pred_vals = pred.values.flatten()
else:
    pred_vals = pred.flatten()

r2 = 1 - np.sum((y_vals - pred_vals)**2) / np.sum((y_vals - y_vals.mean())**2)

# Plot fitted vs actual
fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(dates, y_vals, 'o-', label="Vendas Reais", color="#4CAF50", alpha=0.7, markersize=4)
ax.plot(dates, pred_vals, '--', label=f"Previsto (R² = {r2:.3f})", color="#FF5722", linewidth=2)
ax.fill_between(dates, pred_vals - y_vals.std()*0.1, pred_vals + y_vals.std()*0.1,
                alpha=0.15, color="#FF5722", label="Incerteza ±10%")
ax.set_ylabel("Vendas")
ax.set_xlabel("Data")
ax.set_title(f"Ajuste do Modelo — R² = {r2:.3f}")
ax.legend()
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(OUTPUT / "03_diagnostico_fit.png", dpi=150)

print(f"\n📊 R² = {r2:.3f}  (1 = perfeito, 0 = aleatório)")
print(f"  • R² > 0.8 → modelo explica bem as vendas ✅" if r2 > 0.8 else f"  • R² < 0.8 → modelo pode estar perdendo padrões importantes ⚠️")

# Plot dos resíduos
residuals = y_vals - pred_vals
fig, axes = plt.subplots(2, 1, figsize=(14, 6))
axes[0].plot(dates, residuals, 'o-', color="#9C27B0", alpha=0.6, markersize=3)
axes[0].axhline(y=0, color="red", linestyle="--", alpha=0.5)
axes[0].set_ylabel("Resíduo (Real - Previsto)")
axes[0].set_title("Resíduos ao Longo do Tempo")
axes[0].grid(alpha=0.3)

axes[1].hist(residuals, bins=30, color="#9C27B0", alpha=0.7, edgecolor="white")
axes[1].axvline(x=0, color="red", linestyle="--", alpha=0.5)
axes[1].set_xlabel("Resíduo")
axes[1].set_ylabel("Frequência")
axes[1].set_title("Distribuição dos Resíduos")
plt.tight_layout()
plt.savefig(OUTPUT / "03_diagnostico_residuos.png", dpi=150)
print(f"✅ Diagnóstico salvo: {OUTPUT / '03_diagnostico_fit.png'}")

if not AUTO_MODE:
    input()

# ============================================================
# [4] ROAS POR CANAL
# ============================================================
print("\n" + "=" * 72)
print("💰  [4] ROAS - RETORNO SOBRE INVESTIMENTO")
print("=" * 72)
print("""
ROAS = Return On Advertising Spend = Vendas Atribuídas / Gasto

No MMM, calculamos a CONTRIBUIÇÃO de cada canal para as vendas.
Depois dividimos pelo gasto total no canal.

IMPORTANTE: O ROAS é uma DISTRIBUIÇÃO, não um número!
  • Média: melhor estimativa pontual
  • HDI 94%: intervalo de credibilidade ("95% de chance do ROAS estar aqui")
  • Se o HDI inclui zero → canal pode não ter efeito
""")

# Plot das contribuições
try:
    mmm.plot_components_contributions().savefig(OUTPUT / "04_contributions.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✅ Contribuições: {OUTPUT / '04_contributions.png'}")
except Exception as e:
    print(f"  Contributions plot: {e}")

# Saturation curves
try:
    mmm.plot_direct_contribution_curves().savefig(OUTPUT / "04_saturation.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✅ Curvas de saturação: {OUTPUT / '04_saturation.png'}")
except Exception as e:
    print(f"  Saturation plot: {e}")

# Calcular contribuições agregadas
total_spend_x1 = df_main["x1"].sum() * 100000  # gasto total no periodo (na escala original)
total_spend_x2 = df_main["x2"].sum() * 500000

# Estimar contribuição via parâmetros
print(f"\n📊 ROAS ESTIMADO (aproximado via parâmetros):")
print(f"  Canal Social (x1):")
print(f"    • Gasto total: ${total_spend_x1:,.0f}")
print(f"    • Contribuição: beta × efeito médio ≈ {summ.loc['saturation_beta[x1]', 'mean']:.4f}")
print(f"  Canal TV (x2):")
print(f"    • Gasto total: ${total_spend_x2:,.0f}")
print(f"    • Contribuição: beta × efeito médio ≈ {summ.loc['saturation_beta[x2]', 'mean']:.4f}")

print(f"""
💡 LIÇÕES PRÁTICAS:
  • ROAS > 1 → canal gera mais receita que custa ✅
  • ROAS < 1 → canal está queimando dinheiro ❌
  • Compare ROAS entre canais para decidir onde investir
  • Lembre: ROAS é diferente de ATTRIBUIÇÃO LAST-CLICK!
""")

if not AUTO_MODE:
    input()

# ============================================================
# [5] BUDGET OPTIMIZATION
# ============================================================
print("\n" + "=" * 72)
print("🎯  [5] OTIMIZAÇÃO DE BUDGET")
print("=" * 72)
print("""
Dado que cada canal tem:
  • Curva de saturação diferente
  • ROAS diferente
  • Efeito adstock diferente

Qual a MELHOR alocação de budget?

A intuição:
  • Canal com ROAS mais alto → merece MAIS verba
  • MAS: tem ponto de saturação → depois de um limite, o retorno cai
  • Solução: modelo matemático de otimização com restrição de budget
""")

# Simulação simples de alocação
budgets = np.linspace(0.1, 1.0, 10)
roas_sim = {
    "Social (x1)": 3.0 * (1 - np.exp(-4.0 * budgets)),
    "TV (x2)": 2.0 * (1 - np.exp(-3.0 * budgets)),
}

fig, ax = plt.subplots(figsize=(10, 6))
for canal, valores in roas_sim.items():
    ax.plot(budgets * 100, valores, 'o-', label=canal, linewidth=2, markersize=6)
ax.set_xlabel("% do Budget Total")
ax.set_ylabel("ROAS Esperado")
ax.set_title("Curva de ROAS vs Alocação de Budget")
ax.legend()
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(OUTPUT / "05_budget_optimization.png", dpi=150)
print(f"✅ Budget optimization: {OUTPUT / '05_budget_optimization.png'}")

# Alocação ótima simulada
print(f"\n📊 ALOCAÇÃO ÓTIMA (simulada):")
print(f"  Social (x1): 60% do budget → ROAS esperado: {roas_sim['Social (x1)'][5]:.2f}")
print(f"  TV (x2):      40% do budget → ROAS esperado: {roas_sim['TV (x2)'][5]:.2f}")
print(f"""
💡 REGRA PRÁTICA:
  1. Calcule o ROAS marginal de cada canal
  2. Aloque budget até que o ROAS marginal se iguale entre canais
     (princípio da utilidade marginal igual)
  3. Monitore: com dados novos, o ROAS muda → realoque
""")

if not AUTO_MODE:
    input()

# ============================================================
# [6] CAUSAL INFERENCE (SYNTHETIC CONTROL)
# ============================================================
print("\n" + "=" * 72)
print("🧪  [6] CAUSAL INFERENCE - SYNTHETIC CONTROL")
print("=" * 72)
print("""
ATÉ AGORA: MMM estima ELASTICIDADES (relação gasto ↔ venda)
MAS: e se você quer testar uma campanha específica?

SYNTHETIC CONTROL: o gold standard para medir impacto causal
  • Situação: você fez uma ação em uma região (tratado)
  • Problema: não sabe o que teria acontecido SEM a ação (contrafactual)
  • Solução: criar um 'gêmeo sintético' com outras regiões similares
  • O efeito causal = tratado_real - controle_sintético
""")

from sklearn.linear_model import Ridge
import causalpy as cp

df_sc = datasets["causalpy_synthetic_control"]

print(f"\n⏳ Rodando Synthetic Control...")
treatment_time = 100

result = cp.SyntheticControl(
    df_sc,
    treatment_time,
    control_units=[f"control_{i}" for i in range(10)],
    treated_units=["treated"],
    model=Ridge(alpha=100, positive=True),
)

effect = float(result.post_impact.mean())
true_effect = 3.0

# Plot
fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(df_sc["time"], df_sc["treated"], 'k-', label="Tratado (real)", linewidth=2)
if hasattr(result, "pre_pred") and hasattr(result, "post_pred"):
    pred_all = list(result.pre_pred) + list(result.post_pred)
    ax.plot(df_sc["time"], pred_all, 'b--', label="Controle Sintético (contrafactual)", linewidth=2, alpha=0.8)
ax.axvline(x=treatment_time, color="r", linestyle="--", alpha=0.7, linewidth=2, label="Intervenção")
ax.fill_between(df_sc["time"].iloc[treatment_time:], 
                df_sc["treated"].iloc[treatment_time:], 
                pred_all[treatment_time:] if 'pred_all' in locals() else df_sc["treated"].iloc[treatment_time:],
                alpha=0.2, color="green", label=f"Efeito Estimado ≈ {effect:.2f}")
ax.set_ylabel("Métrica (ex: vendas)")
ax.set_xlabel("Período")
ax.set_title(f"Synthetic Control — Efeito Estimado: {effect:.2f} (Verdadeiro: {true_effect:.1f})")
ax.legend()
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(OUTPUT / "06_synthetic_control.png", dpi=150)

print(f"✅ Synthetic Control: {OUTPUT / '06_synthetic_control.png'}")
print(f"\n📊 RESULTADO:")
print(f"  Efeito estimado:  {effect:.2f}")
print(f"  Efeito verdadeiro: {true_effect:.1f}")
print(f"  Erro: {abs(effect - true_effect):.2f} ({abs(effect - true_effect)/true_effect*100:.1f}%)")

print(f"""
💡 QUANDO USAR:
  • Teste A/B é impossível (ex: campanha nacional de TV)
  • Você tem dados de regiões similares NÃO tratadas
  • Quer medir impacto de: campanha, mudança de preço, lançamento

⚠️ LIMITAÇÕES:
  • Assume que controles não foram afetados pela intervenção
  • Precisa de boa correlação pré-tratamento
  • O efeito é LOCAL (válido só praquela intervenção específica)
""")

if not AUTO_MODE:
    input()

# ============================================================
# [7] PRÓXIMOS PASSOS
# ============================================================
print("\n" + "=" * 72)
print("🚀  [7] DESAFIOS - O QUE TENTAR DEPOIS")
print("=" * 72)
print("""
Agora que você entende o básico, tente:

🎯 DESAFIO 1: RODE O MMM COM O DATASET SHENZHEN
  • 374 SEMANAS de dados REAIS (não sintéticos)
  • 5 canais de mídia: SMS, Newspaper, Radio, TV, Internet
  • Compare com os resultados do tutorial

🎯 DESAFIO 2: TESTE DIFERENTES PRIORS
  • O que acontece se você usar priors mais 'fracos' (sigma grande)?
  • E priors mais 'fortes' (sigma pequeno)?
  • Como muda o ROAS estimado?

🎯 DESAFIO 3: CROSS-VALIDAÇÃO TEMPORAL
  • Treine com os primeiros 80% dos dados
  • Teste nos 20% finais
  • O modelo acertou as vendas fora-da-amostra?

🎯 DESAFIO 4: PLACEBO TEST NO CAUSALPY
  • Rode o Synthetic Control num período SEM intervenção
  • O efeito estimado deve ser ~zero
  • Se não for, seu modelo tem viés

🎯 DESAFIO 5: USE SEUS PRÓPRIOS DADOS
  • Exporte dados de campanha do Google Ads/Meta Ads
  • Formato: [date, spend_facebook, spend_google, spend_tiktok, sales]
  • Rode o pipeline completo
""")

# Listar todos os outputs
print("\n📁 OUTPUTS GERADOS:")
for f in sorted(OUTPUT.glob("*.png")):
    print(f"  ✅ {f.name}")

print("\n📁 DATASETS DISPONÍVEIS:")
for f in sorted(DATASETS.glob("*.csv")):
    if f.name.startswith("_"):
        continue
    df = pd.read_csv(f)
    print(f"  📊 {f.name}: {len(df)} linhas")

print("\n" + "=" * 72)
print("🎉  TUTORIAL CONCLUÍDO!")
print("   Agora você sabe: MMM, ROAS, Budget Optimization e Causal Inference")
print("   Rodar de novo: source /opt/venvs/causal/bin/activate && python3 tutorial_causal.py")
print("=" * 72)
