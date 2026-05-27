#!/usr/bin/env python3
"""Compare existing cloud ASR snippets with local transcript lines."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def normalize(text: str) -> str:
    return re.sub(r"[\s,，。.!！?？、;；:：\"“”'‘’\[\]【】()（）\-—_]+", "", text)


def snippet_text(raw_payload: dict) -> str:
    result = raw_payload.get("volc_result", {}).get("response", {}).get("result", {})
    return result.get("text", "").strip()


def issue_label(local_text: str, cloud_text: str) -> str:
    local = normalize(local_text)
    cloud = normalize(cloud_text)
    if not cloud:
        return "云端无文本"
    if local == cloud:
        return "一致"
    if cloud and cloud in local:
        return "云端为本地子串"
    if local and local in cloud:
        return "本地为云端子串"
    repeated = False
    lines = [normalize(line) for line in local_text.splitlines() if normalize(line)]
    for left, right in zip(lines, lines[1:]):
        if left == right:
            repeated = True
            break
    if repeated:
        return "本地疑似重复"
    return "需人工判断"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--asr-dir", default="transcriptions/metadata/suspicious-snippet-asr")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    asr_dir = repo / args.asr_dir
    raw_dir = asr_dir / "volc-raw-json"
    rows = []

    for raw_path in sorted(raw_dir.glob("*.json")):
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        result = payload.get("volc_result", {})
        item = payload["item"]
        if not result.get("ok"):
            rows.append(
                {
                    "index": item["index"],
                    "audio_id": item["audio_id"],
                    "episode": item["episode"],
                    "status": "fail",
                    "reason": result.get("submit", {}).get("error") or result.get("submit", {}).get("api_message") or "failed",
                }
            )
            continue

        text_path = repo / "transcriptions" / "text" / f"{item['audio_id']}.txt"
        lines = text_path.read_text(encoding="utf-8", errors="replace").splitlines()
        local_lines = []
        for line_no in item.get("line_refs", []):
            if 1 <= line_no <= len(lines):
                local_lines.append(f"{line_no}: {lines[line_no - 1]}")
        local_text = "\n".join(local_lines)
        cloud = snippet_text(payload)
        rows.append(
            {
                "index": item["index"],
                "audio_id": item["audio_id"],
                "episode": item["episode"],
                "status": "ok",
                "start_seconds": item["start_seconds"],
                "end_seconds": item["end_seconds"],
                "issue_types": item.get("issue_types", []),
                "line_refs": item.get("line_refs", []),
                "label": issue_label(local_text, cloud),
                "local_text": local_text,
                "cloud_text": cloud,
                "raw_json_path": str(raw_path.relative_to(repo)),
            }
        )

    summary = {
        "total_raw": len(rows),
        "ok": sum(1 for row in rows if row["status"] == "ok"),
        "fail": sum(1 for row in rows if row["status"] == "fail"),
        "labels": {},
    }
    for row in rows:
        if row["status"] == "ok":
            summary["labels"][row["label"]] = summary["labels"].get(row["label"], 0) + 1

    report = {"summary": summary, "items": rows}
    json_path = asr_dir / "snippet-asr-comparison.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = ["# 可疑切片云端识别对照", "", "## 汇总", ""]
    for key, value in summary.items():
        md.append(f"- {key}: {value}")
    md.append("")
    md.append("## 成功切片")
    for row in rows:
        if row["status"] != "ok":
            continue
        md.append("")
        md.append(f"### #{row['index']:04d} EP{row['episode']} {row['label']}")
        md.append(f"- audio_id: `{row['audio_id']}`")
        md.append(f"- lines: {row['line_refs']} | seconds: {row['start_seconds']}-{row['end_seconds']}")
        md.append(f"- issue: {', '.join(row['issue_types'])}")
        md.append("- local:")
        md.append("```text")
        md.append(row["local_text"])
        md.append("```")
        md.append("- cloud:")
        md.append("```text")
        md.append(row["cloud_text"])
        md.append("```")
    md_path = asr_dir / "snippet-asr-comparison.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
