from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from kata.benchmarks import resolve_eval_pack_path
from kata.config import (
    resolve_validator_api_base,
    resolve_validator_api_key,
    resolve_validator_model,
)
from kata.eval_pack import EvalPackValidationResult, discover_live_eval_pack_tasks
from kata.provenance import EVALUATOR_VERSION, pool_fingerprint
from kata.repository import resolve_repository
from kata.scoring import read_task_weight, score_variant_run

IGNORED_COPY_DIRS = (
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
)
PASSTHROUGH_ENV_VARS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "PYTHONPATH",
    "TMP",
    "TEMP",
    "TMPDIR",
)


@dataclass(frozen=True)
class VariantResult:
    name: str
    artifact_path: str
    workspace: str
    agent_stdout: str
    agent_stderr: str
    checks_stdout: str
    checks_stderr: str
    agent_exit_code: int
    checks_exit_code: int
    task_solved: bool
    validity_passed: bool
    verifier_score: float
    quality_score: float
    weighted_task_score: float
    score_source: str
    changed_paths: list[str]
    path_policy_passed: bool
    path_policy_violations: list[str]
    success: bool


@dataclass(frozen=True)
class TaskRunSummary:
    task_id: str
    task_path: str
    task_repo_ref: str
    task_weight: float
    variants: list[VariantResult]


@dataclass(frozen=True)
class EvalRunSummary:
    run_id: str
    requested_repo_ref: str
    eval_pack: str
    mode: str
    registry_url: str | None
    agent_command: str
    created_at: str
    tasks: list[TaskRunSummary]
    run_kind: str = "eval"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactVariant:
    name: str
    files: dict[str, str]
    entrypoint: str
def run_artifact_variants(
    *,
    repo_ref: str,
    eval_pack_path: str,
    mode: str,
    agent_command: str,
    artifact_variants: list[ArtifactVariant],
    task_names: list[str] | None = None,
    output_root: str | None = None,
    agent_timeout_seconds: int | None = None,
    checks_timeout_seconds: int | None = None,
    run_label: str | None = None,
    run_kind: str = "eval",
    metadata: dict[str, str] | None = None,
) -> EvalRunSummary:
    eval_pack_root = resolve_eval_pack_path(eval_pack_path)
    validations = discover_live_eval_pack_tasks(eval_pack_path)
    if not validations:
        raise ValueError(
            "Eval pack has no live tasks available for validator runs."
        )
    invalid = [result for result in validations if not result.is_valid]
    if invalid:
        invalid_names = ", ".join(result.root.name for result in invalid)
        raise ValueError(
            "Eval pack is invalid. Run `kata eval-pack validate` first. "
            f"Invalid task directories: {invalid_names}"
        )
    selected_validations = select_task_validations(validations, task_names)
    selected_roots = [result.root for result in selected_validations]
    task_ids = [result.root.name for result in selected_validations]
    if run_label is not None:
        run_name = run_label
    elif len(task_ids) > 1:
        run_name = selected_validations[0].root.parent.name
    else:
        run_name = task_ids[0]
    run_id = build_run_id(run_name)
    runs_root = Path(output_root) if output_root else Path("runs")
    run_root = runs_root / run_id
    run_root.mkdir(parents=True, exist_ok=False)

    task_summaries: list[TaskRunSummary] = []
    for validation in selected_validations:
        task_root = validation.root
        task_run_root = run_root / "tasks" / task_root.name
        task_run_root.mkdir(parents=True, exist_ok=False)
        task_snapshot = task_run_root / "eval_pack"
        shutil.copytree(task_root, task_snapshot)
        task_weight = read_task_weight(task_snapshot)

        task_repo_ref = read_task_repo_ref(task_snapshot / "repo_ref.txt", fallback=repo_ref)
        with resolve_repository(task_repo_ref) as repo:
            repo_snapshot = task_run_root / "repo_snapshot"
            copy_repository(repo.root, repo_snapshot)
            variants = [
                run_variant(
                    variant_name=artifact_variant.name,
                    artifact_files=artifact_variant.files,
                    artifact_entrypoint=artifact_variant.entrypoint,
                    variant_root=task_run_root / artifact_variant.name,
                    repo_snapshot=repo_snapshot,
                    eval_pack_root=task_snapshot,
                    repo_ref=task_repo_ref,
                    mode=mode,
                    agent_command=agent_command,
                    agent_timeout_seconds=agent_timeout_seconds,
                    checks_timeout_seconds=checks_timeout_seconds,
                )
                for artifact_variant in artifact_variants
            ]

        task_summaries.append(
            TaskRunSummary(
                task_id=task_root.name,
                task_path=str(task_run_root),
                task_repo_ref=task_repo_ref,
                task_weight=task_weight,
                variants=variants,
            )
        )

    summary = EvalRunSummary(
        run_id=run_id,
        requested_repo_ref=repo_ref,
        eval_pack=str(eval_pack_root),
        mode=mode,
        registry_url=None,
        agent_command=agent_command,
        created_at=datetime.now(UTC).isoformat(),
        tasks=task_summaries,
        run_kind=run_kind,
        metadata=build_run_metadata(
            task_ids=task_ids,
            task_roots=selected_roots,
            extra=metadata,
        ),
    )
    write_summary(run_root / "run_summary.json", summary)
    return summary


