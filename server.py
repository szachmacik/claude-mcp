# HOLON-META: {
#   purpose: "claude-mcp - HOLON Mesh component",
#   morphic_field: "agent-state:4c67a2b1-6830-44ec-97b1-7c8f93722add",
#   startup_protocol: "READ morphic_field + biofield_external + em_grid BEFORE execution",
#   cost_impact: "96.8% token reduction via unified field",
#   wiki: "32d6d069-74d6-8164-a6d5-f41c3d26ae9b"
# }

"""
Coolify MCP Server
Streamable HTTP transport via uvicorn – stabilny za Traefik/Cloudflare
"""
import json
import os
import httpx
from typing import Optional
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

COOLIFY_URL = os.environ.get("COOLIFY_URL", "").rstrip("/")
COOLIFY_TOKEN = os.environ.get("COOLIFY_TOKEN", "")
PORT = int(os.environ.get("PORT", 8080))

mcp = FastMCP("coolify_mcp")

# ── HTTP client ────────────────────────────────────────────────────────────────
def _client() -> httpx.AsyncClient:
    if not COOLIFY_URL or not COOLIFY_TOKEN:
        raise ValueError("COOLIFY_URL and COOLIFY_TOKEN must be set")
    return httpx.AsyncClient(
        base_url=f"{COOLIFY_URL}/api/v1",
        headers={"Authorization": f"Bearer {COOLIFY_TOKEN}", "Content-Type": "application/json"},
        timeout=30,
    )

def _err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        try:
            detail = e.response.json().get("message", e.response.text)
        except Exception:
            detail = e.response.text
        msgs = {401: "Invalid token", 404: f"Not found: {detail}", 422: f"Validation: {detail}"}
        return f"Error {code}: {msgs.get(code, detail)}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out"
    return f"Error: {type(e).__name__}: {e}"

def _fmt(data) -> str:
    return json.dumps(data, indent=2, default=str)

# ── Input models ───────────────────────────────────────────────────────────────
class AppUUID(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID (from coolify_list_applications)")

class ServiceUUID(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Service UUID")

class EnvVarInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID")
    key: str = Field(..., description="Variable name e.g. DATABASE_URL")
    value: str = Field(..., description="Variable value")
    is_preview: bool = Field(default=False)

class DeployInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: Optional[str] = Field(default=None, description="Deploy specific app by UUID")
    tag: Optional[str] = Field(default=None, description="Deploy all apps with this tag")
    force: bool = Field(default=False, description="Force rebuild without cache")

class LogsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID")
    lines: int = Field(default=100, ge=1, le=1000)

# ── Tools ──────────────────────────────────────────────────────────────────────
@mcp.tool(name="coolify_health", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_health() -> str:
    """Check Coolify connectivity and version."""
    try:
        async with _client() as c:
            r = await c.get("/version")
            r.raise_for_status()
            return _fmt({"status": "ok", "version": r.json(), "url": COOLIFY_URL})
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_applications", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_applications() -> str:
    """List all applications with UUID, name, status, domain, repo."""
    try:
        async with _client() as c:
            r = await c.get("/applications")
            r.raise_for_status()
            apps = r.json()
            return _fmt([{
                "uuid": a["uuid"], "name": a["name"],
                "status": a.get("status"), "fqdn": a.get("fqdn"),
                "repo": a.get("git_repository"), "restarts": a.get("restart_count", 0)
            } for a in apps])
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_get_application", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_get_application(params: AppUUID) -> str:
    """Get full details of a specific application."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_deploy", annotations={"readOnlyHint": False, "destructiveHint": False})
async def coolify_deploy(params: DeployInput) -> str:
    """Deploy/redeploy an application. Provide uuid OR tag."""
    try:
        async with _client() as c:
            body = {}
            if params.uuid: body["uuid"] = params.uuid
            if params.tag: body["tag"] = params.tag
            if params.force: body["force"] = True
            r = await c.get("/deploy", params=body)
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_restart_application", annotations={"readOnlyHint": False, "destructiveHint": False})
async def coolify_restart_application(params: AppUUID) -> str:
    """Restart application containers without rebuilding."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/restart")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_stop_application", annotations={"readOnlyHint": False, "destructiveHint": True})
async def coolify_stop_application(params: AppUUID) -> str:
    """Stop a running application."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/stop")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_start_application", annotations={"readOnlyHint": False, "destructiveHint": False})
async def coolify_start_application(params: AppUUID) -> str:
    """Start a stopped application."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/start")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_get_logs", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_get_logs(params: LogsInput) -> str:
    """Get container logs. Essential for debugging crashes."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/logs", params={"lines": params.lines})
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                return "\n".join(str(l) for l in data)
            return str(data)
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_env_vars", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_env_vars(params: AppUUID) -> str:
    """List environment variables for an application."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/envs")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_set_env_var", annotations={"readOnlyHint": False, "destructiveHint": False})
