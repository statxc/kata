from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kata.agent_bundle import load_bundle_files, replace_bundle_contents

PUBLIC_KINGS_DIRNAME = "kings"
KING_METADATA_FILENAME = "king.json"


@dataclass(frozen=True)
class PublicKingMetadata:
    repo_pack: str
    mode: str
    submission_id: str
    challenge_run_id: str
    frontier_artifact_hash: str
    candidate_artifact_hash: str


def publish_public_king(
    *,
    public_root: str,
    repo_pack: str,
    mode: str,
    submission_id: str,
    challenge_run_id: str,
    candidate_artifact_path: str,
    frontier_artifact_hash: str,
    candidate_artifact_hash: str,
) -> Path:
    root = Path(public_root).expanduser().resolve()
    king_root = root / PUBLIC_KINGS_DIRNAME / repo_pack / mode
    candidate_root = Path(candidate_artifact_path).expanduser().resolve()
    replace_bundle_contents(king_root, load_bundle_files(candidate_root))
    metadata = PublicKingMetadata(
        repo_pack=repo_pack,
        mode=mode,
        submission_id=submission_id,
        challenge_run_id=challenge_run_id,
        frontier_artifact_hash=frontier_artifact_hash,
        candidate_artifact_hash=candidate_artifact_hash,
    )
    (king_root / KING_METADATA_FILENAME).write_text(
        json.dumps(asdict(metadata), indent=2) + "\n",
        encoding="utf-8",
    )
    return king_root
