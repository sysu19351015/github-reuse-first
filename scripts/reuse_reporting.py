"""Render explicit evidence-based assessments; never infer suitability from stars."""
from urllib.parse import urlsplit
from reuse_common import ReuseError, cell, new_directory, normalize_repo, now, read_json, write_json


def render_report(assessment_path, output):
    assessment = read_json(assessment_path)
    if not isinstance(assessment.get("goal"), str) or not assessment["goal"].strip():
        raise ReuseError("Assessment requires a goal.")
    candidates = assessment.get("candidates")
    if not isinstance(candidates, list):
        raise ReuseError("Assessment requires a candidates list.")
    lines = ["# 开源复用比较", "", "目标：" + assessment["goal"], "",
             "检索范围：" + cell(assessment.get("search_scope")), "",
             "生成时间：" + now(), "",
             "| 项目 | 功能匹配 | 主要差距 | 许可证判断 | 改造量 |", "| --- | --- | --- | --- |"]
    seen = set()
    for candidate in candidates:
        repo = normalize_repo(candidate["repository"])
        if repo.lower() in seen:
            raise ReuseError("Duplicate candidate repository.")
        seen.add(repo.lower())
        if candidate.get("license_status") not in {"reviewed_for_use", "needs_review", "incompatible_with_request"}:
            raise ReuseError("Invalid candidate license status.")
        for field in ("fit", "gaps", "effort"):
            if not isinstance(candidate.get(field), str) or not candidate[field].strip():
                raise ReuseError(f"Candidate requires {field}.")
        if not isinstance(candidate.get("evidence"), list) or not candidate["evidence"]:
            raise ReuseError("Each candidate requires evidence links and claims.")
        lines.append(f"| [{repo}](https://github.com/{repo}) | {cell(candidate['fit'])} | "
                     f"{cell(candidate['gaps'])} | {candidate['license_status']} | {cell(candidate['effort'])} |")
    for candidate in candidates:
        lines += ["", "## " + candidate["repository"], ""]
        for evidence in candidate["evidence"]:
            if evidence.get("status") not in {"verified", "documented", "inferred", "unknown"}:
                raise ReuseError("Evidence status must distinguish verified/documented/inferred/unknown.")
            url = evidence.get("url", "")
            if urlsplit(url).scheme != "https" or not evidence.get("claim"):
                raise ReuseError("Evidence requires an HTTPS URL and a claim.")
            lines.append("- " + cell(evidence["claim"]) + "（" + evidence["status"] + "）：" + url)
    if not candidates:
        lines += ["", "本次检索范围内尚未确认合适候选；不能推断不存在相似实现。"]
    lines += ["", "## 推荐与选择", "", str(assessment.get("recommendation") or "尚未选定"),
              "", "状态：" + str(assessment.get("decision") or "awaiting_selection")]
    folder = new_directory(output)
    write_json(folder / "assessment.json", assessment)
    (folder / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"report": str(folder / "comparison.md"), "candidates": len(candidates)}


