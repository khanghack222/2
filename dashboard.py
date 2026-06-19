"""dashboard.py — Web Dashboard for bot management."""
from aiohttp import web
import time
import os
import logging

logger = logging.getLogger(__name__)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bot Terminal - Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0f0f23;color:#e0e0e0;min-height:100vh}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:20px 30px;border-bottom:2px solid #0f3460;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:1.5rem;color:#e94560}
.header .status{padding:6px 16px;border-radius:20px;font-size:.85rem;font-weight:600}
.online{background:#0a3d0a;color:#4caf50;border:1px solid #4caf50}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;padding:24px}
.card{background:#1a1a2e;border-radius:12px;padding:20px;border:1px solid #16213e;transition:transform .2s}
.card:hover{transform:translateY(-2px)}
.card .number{font-size:2rem;font-weight:700;color:#e94560}
.card .label{color:#888;margin-top:4px;font-size:.9rem}
.section{padding:24px}
.section h2{color:#e94560;margin-bottom:16px;font-size:1.2rem}
table{width:100%;border-collapse:collapse;background:#1a1a2e;border-radius:8px;overflow:hidden}
th,td{padding:12px 16px;text-align:left;border-bottom:1px solid #16213e}
th{background:#16213e;color:#e94560;font-weight:600}
tr:hover{background:#16213e}
.badge{background:#e94560;color:#fff;padding:2px 8px;border-radius:10px;font-size:.75rem}
.footer{text-align:center;padding:20px;color:#555;font-size:.8rem}
</style>
</head>
<body>
<div class="header">
  <h1>&#129302; Bot Terminal Dashboard</h1>
  <span class="status online">&#9679; Online</span>
</div>

<div class="grid" id="stats-grid"></div>

<div class="section">
  <h2>&#128200; Top Commands</h2>
  <table id="top-cmds"><thead><tr><th>Command</th><th>Count</th></tr></thead><tbody></tbody></table>
</div>

<div class="section">
  <h2>&#128100; Top Users</h2>
  <table id="top-users"><thead><tr><th>User ID</th><th>Username</th><th>Count</th></tr></thead><tbody></tbody></table>
</div>

<div class="section">
  <h2>&#9888;&#65039; Recent Errors</h2>
  <table id="recent-errors"><thead><tr><th>Command</th><th>Error</th><th>Time</th></tr></thead><tbody></tbody></table>
</div>

<div class="footer">Bot Terminal v2.0 &mdash; Powered by Python</div>

<script>
async function load(){
  try{
    const r=await fetch('/api/stats');
    const d=await r.json();
    const g=document.getElementById('stats-grid');
    g.innerHTML=`
      <div class="card"><div class="number">${d.total_cmds}</div><div class="label">Total Commands</div></div>
      <div class="card"><div class="number">${d.today_cmds}</div><div class="label">Today</div></div>
      <div class="card"><div class="number">${d.total_users}</div><div class="label">Users</div></div>
      <div class="card"><div class="number">${d.total_reminders}</div><div class="label">Reminders</div></div>
      <div class="card"><div class="number">${d.total_passwords}</div><div class="label">Passwords</div></div>
    `;
    const tc=document.querySelector('#top-cmds tbody');
    tc.innerHTML=d.top_cmds.map(r=>`<tr><td><span class="badge">${r.command}</span></td><td>${r.cnt}</td></tr>`).join('');
    const tu=document.querySelector('#top-users tbody');
    tu.innerHTML=d.top_users.map(r=>`<tr><td>${r.user_id}</td><td>${r.username||'N/A'}</td><td>${r.cnt}</td></tr>`).join('');
    const er=document.querySelector('#recent-errors tbody');
    er.innerHTML=d.recent_errors.map(r=>`<tr><td><span class="badge">${r.command}</span></td><td style="max-width:400px;overflow:hidden;text-overflow:ellipsis">${r.error||''}</td><td>${new Date(r.timestamp*1000).toLocaleString()}</td></tr>`).join('');
  }catch(e){console.error(e)}
}
load();setInterval(load,30000);
</script>
</body></html>"""


async def dashboard_handler(request):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def api_stats_handler(request):
    from database import get_stats_summary
    stats = await get_stats_summary()
    return web.json_response(stats)


async def api_health_handler(request):
    return web.json_response({"status": "ok", "uptime": time.time() - _start_time})


_start_time = time.time()


def setup_routes(app):
    app.router.add_get("/", dashboard_handler)
    app.router.add_get("/dashboard", dashboard_handler)
    app.router.add_get("/api/stats", api_stats_handler)
    app.router.add_get("/api/health", api_health_handler)
