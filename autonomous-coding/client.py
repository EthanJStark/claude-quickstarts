"""
Claude SDK Client Configuration
===============================

Functions for creating and configuring the Claude Agent SDK client.
"""

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient
from claude_code_sdk.types import HookMatcher

from security import bash_security_hook


# Puppeteer MCP tools for browser automation
PUPPETEER_TOOLS = [
    "mcp__puppeteer__puppeteer_navigate",
    "mcp__puppeteer__puppeteer_screenshot",
    "mcp__puppeteer__puppeteer_click",
    "mcp__puppeteer__puppeteer_fill",
    "mcp__puppeteer__puppeteer_select",
    "mcp__puppeteer__puppeteer_hover",
    "mcp__puppeteer__puppeteer_evaluate",
]

# Built-in tools
BUILTIN_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
]


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _sanitize_model_id(model: str) -> str:
    """
    Remove common accidental ANSI formatting from model IDs.

    Note: Some Bedrock setups may intentionally use bracketed suffixes in model IDs.
    We only strip *actual* ANSI escape sequences by default.

    If you have model IDs that were copy/pasted with visible bracketed ANSI-like
    fragments (e.g. "...:0[1m]"), you can opt-in to stripping them by setting:
      AUTONOMOUS_CODING_STRIP_BRACKETED_MODEL_SUFFIX=1
    """
    model = model.strip()
    model = _ANSI_ESCAPE_RE.sub("", model)
    if _is_truthy(os.getenv("AUTONOMOUS_CODING_STRIP_BRACKETED_MODEL_SUFFIX")):
        model = re.sub(r"\[[0-9;]*m\]", "", model)
    return model.strip()


@lru_cache(maxsize=1)
def _load_claude_code_settings_env() -> dict[str, str]:
    """
    Load env values from Claude Code's config (if present).

    Claude Code CLI injects these env vars for its own process. This harness
    runs in Python, so we read them directly to choose sane defaults.
    """
    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        raw = json.loads(settings_path.read_text())
    except Exception:
        return {}

    env: Any = raw.get("env", {})
    if not isinstance(env, dict):
        return {}

    out: dict[str, str] = {}
    for k, v in env.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


def _get_effective_env(key: str) -> Optional[str]:
    """
    Return env var value, falling back to ~/.claude/settings.json "env".
    """
    v = os.getenv(key)
    if v is not None and v != "":
        return v
    return _load_claude_code_settings_env().get(key)


def _is_truthy(v: Optional[str]) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_bedrock_enabled() -> bool:
    return _is_truthy(_get_effective_env("CLAUDE_CODE_USE_BEDROCK"))


def get_default_model() -> str:
    """
    Choose a reasonable default model for the current auth mode.

    - Anthropic API mode: use the SDK demo default short model name.
    - Bedrock mode: prefer model IDs from Claude Code config/env.
    """
    if _is_bedrock_enabled():
        # Prefer explicit "ANTHROPIC_MODEL" if provided; otherwise default to Sonnet.
        for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"):
            v = _get_effective_env(key)
            if v:
                return _sanitize_model_id(v)

    # Default short name (works for non-Bedrock auth paths).
    return "claude-sonnet-4-5-20250929"


def resolve_model(model: str) -> str:
    """
    Resolve a user-provided model string into a Claude Code-compatible model ID.

    In Bedrock mode, the Claude Code CLI expects Bedrock model IDs (e.g.
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0"), not the short Anthropic API
    names (e.g. "claude-sonnet-4-5-20250929").
    """
    model = _sanitize_model_id(model)
    if not model:
        return get_default_model()

    if _is_bedrock_enabled():
        # If the user passed the short Anthropic-style model name, map it to the
        # configured Bedrock model IDs.
        if model.startswith("claude-") and "anthropic." not in model:
            mapped: Optional[str] = None
            lower = model.lower()
            if "haiku" in lower:
                mapped = _get_effective_env("ANTHROPIC_DEFAULT_HAIKU_MODEL")
            elif "opus" in lower:
                mapped = _get_effective_env("ANTHROPIC_DEFAULT_OPUS_MODEL")
            else:
                mapped = _get_effective_env("ANTHROPIC_DEFAULT_SONNET_MODEL")

            if mapped:
                return _sanitize_model_id(mapped)

            # No mapping available; fall back to any configured explicit model.
            explicit = _get_effective_env("ANTHROPIC_MODEL")
            if explicit:
                return _sanitize_model_id(explicit)

            # Keep the original; the caller will surface the Bedrock error with context.
            return model

    return model


def create_client(project_dir: Path, model: str) -> ClaudeSDKClient:
    """
    Create a Claude Agent SDK client with multi-layered security.

    Args:
        project_dir: Directory for the project
        model: Claude model to use

    Returns:
        Configured ClaudeSDKClient

    Security layers (defense in depth):
    1. Sandbox - OS-level bash command isolation prevents filesystem escape
    2. Permissions - File operations restricted to project_dir only
    3. Security hooks - Bash commands validated against an allowlist
       (see security.py for ALLOWED_COMMANDS)
    """
    # Create comprehensive security settings
    # Note: Using relative paths ("./**") restricts access to project directory
    # since cwd is set to project_dir
    security_settings = {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
        "permissions": {
            "defaultMode": "acceptEdits",  # Auto-approve edits within allowed directories
            "allow": [
                # Allow all file operations within the project directory
                "Read(./**)",
                "Write(./**)",
                "Edit(./**)",
                "Glob(./**)",
                "Grep(./**)",
                # Bash permission granted here, but actual commands are validated
                # by the bash_security_hook (see security.py for allowed commands)
                "Bash(*)",
                # Allow Puppeteer MCP tools for browser automation
                *PUPPETEER_TOOLS,
            ],
        },
    }

    # Ensure project directory exists before creating settings file
    project_dir.mkdir(parents=True, exist_ok=True)

    # Write settings to a file in the project directory
    settings_file = project_dir / ".claude_settings.json"
    with open(settings_file, "w") as f:
        json.dump(security_settings, f, indent=2)

    print(f"Created security settings at {settings_file}")
    print("   - Sandbox enabled (OS-level bash isolation)")
    print(f"   - Filesystem restricted to: {project_dir.resolve()}")
    print("   - Bash commands restricted to allowlist (see security.py)")
    print("   - MCP servers: puppeteer (browser automation)")
    print("   - Authentication: Using Claude Code CLI config (~/.claude/settings.json)")
    print("   - Supports: ANTHROPIC_API_KEY or AWS Bedrock (via awsCredentialExport)")
    print()

    resolved_model = resolve_model(model)
    if resolved_model != model:
        print(f"Resolved model: {model} -> {resolved_model}")
        print()

    return ClaudeSDKClient(
        options=ClaudeCodeOptions(
            model=resolved_model,
            system_prompt="You are an expert full-stack developer building a production-quality web application.",
            allowed_tools=[
                *BUILTIN_TOOLS,
                *PUPPETEER_TOOLS,
            ],
            mcp_servers={
                "puppeteer": {"command": "npx", "args": ["puppeteer-mcp-server"]}
            },
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
                ],
            },
            max_turns=1000,
            cwd=str(project_dir.resolve()),
            settings=str(settings_file.resolve()),  # Use absolute path
        )
    )
