# Coolify MCP Server

Daje Claude stały dostęp do zarządzania Coolify infrastrukturą.

## Co robi

| Tool | Opis |
|------|------|
| `coolify_health` | Sprawdź połączenie |
| `coolify_list_projects` | Lista projektów |
| `coolify_list_servers` | Lista serwerów |
| `coolify_list_applications` | Lista aplikacji + UUID |
| `coolify_get_application` | Szczegóły aplikacji |
| `coolify_deploy_application` | Deploy/redeploy |
| `coolify_restart_application` | Restart bez rebuildu |
| `coolify_start_application` | Uruchom aplikację |
| `coolify_stop_application` | Zatrzymaj aplikację |
| `coolify_get_logs` | Pobierz logi kontenera |
| `coolify_list_env_vars` | Lista env vars |
| `coolify_set_env_var` | Ustaw env var |
| `coolify_list_services` | Lista serwisów (bazy, Redis) |
| `coolify_restart_service` | Restart serwisu |
| `coolify_list_deployments` | Historia deploymentów |
| `coolify_list_databases` | Lista baz danych |

---

## Deploy na Coolify (własny serwer)

### 1. Wrzuć kod na GitHub
```bash
git init
git add .
git commit -m "coolify mcp server"
git remote add origin https://github.com/TWOJ_USER/coolify-mcp
git push -u origin main
```

### 2. Utwórz aplikację w Coolify
- New Resource → Application → Public Repository
- Git URL: `https://github.com/TWOJ_USER/coolify-mcp`
- Build Pack: **Dockerfile**
- Port: `8080`

### 3. Ustaw env vars w Coolify dla tej aplikacji
```
COOLIFY_URL=https://twoj-coolify.example.com
COOLIFY_TOKEN=twoj-api-token
PORT=8080
```

### 4. Deploy → Sprawdź czy działa
```bash
curl https://coolify-mcp.twoja-domena.com/health
```

---

## Podłącz do Claude Projects (stały dostęp!)

1. Otwórz [claude.ai](https://claude.ai)
2. Lewy panel → **Projects** → **New Project** → Nazwij "Infrastructure"
3. W projekcie → **Project Settings** → **Integrations** → **Add MCP Server**
4. Wpisz URL: `https://coolify-mcp.twoja-domena.com`
5. **Save**

Od teraz każda rozmowa w projekcie "Infrastructure" ma automatyczny dostęp do Coolify.

---

## System prompt dla projektu (wklej w Project Instructions)

```
Masz dostęp do Coolify MCP Server zarządzającego moją infrastrukturą na DigitalOcean.

Przy każdym zadaniu infrastrukturalnym:
1. Najpierw użyj coolify_health żeby sprawdzić połączenie
2. Użyj coolify_list_applications żeby znaleźć UUID aplikacji
3. Działaj na podstawie rzeczywistych danych z API, nie zgaduj UUID

Moja infrastruktura:
- Serwer: DigitalOcean
- Coolify: [TWÓJ URL]
- Stack: React + Supabase + Cloudflare Pages

Przy problemach zawsze sprawdź logi przez coolify_get_logs przed podjęciem działania.
```

---

## Lokalne testowanie

```bash
pip install -r requirements.txt

# stdio mode (dla Claude Desktop)
COOLIFY_URL=https://twoj-coolify.com COOLIFY_TOKEN=xxx python server.py

# HTTP mode (dla Claude Projects)
COOLIFY_URL=https://twoj-coolify.com COOLIFY_TOKEN=xxx python server.py http
```

## Claude Desktop (opcja alternatywna)

W `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "coolify": {
      "command": "python",
      "args": ["/ścieżka/do/server.py"],
      "env": {
        "COOLIFY_URL": "https://twoj-coolify.com",
        "COOLIFY_TOKEN": "twoj-token"
      }
    }
  }
}
```