async def coolify_set_env_var(params: EnvVarInput) -> str:
    """Set/update an environment variable. Redeploy app after to apply."""
    try:
        async with _client() as c:
            body = {"key": params.key, "value": params.value, "is_preview": params.is_preview}
            r = await c.post(f"/applications/{params.uuid}/envs", json=body)
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_projects", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_projects() -> str:
    """List all Coolify projects."""
    try:
        async with _client() as c:
            r = await c.get("/projects")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_servers", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_servers() -> str:
    """List all connected servers with status."""
    try:
        async with _client() as c:
            r = await c.get("/servers")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_services", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_services() -> str:
    """List all services (databases, Redis, etc)."""
    try:
        async with _client() as c:
            r = await c.get("/services")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_restart_service", annotations={"readOnlyHint": False, "destructiveHint": False})
async def coolify_restart_service(params: ServiceUUID) -> str:
    """Restart a service stack (database, Redis, etc)."""
    try:
        async with _client() as c:
            r = await c.get(f"/services/{params.uuid}/restart")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

# ── Entry point ────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════
# ECOSYSTEM TOOLS — dodane do istniejącego Coolify MCP
# ══════════════════════════════════════════════════════════
import asyncio
import base64
import json
import os

SUPA_URL  = "https://blgdhfcosqjzrutncbbr.supabase.co"
SUPA_SVC  = os.environ.get("SUPABASE_SERVICE_KEY","")
SUPA_ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJsZ2RoZmNvc3FqenJ1dG5jYmJyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyMjM2OTIsImV4cCI6MjA4Nzc5OTY5Mn0.LoCU2qthc6dzHAPl6BPWmy6LLOnDMjPR6ObvBR549Lc"
BRAIN_URL = "https://brain-router.maciej-koziej01.workers.dev"
BRAIN_KEY = os.environ.get("BRAIN_KEY","holon-brain-router-2026")
CM_URL    = "https://cognitive-mind.maciej-koziej01.workers.dev"
N8N_URL   = "https://n8n-bridge.maciej-koziej01.workers.dev"
TG_BOT    = os.environ.get("TG_BOT","8394457153:AAFZQ4eMHaiAnmwejmTfWZHI_5KSqhXgCXg")
TG_CHAT   = os.environ.get("TG_CHAT","8149345223")
UPSTASH   = "https://fresh-walleye-84119.upstash.io"
UPTOK     = os.environ.get("UPSTASH_TOKEN","gQAAAAAAAUiXAAIncDEwMjljNTI2ZGQ5OWQ0OGJlOTFmYWU2YjQ2OGI0NmIyZXAxODQxMTk")
GH_TOKEN  = os.environ.get("GITHUB_TOKEN","")

