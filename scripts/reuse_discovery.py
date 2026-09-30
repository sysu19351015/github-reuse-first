"""Repository search and immutable evidence collection."""
from pathlib import PurePosixPath
from urllib.parse import quote
from reuse_common import (LICENSE_NAME, MANIFESTS, SHA, ReuseError, cell, digest,
                          new_directory, normalize_repo, now, safe_path, write_json)


def repo_summary(item):
    keys = ("full_name", "html_url", "description", "language", "stargazers_count",
            "pushed_at", "archived", "fork", "default_branch", "visibility")
    result = {k: item.get(k) for k in keys}
    result["license_hint"] = (item.get("license") or {}).get("spdx_id")
    return result


def search(client, queries, output, limit=5, pages=1):
    if not queries or not 1 <= limit <= 100 or not 1 <= pages <= 10:
        raise ReuseError("Supply queries; limit 1..100 and pages 1..10.")
    folder = new_directory(output)
    result = {"schema_version": 1, "searched_at": now(), "provider": "github-rest",
              "scope": "public repositories", "queries": [], "candidates": [], "errors": []}
    seen = set()
    for query in queries:
        if not query.strip():
            raise ReuseError("Empty search query.")
        # Enforce public scope for fallback search; private projects can be inspected explicitly.
        effective = query + " is:public"
        entry = {"query": query, "effective_query": effective, "pages_fetched": 0,
                 "total_count": None, "incomplete_results": False, "truncated": False}
        fetched = 0
        try:
            for page in range(1, pages + 1):
                data = client.get("/search/repositories", {"q": effective, "per_page": limit, "page": page})
                entry["pages_fetched"] += 1
                entry["total_count"] = data["total_count"]
                entry["incomplete_results"] |= data.get("incomplete_results", False)
                items = data["items"]
                fetched += len(items)
                for item in items:
                    if item.get("private"):
                        continue
                    key = item["full_name"].lower()
                    if key not in seen:
                        seen.add(key)
                        result["candidates"].append(repo_summary(item))
                if len(items) < limit or fetched >= data["total_count"]:
                    break
            entry["truncated"] = fetched < (entry["total_count"] or 0)
        except ReuseError as exc:
            result["errors"].append({"query": query, "error": str(exc)})
        result["queries"].append(entry)
    result["status"] = "limited" if result["errors"] or any(
        q["incomplete_results"] or q["truncated"] for q in result["queries"]) else "complete"
    write_json(folder / "search-results.json", result)
    lines = ["# GitHub 检索结果", "", "检索时间：" + result["searched_at"],
             "", "范围：公开仓库；检索状态：" + result["status"],
             "", "此列表仅用于发现候选，尚未核实功能或许可。", "",
             "| 项目 | 描述 | 语言 | 许可标签（未核验） |", "| --- | --- | --- | --- |"]
    for item in result["candidates"]:
        lines.append(f"| [{cell(item['full_name'])}]({item['html_url']}) | {cell(item['description'])} | "
                     f"{cell(item['language'])} | {cell(item['license_hint'])} |")
    if not result["candidates"]:
        lines.extend(["", "本次没有获得候选；不代表 GitHub 上不存在相似项目。"])
    for error in result["errors"]:
        lines.extend(["", "- 检索受限：" + cell(error["error"])])
    (folder / "search-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def inspect_repo(client, repo, ref, output, extra_files=()):
    repo = normalize_repo(repo)
    metadata = client.get(f"/repos/{repo}")
    requested = ref or metadata["default_branch"]
    commit_data = client.get(f"/repos/{repo}/commits/{quote(requested, safe='')}")
    commit = commit_data["sha"]
    if not SHA.fullmatch(commit):
        raise ReuseError("Invalid commit SHA returned by GitHub.")
    tree_sha = commit_data["commit"]["tree"]["sha"]
    tree = client.get(f"/repos/{repo}/git/trees/{tree_sha}", {"recursive": "1"})
    files = [x for x in tree["tree"] if x["type"] == "blob" and x.get("mode") != "120000"]
    chosen = []
    for item in files:
        name = PurePosixPath(item["path"]).name
        if LICENSE_NAME.match(name) or ("/" not in item["path"] and
                (name.lower().startswith("readme") or name in MANIFESTS)):
            chosen.append(item["path"])
    chosen = list(dict.fromkeys([*extra_files, *sorted(chosen, key=lambda p: (p.count("/"), p))]))
    folder = new_directory(output)
    evidence_dir = folder / "evidence"
    evidence_dir.mkdir()
    result = {"schema_version": 1, "repository": repo_summary(metadata),
              "repository_url": "https://github.com/" + repo, "requested_ref": requested,
              "resolved_commit": commit, "inspected_at": now(), "tree_sha": tree_sha,
              "tree_truncated": tree.get("truncated", False),
              "tree": tree["tree"], "evidence": [], "warnings": []}
    if result["tree_truncated"]:
        result["warnings"].append("Repository tree was truncated; paths and license coverage may be incomplete.")
    if len(chosen) > 30:
        result["warnings"].append(f"Only 30 of {len(chosen)} evidence files downloaded; inspect other relevant paths.")
    for path in chosen[:30]:
        try:
            data = client.file(repo, path, commit)
            relative = safe_path(path)
            target = evidence_dir.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            result["evidence"].append({"path": path, "sha256": digest(data),
                "kind": "license" if LICENSE_NAME.match(relative.name) else "source",
                "url": f"https://github.com/{repo}/blob/{commit}/{quote(path, safe='/')}"})
        except ReuseError as exc:
            result["warnings"].append(path + ": " + str(exc))
    write_json(folder / "inspection.json", result)
    review = {"schema_version": 1, "repository_url": result["repository_url"],
              "resolved_commit": commit, "status": "needs_review", "identifier": None,
              "intended_use": "", "license_files": [e for e in result["evidence"] if e["kind"] == "license"],
              "obligations": [], "unresolved": ["Read relevant license text and evaluate the intended use."],
              "selection_basis": ""}
    write_json(folder / "review.json", review)
    return result


