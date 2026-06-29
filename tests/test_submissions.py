from __future__ import annotations

import json
from pathlib import Path

from promptforge.frontier import (
    FRONTIER_SCHEMA_VERSION,
    FrontierManifest,
    FrontierModeConfig,
    write_frontier_manifest,
)
from promptforge.provenance import sha256_text
from promptforge.submissions import (
    init_submission,
    validate_submission,
    verify_submission_result,
)


def write_registry(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "promptforge-benchmark-registry.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "registry_name": "test-registry",
                "benchmarks_dir": "benchmarks",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "benchmarks").mkdir(parents=True, exist_ok=True)


def write_frontier_pack(registry_root: Path, repo_pack: str, repo_ref: str) -> Path:
    pack_root = registry_root / "benchmarks" / repo_pack
    prompt_root = pack_root / "prompts" / "contributor"
    prompt_root.mkdir(parents=True, exist_ok=True)
    baseline_text = "# baseline\n"
    frontier_text = "# frontier\n"
    (prompt_root / "baseline.md").write_text(baseline_text, encoding="utf-8")
    (prompt_root / "frontier.md").write_text(frontier_text, encoding="utf-8")
    manifest = FrontierManifest(
        schema_version=FRONTIER_SCHEMA_VERSION,
        repo_ref=repo_ref,
        eval_pack=str(pack_root),
        updated_at="2026-06-29T00:00:00+00:00",
        modes={
            "contributor": FrontierModeConfig(
                baseline_prompt=str((prompt_root / "baseline.md").resolve()),
                frontier_prompt=str((prompt_root / "frontier.md").resolve()),
                primary_tasks=["task-a"],
                holdout_tasks=[],
                evaluator_version="2026-06-29.v1",
                baseline_prompt_hash=sha256_text(baseline_text),
                frontier_prompt_hash=sha256_text(frontier_text),
                primary_pool_fingerprint="a" * 64,
                holdout_pool_fingerprint=None,
                frontier_updated_at="2026-06-29T00:00:00+00:00",
                frontier_source="seed",
            )
        },
    )
    write_frontier_manifest(str(pack_root), manifest)
    return pack_root


def challenge_summary_payload(
    *,
    pack_root: Path,
    submission_root: Path,
    frontier_prompt_hash: str,
    candidate_prompt_hash: str,
) -> dict[str, object]:
    baseline_prompt = pack_root / "prompts" / "contributor" / "baseline.md"
    frontier_prompt = pack_root / "prompts" / "contributor" / "frontier.md"
    candidate_prompt = submission_root / "candidate.md"
    return {
        "schema_version": 2,
        "run_id": "challenge-1",
        "manifest_path": str((pack_root / "frontier.json").resolve()),
        "mode": "contributor",
        "evaluator_version": "2026-06-29.v1",
        "baseline_prompt": str(baseline_prompt.resolve()),
        "frontier_prompt": str(frontier_prompt.resolve()),
        "candidate_prompt": str(candidate_prompt.resolve()),
        "baseline_prompt_hash": sha256_text("# baseline\n"),
        "frontier_prompt_hash": frontier_prompt_hash,
        "candidate_prompt_hash": candidate_prompt_hash,
        "primary_pool_fingerprint": "a" * 64,
        "holdout_pool_fingerprint": None,
        "promotion_margin_points": 3.0,
        "created_at": "2026-06-29T00:00:00+00:00",
        "primary": {
            "task_ids": ["task-a"],
            "eval_run_summary": "run_summary.json",
            "total_task_weight": 1.0,
            "variant_successes": {"baseline": 0, "frontier": 0, "candidate": 1},
            "variant_invalid_tasks": {"baseline": 0, "frontier": 0, "candidate": 0},
            "variant_scores": {"baseline": 0.0, "frontier": 0.0, "candidate": 100.0},
            "candidate_beats_frontier": True,
            "candidate_score_delta": 100.0,
        },
        "holdout": None,
        "promotion_ready": True,
        "promotion_reason": "candidate cleared the primary score margin",
    }


