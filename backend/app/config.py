"""Configuration for the PoC backend.

Server connections, trust levels and the LLM provider choice are all driven
by environment variables so the PoC can be run without editing code (see
``README.md``). Sensible defaults point at the bundled example MCP server.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Literal

from pydantic import BaseModel, Field

TrustLevel = Literal["trusted", "untrusted"]


class MCPServerConfig(BaseModel):
    """Connection info for one MCP server.

    Only the ``stdio`` transport is implemented in this PoC (the example
    server is spawned as a subprocess). ``streamable-http``/``sse`` are
    listed as the documented extension point for real external servers (see
    docs/konzept-mcp-apps.md, section 8) but are not wired up here.
    """

    id: str
    transport: Literal["stdio", "streamable-http", "sse"] = "stdio"
    command: list[str] | None = None
    url: str | None = None
    trust_level: TrustLevel = Field(default="untrusted", alias="trustLevel")

    model_config = {"populate_by_name": True}


def _default_servers() -> list[MCPServerConfig]:
    return [
        MCPServerConfig(
            id="room-booking",
            transport="stdio",
            command=[sys.executable, "-m", "mcp_server_example"],
            trustLevel="trusted",
        )
    ]


class Settings(BaseModel):
    mcp_servers: list[MCPServerConfig] = Field(default_factory=_default_servers)

    # LLM provider selection. "mock" requires no credentials and is the
    # default so the PoC runs end-to-end without an API key.
    llm_provider: Literal["mock", "anthropic"] = "mock"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:4200"])


def load_settings() -> Settings:
    raw_servers = os.environ.get("MCP_SERVERS_CONFIG")
    servers = (
        [MCPServerConfig.model_validate(s) for s in json.loads(raw_servers)]
        if raw_servers
        else _default_servers()
    )

    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    llm_provider = os.environ.get(
        "LLM_PROVIDER", "anthropic" if anthropic_api_key else "mock"
    )

    cors_env = os.environ.get("CORS_ORIGINS")
    cors_origins = (
        [o.strip() for o in cors_env.split(",") if o.strip()]
        if cors_env
        else ["http://localhost:4200"]
    )

    return Settings(
        mcp_servers=servers,
        llm_provider=llm_provider,  # type: ignore[arg-type]
        anthropic_api_key=anthropic_api_key,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        cors_origins=cors_origins,
    )
