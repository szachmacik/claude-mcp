"""
Coolify MCP Server
Manages Coolify infrastructure via REST API.
Deploy this server, add to Claude Projects as persistent MCP connector.
"""

import json
import os
from typing import Optional, List
import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

# ── Config ──────────────────────────────────────────────────────────────────
COOLIFY_URL = os.environ.get("COOLIFY_URL", "").rstrip("/")
COOLIFY_TOKEN = os.environ.get("COOLIFY_TOKEN", "")

mcp = FastMCP("coolify_mcp")


# ── HTTP Client ──────────────────────────────────────────────────────────────
def _client() -> httpx.AsyncClient:
    if not COOLIFY_URL or not COOLIFY_TOKEN:
        raise ValueError(
            "COOLIFY_URL and COOLIFY_TOKEN env vars must be set. "
            "Example: COOLIFY_URL=https://coolify.example.com COOLIFY_TOKEN=your-token"
        )
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
        if code == 401:
            return "Error 401: Invalid token. Check COOLIFY_TOKEN."
        if code == 404:
            return f"Error 404: Resource not found. {detail}"
        if code == 422:
            return f"Error 422: Validation failed. {detail}"
        return f"Error {code}: {detail}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Is Coolify reachable?"
    return f"Error: {type(e).__name__}: {e}"


def _fmt(data) -> str:
    return json.dumps(data, indent=2, default=str)