def test_validate_submission_accepts_scoped_submission_pr(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_root = tmp_path / "registry"
    write_registry(registry_root)
    write_frontier_pack(registry_root, "example__repo", "/tmp/repo")
    monkeypatch.setenv("PROMPTFORGE_BENCHMARKS_ROOT", str(registry_root))
    repo_root = tmp_path / "PromptForge"
    submission_root = init_submission(
        repo_pack="example__repo",
        mode="contributor",
        submission_id="miner-1",
        output_root=str(repo_root / "submissions"),
    )
    (submission_root / "candidate.md").write_text("# challenger\n", encoding="utf-8")

    result = validate_submission(
        str(submission_root),
        changed_paths=[
            "submissions/example__repo/contributor/miner-1/candidate.md",
            "submissions/example__repo/contributor/miner-1/submission.json",
        ],
        repo_root=str(repo_root),
    )

    assert result.is_valid
    assert result.reasons == []
    assert result.off_scope_paths == []


def test_validate_submission_rejects_off_scope_pr_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_root = tmp_path / "registry"
    write_registry(registry_root)
    write_frontier_pack(registry_root, "example__repo", "/tmp/repo")
    monkeypatch.setenv("PROMPTFORGE_BENCHMARKS_ROOT", str(registry_root))
    repo_root = tmp_path / "PromptForge"
    submission_root = init_submission(
        repo_pack="example__repo",
        mode="contributor",
        submission_id="miner-2",
        output_root=str(repo_root / "submissions"),
    )
    (submission_root / "candidate.md").write_text("# challenger\n", encoding="utf-8")

    result = validate_submission(
        str(submission_root),
        changed_paths=[
            "submissions/example__repo/contributor/miner-2/candidate.md",
            "README.md",
        ],
        repo_root=str(repo_root),
    )

    assert not result.is_valid
    assert "Submission PR touches paths outside the allowed submission scope." in result.reasons
    assert result.off_scope_paths == ["README.md"]


def test_validate_submission_rejects_scaffold_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_root = tmp_path / "registry"
    write_registry(registry_root)
    write_frontier_pack(registry_root, "example__repo", "/tmp/repo")
    monkeypatch.setenv("PROMPTFORGE_BENCHMARKS_ROOT", str(registry_root))
    repo_root = tmp_path / "PromptForge"
    submission_root = init_submission(
        repo_pack="example__repo",
        mode="contributor",
        submission_id="miner-2b",
        output_root=str(repo_root / "submissions"),
    )

    result = validate_submission(str(submission_root))

    assert not result.is_valid
    assert "Candidate prompt still contains scaffold placeholder text." in result.reasons


def test_verify_submission_result_accepts_current_promotion_ready_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_root = tmp_path / "registry"
    write_registry(registry_root)
    pack_root = write_frontier_pack(registry_root, "example__repo", "/tmp/repo")
    monkeypatch.setenv("PROMPTFORGE_BENCHMARKS_ROOT", str(registry_root))
    repo_root = tmp_path / "PromptForge"
    submission_root = init_submission(
        repo_pack="example__repo",
        mode="contributor",
        submission_id="miner-3",
        output_root=str(repo_root / "submissions"),
    )
    candidate_text = "# winner\n"
    (submission_root / "candidate.md").write_text(candidate_text, encoding="utf-8")
    candidate_hash = sha256_text(candidate_text)
    summary_path = tmp_path / "challenge_summary.json"
    summary_path.write_text(
        json.dumps(
            challenge_summary_payload(
                pack_root=pack_root,
                submission_root=submission_root,
                frontier_prompt_hash=sha256_text("# frontier\n"),
                candidate_prompt_hash=candidate_hash,
            )
        )
        + "\n",
        encoding="utf-8",
    )

    result = verify_submission_result(str(submission_root), str(summary_path))

    assert result.submission_matches_challenge
    assert result.frontier_is_current
    assert result.benchmark_is_current
    assert result.auto_merge_ready
    assert result.reasons == []


def test_verify_submission_result_detects_stale_frontier(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_root = tmp_path / "registry"
    write_registry(registry_root)
    pack_root = write_frontier_pack(registry_root, "example__repo", "/tmp/repo")
    monkeypatch.setenv("PROMPTFORGE_BENCHMARKS_ROOT", str(registry_root))
    repo_root = tmp_path / "PromptForge"
    submission_root = init_submission(
        repo_pack="example__repo",
        mode="contributor",
        submission_id="miner-4",
        output_root=str(repo_root / "submissions"),
    )
    candidate_text = "# winner\n"
    (submission_root / "candidate.md").write_text(candidate_text, encoding="utf-8")
    summary_path = tmp_path / "challenge_summary.json"
    summary_path.write_text(
        json.dumps(
            challenge_summary_payload(
                pack_root=pack_root,
                submission_root=submission_root,
                frontier_prompt_hash=sha256_text("# older-frontier\n"),
                candidate_prompt_hash=sha256_text(candidate_text),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    result = verify_submission_result(str(submission_root), str(summary_path))

    assert not result.frontier_is_current
    assert not result.auto_merge_ready
    assert "Challenge result is stale because the frontier prompt has changed." in result.reasons
