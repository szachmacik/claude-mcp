"""
Coolify MCP Server - Streamable HTTP transport for Claude Projects integration
"""
import json
import os
import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

COOLIFY_URL = os.environ.get("COOLIFY_URL", "").rstrip("/")
COOLIFY_TOKEN = os.environ.get("COOLIFY_TOKEN", "")

mcp = FastMCP("coolify_mcp")

def _client() -> httpx.AsyncClient:
    if not COOLIFY_URL or not COOLIFY_TOKEN:
        raise ValueError("COOLIFY_URL and COOLIFY_TOKEN env vars must be set.")
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
        if code == 401: return "Error 401: Invalid token."
        if code == 404: return f"Error 404: Not found. {detail}"
        if code == 422: return f"Error 422: Validation failed. {detail}"
        return f"Error {code}: {detail}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out."
    return f"Error: {type(e).__name__}: {e}"

def _fmt(data) -> str:
    return json.dumps(data, indent=2, default=str)

class AppUUID(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID (from coolify_list_applications)")

class EnvVarInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID")
    key: str = Field(..., description="Env var name")
    value: str = Field(..., description="Env var value")
    is_preview: bool = Field(default=False)

class DeployInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: Optional[str] = Field(default=None, description="App UUID to deploy")
    tag: Optional[str] = Field(default=None, description="Deploy all apps with this tag")
    force: bool = Field(default=False, description="Force rebuild without cache")

class LogsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID")
    lines: int = Field(default=100, ge=1, le=1000)

@mcp.tool(name="coolify_health", annotations={"readOnlyHint": True})
async def coolify_health() -> str:
    """Check Coolify API connectivity and version."""
    try:
        async with _client() as c:
            r = await c.get("/version")
            r.raise_for_status()
            return _fmt({"status": "ok", "version": r.json(), "coolify_url": COOLIFY_URL})
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_applications", annotations={"readOnlyHint": True})
async def coolify_list_applications() -> str:
    """List all applications with UUIDs, status, domain and repo."""
    try:
        async with _client() as c:
            r = await c.get("/applications")
            r.raise_for_status()
            apps = r.json()
            return _fmt([{"uuid": a["uuid"], "name": a["name"], "status": a.get("status"),
                         "fqdn": a.get("fqdn"), "repo": a.get("git_repository"),
                         "restart_count": a.get("restart_count", 0)} for a in apps])
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_get_application", annotations={"readOnlyHint": True})
async def coolify_get_application(params: AppUUID) -> str:
    """Get full details of a specific application."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_deploy", annotations={"readOnlyHint": False})
async def coolify_deploy(params: DeployInput) -> str:
    """Deploy or redeploy an application. Triggers new build."""
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

@mcp.tool(name="coolify_restart_application", annotations={"readOnlyHint": False})
async def coolify_restart_application(params: AppUUID) -> str:
    """Restart application without rebuilding."""
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

@mcp.tool(name="coolify_start_application", annotations={"readOnlyHint": False})
async def coolify_start_application(params: AppUUID) -> str:
    """Start a stopped application."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/start")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_get_logs", annotations={"readOnlyHint": True})
async def coolify_get_logs(params: LogsInput) -> str:
    """Get container logs for debugging."""
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

@mcp.tool(name="coolify_get_deployment_logs", annotations={"readOnlyHint": True})
async def coolify_get_deployment_logs(params: AppUUID) -> str:
    """Get last deployment build logs - use to diagnose build failures."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/deployments", params={"per_page": 1})
            r.raise_for_status()
            deps = r.json().get("data", [])
            if not deps:
                return "No deployments found."
            dep_uuid = deps[0]["deployment_uuid"]
            r2 = await c.get(f"/deployments/{dep_uuid}")
            r2.raise_for_status()
            d = r2.json()
            status = d.get("status", "unknown")
            logs = d.get("logs", "")
            if isinstance(logs, list):
                output = "\n".join(l.get("output", "") for l in logs[-60:])
            else:
                output = str(logs)[-6000:]
            return f"Status: {status}\n\n{output}"
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_env_vars", annotations={"readOnlyHint": True})
async def coolify_list_env_vars(params: AppUUID) -> str:
    """List environment variables for an application."""
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/envs")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_set_env_var", annotations={"readOnlyHint": False})
async def coolify_set_env_var(params: EnvVarInput) -> str:
    """Set an environment variable. Redeploy after to apply."""
    try:
        async with _client() as c:
            body = {"key": params.key, "value": params.value, "is_preview": params.is_preview}
            r = await c.post(f"/applications/{params.uuid}/envs", json=body)
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_services", annotations={"readOnlyHint": True})
async def coolify_list_services() -> str:
    """List all services (databases, Redis, etc)."""
    try:
        async with _client() as c:
            r = await c.get("/services")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

@mcp.tool(name="coolify_list_projects", annotations={"readOnlyHint": True})
async def coolify_list_projects() -> str:
    """List all Coolify projects."""
    try:
        async with _client() as c:
            r = await c.get("/projects")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)

if __name__ == "__main__":
    print(f"Coolify MCP Server starting...")
    print(f"COOLIFY_URL: {COOLIFY_URL or 'NOT SET'}")
    print(f"COOLIFY_TOKEN: {'SET' if COOLIFY_TOKEN else 'NOT SET'}")
    print(f"Transport: streamable-http on port {os.environ.get('FASTMCP_PORT', '8080')}")
    mcp.run(transport="streamable-http")
