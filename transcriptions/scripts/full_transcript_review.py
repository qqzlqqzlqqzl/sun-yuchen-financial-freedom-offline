#!/usr/bin/env python3
"""Full transcript quality review for the offline audio archive.

This script is intentionally report-only. It scans every transcript and flags
likely ASR failure modes so risky files can be rechecked against audio before
any text is changed.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


BOILERPLATE_PATTERNS = [
    "请不吝点赞订阅转发打赏支持明镜与点点栏目",
    "欢迎订阅转发打赏支持明镜与点点栏目",
    "请不吝点赞订阅转发打赏支持",
    "优优独播剧场YoYoTelevisionSeriesExclusive",
]

SUSPICIOUS_TERMS = {
    "深航": "疑似“深杭/深圳杭州”等地名误识别，需听音频确认",
    "波斯顿": "疑似“波士顿”",
    "星业银行": "疑似“兴业银行”",
    "何牧家": "疑似“和睦家”",
    "真公夫": "疑似专名误识别",
    "学语类": "疑似语义断裂",
    "不某样": "疑似语义断裂",
    "赵成仇": "疑似人名误识别",
    "叛击": "疑似术语误识别",
    "归击": "疑似术语误识别",
    "拿诺奖": "疑似“拿诺贝尔奖/拿诺奖”等上下文需确认",
    "据爸爸": "疑似“阿里巴巴”等误识别",
    "铜刀大叔": "疑似“同道大叔”",
    "万通中文": "疑似人名/机构名误识别",
    "小读记长": "疑似成语/短语误识别",
    "牛生碗水": "疑似成语/口语误识别",
    "果壳和新榜": "与部分稿“火壳和新榜”不一致，需确认",
    "火壳和新榜": "与部分稿“果壳和新榜”不一致，需确认",
    "孙宇辰": "疑似“孙宇晨”",
    "孙云辰": "疑似“孙宇晨”",
    "花天酒祭": "疑似“花天酒地”",
    "利润板税": "疑似“利润、版税/利息、投资利润、版税”",
    "编辑效应": "疑似“边际效应”",
    "财票中央者": "疑似“彩票中奖者”",
    "九云沟创业者": "疑似“90后创业者”",
    "切除我时间": "疑似“切出我时间”",
}


def normalize(text: str) -> str:
    return re.sub(r"[\s,，。.!！?？、;；:：\"“”'‘’\[\]【】()（）\-—_]+", "", text.strip())


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def is_boilerplate(text: str) -> bool:
    normalized = normalize(text)
    return any(pattern in normalized for pattern in BOILERPLATE_PATTERNS)


def source_label(item: dict) -> str:
    return str(item.get("source") or "unknown")


def exact_runs(lines: list[str]) -> list[dict]:
    runs: list[dict] = []
    last = ""
    run: list[int] = []
    for index, line in enumerate(lines, 1):
        normalized = normalize(line)
        if normalized and normalized == last:
            if not run:
                run = [index - 1, index]
            else:
                run.append(index)
        else:
            if run:
                runs.append({"start": run[0], "end": run[-1], "len": len(run), "text": lines[run[0] - 1]})
            run = []
        last = normalized
    if run:
        runs.append({"start": run[0], "end": run[-1], "len": len(run), "text": lines[run[0] - 1]})
    return runs


def anywhere_repeats(lines: list[str]) -> list[dict]:
    positions: dict[str, list[int]] = defaultdict(list)
    samples: dict[str, str] = {}
    for index, line in enumerate(lines, 1):
        normalized = normalize(line)
        if len(normalized) >= 12:
            positions[normalized].append(index)
            samples.setdefault(normalized, line)
    rows = []
    for normalized, line_numbers in positions.items():
        if len(line_numbers) >= 3:
            rows.append({"count": len(line_numbers), "lines": line_numbers, "text": samples[normalized]})
    return sorted(rows, key=lambda row: row["count"], reverse=True)


def near_runs(lines: list[str], threshold: float = 0.92) -> list[dict]:
    pairs = []
    for index in range(len(lines) - 1):
        left = normalize(lines[index])
        right = normalize(lines[index + 1])
        if min(len(left), len(right)) < 12:
            continue
        ratio = difflib.SequenceMatcher(None, left, right).ratio()
        if ratio >= threshold:
            pairs.append((index + 1, index + 2, ratio))

    groups = []
    current = []
    for pair in pairs:
        if not current or pair[0] <= current[-1][1]:
            current.append(pair)
        else:
            groups.append(current)
            current = [pair]
    if current:
        groups.append(current)

    return [
        {
            "start": group[0][0],
            "end": group[-1][1],
            "pairs": len(group),
            "max_ratio": round(max(item[2] for item in group), 3),
            "text": lines[group[0][0] - 1],
        }
        for group in groups
    ]


def repeated_unit_hits(line: str) -> list[dict]:
    text = compact(line)
    hits = []
    if len(text) < 8:
        return hits
    for size in range(1, min(13, len(text) // 3 + 1)):
        index = 0
        while index <= len(text) - size * 3:
            unit = text[index : index + size]
            if not unit or unit.isdigit() or (size > 1 and len(set(unit)) == 1):
                index += 1
                continue
            count = 1
            cursor = index + size
            while text[cursor : cursor + size] == unit:
                count += 1
                cursor += size
            if count >= 3:
                hits.append(
                    {
                        "unit": unit,
                        "count": count,
                        "sample": text[max(0, index - 12) : min(len(text), cursor + 12)],
                    }
                )
                index = cursor
            else:
                index += 1
    deduped = []
    seen = set()
    for hit in hits:
        key = (hit["unit"], hit["sample"])
        if key not in seen:
            deduped.append(hit)
            seen.add(key)
    return deduped[:5]


def suspicious_term_hits(text: str) -> list[dict]:
    rows = []
    for term, reason in SUSPICIOUS_TERMS.items():
        count = text.count(term)
        if count:
            rows.append({"term": term, "count": count, "reason": reason})
    return sorted(rows, key=lambda row: row["count"], reverse=True)


def boilerplate_bursts(lines: list[str]) -> list[dict]:
    rows = []
    for pattern in BOILERPLATE_PATTERNS:
        positions = [index for index, line in enumerate(lines, 1) if pattern in normalize(line)]
        if len(positions) >= 3:
            rows.append({"pattern": pattern, "count": len(positions), "lines": positions})
    return rows


def long_lines(lines: list[str]) -> list[dict]:
    rows = []
    for index, line in enumerate(lines, 1):
        length = len(compact(line))
        if length >= 260:
            rows.append({"line": index, "chars": length, "text": line[:160]})
    return rows


def empty_lines(lines: list[str]) -> list[int]:
    return [index for index, line in enumerate(lines, 1) if not line.strip()]


def rate_flags(char_count: int, duration_seconds: float) -> list[dict]:
    if duration_seconds <= 0:
        return []
    minutes = duration_seconds / 60.0
    chars_per_min = char_count / minutes if minutes else 0
    flags = []
    if duration_seconds >= 180 and chars_per_min < 45:
        flags.append({"type": "长音频短文稿", "value": round(chars_per_min, 1), "reason": "疑似整段转写失败或被口播重复占满"})
    if duration_seconds >= 180 and chars_per_min > 430:
        flags.append({"type": "长音频文稿过密", "value": round(chars_per_min, 1), "reason": "疑似重复文本或断句异常"})
    return flags


@dataclass
class ReviewRow:
    audio_id: str
    source: str
    filename: str
    duration_seconds: float
    text_path: str
    line_count: int
    char_count: int
    severity: int
    level: str
    issues: list[dict]


def classify(severity: int) -> str:
    if severity >= 80:
        return "high"
    if severity >= 25:
        return "medium"
    if severity > 0:
        return "low"
    return "clean"


def review_one(repo: Path, item: dict) -> ReviewRow:
    audio_id = item["id"]
    text_path = repo / "transcriptions" / "text" / f"{audio_id}.txt"
    text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
    lines = text.splitlines()
    char_count = len(compact(text))

    issues = []
    if not text_path.exists():
        issues.append({"type": "缺少文稿", "severity": 100, "sample": str(text_path)})
    if not text.strip():
        issues.append({"type": "空文稿", "severity": 100, "sample": ""})

    for row in exact_runs(lines):
        weight = 30 if row["len"] >= 10 else 18 if row["len"] >= 3 else 6
        if is_boilerplate(row["text"]):
            weight += 20
        issues.append({"type": "连续重复", "severity": weight, **row})

    for row in anywhere_repeats(lines):
        if any(issue.get("text") == row["text"] and issue["type"] == "连续重复" for issue in issues):
            continue
        weight = 18 if row["count"] >= 10 else 10
        if is_boilerplate(row["text"]):
            weight += 12
        issues.append({"type": "全文重复", "severity": weight, **row})

    for row in near_runs(lines):
        weight = 16 if row["pairs"] >= 5 else 7
        issues.append({"type": "近似重复", "severity": weight, **row})

    for row in boilerplate_bursts(lines):
        issues.append({"type": "固定口播堆叠", "severity": min(60, row["count"] * 3), **row})

    for index, line in enumerate(lines, 1):
        if is_boilerplate(line):
            continue
        for hit in repeated_unit_hits(line):
            issues.append({"type": "行内循环", "severity": 8 if hit["count"] >= 5 else 4, "line": index, "text": line, **hit})

    for row in suspicious_term_hits(text):
        issues.append({"type": "疑似错词", "severity": min(15, 3 * row["count"]), **row})

    for row in long_lines(lines):
        issues.append({"type": "超长行", "severity": 6, **row})

    blank_lines = empty_lines(lines)
    if blank_lines:
        issues.append({"type": "空行", "severity": min(10, len(blank_lines)), "count": len(blank_lines), "lines": blank_lines[:20]})

    for row in rate_flags(char_count, float(item.get("duration_seconds", 0.0))):
        issues.append({"type": row["type"], "severity": 28, **row})

    severity = sum(issue["severity"] for issue in issues)
    issues = sorted(issues, key=lambda issue: issue["severity"], reverse=True)

    return ReviewRow(
        audio_id=audio_id,
        source=source_label(item),
        filename=item.get("filename", ""),
        duration_seconds=float(item.get("duration_seconds", 0.0)),
        text_path=str(text_path.relative_to(repo)),
        line_count=len(lines),
        char_count=char_count,
        severity=severity,
        level=classify(severity),
        issues=issues,
    )


def row_to_dict(row: ReviewRow) -> dict:
    return {
        "audio_id": row.audio_id,
        "source": row.source,
        "filename": row.filename,
        "duration_seconds": row.duration_seconds,
        "text_path": row.text_path,
        "line_count": row.line_count,
        "char_count": row.char_count,
        "severity": row.severity,
        "level": row.level,
        "issues": row.issues,
    }


def write_markdown(path: Path, rows: list[ReviewRow], summary: dict):
    lines = ["# 全量文稿 Review 报告", ""]
    lines.append("## 汇总")
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("## 高风险 Top 50")
    for row in rows[:50]:
        if row.level == "clean":
            continue
        lines.append("")
        lines.append(f"### {row.audio_id} | {row.level} | severity {row.severity}")
        lines.append(f"- 文件: `{row.filename}`")
        lines.append(f"- 文稿: `{row.text_path}`")
        lines.append(f"- 行数/字数/时长: {row.line_count} 行 / {row.char_count} 字 / {round(row.duration_seconds, 1)} 秒")
        for issue in row.issues[:6]:
            sample = issue.get("text") or issue.get("sample") or issue.get("term") or issue.get("pattern") or ""
            loc = ""
            if "start" in issue and "end" in issue:
                loc = f" L{issue['start']}-L{issue['end']}"
            elif "line" in issue:
                loc = f" L{issue['line']}"
            elif "lines" in issue:
                loc = f" lines {issue['lines'][:8]}"
            sample_text = str(sample)[:140]
            suffix = f": {sample_text}" if sample_text else ":"
            lines.append(f"- {issue['type']}{loc}{suffix}")

    lines.append("")
    lines.append("## 每份文稿状态")
    lines.append("")
    lines.append("| level | severity | audio_id | source | lines | chars | top issue |")
    lines.append("|---|---:|---|---|---:|---:|---|")
    for row in rows:
        top = row.issues[0]["type"] if row.issues else "无明显问题"
        lines.append(f"| {row.level} | {row.severity} | `{row.audio_id}` | {row.source} | {row.line_count} | {row.char_count} | {top} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[ReviewRow]):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            lineterminator="\n",
            fieldnames=[
                "level",
                "severity",
                "audio_id",
                "source",
                "filename",
                "duration_seconds",
                "line_count",
                "char_count",
                "top_issue",
                "text_path",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "level": row.level,
                    "severity": row.severity,
                    "audio_id": row.audio_id,
                    "source": row.source,
                    "filename": row.filename,
                    "duration_seconds": round(row.duration_seconds, 3),
                    "line_count": row.line_count,
                    "char_count": row.char_count,
                    "top_issue": row.issues[0]["type"] if row.issues else "",
                    "text_path": row.text_path,
                }
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument("--out-dir", default="transcriptions/metadata/full-transcript-review")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    out_dir = (repo / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = repo / "transcriptions" / "metadata" / "audio-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = [review_one(repo, item) for item in manifest["items"]]
    rows.sort(key=lambda row: (row.severity, row.char_count), reverse=True)

    by_level = Counter(row.level for row in rows)
    issue_counts = Counter(issue["type"] for row in rows for issue in row.issues)
    summary = {
        "manifest_items": len(manifest["items"]),
        "reviewed_transcripts": len(rows),
        "high": by_level["high"],
        "medium": by_level["medium"],
        "low": by_level["low"],
        "clean": by_level["clean"],
        "issue_counts": dict(issue_counts.most_common()),
    }

    payload = {
        "summary": summary,
        "items": [row_to_dict(row) for row in rows],
    }

    json_path = out_dir / "full-transcript-review.json"
    md_path = out_dir / "full-transcript-review.md"
    csv_path = out_dir / "full-transcript-review.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, rows, summary)
    write_csv(csv_path, rows)

    print(json.dumps({"summary": summary, "json": str(json_path), "markdown": str(md_path), "csv": str(csv_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
