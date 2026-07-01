"""
Financial Bridge BR — Agente de Investimentos Brasil
Fontes:
- brapi.dev (60+ tools, free tier 15k req/mês)
- BCB SGS (dados macro, gratuito, sem token)
- Tesouro Direto (Tesouro Nacional)
- CVM (dados abertos, gratuito, sem token)
- IBGE SIDRA (PIB, IPCA, desemprego)

Modos: online (API real) e offline (dados de exemplo)
"""
import os
import json
import re
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

# =====================================================================
# CONFIG
# =====================================================================
BRAPI_BASE = "https://brapi.dev/api"
BCB_SGS_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"
TESOURO_URL = "https://www.tesourodireto.com.br/json/br/com/b3/tesourodireto/service/api/treasurybondsinfo.json"
IBGE_API = "https://servicodados.ibge.gov.br/api/v3/agregados"

# Cache de requisições simples
# Cache de requisições simples
_request_cache = {}
BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "")

# Tenta importar python-bcb para dados macro
_BCB_AVAILABLE = False
try:
    from bcb import sgs
    _BCB_AVAILABLE = True
except ImportError:
    sgs = None


def _fetch_json(url: str, cache_ttl: int = 300) -> dict:
    """Fetch JSON with caching."""
    now = datetime.now()
    if url in _request_cache:
        data, cached_at = _request_cache[url]
        if (now - cached_at).seconds < cache_ttl:
            return data

    try:
        headers = {
            "User-Agent": "Hermes-Finance/1.0",
            "Accept": "application/json, text/plain, */*"
        }
        req = Request(url, headers=headers)
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
        _request_cache[url] = (data, now)
        return data
    except json.JSONDecodeError:
        raise RuntimeError(f"Resposta inválida (não-JSON) de {url}")
    except URLError as e:
        raise RuntimeError(f"Erro de conexão: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Erro ao acessar {url}: {e}")


# =====================================================================
# BRIDGE PRINCIPAL
# =====================================================================

