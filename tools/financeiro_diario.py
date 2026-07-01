"""
Financial Data Collector — coleta dados de múltiplas fontes para
consolidar um panorama diário de investimentos no Brasil.

Fontes:
1. BCB SGS (via MCP-Brasil) — Selic, CDI, câmbio, IPCA
2. brapi.dev — Ibovespa, ações, FIIs, câmbio
3. HG Brasil — câmbio, indicadores, bolsa (dados em tempo real)
4. Yahoo Finance — Ibovespa (^BVSP), commodities, mercados globais
"""
import json, os, sys
import re
from datetime import datetime, timedelta
from pathlib import Path

# Garante que o diretório raiz está no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

OUTPUT_DIR = Path("/opt/projetos/hermes-unified/output/financeiro_diario")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def coletar_bcb_sgs() -> dict:
    """BCB SGS via MCP-Brasil — dados macroeconômicos."""
    from tools.mcp_brasil_bridge import get_mcp_brasil_bridge
    bridge = get_mcp_brasil_bridge()

    indicadores = {}
    for nome, codigo in [("selic", 11), ("cdi", 12), ("cambio_usd", 1), ("ipca_mensal", 433)]:
        r = bridge.call_tool("bacen_ultimos_valores", codigo=codigo)
        if r.get("success"):
            indicadores[nome] = r["result"]
        else:
            indicadores[nome] = None

    return {"fonte": "BCB SGS", "indicadores": indicadores}


def coletar_brapi() -> dict:
    """brapi.dev — Ibovespa, câmbio, ações (API gratuita, 4 ativos sem token)."""
    dados = {"fonte": "brapi.dev"}
    try:
        # Ibovespa
        r = httpx.get("https://brapi.dev/api/quote/^BVSP?range=1d&interval=1d", timeout=10)
        if r.status_code == 200:
            dados["ibovespa"] = r.json().get("results", [{}])[0]

        # Câmbio USD/BRL
        r = httpx.get("https://brapi.dev/api/quote/USDBRL?range=1d&interval=1d", timeout=10)
        if r.status_code == 200:
            dados["dolar"] = r.json().get("results", [{}])[0]

        # Ações principais (permitidas sem token)
        for ticker in ["PETR4", "VALE3", "ITUB4", "MGLU3"]:
            r = httpx.get(f"https://brapi.dev/api/quote/{ticker}?range=1d&interval=1d", timeout=10)
            if r.status_code == 200:
                quotes = r.json().get("results", [])
                if quotes:
                    dados[ticker.lower()] = quotes[0]
    except Exception as e:
        dados["erro"] = str(e)

    return dados


def coletar_hg_brasil() -> dict:
    """HG Brasil — câmbio, bolsa, indicadores (API gratuita, sem token necessário para básico)."""
    dados = {"fonte": "HG Brasil"}
    try:
        # Taxas
        r = httpx.get("https://api.hgbrasil.com/finance/taxas?format=json", timeout=10)
        if r.status_code == 200:
            dados["taxas"] = r.json().get("results", {})

        # Cotações (moedas, bolsas, etc)
        r = httpx.get("https://api.hgbrasil.com/finance/quotations?format=json", timeout=10)
        if r.status_code == 200:
            dados["cotacoes"] = r.json().get("results", {})

        # Boletim IBOV
        r = httpx.get("https://api.hgbrasil.com/finance/stock_price?format=json&symbol=BVSP", timeout=10)
        if r.status_code == 200:
            dados["ibovespa"] = r.json()
    except Exception as e:
        dados["erro"] = str(e)

    return dados


