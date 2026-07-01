#!/usr/bin/env bash
set -euo pipefail

workspace=${KATA_WORKSPACE:-}
agent_file=${KATA_AGENT_FILE:-}
task_text=${KATA_TASK_TEXT:-}
model=${KATA_VALIDATOR_MODEL:-Qwen3-32B}
api_base=${KATA_VALIDATOR_API_BASE:-}
api_key=${KATA_VALIDATOR_API_KEY:-}

: "${workspace:?KATA_WORKSPACE is required}"
: "${agent_file:?KATA_AGENT_FILE is required}"
: "${task_text:?KATA_TASK_TEXT is required}"

python3 - <<'PY'
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def load_agent_module(agent_path: Path):
    spec = importlib.util.spec_from_file_location("kata_submission_agent", agent_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load agent module: {agent_path}")
    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(agent_path.parent))
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous_module is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous_module
        raise
    finally:
        sys.path.pop(0)
    return module


def apply_patch(repo_path: Path, patch_text: str) -> None:
    normalized = patch_text.strip()
    if not normalized:
        return
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(normalized + "\n")
        patch_path = Path(handle.name)
    try:
        created_temp_git_dir = False
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            subprocess.run(
                ["git", "init", "-q"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=True,
            )
            created_temp_git_dir = True
        completed = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(patch_path)],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "git apply failed")
    finally:
        if "created_temp_git_dir" in locals() and created_temp_git_dir:
            shutil.rmtree(repo_path / ".git", ignore_errors=True)
        patch_path.unlink(missing_ok=True)


workspace = Path(os.environ["KATA_WORKSPACE"]).resolve()
agent_path = Path(os.environ["KATA_AGENT_FILE"]).resolve()
issue = os.environ["KATA_TASK_TEXT"]
model = (
    os.environ.get("KATA_VALIDATOR_MODEL")
    or "Qwen3-32B"
)
api_base = (
    os.environ.get("KATA_VALIDATOR_API_BASE")
    or ""
)
api_key = (
    os.environ.get("KATA_VALIDATOR_API_KEY")
    or ""
)

module = load_agent_module(agent_path)
solve = getattr(module, "solve", None)
if solve is None or not callable(solve):
        raise RuntimeError(
            "agent.py must define callable solve(repo_path, issue, model, api_base, api_key)"
        )

result = solve(
    repo_path=str(workspace),
    issue=issue,
    model=model,
    api_base=api_base,
    api_key=api_key,
)

if result is None:
    result = {}
if not isinstance(result, dict):
    raise RuntimeError("solve(...) must return a dict")

patch_text = result.get("patch") or result.get("diff") or ""
if patch_text:
    apply_patch(workspace, str(patch_text))

message = str(result.get("message") or "").strip()
if message:
    print(message)
print(json.dumps({"success": bool(result.get("success", True))}))
PY