def run_variant(
    *,
    variant_name: str,
    artifact_files: dict[str, str],
    artifact_entrypoint: str,
    variant_root: Path,
    repo_snapshot: Path,
    eval_pack_root: Path,
    repo_ref: str,
    mode: str,
    agent_command: str,
    agent_timeout_seconds: int | None,
    checks_timeout_seconds: int | None,
) -> VariantResult:
    workspace = variant_root / "workspace"
    shutil.copytree(repo_snapshot, workspace)

    artifact_root = variant_root / "artifact"
    artifact_path = stage_artifact_bundle(
        artifact_root=artifact_root,
        entrypoint=artifact_entrypoint,
        files=artifact_files,
    )

    agent_stdout = variant_root / "agent.stdout.txt"
    agent_stderr = variant_root / "agent.stderr.txt"
    checks_stdout = variant_root / "checks.stdout.txt"
    checks_stderr = variant_root / "checks.stderr.txt"
    score_file = variant_root / "score.txt"

    agent_exit_code = run_agent_command(
        command=agent_command,
        workspace=workspace,
        artifact_path=artifact_path,
        eval_pack_root=eval_pack_root,
        repo_snapshot=repo_snapshot,
        mode=mode,
        repo_ref=repo_ref,
        stdout_path=agent_stdout,
        stderr_path=agent_stderr,
        score_file=score_file,
        timeout_seconds=agent_timeout_seconds,
    )
    checks_exit_code = run_checks(
        checks_path=eval_pack_root / "checks.sh",
        workspace=workspace,
        artifact_path=artifact_path,
        eval_pack_root=eval_pack_root,
        repo_snapshot=repo_snapshot,
        mode=mode,
        repo_ref=repo_ref,
        stdout_path=checks_stdout,
        stderr_path=checks_stderr,
        score_file=score_file,
        timeout_seconds=checks_timeout_seconds,
    )
    benchmark_score = score_variant_run(
        repo_snapshot=repo_snapshot,
        eval_pack_root=eval_pack_root,
        workspace=workspace,
        agent_exit_code=agent_exit_code,
        checks_exit_code=checks_exit_code,
        score_file=score_file,
    )
    return VariantResult(
        name=variant_name,
        artifact_path=str(artifact_root),
        workspace=str(workspace),
        agent_stdout=str(agent_stdout),
        agent_stderr=str(agent_stderr),
        checks_stdout=str(checks_stdout),
        checks_stderr=str(checks_stderr),
        agent_exit_code=agent_exit_code,
        checks_exit_code=checks_exit_code,
        task_solved=benchmark_score.task_solved,
        validity_passed=benchmark_score.validity_passed,
        verifier_score=benchmark_score.verifier_score,
        quality_score=benchmark_score.quality_score,
        weighted_task_score=benchmark_score.weighted_task_score,
        score_source=benchmark_score.score_source,
        changed_paths=benchmark_score.changed_paths,
        path_policy_passed=benchmark_score.path_policy_passed,
        path_policy_violations=benchmark_score.path_policy_violations,
        success=(
            benchmark_score.agent_ok
            and benchmark_score.checks_passed
            and benchmark_score.path_policy_passed
        ),
    )


def run_agent_command(
    *,
    command: str,
    workspace: Path,
    artifact_path: Path,
    eval_pack_root: Path,
    repo_snapshot: Path,
    mode: str,
    repo_ref: str,
    stdout_path: Path,
    stderr_path: Path,
    score_file: Path,
    timeout_seconds: int | None,
) -> int:
    env = build_agent_env(
        workspace=workspace,
        artifact_path=artifact_path,
        eval_pack_root=eval_pack_root,
        repo_snapshot=repo_snapshot,
        mode=mode,
        repo_ref=repo_ref,
        score_file=score_file,
    )
    return run_shell_command(
        command,
        workspace,
        env,
        stdout_path,
        stderr_path,
        timeout_seconds=timeout_seconds,
    )


def run_checks(
    *,
    checks_path: Path,
    workspace: Path,
    artifact_path: Path,
    eval_pack_root: Path,
    repo_snapshot: Path,
    mode: str,
    repo_ref: str,
    stdout_path: Path,
    stderr_path: Path,
    score_file: Path,
    timeout_seconds: int | None,
) -> int:
    env = build_checks_env(
        workspace=workspace,
        artifact_path=artifact_path,
        eval_pack_root=eval_pack_root,
        repo_snapshot=repo_snapshot,
        mode=mode,
        repo_ref=repo_ref,
        score_file=score_file,
    )
    return run_process(
        ["bash", str(checks_path.resolve())],
        workspace,
        env,
        stdout_path,
        stderr_path,
        timeout_seconds=timeout_seconds,
    )


def run_shell_command(
    command: str,
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int | None,
) -> int:
    return run_process(
        ["bash", "-lc", command],
        cwd,
        env,
        stdout_path,
        stderr_path,
        timeout_seconds=timeout_seconds,
    )


