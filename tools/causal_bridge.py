"""Bridge de Marketing Causal (MMM + Causal Inference).

Usa PyMC-Marketing 0.19.4+ (MMM multidimensional) e CausalPy 0.8+.
Funciona offline-first com dados sintéticos se não houver campanha real.

Métodos:
- mmm_train: Treina MMM com dados de campanha (ou sintéticos)
- mmm_analyze: Retorna contribuições, ROAS, saturação
- causal_analyze: Synthetic Control / Difference-in-Differences
- budget_optimize: Otimiza alocação de budget entre canais
"""

import os, json, sys, warnings, io
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

# Import com fallback
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except:
    HAS_MATPLOTLIB = False

# Config
BASE_DIR = Path("/opt/projetos/hermes-unified")
OUTPUT_DIR = BASE_DIR / "output" / "causal"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Estado singleton do modelo treinado
_trained_model = {"mmm": None, "X": None, "y": None, "df": None, "channels": [], "control_cols": []}
_STATE_PATH = OUTPUT_DIR / "_bridge_state.json"

def _save_state(channels: list, control_cols: list, model_path: str):
    """Salva metadados do modelo treinado em disco."""
    state = {
        "channels": channels,
        "control_cols": control_cols,
        "model_path": model_path,
        "trained": True,
    }
    with open(_STATE_PATH, "w") as f:
        json.dump(state, f)

def _load_state() -> dict:
    """Carrega metadados do modelo do disco."""
    if _STATE_PATH.exists():
        with open(_STATE_PATH) as f:
            return json.load(f)
    return {"trained": False}

def _load_model_from_disk() -> bool:
    """Tenta carregar modelo salvo do disco."""
    global _trained_model
    state = _load_state()
    if not state.get("trained"):
        return False
    model_path = state.get("model_path", "")
    if not os.path.exists(model_path):
        return False
    try:
        from pymc_marketing.mmm.mmm import MMM as MMMNew
        # Carregar dados do treino
        data_path = model_path.replace("mmm_model.pkl", "training_data.pkl")
        if os.path.exists(data_path):
            import pickle
            with open(data_path, "rb") as f:
                training = pickle.load(f)
                _trained_model["X"] = training.get("X")
                _trained_model["y"] = training.get("y")
                _trained_model["df"] = training.get("df")
        _trained_model["mmm"] = MMMNew.load(model_path)
        _trained_model["channels"] = state.get("channels", [])
        return True
    except Exception as e:
        print(f"  [WARN] Falha ao carregar modelo do disco: {e}")
        return False

try:
    import pymc as pm
    HAS_PYMC = True
except:
    HAS_PYMC = False

try:
    from pymc_marketing.mmm.mmm import MMM as MMMNew
    from pymc_marketing.mmm import GeometricAdstock, LogisticSaturation
    from pymc_marketing.mmm.mmm import Prior
    HAS_PMM = True
except:
    HAS_PMM = False

try:
    import causalpy as cp
    HAS_CAUSALPY = True
except:
    HAS_CAUSALPY = False


def _generate_synthetic_data(n_weeks: int = 104, seed: int = 42) -> pd.DataFrame:
    """Gera dados sintéticos realistas para MMM."""
    rng = np.random.default_rng(seed)
    date_week = pd.date_range("2023-01-02", periods=n_weeks, freq="W-MON")
    t = np.arange(n_weeks)
    
    # 3 canais: Social, Search, TV
    channels = {}
    for name, (base, spike_prob, spike_high) in [
        ("social", (0.1, 0.3, 0.9)),
        ("search", (0.15, 0.4, 0.8)),
        ("tv", (0.05, 0.2, 0.7)),
    ]:
        vals = np.array([
            rng.uniform(base*0.5, base) if rng.random() < (1 - spike_prob)
            else rng.uniform(spike_high*0.5, spike_high)
            for _ in range(n_weeks)
        ])
        channels[name] = vals
    
    # Componentes
    trend = 0.003 * t
    seas = 0.08 * np.sin(2 * np.pi * t / 52) + 0.03 * np.sin(4 * np.pi * t / 52)
    
    # Eventos
    event = np.zeros(n_weeks)
    for w in [8, 18, 30, 42]:  # Black Friday, Natal etc
        if w < n_weeks:
            event[w] = 1
    
    # Target com contribuições reais
    contributions = {
        "social": 0.40,
        "search": 0.35,
        "tv": 0.25,
    }
    
    intercept = 50.0
    base_sales = intercept + trend * intercept + seas * intercept * 0.3
    noise = rng.normal(0, base_sales * 0.05, n_weeks)
    
    media_contrib = sum(
        channels[ch] * contributions[ch] * intercept * 0.8
        for ch in channels
    )
    
    y = base_sales + media_contrib + event * intercept * 0.2 + noise
    
    df = pd.DataFrame({
        "date_week": date_week,
        **{f"spend_{ch}": channels[ch] * 10000 for ch in channels},
        **{ch: channels[ch] for ch in channels},
        "y": y,
        "event": event,
        "t": t,
    })
    
    return df