# ── Supabase ──────────────────────────────────────────────
@mcp.tool(name="supabase_sql", annotations={"readOnlyHint": False})
async def supabase_sql(sql: str) -> str:
    """Execute SQL on Supabase. Use for queries, inserts, function calls."""
    key = SUPA_SVC or SUPA_ANON
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPA_URL}/rest/v1/rpc/execute_sql_with_result",
            headers={"apikey":key,"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"query": sql})
        if r.status_code == 200:
            return r.text[:4000]
        # Fallback to direct table query
        return f"Error {r.status_code}: {r.text[:200]}"

@mcp.tool(name="supabase_rpc", annotations={"readOnlyHint": False})
async def supabase_rpc(function_name: str, params: dict = {}) -> str:
    """Call a Supabase RPC function."""
    key = SUPA_SVC or SUPA_ANON
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPA_URL}/rest/v1/rpc/{function_name}",
            headers={"apikey":key,"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json=params)
        return f"HTTP {r.status_code}: {r.text[:1000]}"

# ── Brain-router AI ───────────────────────────────────────
@mcp.tool(name="ai_chat", annotations={"readOnlyHint": True})
async def ai_chat(prompt: str, path: str = "reflex") -> str:
    """Chat with brain-router AI (Groq llama, ~120ms, $0). Paths: reflex/think/reason/code"""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{BRAIN_URL}/chat",
            headers={"Content-Type":"application/json","x-app-token":BRAIN_KEY,"x-urgency":"realtime"},
            json={"prompt": prompt, "force_path": path})
        d = r.json()
        return f"[{d.get('model','?')} {d.get('latency_ms')}ms] {d.get('text','')}"

# ── CognitiveMind ─────────────────────────────────────────
@mcp.tool(name="cognitive_mind_status", annotations={"readOnlyHint": True})
async def cognitive_mind_status() -> str:
    """Get CognitiveMind Durable Object status - connected nodes, hot topics."""
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.get(f"{CM_URL}/status")
        return r.text[:500]

@mcp.tool(name="cognitive_mind_push", annotations={"readOnlyHint": False})
async def cognitive_mind_push(topic: str, payload: dict, event: str = "learn") -> str:
    """Publish knowledge to CognitiveMind - broadcasts to all connected WS nodes."""
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.post(f"{CM_URL}/push",
            json={"type":"publish","topic":topic,"event":event,"payload":payload,"source_node":"claude-mcp"})
        return r.text[:200]

@mcp.tool(name="cognitive_mind_groq", annotations={"readOnlyHint": True})
async def cognitive_mind_groq(prompt: str, max_tokens: int = 500) -> str:
    """Run Groq inference via CognitiveMind edge DO (with KV cache)."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{CM_URL}/groq", json={"prompt": prompt, "max_tokens": max_tokens})
        d = r.json()
        cached = "⚡cached" if d.get("cached") else f"{d.get('latency_ms')}ms"
        return f"[{cached}] {d.get('text','')}"

@mcp.tool(name="cognitive_mind_state", annotations={"readOnlyHint": True})
async def cognitive_mind_state(key: str) -> str:
    """Get state for a topic from CognitiveMind KV cache (L0→L1→L3)."""
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.get(f"{CM_URL}/state/{key}")
        return r.text[:500]

# ── Telegram ──────────────────────────────────────────────
@mcp.tool(name="send_telegram", annotations={"readOnlyHint": False})
async def send_telegram(message: str, parse_mode: str = "") -> str:
    """Send message to Maciej via Telegram Guardian bot."""
    payload = {"chat_id": TG_CHAT, "text": message}
    if parse_mode: payload["parse_mode"] = parse_mode
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"https://api.telegram.org/bot{TG_BOT}/sendMessage", json=payload)
        d = r.json()
        return f"ok={d.get('ok')} msg_id={d.get('result',{}).get('message_id','?')}"

# ── n8n ───────────────────────────────────────────────────
@mcp.tool(name="n8n_trigger", annotations={"readOnlyHint": False})
async def n8n_trigger(webhook: str, payload: dict = {}) -> str:
    """Trigger n8n webhook via n8n-bridge CF Worker. Available: autoheal-alert, agent-factory, deploy-notification, etc."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{N8N_URL}/trigger/{webhook}",
            headers={"Content-Type":"application/json"}, json=payload)
        return r.text[:400]

# ── Upstash Redis ─────────────────────────────────────────
@mcp.tool(name="redis_get", annotations={"readOnlyHint": True})
async def redis_get(key: str) -> str:
    """Get value from Upstash Redis KV store."""
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{UPSTASH}/get/{key}", headers={"Authorization":f"Bearer {UPTOK}"})
        return r.text[:500]