def run_process(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int | None,
) -> int:
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                env=env,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            stderr_file.write(
                f"Kata timeout after {timeout_seconds} seconds for command: "
                f"{' '.join(command)}\n"
            )
            return 124
    return completed.returncode


def build_run_metadata(
    *,
    task_ids: list[str],
    task_roots: list[Path],
    extra: dict[str, str] | None,
) -> dict[str, str]:
    metadata = {
        "evaluator_version": EVALUATOR_VERSION,
        "validator_model": resolve_validator_model(),
        "task_count": str(len(task_ids)),
        "task_ids": ",".join(task_ids),
        "task_pool_fingerprint": pool_fingerprint(task_roots),
    }
    if extra:
        metadata.update(extra)
    return metadata


def build_common_env(
    *,
    workspace: Path,
    artifact_path: Path,
    repo_snapshot: Path,
    mode: str,
    repo_ref: str,
) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key in PASSTHROUGH_ENV_VARS
    }
    env["PYTHONNOUSERSITE"] = "1"
    env["KATA_WORKSPACE"] = str(workspace.resolve())
    env["KATA_VALIDATOR_MODEL"] = resolve_validator_model()
    env["KATA_VALIDATOR_API_BASE"] = resolve_validator_api_base()
    env["KATA_VALIDATOR_API_KEY"] = resolve_validator_api_key()
    resolved_artifact = str(artifact_path.resolve())
    env["KATA_ARTIFACT_FILE"] = resolved_artifact
    env["KATA_ARTIFACT_DIR"] = str(artifact_path.parent.resolve())
    if artifact_path.suffix != ".py":
        raise ValueError(
            "Kata competition artifacts must use a Python agent entrypoint."
        )
    env["KATA_AGENT_FILE"] = resolved_artifact
    env["KATA_AGENT_BUNDLE_DIR"] = str(artifact_path.parent.resolve())
    env["KATA_MODE"] = mode
    env["KATA_REPO_REF"] = repo_ref
    env["KATA_REPO_SNAPSHOT"] = str(repo_snapshot.resolve())
    return env


def build_agent_env(
    *,
    workspace: Path,
    artifact_path: Path,
    eval_pack_root: Path,
    repo_snapshot: Path,
    mode: str,
    repo_ref: str,
    score_file: Path,
) -> dict[str, str]:
    del score_file
    env = build_common_env(
        workspace=workspace,
        artifact_path=artifact_path,
        repo_snapshot=repo_snapshot,
        mode=mode,
        repo_ref=repo_ref,
    )
    env["KATA_TASK_TEXT"] = (eval_pack_root / "task.md").read_text(encoding="utf-8")
    return env


def build_checks_env(
    *,
    workspace: Path,
    artifact_path: Path,
    eval_pack_root: Path,
    repo_snapshot: Path,
    mode: str,
    repo_ref: str,
    score_file: Path,
) -> dict[str, str]:
    env = build_common_env(
        workspace=workspace,
        artifact_path=artifact_path,
        repo_snapshot=repo_snapshot,
        mode=mode,
        repo_ref=repo_ref,
    )
    env["KATA_EVAL_TASK_DIR"] = str(eval_pack_root.resolve())
    env["KATA_SCORE_FILE"] = str(score_file.resolve())
    env["KATA_TASK_FILE"] = str((eval_pack_root / "task.md").resolve())
    env["KATA_RUBRIC_FILE"] = str((eval_pack_root / "rubric.md").resolve())
    env["KATA_ALLOWED_PATHS_FILE"] = str((eval_pack_root / "allowed_paths.txt").resolve())
    env["KATA_FORBIDDEN_PATHS_FILE"] = str((eval_pack_root / "forbidden_paths.txt").resolve())
    return env


def read_task_repo_ref(path: Path, *, fallback: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped
    return fallback


def build_run_id(task_id: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{task_id}-{timestamp}"


def copy_repository(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*IGNORED_COPY_DIRS))


def write_summary(path: Path, summary: EvalRunSummary) -> None:
    path.write_text(json.dumps(asdict(summary), indent=2) + "\n", encoding="utf-8")


def select_task_validations(
    validations: list[EvalPackValidationResult],
    task_names: list[str] | None,
) -> list[EvalPackValidationResult]:
    if not task_names:
        return validations
    by_name = {validation.root.name: validation for validation in validations}
    missing = [task_name for task_name in task_names if task_name not in by_name]
    if missing:
        raise ValueError(f"Unknown eval-pack tasks: {', '.join(missing)}")
    return [by_name[task_name] for task_name in task_names]


def stage_artifact_bundle(
    *,
    artifact_root: Path,
    entrypoint: str,
    files: dict[str, str],
) -> Path:
    for relative_path, content in files.items():
        file_path = artifact_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    entrypoint_path = artifact_root / entrypoint
    if not entrypoint_path.exists():
        raise ValueError(f"Artifact bundle is missing entrypoint: {entrypoint}")
    return entrypoint_path
