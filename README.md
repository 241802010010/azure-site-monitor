# azure-site-monitor

A tiny serverless site-uptime monitor built on **Azure Functions (Python)**.
It runs in the cloud — independent of any local machine — so it can tell you
when *your own* self-hosted services go offline.

> Key idea: a monitor cannot monitor itself. If your home server dies, the only
> way to know is an **external** observer. This function is that observer.

## What it does

- Probes a configurable list of URLs on a schedule (default: every 6 hours)
- Classifies each result: `ok` / `warn` / `down`
  - any HTTP response (including `401`/`403`) counts as *online* — the service is alive, it just wants credentials
  - `5xx` counts as *warn*
  - connection failure / timeout counts as *down*
- Serves two endpoints:
  - `/dashboard` — a small HTML dashboard (auto-refreshes every 60s)
  - `/api/monitor` — raw JSON, for scripting or alerting

## Endpoints

| Path | Content |
| --- | --- |
| `/dashboard` | HTML dashboard |
| `/api/monitor` | JSON payload |

Example JSON:

```json
{
  "checked_at": "2026-10-12 14:30:44 UTC",
  "summary": { "total": 4, "up": 4, "down": 0 },
  "results": [
    { "name": "My API", "url": "https://api.example.com", "http": 200, "state": "ok", "ms": 312 }
  ]
}
```

## Configure your targets

Edit the `SITES` list at the top of `function_app.py`:

```python
SITES = [
    {"name": "My API",   "url": "https://api.example.com",     "group": "self-hosted"},
    {"name": "Dashboard", "url": "https://console.example.com", "group": "self-hosted"},
    {"name": "GitHub",    "url": "https://github.com",          "group": "baseline"},
]
```

## Deploy

```bash
# 1. create supporting resources (pick a region allowed by your subscription)
az group create -n my-monitor-rg -l japaneast
az storage account create -n mymonitorstore -g my-monitor-rg -l japaneast --sku Standard_LRS
az provider register --namespace Microsoft.Web

# 2. create the function app (Consumption plan = free tier)
az functionapp create -g my-monitor-rg -n my-site-monitor \
  --storage-account mymonitorstore --consumption-plan-location japaneast \
  --runtime python --runtime-version 3.11 --functions-version 4 --os-type Linux

# 3. deploy the code
zip -r deploy.zip function_app.py requirements.txt host.json
az functionapp deployment source config-zip -g my-monitor-rg -n my-site-monitor --src deploy.zip
```

> Note: when using a non-empty `routePrefix` in `host.json`, adjust the URLs.
> This project uses `"routePrefix": ""` so `/dashboard` and `/api/monitor`
> live at the root.

## Notes

- Runs entirely on the Azure Functions **free tier** for typical schedules.
- No credentials required for the probes — it only checks reachability, so it
  never needs your API keys.
- Be a good citizen: don't point it at sites you don't own, and keep the
  interval reasonable.

## License

MIT
