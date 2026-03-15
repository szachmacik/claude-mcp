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
if __name__ == "__main__":
    import uvicorn
    print(f"[coolify-mcp] Starting on port {PORT}")
    print(f"[coolify-mcp] COOLIFY_URL: {COOLIFY_URL or 'NOT SET'}")
    print(f"[coolify-mcp] COOLIFY_TOKEN: {'SET' if COOLIFY_TOKEN else 'NOT SET'}")
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