class FinancialBridgeBR:
    """Bridge de investimentos Brasil — macro, ações, FIIs, Tesouro Direto."""

    def __init__(self):
        self.output_dir = "/opt/projetos/hermes-unified/output/financeiro/"
        os.makedirs(self.output_dir, exist_ok=True)

    # ==================================================================
    # MACROECONOMIA — BCB SGS + IBGE
    # ==================================================================

    _MACRO_CODES = {
        "selic": 11, "selic_meta": 1178, "selic_acum_mes": 4390,
        "cdi": 12, "ipca": 433, "ipca_15": 7478, "ipca_12m": 13522,
        "igpm": 189, "igpdi": 190, "inpc": 188, "tr": 226,
        "cambio_usd": 1, "cambio_usd_ptax_venda": 3698,
        "cambio_eur": 21619, "pib_mensal": 4380, "ibc_br": 24363,
        "desemprego": 24369, "divida_publica": 4513,
        "resultado_primario": 4537, "imab": 12466,
    }

    def get_macro(self, indicador: str, data_inicio: str = None, data_fim: str = None) -> dict:
        """
        Busca indicador macroeconômico do BCB SGS.

        Args:
            indicador: Nome do indicador (selic, ipca, cdi, cambio_usd, pib_mensal, etc.)
            data_inicio: YYYY-MM-DD (opcional)
            data_fim: YYYY-MM-DD (opcional)

        Returns: { "indicador": "...", "codigo": N, "valores": [...], "ultimo": N }
        """
        codigo = self._MACRO_CODES.get(indicador.lower())
        if not codigo:
            return self._error(f"Indicador '{indicador}' não encontrado. Disponíveis: {list(self._MACRO_CODES.keys())}")

        try:
            # Tenta python-bcb (mais robusto)
            if _BCB_AVAILABLE:
                import pandas as pd
                serie = sgs.get(codigo)
                if serie is not None and len(serie) > 0:
                    valores = serie.dropna()
                    if len(valores) > 0:
                        ultimo = float(valores.iloc[-1])
                        ultima_data = str(valores.index[-1].date())
                        result = {
                            "indicador": indicador,
                            "codigo_sgs": codigo,
                            "fonte": "BCB SGS (python-bcb)",
                            "ultimo_valor": round(ultimo, 4),
                            "ultima_data": ultima_data,
                            "total_observacoes": len(valores),
                        }
                        self._save_json(result, f"macro_{indicador}.json")
                        return result

            # Fallback: URL direta
            url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
            if data_inicio:
                url += f"&dataInicial={data_inicio.replace('-', '/')}"
            if data_fim:
                url += f"&dataFinal={data_fim.replace('-', '/')}"

            raw_data = _fetch_json(url, cache_ttl=600)
            ultimo = float(raw_data[-1]["valor"]) if raw_data else 0
            ultima_data = raw_data[-1]["data"] if raw_data else ""

            result = {
                "indicador": indicador,
                "codigo_sgs": codigo,
                "fonte": "BCB SGS",
                "ultimo_valor": round(ultimo, 4),
                "ultima_data": ultima_data,
                "total_observacoes": len(raw_data),
                "valores": raw_data[-60:],
            }
            self._save_json(result, f"macro_{indicador}.json")
            return result
        except Exception as e:
            return self._offline_macro(indicador, codigo)

    def get_multi_macro(self, indicadores: list) -> dict:
        """Busca múltiplos indicadores de uma vez."""
        results = {}
        for ind in indicadores:
            results[ind] = self.get_macro(ind)
        return results

    def get_panorama_macro(self) -> dict:
        """Retorna panorama macro completo (Selic, IPCA, CDI, câmbio, PIB)."""
        return self.get_multi_macro(["selic", "ipca", "cdi", "cambio_usd", "pib_mensal", "desemprego"])

    # ==================================================================
    # AÇÕES — brapi.dev
    # ==================================================================

    def get_cotacao(self, ticker: str) -> dict:
        """
        Cotação atual de um ativo na B3.

        Args:
            ticker: Código do ativo (PETR4, VALE3, ITUB4, MGLU3, etc.)

        Returns: { "ticker": "...", "preco": N, "variacao": N, "nome": "...", ... }
        """
        try:
            url = f"{BRAPI_BASE}/quote/{ticker}?token={BRAPI_TOKEN}" if BRAPI_TOKEN else f"{BRAPI_BASE}/quote/{ticker}"
            # Ativos sem token: PETR4, MGLU3, VALE3, ITUB4 funcionam sem token
            data = _fetch_json(url, cache_ttl=120)
            quotes = data.get("results", [])
            if not quotes:
                return self._error(f"Ticker não encontrado: {ticker}")

            quote = quotes[0]
            result = {
                "ticker": quote.get("symbol", ticker),
                "nome": quote.get("longName", ""),
                "preco_atual": quote.get("regularMarketPrice", 0),
                "variacao_percentual": quote.get("regularMarketChangePercent", 0),
                "variacao_absoluta": quote.get("regularMarketChange", 0),
                "maxima_dia": quote.get("regularMarketDayHigh", 0),
                "minima_dia": quote.get("regularMarketDayLow", 0),
                "abertura": quote.get("regularMarketOpen", 0),
                "volume": quote.get("regularMarketVolume", 0),
                "data": datetime.now().isoformat(),
                "fonte": "brapi.dev",
            }
            self._save_json(result, f"cotacao_{ticker}.json")
            return result
        except Exception as e:
            return self._error(f"Erro brapi: {e}")

    def get_multiplas_cotacoes(self, tickers: list) -> dict:
        """Cotações de múltiplos ativos."""
        results = {}
        for t in tickers:
            results[t] = self.get_cotacao(t)
        return results

    def get_ranking(self, tipo: str = "high") -> list:
        """
        Ranking de ativos. Tipos: high (maiores altas), low (maiores baixas),
        volume (maior volume), change (maior variação).
        """
        try:
            params = {"sortBy": tipo, "sortOrder": "desc", "limit": "20"}
            if BRAPI_TOKEN:
                params["token"] = BRAPI_TOKEN
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{BRAPI_BASE}/quote/list?{query}"
            data = _fetch_json(url, cache_ttl=300)

            stocks = data.get("stocks", [])
            result = [{
                "ticker": s.get("stock", ""),
                "preco": s.get("close", 0),
                "variacao": s.get("change", 0),
                "variacao_percentual": s.get("changePercent", 0),
                "volume": s.get("volume", 0),
                "setor": s.get("sector", ""),
            } for s in stocks[:20]]

            self._save_json({"tipo": tipo, "data": result}, f"ranking_{tipo}.json")
            return result if result else self._offline_ranking(tipo)
        except Exception:
            return self._offline_ranking(tipo)

    # ==================================================================
    # FIIS — brapi.dev
    # ==================================================================

    def get_fii(self, ticker: str) -> dict:
        """Dados de um Fundo Imobiliário."""
        try:
            url = f"{BRAPI_BASE}/quote/{ticker}?token={BRAPI_TOKEN}" if BRAPI_TOKEN else f"{BRAPI_BASE}/quote/{ticker}"
            data = _fetch_json(url, cache_ttl=120)
            quotes = data.get("results", [])
            if not quotes:
                return self._error(f"FII não encontrado: {ticker}")

            q = quotes[0]
            result = {
                "ticker": q.get("symbol", ticker),
                "nome": q.get("longName", ""),
                "preco": q.get("regularMarketPrice", 0),
                "variacao": q.get("regularMarketChangePercent", 0),
                "dividend_yield": q.get("dividendYield", 0),
                "p_vp": q.get("priceToBook", 0),
                "valor_patrimonial": q.get("bookValue", 0),
                "volume": q.get("regularMarketVolume", 0),
                "maxima_52s": q.get("fiftyTwoWeekHigh", 0),
                "minima_52s": q.get("fiftyTwoWeekLow", 0),
                "setor": q.get("sector", ""),
                "fonte": "brapi.dev",
            }
            self._save_json(result, f"fii_{ticker}.json")
            return result
        except Exception as e:
            return self._error(f"Erro FII: {e}")

    def get_fiis_ranking(self) -> list:
        """Ranking dos FIIs com maior dividend yield."""
        try:
            url = f"{BRAPI_BASE}/v2/fii?limit=50&sortBy=dy&sortOrder=desc&token={BRAPI_TOKEN}" if BRAPI_TOKEN else None
            if not url:
                return self._offline_fiis_ranking()
            data = _fetch_json(url, cache_ttl=600)
            fiis = data.get("fiis", [])
            result = [{
                "ticker": f.get("ticker", ""),
                "nome": f.get("name", ""),
                "preco": f.get("currentPrice", 0),
                "dy": f.get("dy", 0),
                "p_vp": f.get("p_vp", 0),
                "valor_patrimonial": f.get(" patrimonyPrice", 0),
                "liquidez": f.get("liquidity", 0),
                "setor": f.get("segment", ""),
            } for f in fiis[:20]]
            self._save_json({"data": result}, "fiis_ranking.json")
            return result
        except Exception:
            return self._offline_fiis_ranking()

    # ==================================================================
    # TESOURO DIRETO
    # ==================================================================

    def get_tesouro(self) -> dict:
        """Títulos públicos disponíveis no Tesouro Direto."""
        try:
            data = _fetch_json(TESOURO_URL, cache_ttl=600)
            bonds = data.get("response", {}).get("trsrBondList", [])
            if not bonds:
                return self._offline_tesouro()

        except Exception:
            return self._offline_tesouro()

        result = {
            "titulos": [],
            "data_atualizacao": data.get("response", {}).get("msgDate", ""),
            "total_titulos": len(bonds),
        }

        for bond in bonds:
            result["titulos"].append({
                "nome": bond.get("nmTitulo", ""),
                "vencimento": bond.get("dtVencimento", ""),
                "taxa_compra": bond.get("pctTaxaCompra", 0),
                "taxa_venda": bond.get("pctTaxaVenda", 0),
                "preco_compra": bond.get("vlUnitatioCompra", 0),
                "preco_venda": bond.get("vlUnitatioVenda", 0),
                "valor_minimo": bond.get("vlMinimo", 0),
            })

        self._save_json(result, "tesouro_direto.json")
        return result

    # ==================================================================
    # FUNDAMENTOS (CVM + brapi)
    # ==================================================================

    def get_dividendos(self, ticker: str) -> dict:
        """Histórico de dividendos de um ativo."""
        try:
            url = f"{BRAPI_BASE}/quote/{ticker}/dividends?token={BRAPI_TOKEN}" if BRAPI_TOKEN else None
            if not url:
                return self._offline_dividendos(ticker)

            data = _fetch_json(url, cache_ttl=3600)
            dividends = data.get("dividends", [])
            total = sum(float(d.get("value", 0)) for d in dividends)
            result = {
                "ticker": ticker.upper(),
                "total_dividendos_12m": round(total, 2),
                "quantidade_pagamentos": len(dividends),
                "ultimos": [
                    {"data": d.get("date", ""), "valor": d.get("value", 0), "tipo": d.get("type", "")}
                    for d in dividends[-6:]
                ],
                "fonte": "brapi.dev",
            }
            self._save_json(result, f"dividendos_{ticker}.json")
            return result
        except Exception:
            return self._offline_dividendos(ticker)

    def get_balanco(self, ticker: str) -> dict:
        """Balanço patrimonial via brapi.dev (plano free: histórico 3 meses)."""
        try:
            url = f"{BRAPI_BASE}/quote/{ticker}/balancesheet?token={BRAPI_TOKEN}" if BRAPI_TOKEN else f"{BRAPI_BASE}/quote/{ticker}"
            data = _fetch_json(url, cache_ttl=3600)
            result = {
                "ticker": ticker.upper(),
                "fonte": "brapi.dev",
                "dados": data,
            }
            return result
        except Exception:
            return self._error(f"Balanço não disponível para {ticker} (requer token brapi.dev)")

    # ==================================================================
    # COMPARAÇÃO E SÍNTESE
    # ==================================================================

    def comparar_ativos(self, tickers: list) -> dict:
        """Compara múltiplos ativos lado a lado."""
        cotacoes = self.get_multiplas_cotacoes(tickers)
        comparacao = {
            "tickers": tickers,
            "data": datetime.now().isoformat(),
            "ativos": cotacoes,
            "resumo": {},
        }

        precos = {t: c.get("preco_atual", 0) for t, c in cotacoes.items() if "preco_atual" in c}
        variacoes = {t: c.get("variacao_percentual", 0) for t, c in cotacoes.items() if "variacao_percentual" in c}

        if precos:
            melhor_ticker = max(variacoes, key=variacoes.get) if variacoes else None
            comparacao["resumo"] = {
                "maior_valor": max(precos, key=precos.get),
                "menor_valor": min(precos, key=precos.get),
                "melhor_dia": melhor_ticker,
                "quantidade": len(tickers),
            }

        self._save_json(comparacao, f"comparacao_{'_'.join(tickers)}.json")
        return comparacao

    def sintese_mercado(self) -> dict:
        """Síntese completa do mercado: macro + top ações + FIIs + Tesouro."""
        return {
            "data": datetime.now().isoformat(),
            "panorama_macro": self.get_panorama_macro(),
            "top_acoes": self.get_ranking("volume")[:5],
            "top_fiis": self.get_fiis_ranking()[:5],
            "tesouro": self.get_tesouro(),
        }

    # ==================================================================
    # UTILITÁRIOS
    # ==================================================================

    def status(self) -> dict:
        """Status da bridge e disponibilidade das APIs."""
        apis = {
            "bcb_sgs": True,
            "brapi_dev": bool(BRAPI_TOKEN),
            "tesouro_direto": True,
            "ibge_sidra": True,
        }
        return {
            "online": any(apis.values()),
            "apis": apis,
            "brapi_token_configured": bool(BRAPI_TOKEN),
            "acoes_sem_token": ["PETR4", "MGLU3", "VALE3", "ITUB4"],
        }

    def _save_json(self, data: dict, filename: str) -> str:
        path = os.path.join(self.output_dir, filename)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return path

    def _error(self, msg: str) -> dict:
        return {"error": True, "message": msg}

    def _offline_macro(self, indicador: str, codigo: int) -> dict:
        """Fallback offline para dados macro."""
        offline_data = {
            "selic": {"ultimo_valor": 14.25, "ultima_data": "2026-06-19"},
            "selic_meta": {"ultimo_valor": 14.25, "ultima_data": "2026-06-18"},
            "cdi": {"ultimo_valor": 14.15, "ultima_data": "2026-06-19"},
            "ipca": {"ultimo_valor": 0.58, "ultima_data": "2026-05-30"},
            "ipca_12m": {"ultimo_valor": 5.20, "ultima_data": "2026-05-30"},
            "igpm": {"ultimo_valor": 0.82, "ultima_data": "2026-05-30"},
            "cambio_usd": {"ultimo_valor": 5.04, "ultima_data": "2026-06-19"},
            "pib_mensal": {"ultimo_valor": 1142240.6, "ultima_data": "2026-04-30"},
            "desemprego": {"ultimo_valor": 5.6, "ultima_data": "2026-04-30"},
            "divida_publica": {"ultimo_valor": 78.5, "ultima_data": "2026-04-30"},
        }
        data = offline_data.get(indicador, {"ultimo_valor": 0, "ultima_data": ""})
        return {
            "indicador": indicador,
            "codigo_sgs": codigo,
            "fonte": "offline_sample",
            "ultimo_valor": data["ultimo_valor"],
            "ultima_data": data["ultima_data"],
            "total_observacoes": 0,
            "offline": True,
        }

    # ==================================================================
    # DADOS OFFLINE (fallback)
    # ==================================================================

    def _offline_ranking(self, tipo: str = "volume") -> list:
        sample = {
            "high": [{"ticker": "PETR4", "preco": 42.50, "variacao_percentual": 3.2, "volume": 45000000}],
            "low": [{"ticker": "MGLU3", "preco": 8.75, "variacao_percentual": -4.1, "volume": 28000000}],
            "volume": [
                {"ticker": "PETR4", "preco": 42.50, "variacao": 1.32, "volume": 45000000},
                {"ticker": "VALE3", "preco": 68.90, "variacao": -0.45, "volume": 38000000},
                {"ticker": "ITUB4", "preco": 35.20, "variacao": 0.85, "volume": 31000000},
                {"ticker": "BBAS3", "preco": 52.10, "variacao": 1.10, "volume": 25000000},
                {"ticker": "B3SA3", "preco": 14.30, "variacao": -0.20, "volume": 22000000},
            ],
        }
        return sample.get(tipo, sample["volume"])

    def _offline_fiis_ranking(self) -> list:
        return [
            {"ticker": "KNRI11", "nome": "Kinea Renda Imobiliaria", "preco": 110.50, "dy": 8.5, "setor": "Renda"},
            {"ticker": "HGLG11", "nome": "CSHG Logistica", "preco": 95.20, "dy": 9.2, "setor": "Logistica"},
            {"ticker": "XPLG11", "nome": "XP Logistica", "preco": 88.40, "dy": 10.1, "setor": "Logistica"},
            {"ticker": "MXRF11", "nome": "Maxi Renda", "preco": 10.80, "dy": 11.5, "setor": "Hibrido"},
            {"ticker": "BCFF11", "nome": "BTC Pactual FII", "preco": 78.30, "dy": 9.8, "setor": "Papel"},
        ]

    def _offline_tesouro(self) -> dict:
        return {
            "data_atualizacao": datetime.now().strftime("%Y-%m-%d"),
            "total_titulos": 8,
            "titulos": [
                {"nome": "Tesouro Selic 2027", "vencimento": "2027-03-01", "taxa_compra": 14.25, "preco_venda": 10000.00},
                {"nome": "Tesouro IPCA+ 2035", "vencimento": "2035-05-15", "taxa_compra": 6.50, "preco_venda": 8500.00},
                {"nome": "Tesouro Prefixado 2029", "vencimento": "2029-01-01", "taxa_compra": 13.80, "preco_venda": 9200.00},
                {"nome": "Tesouro IPCA+ 2045", "vencimento": "2045-05-15", "taxa_compra": 6.70, "preco_venda": 7200.00},
                {"nome": "Tesouro RendA+ 2030", "vencimento": "2030-06-15", "taxa_compra": 6.40, "preco_venda": 8800.00},
                {"nome": "Tesouro Educa+ 2031", "vencimento": "2031-06-15", "taxa_compra": 6.55, "preco_venda": 8100.00},
            ],
        }

    def _offline_dividendos(self, ticker: str) -> dict:
        return {
            "ticker": ticker.upper(),
            "total_dividendos_12m": 2.85,
            "quantidade_pagamentos": 6,
            "ultimos": [
                {"data": "2026-05-15", "valor": 0.52, "tipo": "dividendo"},
                {"data": "2026-04-15", "valor": 0.48, "tipo": "dividendo"},
                {"data": "2026-03-15", "valor": 0.50, "tipo": "dividendo"},
                {"data": "2026-02-15", "valor": 0.45, "tipo": "dividendo"},
                {"data": "2026-01-15", "valor": 0.47, "tipo": "dividendo"},
                {"data": "2025-12-15", "valor": 0.43, "tipo": "dividendo"},
            ],
            "fonte": "offline_sample",
        }


# =====================================================================
# SINGLETON
# =====================================================================
_financial_bridge = None


def get_financial_bridge() -> FinancialBridgeBR:
    global _financial_bridge
    if _financial_bridge is None:
        _financial_bridge = FinancialBridgeBR()
    return _financial_bridge
