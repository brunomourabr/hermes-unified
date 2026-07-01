#!/usr/bin/env python3
"""Teste comparativo: CausalPy sem/std + GeoLift ASCM.
Reproduz o estudo Recast com dados sintéticos de ground truth conhecido."""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, '/opt/projetos/hermes-unified')
import numpy as np
import pandas as pd

from tools.causal_bridge import CausalBridge

# Forçar matplotlib
os.environ['MPLBACKEND'] = 'Agg'

bridge = CausalBridge()

# Config do teste
N_SIMULACOES = 20  # quantas simulações rodar pra cada método
np_pre, np_post = 100, 50
TRUE_EFFECT = 3.0

print("=" * 70)
print(" TESTE COMPARATIVO: CausalPy vs GeoLift ASCM")
print(f" Ground truth: efeito={TRUE_EFFECT}, {np_pre} pre + {np_post} post")
print(f" {N_SIMULACOES} simulacoes por metodo")
print("=" * 70)

# Resultados
results = {
    "causalpy_sem_std": {"effects": [], "biases": []},
    "causalpy_com_std": {"effects": [], "biases": []},
    "geolift_ascm": {"effects": [], "biases": []},
}

for seed in range(N_SIMULACOES):
    np.random.seed(seed)
    
    tp = np.arange(np_pre + np_post)
    data = {"time": tp}
    data["treated"] = [10 + 0.02*t + np.random.normal(0, 0.5) for t in tp[:np_pre]] + \
                      [10 + 0.02*t + TRUE_EFFECT + np.random.normal(0, 0.5) for t in range(np_post)]
    for i in range(5):
        data[f"c{i}"] = [10 + 0.02*t + np.random.normal(0, 1) + i*0.5 for t in tp]
    df = pd.DataFrame(data)
    
    treatment_time = np_pre
    control_units = [c for c in df.columns if c.startswith("c")]
    treated_units = ["treated"]
    
    # Método 1: CausalPy SEM standardization (comportamento antigo)
    from sklearn.linear_model import Ridge
    import causalpy as cp
    
    df_fit_sem = df
    result_sem = cp.SyntheticControl(
        df_fit_sem, treatment_time,
        control_units=control_units, treated_units=treated_units,
        model=Ridge(alpha=100, positive=True),
    )
    effect_sem = float(result_sem.post_impact.mean())
    results["causalpy_sem_std"]["effects"].append(effect_sem)
    results["causalpy_sem_std"]["biases"].append(effect_sem - TRUE_EFFECT)
    
    # Método 2: CausalPy COM standardization
    df_scaled = df.copy()
    pre_mask = df.index < treatment_time
    for col in treated_units + control_units:
        mu = df.loc[pre_mask, col].mean()
        sigma = df.loc[pre_mask, col].std()
        if sigma == 0: sigma = 1.0
        df_scaled[col] = (df[col] - mu) / sigma
    
    result_std = cp.SyntheticControl(
        df_scaled, treatment_time,
        control_units=control_units, treated_units=treated_units,
        model=Ridge(alpha=100, positive=True),
    )
    effect_std_scaled = float(result_std.post_impact.mean())
    treated_sigma = df.loc[pre_mask, "treated"].std()
    effect_std = effect_std_scaled * treated_sigma
    results["causalpy_com_std"]["effects"].append(effect_std)
    results["causalpy_com_std"]["biases"].append(effect_std - TRUE_EFFECT)
    
    # Método 3: GeoLift ASCM
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler
    
    y_pre = df["treated"].iloc[:np_pre].values
    X_pre = df[control_units].iloc[:np_pre].values
    y_all = df["treated"].values
    X_all = df[control_units].values
    
    ridge_cv = RidgeCV(alphas=[0.1, 1, 10, 100, 500, 1000], fit_intercept=False, cv=5)
    ridge_cv.fit(X_pre, y_pre)
    counterfactual = ridge_cv.predict(X_all)
    
    post_mask = np.arange(np_pre + np_post) >= np_pre
    effect_geo = (y_all[post_mask] - counterfactual[post_mask]).mean()
    results["geolift_ascm"]["effects"].append(effect_geo)
    results["geolift_ascm"]["biases"].append(effect_geo - TRUE_EFFECT)

# Relatório
print("\n")
print("=" * 70)
print(" RESULTADOS")
print("=" * 70)

for metodo, data in results.items():
    effects = np.array(data["effects"])
    biases = np.array(data["biases"])
    
    mae = np.abs(biases).mean()
    rmse = np.sqrt((biases ** 2).mean())
    bias_medio = biases.mean()
    pct_dentro_1pp = np.abs(biases < 1.0).mean() * 100
    
    print(f"\n {metodo}:")
    print(f"   Efeito medio: {effects.mean():.3f} (verdadeiro: {TRUE_EFFECT})")
    print(f"   Bias medio: {bias_medio:+.3f}")
    print(f"   MAE: {mae:.3f}")
    print(f"   RMSE: {rmse:.3f}")
    print(f"   Dentro de 1pp: {pct_dentro_1pp:.0f}%")
    print(f"   Min: {effects.min():.3f}, Max: {effects.max():.3f}")
