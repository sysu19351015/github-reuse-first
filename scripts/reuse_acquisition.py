"""Verified source acquisition without running third-party code."""
from datetime import datetime
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from reuse_common import (MANIFESTS, SHA, ReuseError, digest, new_directory,
                          normalize_repo, now, read_json, safe_path, write_json)


def validate_review(inspection, review):
    if review.get("schema_version") != 1 or inspection.get("schema_version") != 1:
        raise ReuseError("Unsupported inspection/review version.")
    repo = normalize_repo(inspection["repository_url"])
    commit = inspection["resolved_commit"]
    if not SHA.fullmatch(commit):
        raise ReuseError("A full immutable commit SHA is required.")
    if review.get("repository_url") != inspection["repository_url"] or review.get("resolved_commit") != commit:
        raise ReuseError("Review must match the exact repository and commit.")
    if review.get("status") != "reviewed_for_use" or review.get("unresolved") != []:
        raise ReuseError("License review is unresolved; read evidence before acquiring a development base.")
    for field in ("intended_use", "selection_basis"):
        if not isinstance(review.get(field), str) or not review[field].strip():
            raise ReuseError(f"Review requires {field}.")
    if not isinstance(review.get("obligations"), list) or not all(isinstance(x, str) for x in review["obligations"]):
        raise ReuseError("Review obligations must be a string list.")
    known = {e["path"]: e for e in inspection["evidence"]}
    if not review.get("license_files"):
        raise ReuseError("Review requires at least one actual license evidence file.")
    for item in review["license_files"]:
        path = str(safe_path(item["path"]))
        if path not in known or item.get("sha256") != known[path]["sha256"]:
            raise ReuseError("License review evidence does not match inspection.")
    return repo, commit


