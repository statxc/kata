from __future__ import annotations

import json
from pathlib import Path

from kata.eval_pack import (
    discover_live_eval_pack_tasks,
    render_validation_result,
    validate_eval_pack,
)


def write_eval_file(root: Path, name: str, content: str) -> None:
    path = root / name
    path.write_text(content, encoding="utf-8")
    if name == "checks.sh":
        path.chmod(0o755)


def write_live_metadata(root: Path, *, status: str) -> None:
    (root / "benchkit.json").write_text(
        json.dumps({"status": status}) + "\n",
        encoding="utf-8",
    )


def test_validate_eval_pack_rejects_placeholder_scaffold(tmp_path: Path) -> None:
    write_eval_file(
        tmp_path,
        "task.md",
        "# Eval Task: demo\n\n## Goal\n- Describe the exact change the agent must make.\n",
    )
    write_eval_file(tmp_path, "repo_ref.txt", "https://github.com/example/repo.git@main\n")
    write_eval_file(
        tmp_path,
        "checks.sh",
        '#!/usr/bin/env bash\nset -euo pipefail\necho "TODO: add repo-specific checks"\n',
    )
    write_eval_file(tmp_path, "rubric.md", "# Rubric\n\n- Task goal is completed.\n")
    write_eval_file(tmp_path, "allowed_paths.txt", "src/\n")
    write_eval_file(tmp_path, "forbidden_paths.txt", "eval/\n")

    result = validate_eval_pack(str(tmp_path))

    assert not result.is_valid
    assert result.placeholder_files == ["task.md", "checks.sh", "rubric.md"]
    rendered = render_validation_result(result)
    assert "Placeholder scaffold content still present:" in rendered


def test_validate_eval_pack_accepts_real_content(tmp_path: Path) -> None:
    write_eval_file(
        tmp_path,
        "task.md",
        "# Eval Task: demo\n\n## Goal\n- Add a missing CLI flag to export JSON output.\n",
    )
    write_eval_file(tmp_path, "repo_ref.txt", "https://github.com/example/repo.git@main\n")
    write_eval_file(
        tmp_path,
        "checks.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\npython -m pytest tests/test_cli.py\n",
    )
    write_eval_file(
        tmp_path,
        "rubric.md",
        "# Rubric\n\n## Pass Conditions\n- The new flag writes valid JSON to stdout.\n",
    )
    write_eval_file(tmp_path, "allowed_paths.txt", "src/\n")
    write_eval_file(tmp_path, "forbidden_paths.txt", "eval/\n")

    result = validate_eval_pack(str(tmp_path))

    assert result.is_valid
    assert result.placeholder_files == []


def test_discover_live_eval_pack_tasks_filters_non_live_children(tmp_path: Path) -> None:
    live_task = tmp_path / "task-live"
    retired_task = tmp_path / "task-retired"
    for root in (live_task, retired_task):
        root.mkdir(parents=True, exist_ok=True)
        write_eval_file(
            root,
            "task.md",
            "# Eval Task: demo\n\n## Goal\n- Add a missing CLI flag to export JSON output.\n",
        )
        write_eval_file(root, "repo_ref.txt", "https://github.com/example/repo.git@main\n")
        write_eval_file(
            root,
            "checks.sh",
            "#!/usr/bin/env bash\nset -euo pipefail\npython -m pytest tests/test_cli.py\n",
        )
        write_eval_file(
            root,
            "rubric.md",
            "# Rubric\n\n## Pass Conditions\n- The new flag writes valid JSON to stdout.\n",
        )
        write_eval_file(root, "allowed_paths.txt", "src/\n")
        write_eval_file(root, "forbidden_paths.txt", "eval/\n")
    write_live_metadata(live_task, status="live")
    write_live_metadata(retired_task, status="retired")

    results = discover_live_eval_pack_tasks(str(tmp_path))

    assert [result.root.name for result in results] == ["task-live"]
