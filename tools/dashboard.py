#!/usr/bin/env python3
"""
Dashboard de Status — página web com métricas de telemetria.

Uso:
    python tools/dashboard.py          # Serve na porta 8080
    python tools/dashboard.py --port 9090

Endpoints:
    GET /         → Dashboard HTML completo
    GET /api      → JSON com todas as métricas
"""
import sys
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

# Adiciona o path do projeto
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))

from tools.telemetry import queries


# =====================================================================
# HTML TEMPLATE
# =====================================================================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes — Dashboard de Status</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f0f1a;color:#e0e0e0;padding:20px}
h1{color:#fff;font-size:24px;margin-bottom:5px}
.sub{color:#888;font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px}
.card{background:#1a1a2e;border-radius:10px;padding:16px}
.card .label{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:1px}
.card .value{font-size:28px;font-weight:700;color:#fff;margin-top:4px}
.card .value.green{color:#4ade80}
.card .value.red{color:#f87171}
.card .value.blue{color:#60a5fa}
.card .value.yellow{color:#fbbf24}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}
th{text-align:left;padding:8px 10px;background:#16213e;color:#888;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #1a1a2e}
td{padding:8px 10px;border-bottom:1px solid #1e1e32}
tr:hover td{background:#1a1a30}
.badge{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.badge.ok{background:#065f46;color:#6ee7b7}
.badge.erro{background:#7f1d1d;color:#fca5a5}
.section-title{font-size:16px;font-weight:600;margin:24px 0 8px;color:#cbd5e1}
.refresh{color:#60a5fa;font-size:12px;cursor:pointer;text-decoration:underline;margin-left:8px}
</style>
</head>
<body>
<h1>⚙️ Hermes — Dashboard de Status</h1>
<p class="sub" id="subtitle">Carregando...</p>
<div class="grid" id="kpis"></div>
<h2 class="section-title">📊 Taxa de Erro por Bridge <span class="refresh" onclick="loadData()">↻</span></h2>
<div id="errorTable"></div>
<h2 class="section-title">⏱ Latência por Bridge</h2>
<div id="latencyTable"></div>
<h2 class="section-title">📅 Atividade Diária</h2>
<div id="dailyTable"></div>
<script>
async function loadData(){try{
const r=await fetch('/api');const d=await r.json();
document.getElementById('subtitle').textContent=`Últimos ${d.days} dias — Atualizado ${d.generated_at}`;
const kpi=document.getElementById('kpis');
kpi.innerHTML=`
<div class="card"><div class="label">Total de Chamadas</div><div class="value blue">${d.total_calls}</div></div>
<div class="card"><div class="label">Bridges Ativas</div><div class="value">${d.active_bridges}</div></div>
<div class="card"><div class="label">Taxa Cache Hit</div><div class="value green">${d.cache_hit_rate}%</div></div>
<div class="card"><div class="label">Custo Total (7d)</div><div class="value yellow">$${d.total_cost.toFixed(4)}</div></div>
<div class="card"><div class="label">Erro Total</div><div class="value red">${d.total_errors}</div></div>
<div class="card"><div class="label">Latência Média</div><div class="value">${d.avg_latency_ms}ms</div></div>`;
let et='<table><tr><th>Bridge</th><th>Chamadas</th><th>Erros</th><th>Taxa Erro</th><th>Lat. Média</th><th>Custo</th></tr>';
d.error_rates.forEach(r=>{
const cls=r.error_rate_pct>10?'badge erro':'badge ok';
et+=`<tr><td><strong>${r.bridge}</strong></td><td>${r.total}</td><td>${r.errors}</td><td><span class="${cls}">${r.error_rate_pct}%</span></td><td>${r.avg_latency_ms}ms</td><td>$${r.total_cost_usd.toFixed(4)}</td></tr>`;
});
et+='</table>';document.getElementById('errorTable').innerHTML=et;
let lt='<table><tr><th>Bridge</th><th>Amostras</th><th>Mínimo</th><th>Médio</th><th>Máximo</th></tr>';
d.latency.forEach(r=>{lt+=`<tr><td><strong>${r.bridge}</strong></td><td>${r.samples}</td><td>${r.min_ms}ms</td><td>${r.avg_ms}ms</td><td>${r.max_ms}ms</td></tr>`;});
lt+='</table>';document.getElementById('latencyTable').innerHTML=lt;
let dt='<table><tr><th>Dia</th><th>Chamadas</th><th>Bridges</th><th>Erros</th><th>Lat. Média</th><th>Custo</th></tr>';
d.daily.forEach(r=>{dt+=`<tr><td><strong>${r.day}</strong></td><td>${r.calls}</td><td>${r.bridges_active}</td><td>${r.errors}</td><td>${r.avg_latency_ms}ms</td><td>$${r.cost_usd.toFixed(4)}</td></tr>`;});
dt+='</table>';document.getElementById('dailyTable').innerHTML=dt;
}catch(e){document.getElementById('subtitle').textContent='Erro ao carregar dados'}}
loadData();setInterval(loadData,30000);
</script>
</body>
</html>"""


# =====================================================================
# HTTP HANDLER
# =====================================================================
class DashboardHandler(BaseHTTPRequestHandler):
    def _json(self, data: Any, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _html(self, html: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_GET(self):
        from datetime import datetime

        if self.path == "/api":
            days = 7
            error_rates = queries.error_rate(days=days) or []
            latency = queries.latency_percentiles(days=days) or []
            daily = queries.daily_summary(days=days) or []

            total_calls = sum(r["total"] for r in error_rates)
            total_errors = sum(r["errors"] for r in error_rates)
            active_bridges = len(error_rates)
            avg_latency_ms = round(
                sum(r["avg_latency_ms"] for r in error_rates if r["avg_latency_ms"])
                / max(len([r for r in error_rates if r["avg_latency_ms"]]), 1), 1
            )

            self._json({
                "days": days,
                "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "total_calls": total_calls,
                "total_errors": total_errors,
                "active_bridges": active_bridges,
                "avg_latency_ms": avg_latency_ms,
                "cache_hit_rate": queries.cache_hit_rate(days=days),
                "total_cost": queries.total_cost(days=days),
                "error_rates": error_rates,
                "latency": latency,
                "daily": daily,
            })
        else:
            self._html(HTML_TEMPLATE)


# =====================================================================
# MAIN
# =====================================================================
def main():
    port = 8080
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"[DASHBOARD] Servindo em http://0.0.0.0:{port}")
    print(f"[DASHBOARD] Dashboard em http://0.0.0.0:{port}/")
    print(f"[DASHBOARD] API JSON em http://0.0.0.0:{port}/api")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[DASHBOARD] Encerrando...")
        server.server_close()


if __name__ == "__main__":
    main()
