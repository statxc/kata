from __future__ import annotations

from pathlib import Path

from kata import eval_runner
from kata.eval_runner import (
    build_agent_env,
    build_checks_env,
    prepare_repository_dependencies,
)


def test_build_agent_env_filters_host_secrets_and_private_task_paths(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/tmp/home")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-should-not-leak")
    task_root = tmp_path / "task"
    task_root.mkdir()
    (task_root / "task.md").write_text("# fix the bug\n", encoding="utf-8")
    env = build_agent_env(
        workspace=tmp_path / "workspace",
        artifact_path=tmp_path / "artifact" / "agent.py",
        eval_pack_root=task_root,
        repo_snapshot=tmp_path / "repo",
        mode="contributor",
        repo_ref="https://github.com/example/repo.git@main",
        score_file=tmp_path / "score.txt",
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert "OPENAI_API_KEY" not in env
    assert env["KATA_MODE"] == "contributor"
    assert env["KATA_TASK_TEXT"] == "# fix the bug\n"
    assert "KATA_TASK_FILE" not in env
    assert "KATA_RUBRIC_FILE" not in env
    assert "KATA_ALLOWED_PATHS_FILE" not in env
    assert "KATA_FORBIDDEN_PATHS_FILE" not in env
    assert "KATA_EVAL_TASK_DIR" not in env
    assert "KATA_SCORE_FILE" not in env


def test_build_checks_env_keeps_private_task_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    task_root = tmp_path / "task"
    task_root.mkdir()
    (task_root / "task.md").write_text("# fix the bug\n", encoding="utf-8")
    (task_root / "rubric.md").write_text("rubric\n", encoding="utf-8")
    (task_root / "allowed_paths.txt").write_text("docs/\n", encoding="utf-8")
    (task_root / "forbidden_paths.txt").write_text("src/\n", encoding="utf-8")
    score_file = tmp_path / "score.txt"
    env = build_checks_env(
        workspace=tmp_path / "workspace",
        artifact_path=tmp_path / "artifact" / "agent.py",
        eval_pack_root=task_root,
        repo_snapshot=tmp_path / "repo",
        mode="contributor",
        repo_ref="https://github.com/example/repo.git@main",
        score_file=score_file,
    )

    assert env["KATA_TASK_FILE"] == str((task_root / "task.md").resolve())
    assert env["KATA_RUBRIC_FILE"] == str((task_root / "rubric.md").resolve())
    assert env["KATA_ALLOWED_PATHS_FILE"] == str(
        (task_root / "allowed_paths.txt").resolve()
    )
    assert env["KATA_FORBIDDEN_PATHS_FILE"] == str(
        (task_root / "forbidden_paths.txt").resolve()
    )
    assert env["KATA_EVAL_TASK_DIR"] == str(task_root.resolve())
    assert env["KATA_SCORE_FILE"] == str(score_file.resolve())
    assert "KATA_TASK_TEXT" not in env


def test_prepare_repository_dependencies_runs_npm_ci_for_locked_node_repo(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"scripts":{}}\n', encoding="utf-8")
    (repo / "package-lock.json").write_text("{}\n", encoding="utf-8")
    run_root = tmp_path / "run"
    run_root.mkdir()
    captured: dict[str, object] = {}

    def fake_run_process(command, cwd, env, stdout_path, stderr_path, timeout_seconds):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        captured["stdout_path"] = stdout_path
        captured["stderr_path"] = stderr_path
        captured["timeout_seconds"] = timeout_seconds
        stdout_path.write_text("installed\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return 0

    monkeypatch.setattr(eval_runner, "run_process", fake_run_process)
    monkeypatch.setenv("KATA_DEPENDENCY_INSTALL_TIMEOUT_SECONDS", "42")

    prepare_repository_dependencies(repo, run_root)

    assert captured["command"] == ["npm", "ci", "--ignore-scripts"]
    assert captured["cwd"] == repo
    assert captured["timeout_seconds"] == 42
    assert captured["stdout_path"] == run_root / "dependency-install.stdout.txt"
    assert captured["stderr_path"] == run_root / "dependency-install.stderr.txt"


def test_prepare_repository_dependencies_skips_repo_without_lockfile(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"scripts":{}}\n', encoding="utf-8")
    run_root = tmp_path / "run"
    run_root.mkdir()
    called = False

    def fake_run_process(*_args, **_kwargs):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(eval_runner, "run_process", fake_run_process)

    prepare_repository_dependencies(repo, run_root)

    assert not called
