#!/usr/bin/env python3
"""Generate per-episode evidence for the final offline website transcripts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def load_episodes(website: Path) -> list[dict]:
    html = website.read_text(encoding="utf-8")
    match = re.search(r"const episodes = (\[.*?\]);", html, re.S)
    if not match:
        raise RuntimeError(f"Unable to find episodes array in {website}")
    return json.loads(match.group(1))


def issue_location(issue: dict) -> str:
    if "start" in issue and "end" in issue:
        return f"L{issue['start']}-L{issue['end']}"
    if "line" in issue:
        return f"L{issue['line']}"
    if "lines" in issue:
        lines = issue["lines"]
        if isinstance(lines, list):
            return ",".join(f"L{line}" for line in lines[:5])
        return str(lines)
    return ""


def issue_sample(issue: dict) -> str:
    sample = issue.get("text") or issue.get("sample") or issue.get("term") or issue.get("pattern") or ""
    return str(sample).replace("\n", " ")[:120]


def episode_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def verdict(level: str) -> str:
    if level == "clean":
        return "未见明显风险"
    if level == "low":
        return "低风险留痕"
    if level == "medium":
        return "需人工复核"
    return "高风险需重听"


def write_markdown(path: Path, payload: dict) -> None:
    summary = payload["summary"]
    lines = [
        "# 最终网页文稿逐篇 Review 证据",
        "",
        "## 范围",
        f"- 网页: `{summary['website']}`",
        f"- 最终网页篇数: {summary['episode_count']}",
        f"- 生成时间: {summary['generated_at']}",
        f"- 风险分布: clean {summary['levels'].get('clean', 0)} / low {summary['levels'].get('low', 0)} / medium {summary['levels'].get('medium', 0)} / high {summary['levels'].get('high', 0)}",
        f"- 本轮切片重识别: 接收 {summary['rerun'].get('accepted', 0)} / 拒收 {summary['rerun'].get('rejected', 0)} / 失败 {summary['rerun'].get('failed', 0)}",
        "",
        "## 每篇证据",
        "",
        "| 集数 | level | severity | 行数 | 字数 | sha256 | 结论 | top issue |",
        "|---:|---|---:|---:|---:|---|---|---|",
    ]
    for row in payload["episodes"]:
        top = row["top_issues"][0] if row["top_issues"] else {"type": "无明显问题", "loc": "", "sample": ""}
        loc = f" {top['loc']}" if top.get("loc") else ""
        sample = f": {top['sample']}" if top.get("sample") else ""
        top_text = f"{top['type']}{loc}{sample}".replace("|", "/")
        lines.append(
            f"| {row['episode']} | {row['level']} | {row['severity']} | {row['line_count']} | {row['char_count']} | `{row['sha256'][:12]}` | {row['verdict']} | {top_text} |"
        )

    lines.extend(["", "## 仍需人工复核"])
    risky = [row for row in payload["episodes"] if row["level"] in {"medium", "high"}]
    if not risky:
        lines.append("- 无。")
    for row in risky:
        lines.append(
            f"- {row['episode']} `{row['id']}` {row['level']} severity {row['severity']}: {row['title']}"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "episode",
        "id",
        "title",
        "source",
        "level",
        "severity",
        "line_count",
        "char_count",
        "sha256",
        "verdict",
        "top_issue",
        "top_issue_location",
        "top_issue_sample",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            top = row["top_issues"][0] if row["top_issues"] else {}
            writer.writerow(
                {
                    "episode": row["episode"],
                    "id": row["id"],
                    "title": row["title"],
                    "source": row["source"],
                    "level": row["level"],
                    "severity": row["severity"],
                    "line_count": row["line_count"],
                    "char_count": row["char_count"],
                    "sha256": row["sha256"],
                    "verdict": row["verdict"],
                    "top_issue": top.get("type", ""),
                    "top_issue_location": top.get("loc", ""),
                    "top_issue_sample": top.get("sample", ""),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--website", default="sun-audio-offline-website.html")
    parser.add_argument("--out-dir", default="transcriptions/metadata/final-website-review")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    website = (repo / args.website).resolve()
    out_dir = (repo / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    episodes = load_episodes(website)
    review_path = repo / "transcriptions" / "metadata" / "full-transcript-review" / "full-transcript-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review_by_id = {item["audio_id"]: item for item in review.get("items", [])}

    rerun_path = repo / "transcriptions" / "metadata" / "asr-rerun-high-risk-chunked" / "rerun-results.json"
    rerun_data = json.loads(rerun_path.read_text(encoding="utf-8")) if rerun_path.exists() else []
    rerun_rows = rerun_data.get("items", []) if isinstance(rerun_data, dict) else rerun_data
    rerun_counts = Counter(row.get("status", "unknown") for row in rerun_rows)

    rows = []
    for episode in episodes:
        text = episode.get("transcript", "")
        lines = episode_lines(text)
        review_item = review_by_id.get(episode["id"], {})
        issues = review_item.get("issues", [])
        top_issues = [
            {
                "type": issue.get("type", ""),
                "severity": issue.get("severity", 0),
                "loc": issue_location(issue),
                "sample": issue_sample(issue),
            }
            for issue in issues[:5]
        ]
        level = review_item.get("level", "clean")
        severity = int(review_item.get("severity", 0))
        rows.append(
            {
                "episode": episode.get("episode", ""),
                "id": episode.get("id", ""),
                "title": episode.get("title", ""),
                "source": episode.get("source", ""),
                "duration": episode.get("duration", ""),
                "duration_seconds": episode.get("duration_seconds", 0),
                "line_count": len(lines),
                "char_count": len(compact(text)),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "level": level,
                "severity": severity,
                "verdict": verdict(level),
                "first_lines": lines[:3],
                "last_lines": lines[-3:],
                "top_issues": top_issues,
            }
        )

    rows.sort(key=lambda row: int(row["episode"]))
    levels = Counter(row["level"] for row in rows)
    payload = {
        "summary": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "website": str(website),
            "episode_count": len(rows),
            "levels": dict(levels),
            "rerun": {
                "accepted": rerun_counts.get("accepted", 0),
                "rejected": rerun_counts.get("rejected", 0),
                "failed": rerun_counts.get("failed", 0),
                "targets": len(rerun_rows),
            },
        },
        "episodes": rows,
    }

    json_path = out_dir / "final-website-transcript-review.json"
    md_path = out_dir / "final-website-transcript-review.md"
    csv_path = out_dir / "final-website-transcript-review.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, payload)
    write_csv(csv_path, rows)
    print(
        json.dumps(
            {
                "episodes": len(rows),
                "levels": dict(levels),
                "json": str(json_path),
                "markdown": str(md_path),
                "csv": str(csv_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