def coletar_yahoo_finance() -> dict:
    """Yahoo Finance via web scraping — ^BVSP, commodities, NY."""
    dados = {"fonte": "Yahoo Finance"}
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = httpx.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/^BVSP?range=1d&interval=1d",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            dados["ibovespa"] = r.json().get("chart", {}).get("result", [{}])[0]

        # Dólar
        r = httpx.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/USDBRL=X?range=1d&interval=1d",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            dados["dolar"] = r.json().get("chart", {}).get("result", [{}])[0]

        # S&P 500 (mercado americano)
        r = httpx.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?range=1d&interval=1d",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            dados["sp500"] = r.json().get("chart", {}).get("result", [{}])[0]
    except Exception as e:
        dados["erro"] = str(e)

    return dados


def _extrair_preco(dados_fonte, caminho: list) -> float:
    """Extrai preço de uma estrutura aninhada, percorrendo chaves."""
    try:
        val = dados_fonte
        for chave in caminho:
            if isinstance(val, dict):
                val = val.get(chave)
            elif isinstance(val, list) and chave == 0:
                val = val[0] if val else None
            else:
                return None
        return float(val) if val is not None else None
    except (TypeError, ValueError, IndexError):
        return None


def coletar_ranking_acoes_brapi() -> dict:
    """brapi.dev — ranking de ações mais negociadas do dia."""
    dados = {"fonte": "brapi.dev"}
    try:
        # Ticker genérico para pegar o ranking do dia
        r = httpx.get(
            "https://brapi.dev/api/quote/list?sortBy=change&sortOrder=desc&limit=10",
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            dados["altas_dia"] = [
                {
                    "ticker": q.get("symbol"),
                    "nome": q.get("longName", q.get("shortName", "")),
                    "preco": q.get("regularMarketPrice"),
                    "variacao": q.get("regularMarketChangePercent"),
                    "volume": q.get("regularMarketVolume"),
                }
                for q in (data.get("stocks", [])[:10])
                if q.get("regularMarketChangePercent", 0) > 0
            ]
            # Baixas
            r2 = httpx.get(
                "https://brapi.dev/api/quote/list?sortBy=change&sortOrder=asc&limit=10",
                timeout=10
            )
            if r2.status_code == 200:
                data2 = r2.json()
                dados["baixas_dia"] = [
                    {
                        "ticker": q.get("symbol"),
                        "nome": q.get("longName", q.get("shortName", "")),
                        "preco": q.get("regularMarketPrice"),
                        "variacao": q.get("regularMarketChangePercent"),
                        "volume": q.get("regularMarketVolume"),
                    }
                    for q in (data2.get("stocks", [])[:10])
                    if q.get("regularMarketChangePercent", 0) < 0
                ]
    except Exception as e:
        dados["erro"] = str(e)
    return dados


def coletar_criptomoedas() -> dict:
    """CoinGecko — top criptomoedas. Fallbacks: CoinCap, scraping."""
    dados = {"fonte": "CoinGecko"}

    # Tenta CoinGecko primeiro
    try:
        r = httpx.get(
            "https://api.coingecko.com/api/v3/coins/markets"
            "?vs_currency=usd"
            "&order=volume_desc"
            "&per_page=50"
            "&page=1"
            "&sparkline=false"
            "&price_change_percentage=1h%2C24h%2C7d%2C30d",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code == 200:
            return _processar_coingecko(r.json())
    except Exception:
        pass

    # Fallback 1: CoinCap
    try:
        dados["fonte"] = "CoinCap"
        r = httpx.get("https://api.coincap.io/v2/assets?limit=50", timeout=10,
                      headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return _processar_coincap(r.json())
    except Exception:
        pass

    # Fallback 2: HG Brasil
    try:
        dados["fonte"] = "HG Brasil"
        r = httpx.get("https://api.hgbrasil.com/finance/quotations?format=json", timeout=10)
        if r.status_code == 200:
            return _processar_hg_cripto(r.json())
    except Exception:
        pass

    dados["erro"] = "Todas as fontes de cripto falharam"
    return dados


def _processar_coingecko(moedas: list) -> dict:
    """Processa dados do CoinGecko."""
    dados = {"fonte": "CoinGecko"}
    altas_dia = sorted(moedas, key=lambda m: m.get("price_change_percentage_24h_in_currency", 0), reverse=True)[:5]
    dados["altas_dia"] = [
        {"nome": m["name"], "simbolo": m["symbol"].upper(), "preco": m["current_price"],
         "variacao_24h": m.get("price_change_percentage_24h_in_currency"),
         "variacao_7d": m.get("price_change_percentage_7d_in_currency"),
         "variacao_30d": m.get("price_change_percentage_30d_in_currency")}
        for m in altas_dia
    ]
    baixas_dia = sorted(moedas, key=lambda m: m.get("price_change_percentage_24h_in_currency", 0))[:5]
    dados["baixas_dia"] = [
        {"nome": m["name"], "simbolo": m["symbol"].upper(), "preco": m["current_price"],
         "variacao_24h": m.get("price_change_percentage_24h_in_currency")}
        for m in baixas_dia
    ]
    altas_semana = sorted(moedas, key=lambda m: m.get("price_change_percentage_7d_in_currency", 0) or 0, reverse=True)[:5]
    dados["altas_semana"] = [
        {"nome": m["name"], "simbolo": m["symbol"].upper(), "preco": m["current_price"], "variacao": m.get("price_change_percentage_7d_in_currency")}
        for m in altas_semana
    ]
    altas_mes = sorted(moedas, key=lambda m: m.get("price_change_percentage_30d_in_currency", 0) or 0, reverse=True)[:5]
    dados["altas_mes"] = [
        {"nome": m["name"], "simbolo": m["symbol"].upper(), "preco": m["current_price"], "variacao": m.get("price_change_percentage_30d_in_currency")}
        for m in altas_mes
    ]
    for ticker in ["bitcoin", "ethereum"]:
        m = next((c for c in moedas if c["id"] == ticker), None)
        if m:
            dados[ticker] = {
                "preco": m["current_price"],
                "variacao_24h": m.get("price_change_percentage_24h_in_currency"),
                "variacao_7d": m.get("price_change_percentage_7d_in_currency"),
                "variacao_30d": m.get("price_change_percentage_30d_in_currency"),
                "maxima_24h": m.get("high_24h"),
                "minima_24h": m.get("low_24h"),
            }
    return dados


def _processar_coincap(data: dict) -> dict:
    """Processa dados do CoinCap (formato diferente)."""
    dados = {"fonte": "CoinCap"}
    moedas = data.get("data", [])
    if not moedas:
        return dados

    # CoinCap não fornece variação percentual diretamente,
    # mas temos changePercent24Hr
    for m in moedas:
        try:
            m["var24"] = float(m.get("changePercent24Hr", 0))
        except (TypeError, ValueError):
            m["var24"] = 0.0

    altas_dia = sorted(moedas, key=lambda m: m["var24"], reverse=True)[:5]
    dados["altas_dia"] = [
        {"nome": m["name"], "simbolo": m["symbol"], "preco": float(m.get("priceUsd", 0)),
         "variacao_24h": m["var24"]}
        for m in altas_dia
    ]
    baixas_dia = sorted(moedas, key=lambda m: m["var24"])[:5]
    dados["baixas_dia"] = [
        {"nome": m["name"], "simbolo": m["symbol"], "preco": float(m.get("priceUsd", 0)),
         "variacao_24h": m["var24"]}
        for m in baixas_dia
    ]
    for ticker, tid in [("bitcoin", "bitcoin"), ("ethereum", "ethereum")]:
        m = next((c for c in moedas if c.get("id") == tid), None)
        if m:
            dados[ticker] = {
                "preco": float(m.get("priceUsd", 0)),
                "variacao_24h": m["var24"],
                "maxima_24h": None,
                "minima_24h": None,
            }
    return dados


def _processar_hg_cripto(data: dict) -> dict:
    """Processa dados de cripto da HG Brasil."""
    dados = {"fonte": "HG Brasil"}
    moedas = {}
    results = data.get("results", {}).get("currencies", {})
    # HG tem BTC e ETH
    for key, label in [("BTC", "Bitcoin"), ("ETH", "Ethereum")]:
        c = results.get(key, {})
        if c:
            moedas[label.lower()] = {
                "preco": c.get("buy", 0),
                "variacao_24h": c.get("variation", 0),
            }
    if moedas:
        dados["bitcoin"] = moedas.get("bitcoin", {})
        dados["ethereum"] = moedas.get("ethereum", {})
        dados["altas_dia"] = [{"nome": k.capitalize(), "simbolo": k[:3].upper(), "preco": v["preco"], "variacao_24h": v["variacao_24h"]} for k, v in moedas.items()]
    return dados


def consolidar() -> dict:
    """Coleta de todas as fontes e consolida em um resumo único."""
    fontes = {
        "bcb": coletar_bcb_sgs(),
        "brapi": coletar_brapi(),
        "hg_brasil": coletar_hg_brasil(),
        "yahoo": coletar_yahoo_finance(),
        "ranking_acoes": coletar_ranking_acoes_brapi(),
        "criptomoedas": coletar_criptomoedas(),
    }

    # Consolidação inteligente — pega o melhor dado disponível
    ibov = None
    dolar = None
    sp500 = None

    # Ibovespa: brapi > yahoo > hg
    for fonte in ["brapi", "yahoo", "hg_brasil"]:
        dados = fontes[fonte]
        if not ibov:
            if fonte == "brapi":
                q = dados.get("ibovespa", {})
                if q:
                    ibov = {
                        "fonte": "brapi.dev",
                        "preco": _extrair_preco(q, ["regularMarketPrice"]),
                        "variacao_percentual": _extrair_preco(q, ["regularMarketChangePercent"]),
                        "variacao": _extrair_preco(q, ["regularMarketChange"]),
                        "maxima_dia": _extrair_preco(q, ["regularMarketDayHigh"]),
                        "minima_dia": _extrair_preco(q, ["regularMarketDayLow"]),
                    }
                    # Fallback: brapi pode ter nomes diferentes
                    if not ibov["preco"]:
                        meta = q.get("meta", {}) if isinstance(q, dict) else {}
                        ibov = None  # tenta outra fonte
            elif fonte == "yahoo":
                chart = dados.get("ibovespa", {})
                meta = chart.get("meta", {}) if isinstance(chart, dict) else {}
                if meta:
                    preco_anterior = meta.get("chartPreviousClose")
                    preco_atual = meta.get("regularMarketPrice")
                    var_pct = None
                    if preco_anterior and preco_atual and preco_anterior > 0:
                        var_pct = ((preco_atual - preco_anterior) / preco_anterior) * 100
                    ibov = {
                        "fonte": "Yahoo Finance",
                        "preco": preco_atual,
                        "variacao_percentual": var_pct,
                        "maxima_dia": meta.get("regularMarketDayHigh"),
                        "minima_dia": meta.get("regularMarketDayLow"),
                    }

    # Dólar: brapi > yahoo > hg
    for fonte in ["brapi", "yahoo", "hg_brasil"]:
        dados = fontes[fonte]
        if not dolar:
            if fonte == "brapi":
                q = dados.get("dolar", {})
                if q:
                    dolar = {
                        "fonte": "brapi.dev",
                        "preco": _extrair_preco(q, ["regularMarketPrice"]),
                        "variacao_percentual": _extrair_preco(q, ["regularMarketChangePercent"]),
                        "maxima_dia": _extrair_preco(q, ["regularMarketDayHigh"]),
                        "minima_dia": _extrair_preco(q, ["regularMarketDayLow"]),
                    }

    # S&P 500
    sp_data = fontes["yahoo"].get("sp500", {})
    meta = sp_data.get("meta", {}) if isinstance(sp_data, dict) else {}
    if meta:
        sp500 = {
            "fonte": "Yahoo Finance",
            "preco": meta.get("regularMarketPrice"),
            "maxima_dia": meta.get("regularMarketDayHigh"),
            "minima_dia": meta.get("regularMarketDayLow"),
        }

    # Extrai indicadores BCB
    bcb = fontes.get("bcb", {}).get("indicadores", {})

    return {
        "data_coleta": datetime.now().isoformat(),
        "ibovespa": ibov,
        "dolar": dolar,
        "sp500": sp500,
        "selic": bcb.get("selic"),
        "cdi": bcb.get("cdi"),
        "cambio_bcb": bcb.get("cambio_usd"),
        "ipca": bcb.get("ipca_mensal"),
        "ranking_acoes": fontes.get("ranking_acoes", {}),
        "criptomoedas": fontes.get("criptomoedas", {}),
        "fontes_utilizadas": [f["fonte"] for f in fontes.values() if isinstance(f, dict) and not f.get("erro")],
        "fontes_com_erro": [f["fonte"] for f in fontes.values() if isinstance(f, dict) and f.get("erro")],
        "_dados_brutos": fontes,
    }


def resumo_para_texto(dados: dict) -> str:
    """Converte dados consolidados em texto legível."""
    hoje = datetime.now().strftime("%d/%m/%Y")
    linhas = [f"📊 **Panorama Financeiro — {hoje}**\n"]

    # Ibovespa
    ibov = dados.get("ibovespa") or {}
    if ibov.get("preco"):
        var = ibov.get("variacao_percentual")
        var_sinal = f"{var:+.2f}%" if var else ""
        linhas.append(f"**Ibovespa:** {ibov['preco']:.0f} pts {var_sinal}")
        linhas.append(f"  • Máx: {ibov.get('maxima_dia', '—')} | Mín: {ibov.get('minima_dia', '—')}")
        linhas.append(f"  • Fonte: {ibov.get('fonte', '—')}")
        linhas.append("")

    # Dólar
    dolar = dados.get("dolar") or {}
    if dolar.get("preco"):
        var = dolar.get("variacao_percentual")
        var_sinal = f"{var:+.2f}%" if var else ""
        linhas.append(f"**Dólar:** R$ {dolar['preco']:.4f} {var_sinal}")
        linhas.append(f"  • Máx: {dolar.get('maxima_dia', '—')} | Mín: {dolar.get('minima_dia', '—')}")
        linhas.append("")

    # S&P 500
    sp = dados.get("sp500") or {}
    if sp.get("preco"):
        linhas.append(f"**S&P 500:** {sp['preco']:.0f} pts")
        linhas.append("")

    # BCB
    selic = dados.get("selic")
    if selic:
        linhas_selic = [l.strip() for l in selic.split("\n") if "|" in l]
        ultimo = linhas_selic[-1] if linhas_selic else ""
        linhas.append(f"**Selic:** {ultimo[:60]}")

    cdi = dados.get("cdi")
    if cdi:
        linhas_cdi = [l.strip() for l in cdi.split("\n") if "|" in l]
        ultimo = linhas_cdi[-1] if linhas_cdi else ""
        linhas.append(f"**CDI:** {ultimo[:60]}")

    ipca = dados.get("ipca")
    if ipca:
        linhas_ipca = [l.strip() for l in ipca.split("\n") if "|" in l]
        ultimo = linhas_ipca[-1] if linhas_ipca else ""
        linhas.append(f"**IPCA:** {ultimo[:60]}")

    linhas.append("")

    # ==================================================================
    # RANKING DE AÇÕES — Destaques do dia
    # ==================================================================
    ranking = dados.get("ranking_acoes", {})
    altas_dia = ranking.get("altas_dia", [])[:5]
    baixas_dia = ranking.get("baixas_dia", [])[:5]

    if altas_dia:
        linhas.append("**🔥 Altas do Dia — Ações:**")
        for a in altas_dia:
            var = a.get("variacao", 0) or 0
            linhas.append(f"  • {a['ticker']} ({a.get('nome', '')[:30]}): {var:+.2f}%")
        linhas.append("")

    if baixas_dia:
        linhas.append("**📉 Baixas do Dia — Ações:**")
        for a in baixas_dia[:5]:
            var = a.get("variacao", 0) or 0
            linhas.append(f"  • {a['ticker']} ({a.get('nome', '')[:30]}): {var:+.2f}%")
        linhas.append("")

    # ==================================================================
    # CRIPTOMOEDAS
    # ==================================================================
    cripto = dados.get("criptomoedas", {})

    # Bitcoin e Ethereum — referência
    for ticker, label in [("bitcoin", "Bitcoin"), ("ethereum", "Ethereum")]:
        coin = cripto.get(ticker, {})
        if coin:
            v24 = coin.get("variacao_24h")
            v7 = coin.get("variacao_7d")
            v30 = coin.get("variacao_30d")
            v_sinal = f"{v24:+.2f}%" if v24 else ""
            linhas.append(f"**{label}:** US$ {coin['preco']:,.0f} {v_sinal}")
            linhas.append(f"  • 7d: {v7:+.2f}% | 30d: {v30:+.2f}%" if v7 and v30 else "")
            if coin.get("maxima_24h"):
                linhas.append(f"  • Máx 24h: US$ {coin['maxima_24h']:,.0f} | Mín: US$ {coin['minima_24h']:,.0f}")
            linhas.append("")

    # Top 5 altas do dia — criptos
    cripto_altas_dia = cripto.get("altas_dia", [])
    if cripto_altas_dia:
        linhas.append("**🔥 Criptos em Alta (24h):**")
        for m in cripto_altas_dia:
            linhas.append(f"  • {m['nome']} ({m['simbolo']}): {m['variacao_24h']:+.2f}% → US$ {m['preco']:,.4f}")
        linhas.append("")

    # Top 5 baixas do dia — criptos
    cripto_baixas_dia = cripto.get("baixas_dia", [])
    if cripto_baixas_dia:
        linhas.append("**📉 Criptos em Baixa (24h):**")
        for m in cripto_baixas_dia:
            linhas.append(f"  • {m['nome']} ({m['simbolo']}): {m['variacao_24h']:+.2f}% → US$ {m['preco']:,.4f}")
        linhas.append("")

    # Top 5 da semana
    cripto_semana = cripto.get("altas_semana", [])
    if cripto_semana:
        linhas.append("**📅 Altas da Semana — Criptos:**")
        for m in cripto_semana:
            linhas.append(f"  • {m['nome']} ({m['simbolo']}): {m['variacao']:+.2f}% → US$ {m['preco']:,.4f}")
        linhas.append("")

    # Top 5 do mês
    cripto_mes = cripto.get("altas_mes", [])
    if cripto_mes:
        linhas.append("**📆 Altas do Mês — Criptos:**")
        for m in cripto_mes:
            linhas.append(f"  • {m['nome']} ({m['simbolo']}): {m['variacao']:+.2f}% → US$ {m['preco']:,.4f}")
        linhas.append("")

    linhas.append("")
    fontes_ok = dados.get("fontes_utilizadas", [])
    fontes_erro = dados.get("fontes_com_erro", [])
    linhas.append(f"Fontes: {', '.join(fontes_ok)}" if fontes_ok else "")
    if fontes_erro:
        linhas.append(f"⚠ Falha: {', '.join(fontes_erro)}")

    return "\n".join(linhas)


def salvar(dados: dict):
    """Salva dados brutos em JSON."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    path = OUTPUT_DIR / f"panorama_{hoje}.json"
    with open(path, "w") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False, default=str)
    return path


if __name__ == "__main__":
    import time
    t0 = time.time()
    dados = consolidar()
    path = salvar(dados)
    print(resumo_para_texto(dados))
    print(f"\n(Dados salvos em {path}, {time.time()-t0:.1f}s)")