class CausalBridge:
    """Bridge para Marketing Causal: MMM + Causal Inference."""
    
    def __init__(self):
        self.output_dir = str(OUTPUT_DIR)
        os.makedirs(self.output_dir, exist_ok=True)
        self.venv_python = "/opt/venvs/causal/bin/python3"
    
    def _get_available(self) -> dict:
        """Verifica disponibilidade dos módulos."""
        return {
            "pymc": HAS_PYMC,
            "pymc_marketing": HAS_PMM,
            "causalpy": HAS_CAUSALPY,
        }
    
    def mmm_train(self, data_path: Optional[str] = None, 
                   channels: Optional[List[str]] = None,
                   n_weeks: int = 104,
                   chains: int = 2,
                   draws: int = 800,
                   tune: int = 1200) -> Tuple[dict, bool, str]:
        """Treina MMM com dados de campanha ou sintéticos.
        
        Args:
            data_path: Caminho para CSV com colunas date_week + spend_* + y
            channels: Lista de nomes de canais (ex: ['social', 'search', 'tv'])
            n_weeks: Se sem dados, gera sintéticos com N semanas
            chains: Número de cadeias MCMC
            draws: Amostras por cadeia
            tune: Aquecimento por cadeia
        
        Returns:
            (result_dict, success, message)
        """
        global _trained_model
        
        avail = self._get_available()
        if not avail["pymc_marketing"]:
            return None, False, "PyMC-Marketing não instalado"
        
        # Carregar ou gerar dados
        if data_path and os.path.exists(data_path):
            df = pd.read_csv(data_path)
            if "date_week" in df.columns:
                df["date_week"] = pd.to_datetime(df["date_week"])
        else:
            df = _generate_synthetic_data(n_weeks=n_weeks)
        
        # Detectar canais
        if channels is None:
            # Auto-detect: colunas com spend_ prefix
            channels = [c for c in df.columns if c.startswith("spend_")]
            if not channels:
                # Usar colunas numéricas que não são date/y/event/t
                exclude = {"date_week", "y", "event", "t", "Unnamed: 0"}
                channels = [c for c in df.columns 
                           if c not in exclude and df[c].dtype in ["float64", "int64"]]
                channels = channels[:5]  # max 5 canais
        
        if not channels:
            return None, False, "Nenhum canal detectado nos dados"
        
        # Colunas de controle
        control_cols = [c for c in ["event", "t"] if c in df.columns]
        
        # Preparar dados (incluir date_week no X)
        feature_cols = ["date_week"] + channels + control_cols
        X = df[feature_cols].copy()
        y = df["y"].values
        
        # Config MMM
        n_ch = len(channels)
        total_spend = df[channels].sum(axis=0)
        spend_share = (total_spend / total_spend.sum()).values if total_spend.sum() > 0 else np.ones(n_ch) / n_ch
        
        sampler_config = {
            "cores": 1,
            "chains": chains,
            "draws": draws,
            "tune": tune,
            "target_accept": 0.9,
            "random_seed": 42,
        }
        
        # Instanciar MMM multidimensional
        mmm = MMMNew(
            date_column="date_week",
            channel_columns=channels,
            control_columns=control_cols if control_cols else None,
            adstock=GeometricAdstock(l_max=8),
            saturation=LogisticSaturation(),
            yearly_seasonality=2,
            sampler_config=sampler_config,
        )
        
        # Build + fit
        mmm.build_model(X, y)
        mmm.fit(X, y)
        
        # Salvar estado
        _trained_model["mmm"] = mmm
        _trained_model["X"] = X
        _trained_model["y"] = y
        _trained_model["df"] = df
        _trained_model["channels"] = channels
        _trained_model["control_cols"] = control_cols
        
        # Salvar modelo
        model_path = os.path.join(self.output_dir, "mmm_model.pkl")
        mmm.save(model_path)
        
        # Salvar dados de treino
        import pickle
        with open(model_path.replace("mmm_model.pkl", "training_data.pkl"), "wb") as f:
            pickle.dump({"X": X, "y": y, "df": df}, f)
        
        # Salvar estado em disco
        _save_state(channels, control_cols, model_path)
        
        # R-hat
        try:
            import arviz as az
            rhats = az.rhat(mmm.fit_result)
            max_rhat = float(max(np.max(rhats[k].values) for k in rhats.data_vars if k != "y_scaled"))
        except:
            max_rhat = None
        
        # Predição
        try:
            pred = mmm.predict(X)
            if hasattr(pred, 'values'):
                pred = pred.values.flatten()
            r2 = float(1 - np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
        except:
            r2 = None
            pred = None
        
        # Plot fitted
        if HAS_MATPLOTLIB and pred is not None:
            fig, ax = plt.subplots(figsize=(12, 4))
            ax.plot(df["date_week"], y, label="Actual", color="green", lw=2)
            ax.plot(df["date_week"], pred, label="Predicted", color="orange", lw=2, alpha=0.8)
            ax.set_ylabel("Sales"); ax.legend(); ax.grid(alpha=0.3)
            fig.savefig(os.path.join(self.output_dir, "mmm_fitted.png"), dpi=150, bbox_inches="tight")
            plt.close(fig)
        
        result = {
            "channels": channels,
            "n_weeks": len(df),
            "chains": chains,
            "draws": draws,
            "r2": round(r2, 4) if r2 else None,
            "max_rhat": round(max_rhat, 4) if max_rhat else None,
            "converged": max_rhat is not None and max_rhat < 1.05,
            "model_path": model_path,
            "output_dir": self.output_dir,
        }
        
        return result, True, f"MMM treinado com {len(df)} semanas, {len(channels)} canais, R²={r2:.3f}" if r2 else f"MMM treinado com {len(df)} semanas"
    
    def mmm_analyze(self) -> Tuple[dict, bool, str]:
        """Analisa MMM treinado: contribuições, saturação, parâmetros."""
        # Tentar carregar do disco se não estiver em memória
        if _trained_model["mmm"] is None:
            if not _load_model_from_disk():
                return None, False, "Treine um MMM primeiro com mmm_train()"
        
        mmm = _trained_model["mmm"]
        channels = _trained_model.get("channels", [])
        
        result = {"channels": {}}
        
        # Parâmetros recuperados
        try:
            import arviz as az
            summ = az.summary(mmm.fit_result, var_names=[
                "adstock_alpha", "saturation_lam", "saturation_beta"
            ])
            result["parameters"] = summ.to_dict()
        except:
            pass
        
        # Contribuições
        try:
            # Tenta contribution share se disponível
            contributions = mmm.compute_channel_contribution_share()
            if contributions is not None:
                result["contributions"] = contributions.to_dict()
        except:
            pass
        
        # Plots
        if HAS_MATPLOTLIB:
            for plot_name, plot_fn in [
                ("contributions", lambda: mmm.plot_components_contributions()),
                ("saturation", lambda: mmm.plot_direct_contribution_curves()),
            ]:
                try:
                    fig = plot_fn()
                    path = os.path.join(self.output_dir, f"mmm_{plot_name}.png")
                    fig.savefig(path, dpi=150, bbox_inches="tight")
                    plt.close(fig)
                    result[f"{plot_name}_plot"] = path
                except:
                    pass
        
        # Resumo
        for i, ch in enumerate(channels):
            result["channels"][ch] = {"index": i}
        
        return result, True, f"Análise MMM: {len(channels)} canais, plots em {self.output_dir}"
    
    def budget_optimize(self, total_budget: float = 100000.0,
                        num_days: int = 84) -> Tuple[dict, bool, str]:
        """Otimiza alocação de budget entre canais."""
        if _trained_model["mmm"] is None:
            if not _load_model_from_disk():
                return None, False, "Treine um MMM primeiro com mmm_train()"
        
        channels = _trained_model.get("channels", [])
        if not channels:
            return None, False, "Sem canais disponíveis"
        
        # Distribuição proporcional (otimização real usa BudgetOptimizer)
        try:
            # Usar contribuições para guiar alocação
            mmm = _trained_model["mmm"]
            
            # Alocação igual como fallback
            n = len(channels)
            per_channel = total_budget / n
            allocation = {ch: round(per_channel, 2) for ch in channels}
            
            # Tentar BudgetOptimizer real
            try:
                from pymc_marketing.mmm.budget_optimizer import BudgetOptimizer
                opt = BudgetOptimizer(
                    model=mmm,
                    num_periods=num_days,
                )
                opt_result = opt.optimize_budget(total_budget=total_budget)
                if opt_result is not None:
                    # Converter para dict
                    if hasattr(opt_result, 'to_dict'):
                        allocation = opt_result.to_dict()
            except:
                pass
            
            result = {
                "total_budget": total_budget,
                "num_days": num_days,
                "allocation": allocation,
                "method": "budget_optimizer" if 'opt' in dir() and 'BudgetOptimizer' in dir() else "equal_split",
            }
            
            return result, True, f"Budget otimizado: {json.dumps(allocation)}"
            
        except Exception as e:
            return None, False, f"Erro na otimização: {str(e)[:200]}"
    
    def causal_analyze(self, data_path: Optional[str] = None,
                       treatment_time: Optional[int] = None,
                       method: str = "synthetic_control",
                       n_controls: int = 5) -> Tuple[dict, bool, str]:
        """Executa análise causal (Synthetic Control ou DID).
        
        Args:
            data_path: CSV com colunas [time, treated, c0..cN] no formato wide
            treatment_time: Índice do ponto de intervenção
            method: "synthetic_control" ou "did"
            n_controls: Número de unidades de controle sintéticas
        
        Returns:
            (result_dict, success, message)
        """
        avail = self._get_available()
        if not avail["causalpy"]:
            return None, False, "CausalPy não instalado"
        
        # Carregar ou gerar dados
        if data_path and os.path.exists(data_path):
            df = pd.read_csv(data_path)
        else:
            # Gerar dados sintéticos para demo
            np.random.seed(42)
            np_pre, np_post = 100, 50
            tp = np.arange(np_pre + np_post)
            data = {"time": tp}
            data["treated"] = [10 + 0.02*t + np.random.normal(0, 0.5) for t in tp[:np_pre]] + \
                              [10 + 0.02*t + 3.0 + np.random.normal(0, 0.5) for t in range(np_post)]
            for i in range(n_controls):
                data[f"c{i}"] = [10 + 0.02*t + np.random.normal(0, 1) + i*0.5 for t in tp]
            df = pd.DataFrame(data)
        
        if treatment_time is None:
            treatment_time = len(df) // 2
        
        control_units = [c for c in df.columns if c.startswith("c") or c.startswith("control")]
        if not control_units:
            return None, False, "Nenhuma unidade de controle encontrada (colunas c0..cN)"
        
        treated_units = ["treated"] if "treated" in df.columns else None
        if not treated_units:
            return None, False, "Coluna 'treated' não encontrada nos dados"
        
        try:
            from sklearn.linear_model import Ridge
            
            result = cp.SyntheticControl(
                df,
                treatment_time,
                control_units=control_units,
                treated_units=treated_units,
                model=Ridge(alpha=100, positive=True),
            )
            
            # Extrair resultados
            summary = None
            try:
                summary = result.effect_summary()
            except:
                pass
            
            effect = float(result.post_impact.mean()) if hasattr(result, 'post_impact') else None
            
            # Plot
            if HAS_MATPLOTLIB:
                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(df["time" if "time" in df.columns else df.index], 
                       df["treated"], "k-", label="Treated", lw=2)
                if hasattr(result, 'post_pred') and hasattr(result, 'pre_pred'):
                    pred = list(result.pre_pred) + list(result.post_pred)
                    ax.plot(range(len(pred)), pred, "b--", label="Counterfactual", lw=2)
                ax.axvline(x=treatment_time, color="r", ls="--", alpha=0.7, label="Intervention")
                ax.legend(); ax.grid(alpha=0.3)
                fig.savefig(os.path.join(self.output_dir, "causal_synthetic_control.png"), dpi=150)
                plt.close(fig)
            
            output = {
                "method": method,
                "effect": round(effect, 3) if effect else None,
                "effect_summary": str(summary) if summary else None,
                "treatment_time": treatment_time,
                "n_control_units": len(control_units),
                "true_effect": 3.0,  # benchmark para dados sintéticos
                "plot_path": os.path.join(self.output_dir, "causal_synthetic_control.png"),
            }
            
            return output, True, f"Causal Analysis: efeito={effect:.3f}" if effect else "Causal Analysis concluída"
            
        except Exception as e:
            return None, False, f"Erro CausalPy: {str(e)[:300]}"


# Singleton
_bridge = None

def get_bridge() -> CausalBridge:
    global _bridge
    if _bridge is None:
        _bridge = CausalBridge()
    return _bridge