# ── Input Models ─────────────────────────────────────────────────────────────
class AppUUID(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID (from coolify_list_applications)")


class ServiceUUID(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Service UUID (from coolify_list_services)")


class EnvVarInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID")
    key: str = Field(..., description="Environment variable name, e.g. DATABASE_URL")
    value: str = Field(..., description="Environment variable value")
    is_preview: bool = Field(default=False, description="Set for preview environments")


class DeployTagInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    tag: Optional[str] = Field(default=None, description="Deploy all apps with this tag")
    uuid: Optional[str] = Field(default=None, description="Deploy specific app by UUID")
    force: bool = Field(default=False, description="Force rebuild without cache")


class CreateAppInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    project_uuid: str = Field(..., description="Project UUID to deploy into")
    server_uuid: str = Field(..., description="Server UUID to deploy on")
    environment_name: str = Field(default="production", description="Environment name")
    git_repository: str = Field(..., description="Git repo URL, e.g. https://github.com/user/repo")
    git_branch: str = Field(default="main", description="Branch to deploy")
    build_pack: str = Field(default="nixpacks", description="Build pack: nixpacks, dockerfile, static, dockerimage")
    name: str = Field(..., description="Application name")
    domains: Optional[str] = Field(default=None, description="Domain(s), comma-separated")
    port: Optional[int] = Field(default=None, description="Port the app listens on")


class LogsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    uuid: str = Field(..., description="Application UUID")
    lines: int = Field(default=100, ge=1, le=1000, description="Number of log lines to fetch")


# ── Tools ─────────────────────────────────────────────────────────────────────

# HEALTH & INFO
@mcp.tool(name="coolify_health", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_health() -> str:
    """Check Coolify instance health and API version. Use this first to verify connectivity.

    Returns: JSON with status and version info.
    """
    try:
        async with _client() as c:
            r = await c.get("/version")
            r.raise_for_status()
            return _fmt({"status": "ok", "version": r.json()})
    except Exception as e:
        return _err(e)


# PROJECTS
@mcp.tool(name="coolify_list_projects", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_projects() -> str:
    """List all Coolify projects with their UUIDs and environments.

    Returns: JSON array of projects with uuid, name, environments.
    """
    try:
        async with _client() as c:
            r = await c.get("/projects")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


# SERVERS
@mcp.tool(name="coolify_list_servers", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_servers() -> str:
    """List all connected servers with their UUIDs, IPs and status.

    Returns: JSON array of servers.
    """
    try:
        async with _client() as c:
            r = await c.get("/servers")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


# APPLICATIONS
@mcp.tool(name="coolify_list_applications", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_applications() -> str:
    """List all applications across all projects. Returns UUIDs needed for other tools.

    Returns: JSON array with uuid, name, status, fqdn, git_repository, git_branch per app.
    """
    try:
        async with _client() as c:
            r = await c.get("/applications")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool(name="coolify_get_application", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_get_application(params: AppUUID) -> str:
    """Get full details of a specific application including env vars, domains, build settings.

    Args:
        params: AppUUID with uuid field

    Returns: JSON with complete application configuration.
    """
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool(name="coolify_deploy_application", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
async def coolify_deploy_application(params: DeployTagInput) -> str:
    """Deploy/redeploy an application. Triggers a new build and deployment.

    Args:
        params: DeployTagInput - provide either uuid (single app) or tag (all apps with that tag)

    Returns: JSON with deployment UUID and status.
    """
    try:
        async with _client() as c:
            body: dict = {}
            if params.uuid:
                body["uuid"] = params.uuid
            if params.tag:
                body["tag"] = params.tag
            if params.force:
                body["force"] = True
            r = await c.get(f"/deploy", params=body)
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool(name="coolify_restart_application", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def coolify_restart_application(params: AppUUID) -> str:
    """Restart a running application (without rebuilding). Fast restart of containers.

    Args:
        params: AppUUID with uuid field

    Returns: JSON confirmation.
    """
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/restart")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool(name="coolify_stop_application", annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True})
async def coolify_stop_application(params: AppUUID) -> str:
    """Stop a running application. Containers will be stopped.

    Args:
        params: AppUUID with uuid field

    Returns: JSON confirmation.
    """
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/stop")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool(name="coolify_start_application", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def coolify_start_application(params: AppUUID) -> str:
    """Start a stopped application.

    Args:
        params: AppUUID with uuid field

    Returns: JSON confirmation.
    """
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/start")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool(name="coolify_get_logs", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_get_logs(params: LogsInput) -> str:
    """Fetch recent container logs for an application. Essential for debugging.

    Args:
        params: LogsInput with uuid and lines (default 100, max 1000)

    Returns: Log text output.
    """
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/logs", params={"lines": params.lines})
            r.raise_for_status()
            data = r.json()
            # logs can be array or string
            if isinstance(data, list):
                return "\n".join(str(l) for l in data)
            return str(data)
    except Exception as e:
        return _err(e)


# ENV VARS
@mcp.tool(name="coolify_list_env_vars", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_env_vars(params: AppUUID) -> str:
    """List all environment variables for an application.

    Args:
        params: AppUUID with uuid field

    Returns: JSON array of env vars (key, value, is_preview, is_build_time).
    """
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/envs")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool(name="coolify_set_env_var", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def coolify_set_env_var(params: EnvVarInput) -> str:
    """Create or update an environment variable for an application.
    NOTE: You must redeploy the app after changing env vars.

    Args:
        params: EnvVarInput with uuid, key, value, is_preview

    Returns: JSON confirmation with created/updated env var.
    """
    try:
        async with _client() as c:
            body = {"key": params.key, "value": params.value, "is_preview": params.is_preview}
            r = await c.post(f"/applications/{params.uuid}/envs", json=body)
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


# SERVICES
@mcp.tool(name="coolify_list_services", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_services() -> str:
    """List all services (multi-container stacks like databases, Redis, etc).

    Returns: JSON array of services with uuid, name, status.
    """
    try:
        async with _client() as c:
            r = await c.get("/services")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool(name="coolify_restart_service", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def coolify_restart_service(params: ServiceUUID) -> str:
    """Restart a service stack (e.g. database, Redis).

    Args:
        params: ServiceUUID with uuid field

    Returns: JSON confirmation.
    """
    try:
        async with _client() as c:
            r = await c.get(f"/services/{params.uuid}/restart")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


# DEPLOYMENTS
@mcp.tool(name="coolify_list_deployments", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_deployments(params: AppUUID) -> str:
    """List recent deployments for an application with their status and logs URL.

    Args:
        params: AppUUID with uuid field

    Returns: JSON array of deployments (uuid, status, created_at, commit).
    """
    try:
        async with _client() as c:
            r = await c.get(f"/applications/{params.uuid}/deployments")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


# DATABASES
@mcp.tool(name="coolify_list_databases", annotations={"readOnlyHint": True, "destructiveHint": False})
async def coolify_list_databases() -> str:
    """List all databases managed by Coolify.

    Returns: JSON array of databases with uuid, name, type, status.
    """
    try:
        async with _client() as c:
            r = await c.get("/databases")
            r.raise_for_status()
            return _fmt(r.json())
    except Exception as e:
        return _err(e)


if __name__ == "__main__":
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "http":
        mcp.run(transport="streamable_http", port=int(os.environ.get("PORT", 8080)))
    else:
        mcp.run()
