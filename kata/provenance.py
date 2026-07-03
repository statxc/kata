from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def sha256_directory(root: str | Path, *, include: list[str] | None = None) -> str:
    root_path = Path(root).expanduser().resolve()
    relative_paths = include or [
        path.relative_to(root_path).as_posix()
        for path in sorted(root_path.rglob("*"))
        if path.is_file()
    ]
    hasher = sha256()
    for relative_path in sorted(relative_paths):
        file_path = root_path / relative_path
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(file_path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()



def short_hash(value: str, length: int = 12) -> str:
    return value[:length]