def extract_archive(archive, destination, max_size=512 * 1024 * 1024, max_files=30000):
    """Validate the entire archive before writing. Reject links and cross-platform aliases."""
    destination = Path(destination)
    if destination.exists():
        raise ReuseError("Archive destination already exists.")
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if not entries or len(entries) > max_files:
            raise ReuseError("Empty archive or archive entry limit exceeded.")
        roots, seen, planned, total = set(), set(), [], 0
        for item in entries:
            raw = item.filename.rstrip("/")
            full = safe_path(raw)
            roots.add(full.parts[0])
            mode = (item.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ReuseError("Archive contains a symlink or special file; use Git for inspection.")
            if len(full.parts) == 1:
                if not item.is_dir():
                    raise ReuseError("Expected one GitHub archive root directory.")
                continue
            relative = PurePosixPath(*full.parts[1:])
            key = str(relative).casefold()
            if key in seen:
                raise ReuseError("Duplicate or case-colliding archive paths.")
            seen.add(key)
            total += item.file_size
            if total > max_size:
                raise ReuseError("Expanded archive size limit exceeded.")
            planned.append((item, relative))
        if len(roots) != 1:
            raise ReuseError("Expected exactly one GitHub archive root.")
        # Detect file/directory collisions before creating destination.
        regular = {str(p).casefold() for i, p in planned if not i.is_dir()}
        for _, path in planned:
            if any(str(p).casefold() in regular for p in path.parents if str(p) != "."):
                raise ReuseError("Archive file/directory collision.")
        destination.mkdir(parents=True, exist_ok=False)
        for item, relative in planned:
            target = destination.joinpath(*relative.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(item) as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)


def git_checkout(repo, commit, destination):
    if not shutil.which("git"):
        raise ReuseError("Git is unavailable; use --method archive.")
    destination = new_directory(destination)
    # Ignore global filters, credential commands, URL rewrites and inherited Git configuration.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"})
    with tempfile.TemporaryDirectory(prefix="reuse-git-") as empty:
        def run(*args):
            command = ["git", "-c", "core.hooksPath=" + empty, "-c", "core.symlinks=false",
                       "-c", "protocol.file.allow=never", *args]
            result = subprocess.run(command, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=180)
            if result.returncode:
                operation = args[2] if args[0] == "-C" else args[0]
                raise ReuseError("Git " + operation + " failed (exit " + str(result.returncode) +
                                 "); check connectivity/access. Use archive for token-authenticated repositories.")
            return result.stdout.strip()
        run("init", "--template=" + empty, str(destination))
        run("-C", str(destination), "remote", "add", "origin", f"https://github.com/{repo}.git")
        run("-C", str(destination), "fetch", "--no-tags", "--depth=1", "origin", commit)
        if run("-C", str(destination), "rev-parse", "FETCH_HEAD") != commit:
            raise ReuseError("Fetched Git commit does not match the reviewed commit.")
        run("-C", str(destination), "checkout", "--detach", commit, "--")
        if run("-C", str(destination), "rev-parse", "HEAD") != commit:
            raise ReuseError("Checked-out HEAD mismatch.")
        return {"head": commit, "remote": run("-C", str(destination), "remote", "get-url", "origin"),
                "history": "shallow", "symlinks": "materialized as text, not followed"}


def audit_source(folder, inspection):
    """Compare ordinary files with Git blob IDs; list absent submodules/LFS/links."""
    missing, mismatches, checked = [], [], 0
    folder = Path(folder).resolve()
    for entry in inspection["tree"]:
        if entry["type"] not in {"blob", "commit"}:
            continue
        path = safe_path(entry["path"])
        local = folder.joinpath(*path.parts)
        if entry["type"] == "commit":
            missing.append("submodule: " + str(path))
            continue
        if entry.get("mode") == "120000":
            missing.append("symlink not materialized: " + str(path))
            continue
        if local.is_symlink() or not local.resolve().is_relative_to(folder):
            raise ReuseError("Source file escapes acquisition directory.")
        if not local.is_file():
            missing.append(str(path))
            continue
        size = local.stat().st_size
        hasher = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
        with local.open("rb") as stream:
            prefix = stream.read(200)
            hasher.update(prefix)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != entry["sha"]:
            mismatches.append(str(path))
        if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
            missing.append("LFS object: " + str(path))
        checked += 1
    if inspection.get("tree_truncated"):
        missing.append("repository tree truncated; complete file coverage not verified")
    if mismatches:
        raise ReuseError("Source differs from Git tree: " + ", ".join(mismatches[:10]))
    return missing, checked


def acquire(client, inspection_path, review_path, destination, report_dir, method="archive"):
    inspection, review = read_json(inspection_path), read_json(review_path)
    repo, commit = validate_review(inspection, review)
    dest = Path(destination).expanduser().absolute()
    report = Path(report_dir).expanduser().absolute()
    if dest.exists() or dest.is_symlink():
        raise ReuseError("Source destination already exists; it will not be overwritten.")
    # Reports must not enter the source tree or contain it.
    if dest.resolve() == report.resolve() or dest.resolve() in report.resolve().parents or report.resolve() in dest.resolve().parents:
        raise ReuseError("Source and report directories must be separate.")
    report = new_directory(report)
    record = {"schema_version": 1, "repository_url": inspection["repository_url"],
              "requested_ref": inspection["requested_ref"], "resolved_commit": commit,
              "retrieved_at": now(), "method": "git_clone" if method == "git" else "commit_archive",
              "local_path": str(dest), "status": "failed", "missing_items": [], "failure_reason": None,
              "archive_sha256": None,
              "license": {"status": review["status"], "identifier": review.get("identifier"),
                          "files": review["license_files"], "obligations": review["obligations"], "unresolved": []},
              "selection_basis": review["selection_basis"],
              "verification": {"source_checks": {}, "runtime_checks": {"status": "not_run",
                                    "reason": "Source acquisition does not execute third-party code."}}}
    try:
        # Re-fetch tree at the reviewed immutable commit; do not trust an edited inspection tree.
        fresh = client.get(f"/repos/{repo}/commits/{commit}")
        if fresh["sha"] != commit:
            raise ReuseError("GitHub commit identity mismatch.")
        tree = client.get(f"/repos/{repo}/git/trees/{fresh['commit']['tree']['sha']}", {"recursive": "1"})
        inspection = dict(inspection, tree=tree["tree"], tree_truncated=tree.get("truncated", False))
        if method == "archive":
            with tempfile.TemporaryDirectory(prefix="reuse-archive-") as temp:
                archive = Path(temp) / "source.zip"
                record["archive_sha256"] = client.archive(repo, commit, archive)
                extract_archive(archive, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            record["verification"]["source_checks"]["git"] = git_checkout(repo, commit, dest)
        missing, checked = audit_source(dest, inspection)
        for evidence in review["license_files"]:
            target = dest.joinpath(*safe_path(evidence["path"]).parts)
            if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(dest.resolve()):
                raise ReuseError("Reviewed license file missing or unsafe.")
            if digest(target.read_bytes()) != evidence["sha256"]:
                raise ReuseError("Downloaded license differs from reviewed evidence.")
        record["missing_items"] = missing
        record["status"] = "partial" if missing else "complete"
        record["verification"]["source_checks"].update({"commit": commit, "git_blobs_verified": checked,
                "license_hashes_verified": True, "tree_truncated": inspection["tree_truncated"]})
    except (ReuseError, OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        record["failure_reason"] = str(exc)
        write_json(report / "source-record.json", record)
        raise ReuseError(f"Acquisition failed; partial files preserved. See {report / 'source-record.json'}") from exc
    validate_record(record)
    write_json(report / "source-record.json", record)
    handoff = ["# 二次开发交接", "", "仓库：" + record["repository_url"], "",
               "固定提交：" + commit, "", "源码目录：" + str(dest), "",
               "源码状态：" + record["status"], "", "选型依据：" + review["selection_basis"],
               "", "用途：" + review["intended_use"], "", "## 许可条件", ""]
    handoff += ["- " + item for item in review["obligations"]] or ["- 以已审阅的原始许可文本为准。"]
    handoff += ["", "## 已发现的入口与配置", ""]
    paths = [e["path"] for e in inspection["tree"] if e["type"] == "blob"]
    entrypoints = [p for p in paths if PurePosixPath(p).name in MANIFESTS or
                   PurePosixPath(p).name.lower() in {"main.py", "__main__.py", "index.ts", "index.js"}]
    handoff += ["- " + p for p in entrypoints[:30]] or ["- 未自动识别，需要结合实际源码检查。"]
    handoff += ["", "## 未完成事项", "", "- 尚未执行安装、构建或功能测试。",
                "- Codex 需补充需求 → 现有实现 → 修改/新增模块的对应表。",
                "- Codex 需读取相关入口，写出具体修改路径、实施顺序与验收步骤。"]
    handoff += ["- 缺失：" + item for item in missing]
    (report / "development-plan.md").write_text("\n".join(handoff) + "\n", encoding="utf-8")
    return record


def validate_record(record):
    if record.get("schema_version") != 1 or record.get("status") not in {"complete", "partial", "failed"}:
        raise ReuseError("Invalid source record version/status.")
    normalize_repo(record["repository_url"])
    if not SHA.fullmatch(record.get("resolved_commit") or ""):
        raise ReuseError("Source record requires a full commit SHA.")
    if record.get("method") not in {"git_clone", "commit_archive", "file_subset"}:
        raise ReuseError("Invalid acquisition method.")
    if not isinstance(record.get("missing_items"), list) or not all(isinstance(x, str) for x in record["missing_items"]):
        raise ReuseError("missing_items must be a string list.")
    try:
        timestamp = datetime.fromisoformat(record["retrieved_at"])
        if timestamp.tzinfo is None:
            raise ValueError("missing timezone")
    except (KeyError, TypeError, ValueError) as exc:
        raise ReuseError("Source record needs a timestamp with timezone.") from exc
    if not isinstance(record.get("selection_basis"), str) or not record["selection_basis"].strip():
        raise ReuseError("Source record needs a selection basis.")
    if not isinstance(record.get("verification", {}).get("runtime_checks"), dict):
        raise ReuseError("Source record must distinguish runtime verification.")
    if record["status"] == "complete":
        checks = record.get("verification", {}).get("source_checks", {})
        if record["missing_items"] or record["method"] == "file_subset" or record.get("failure_reason"):
            raise ReuseError("Complete source record cannot have missing files or failure.")
        if record["method"] == "commit_archive" and not re.fullmatch(r"[0-9a-f]{64}", record.get("archive_sha256") or ""):
            raise ReuseError("Complete archive record needs SHA-256.")
        if not checks.get("license_hashes_verified") or checks.get("tree_truncated") or checks.get("git_blobs_verified", 0) < 1:
            raise ReuseError("Complete source record lacks integrity verification.")
    if record["status"] == "failed" and not record.get("failure_reason"):
        raise ReuseError("Failed source record needs a reason.")
    if record["status"] == "partial" and not record["missing_items"]:
        raise ReuseError("Partial source record needs a missing-items list.")
    if record.get("license", {}).get("status") != "reviewed_for_use":
        raise ReuseError("Source record lacks a reviewed license.")
    if not Path(record.get("local_path", "")).is_absolute():
        raise ReuseError("Source record requires an absolute local_path.")
    return True


