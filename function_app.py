# -*- coding: utf-8 -*-
"""
Azure Function: site uptime monitor
===================================
Serves:
  GET /dashboard    -> small HTML dashboard (auto-refresh)
  GET /api/monitor  -> JSON payload

Plus a scheduled trigger that probes everything every 6 hours.

Why it exists: your own self-hosted services can't tell you they went down.
An external observer in a different datacenter can.
"""
import azure.functions as func
import json
import time
import datetime
import urllib.request
import urllib.error

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# ============ configure your targets here ============
SITES = [
    # self-hosted services (reachable through a tunnel / public entry point)
    {"name": "My API", "url": "https://api.example.com", "group": "self-hosted"},
    {"name": "Dashboard", "url": "https://console.example.com", "group": "self-hosted"},
    # third-party services
    {"name": "GitHub", "url": "https://github.com", "group": "baseline"},
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0"


def probe(url: str, timeout: int = 12) -> dict:
    """Probe one URL.

    Rules:
      - any HTTP response (even 401/403) -> service is up
      - 5xx -> warn
      - connection error / timeout -> down
    """
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        r = urllib.request.urlopen(req, timeout=timeout)
        code = r.status
        state = "ok" if code < 400 else ("warn" if code < 500 else "down")
        return {"http": code, "state": state, "ms": round((time.time() - t0) * 1000)}
    except urllib.error.HTTPError as e:
        code = e.code
        state = "ok" if code in (401, 403) else ("warn" if code < 500 else "down")
        return {"http": code, "state": state, "ms": round((time.time() - t0) * 1000)}
    except Exception as e:
        return {"http": None, "state": "down", "ms": round((time.time() - t0) * 1000),
                "detail": type(e).__name__}


def run_all() -> dict:
    results = []
    for s in SITES:
        results.append({**s, **probe(s["url"])})
    return {
        "checked_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "summary": {
            "total": len(results),
            "up": sum(1 for r in results if r["state"] == "ok"),
            "down": sum(1 for r in results if r["state"] == "down"),
        },
        "results": results,
    }


# ============ JSON endpoint ============
@app.route(route="api/monitor", methods=["GET"])
def monitor(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(run_all(), ensure_ascii=False, indent=1),
        mimetype="application/json; charset=utf-8", status_code=200)


# ============ HTML dashboard ============
CSS = """
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}
.sub{color:#8b949e;font-size:12px;margin-bottom:16px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 18px;min-width:110px}
.card .n{font-size:26px;font-weight:700;line-height:1.1}
.card .l{font-size:12px;color:#8b949e}
.ok{color:#3fb950}.down{color:#f85149}.warn{color:#d29922}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #21262d}
th{color:#8b949e;font-size:12px;font-weight:600}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px}
.dot.ok{background:#3fb950;box-shadow:0 0 6px #3fb95088}
.dot.down{background:#f85149;box-shadow:0 0 6px #f8514988}
.dot.warn{background:#d29922}
.lat{font-variant-numeric:tabular-nums;color:#8b949e}
a{color:#58a6ff;text-decoration:none}
.foot{color:#8b949e;font-size:12px;margin-top:18px;line-height:1.7}
"""


def render_html(data: dict) -> str:
    s = data["summary"]
    rows = []
    last_group = None
    for r in data["results"]:
        if r["group"] != last_group:
            last_group = r["group"]
            rows.append(f'<tr><td colspan="4" style="color:#8b949e;font-size:12px;'
                        f'padding-top:16px;border-bottom:none">{last_group}</td></tr>')
        st = r["state"]
        label = {"ok": "up", "warn": "warn", "down": "down"}[st]
        http = r.get("http") or "-"
        d = r.get("detail", "")
        rows.append(
            f'<tr><td><span class="dot {st}"></span>{r["name"]}</td>'
            f'<td class="{st}">{label}</td>'
            f'<td class="lat">{http}{" / " + d if d else ""}</td>'
            f'<td class="lat">{r["ms"]} ms</td></tr>')
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Site Monitor</title><meta http-equiv="refresh" content="60">
<style>{CSS}</style></head><body><div class=wrap>
<h1>Site uptime monitor</h1>
<div class=sub>external observer · auto-refresh 60s · checked {data["checked_at"]}</div>
<div class=cards>
<div class=card><div class="n">{s["total"]}</div><div class=l>targets</div></div>
<div class=card><div class="n ok">{s["up"]}</div><div class=l>up</div></div>
<div class=card><div class="n {'down' if s['down'] else 'ok'}">{s["down"]}</div><div class=l>down</div></div>
</div>
<table><tr><th>target</th><th>state</th><th>http</th><th>latency</th></tr>
{"".join(rows)}
</table>
<div class=foot>JSON: <a href="/api/monitor">/api/monitor</a></div>
</div></body></html>"""


@app.route(route="dashboard", methods=["GET"])
def dashboard(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(render_html(run_all()),
                             mimetype="text/html; charset=utf-8", status_code=200)


# ============ scheduled trigger (every 6 hours) ============
@app.schedule(schedule="0 0 */6 * * *", arg_name="timer", run_on_startup=False,
              use_monitor=False)
def monitor_scheduled(timer: func.TimerRequest) -> None:
    print(json.dumps(run_all(), ensure_ascii=False))