@mcp.tool(name="redis_set", annotations={"readOnlyHint": False})
async def redis_set(key: str, value: str, ttl: int = 3600) -> str:
    """Set value in Upstash Redis with TTL (seconds)."""
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{UPSTASH}/set/{key}/{value}/EX/{ttl}", headers={"Authorization":f"Bearer {UPTOK}"})
        return r.text[:100]

# ── GitHub ────────────────────────────────────────────────
@mcp.tool(name="github_read_file", annotations={"readOnlyHint": True})
async def github_read_file(repo: str, path: str, branch: str = "main") -> str:
    """Read a file from GitHub. repo format: szachmacik/brain-router"""
    if not GH_TOKEN: return "Error: GITHUB_TOKEN not set"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}",
            headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github.v3+json"})
        if r.status_code == 200:
            return base64.b64decode(r.json()["content"]).decode()[:5000]
        return f"Error {r.status_code}: {r.text[:200]}"

@mcp.tool(name="github_write_file", annotations={"readOnlyHint": False})
async def github_write_file(repo: str, path: str, content: str, message: str) -> str:
    """Write/update a file in GitHub repository."""
    if not GH_TOKEN: return "Error: GITHUB_TOKEN not set"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"https://api.github.com/repos/{repo}/contents/{path}",
            headers={"Authorization":f"token {GH_TOKEN}"})
        sha = r.json().get("sha","") if r.status_code == 200 else ""
        payload = {"message":message,"content":base64.b64encode(content.encode()).decode()}
        if sha: payload["sha"] = sha
        r2 = await c.put(f"https://api.github.com/repos/{repo}/contents/{path}",
            headers={"Authorization":f"token {GH_TOKEN}","Content-Type":"application/json"}, json=payload)
        return f"commit {r2.json().get('commit',{}).get('sha','?')[:12]} | {r2.status_code}"

# ── Ecosystem audit ───────────────────────────────────────
@mcp.tool(name="ecosystem_audit", annotations={"readOnlyHint": True})
async def ecosystem_audit() -> str:
    """Full parallel health check of all ecosystem components."""
    workers = ["brain-router","cognitive-mind","agent-router","n8n-bridge",
               "task-executor","watchdog-v2","coolify-agent","council-dispatcher",
               "intelligence-engine","adaptive-router","mesh-coordinator","lane-gateway"]
    async with httpx.AsyncClient(timeout=8) as c:
        tasks = [c.get(f"https://{w}.maciej-koziej01.workers.dev/health") for w in workers]
        hub_t = c.get("https://hub.ofshore.dev/api/health")
        all_tasks = tasks + [hub_t]
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
    
    names = workers + ["integration-hub"]
    report = {}
    ok = 0
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            report[name] = "❌ error"
        elif result.status_code == 200:
            report[name] = "✅ ok"
            ok += 1
        else:
            report[name] = f"❌ {result.status_code}"
    
    report["score"] = f"{ok}/{len(names)}"
    return json.dumps(report, indent=2)

# ── CF Worker call ────────────────────────────────────────
@mcp.tool(name="worker_call", annotations={"readOnlyHint": False})
async def worker_call(worker: str, path: str = "/health", method: str = "GET", body: dict = {}) -> str:
    """Call any Cloudflare Worker endpoint. worker=name, e.g. brain-router"""
    url = f"https://{worker}.maciej-koziej01.workers.dev{path}"
    async with httpx.AsyncClient(timeout=15) as c:
        if method.upper() == "GET":
            r = await c.get(url)
        else:
            r = await c.post(url, json=body, headers={"Content-Type":"application/json"})
        return f"HTTP {r.status_code}: {r.text[:2000]}"


if __name__ == "__main__":
    import uvicorn
    print(f"[coolify-mcp] Starting on port {PORT}")
    print(f"[coolify-mcp] COOLIFY_URL: {COOLIFY_URL or 'NOT SET'}")
    print(f"[coolify-mcp] COOLIFY_TOKEN: {'SET' if COOLIFY_TOKEN else 'NOT SET'}")
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
