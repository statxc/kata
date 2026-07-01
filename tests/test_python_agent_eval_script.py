from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_python_agent_eval_script_loads_dataclass_agents(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    agent = tmp_path / "agent.py"
    agent.write_text(
        "\n".join(
            [
                "from dataclasses import dataclass",
                "",
                "@dataclass(frozen=True)",
                "class Config:",
                "    value: str",
                "",
                "def solve(repo_path, issue, model, api_base, api_key):",
                "    config = Config(value=issue)",
                "    return {'success': True, 'message': config.value, 'diff': ''}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_python_agent_eval.sh"
    env = {
        **os.environ,
        "KATA_WORKSPACE": str(workspace),
        "KATA_AGENT_FILE": str(agent),
        "KATA_TASK_TEXT": "dataclass smoke",
        "KATA_VALIDATOR_MODEL": "test-model",
        "KATA_VALIDATOR_API_BASE": "http://127.0.0.1",
        "KATA_VALIDATOR_API_KEY": "",
    }

    completed = subprocess.run(
        [str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "dataclass smoke" in completed.stdout
