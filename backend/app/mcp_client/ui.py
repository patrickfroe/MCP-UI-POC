"""Helpers for the MCP Apps / MCP-UI conventions (see docs/konzept-mcp-apps.md).

This module is the single place that interprets ``_meta.ui`` on tools and
derives the sandbox/CSP policy for a UI resource. Keeping this logic in one
place makes it easy to adapt if the SEP-1865 field names change (see
"Risiken & offene Punkte" #1 in the concept doc).
"""

from __future__ import annotations

from typing import Literal

import mcp.types as types
from pydantic import BaseModel, Field

from app.config import TrustLevel


class UIMeta(BaseModel):
    """Parsed ``tool._meta.ui`` (SEP-1865 tool-UI linkage)."""

    resource_uri: str = Field(alias="resourceUri")
    visibility: list[Literal["model", "app"]] = Field(
        default_factory=lambda: ["model", "app"]
    )

    model_config = {"populate_by_name": True, "extra": "ignore"}


def extract_ui_meta(tool: types.Tool) -> UIMeta | None:
    """Return ``tool._meta.ui`` as a :class:`UIMeta`, or ``None`` if absent/invalid."""

    if not tool.meta:
        return None
    ui = tool.meta.get("ui")
    if not isinstance(ui, dict):
        return None
    try:
        return UIMeta.model_validate(ui)
    except Exception:
        return None


class SandboxPolicy(BaseModel):
    """Sent to the frontend alongside a ``ui_resource`` message.

    The frontend MUST apply ``sandbox_attributes`` and ``csp`` as-is; it must
    not widen them (see docs/konzept-mcp-apps.md section 7.2/7.4).
    """

    sandbox_attributes: str = Field(alias="sandboxAttributes")
    csp: str
    trust_level: TrustLevel = Field(alias="trustLevel")

    model_config = {"populate_by_name": True}


# Restrictive default CSP applied when a resource declares no `_meta.ui.csp`
# (or when the originating server is untrusted). See concept doc section 7.2.
_DEFAULT_CSP_DIRECTIVES: dict[str, list[str]] = {
    "default-src": ["'none'"],
    "script-src": ["'unsafe-inline'"],
    "style-src": ["'unsafe-inline'"],
    "img-src": ["data:"],
    "connect-src": ["'none'"],
    "frame-src": ["'none'"],
    "form-action": ["'none'"],
}


def _csp_from_directives(directives: dict[str, list[str]]) -> str:
    return "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items()) + ";"


def build_sandbox_policy(
    trust_level: TrustLevel,
    resource_content: types.TextResourceContents | types.BlobResourceContents | None,
    content_type: Literal["rawHtml", "externalUrl"] = "rawHtml",
) -> SandboxPolicy:
    """Compute the sandbox/CSP policy for a UI resource.

    ``resource_content.meta["ui"]["csp"]`` (``connectDomains`` /
    ``resourceDomains`` / ``frameDomains``, per SEP-1865) is honoured *only*
    for ``trusted`` servers and only ever *extends* the restrictive default -
    it can never loosen ``default-src``/``form-action``. Untrusted servers
    always get the hard default, regardless of what they declare.

    Note: with the bundled example server, ``resources/read`` never carries
    ``_meta`` (FastMCP's function-resource handler only returns a plain
    string), so the declared-CSP branch is currently unreachable in the PoC.
    It is implemented for forward-compatibility with servers that *do* set
    ``_meta.ui.csp`` on the resource.
    """

    directives = {k: list(v) for k, v in _DEFAULT_CSP_DIRECTIVES.items()}

    declared_csp: dict | None = None
    if resource_content is not None and resource_content.meta:
        ui_meta = resource_content.meta.get("ui")
        if isinstance(ui_meta, dict):
            csp = ui_meta.get("csp")
            if isinstance(csp, dict):
                declared_csp = csp

    if declared_csp and trust_level == "trusted":
        connect_domains = declared_csp.get("connectDomains") or []
        frame_domains = declared_csp.get("frameDomains") or []
        resource_domains = declared_csp.get("resourceDomains") or []

        if connect_domains:
            directives["connect-src"] = list(connect_domains)
        if frame_domains:
            directives["frame-src"] = list(frame_domains)
        if resource_domains:
            for key in ("style-src", "img-src", "script-src"):
                directives[key] = directives[key] + list(resource_domains)

    sandbox_attributes = "allow-scripts allow-forms" if content_type == "rawHtml" else "allow-scripts"

    return SandboxPolicy(
        sandboxAttributes=sandbox_attributes,
        csp=_csp_from_directives(directives),
        trustLevel=trust_level,
    )


def summarize_tool_result(result: types.CallToolResult) -> str:
    """Render a CallToolResult as plain text for the LLM / chat transcript."""

    parts: list[str] = []
    for block in result.content:
        if isinstance(block, types.TextContent):
            parts.append(block.text)
        elif isinstance(block, types.EmbeddedResource):
            parts.append(f"[resource: {block.resource.uri}]")
        elif isinstance(block, types.ImageContent):
            parts.append("[image]")
        else:
            parts.append(f"[{getattr(block, 'type', 'content')}]")
    return "\n".join(parts) if parts else ""
