#!/usr/bin/env python3
"""Install this self-contained skill; upgrades preserve a timestamped backup."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

PAYLOAD = ("SKILL.md", "agents", "scripts", "references", "examples", "docs", "README.md", "LICENSE", "VERSION")


def install(source, destination, upgrade=False):
    source, destination = Path(source).resolve(), Path(destination).expanduser().absolute()
    if source == destination.resolve() or source in destination.resolve().parents:
        raise ValueError("Installation destination must be outside the source tree.")
    required = ("SKILL.md", "agents/openai.yaml", "scripts/reuse.py", "references/cli.md",
                "scripts/reuse_common.py", "scripts/reuse_discovery.py",
                "scripts/reuse_acquisition.py", "scripts/reuse_reporting.py")
    for name in required:
        if not (source / name).is_file():
            raise ValueError("Incomplete skill: " + name)
    skill = (source / "SKILL.md").read_text(encoding="utf-8")
    if not skill.startswith("---\n") or "name: github-reuse-first" not in skill:
        raise ValueError("Invalid skill entrypoint.")
    for path in (source / "scripts").glob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    if destination.is_symlink():
        raise ValueError("Refusing a symlink installation destination.")
    if destination.exists() and (not upgrade or not destination.is_dir()):
        raise ValueError("Destination exists. Use --upgrade to preserve it as a backup and install.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    with tempfile.TemporaryDirectory(prefix=".github-reuse-first-stage-", dir=destination.parent) as temp:
        stage = Path(temp) / "github-reuse-first"
        stage.mkdir()
        for name in PAYLOAD:
            src = source / name
            if src.is_dir():
                shutil.copytree(src, stage / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif src.is_file():
                shutil.copy2(src, stage / name)
        if destination.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_root = (destination.parent.parent if destination.parent.name == "skills" else destination.parent) / "skill-backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            backup_root = backup_root.resolve()
            backup = backup_root / (destination.name + "-" + stamp + "-" + uuid.uuid4().hex[:8])
            if not backup.resolve().is_relative_to(backup_root) or backup.exists():
                raise ValueError("Unsafe or occupied backup destination.")
            destination.rename(backup)
        try:
            stage.rename(destination)
        except OSError:
            if backup is not None and not destination.exists():
                backup.rename(destination)
            raise
    return destination, backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", default=str(Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills" / "github-reuse-first"))
    parser.add_argument("--upgrade", action="store_true")
    args = parser.parse_args()
    try:
        destination, backup = install(Path(__file__).resolve().parent.parent, args.dest, args.upgrade)
        print("Installed: " + str(destination))
        if backup:
            print("Backup: " + str(backup))
        return 0
    except (ValueError, OSError, SyntaxError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
