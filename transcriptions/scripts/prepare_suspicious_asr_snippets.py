#!/usr/bin/env python3
"""Cut only suspicious transcript segments for second-pass cloud ASR."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ISSUE_TYPES = {
    "连续重复",
    "近似重复",
    "全文重复",
    "行内循环",
    "疑似错词",
    "超长行",
}


def load_episodes(html_path: Path) -> list[dict]:
    html = html_path.read_text(encoding="utf-8")
    match = re.search(r"const episodes = (\[.*?\n\s*\]);", html, re.S)
    if not match:
        raise RuntimeError("Unable to find embedded episodes in website")
    return json.loads(match.group(1))


def parse_issue_lines(issue: dict) -> list[int]:
    if "line" in issue:
        return [int(issue["line"])]
    if "start" in issue and "end" in issue:
        return list(range(int(issue["start"]), int(issue["end"]) + 1))
    if "lines" in issue:
        return [int(line) for line in issue["lines"]]
    return []


def segment_bounds(repo: Path, audio_id: str, lines: list[int], context_seconds: float) -> tuple[float, float] | None:
    clean_path = repo / "transcriptions" / "clean-json" / f"{audio_id}.json"
    if not clean_path.exists():
        return None
    data = json.loads(clean_path.read_text(encoding="utf-8", errors="replace"))
    segments = data.get("transcription") or []
    indexes = [line - 1 for line in lines if 1 <= line <= len(segments)]
    if not indexes:
        return None
    start = min(float(segments[index].get("offsets", {}).get("from", 0)) for index in indexes) / 1000.0
    end = max(float(segments[index].get("offsets", {}).get("to", 0)) for index in indexes) / 1000.0
    return max(0.0, start - context_seconds), max(start + 0.5, end + context_seconds)


def merge_windows(windows: list[dict], gap_seconds: float, max_seconds: float) -> list[dict]:
    merged: list[dict] = []
    for window in sorted(windows, key=lambda row: (row["start_seconds"], row["end_seconds"])):
        if not merged:
            merged.append(window)
            continue
        last = merged[-1]
        combined_duration = max(last["end_seconds"], window["end_seconds"]) - min(last["start_seconds"], window["start_seconds"])
        if window["start_seconds"] <= last["end_seconds"] + gap_seconds and combined_duration <= max_seconds:
            last["end_seconds"] = max(last["end_seconds"], window["end_seconds"])
            last["issue_types"] = sorted(set(last["issue_types"]) | set(window["issue_types"]))
            last["line_refs"].extend(window["line_refs"])
            last["samples"].extend(window["samples"])
        else:
            merged.append(window)
    return merged


def make_snippet(repo: Path, item: dict) -> None:
    audio_path = repo / item["audio_path"]
    output_path = repo / item["snippet_path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 0:
        return
    duration = max(0.2, item["end_seconds"] - item["start_seconds"])
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{item['start_seconds']:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-codec:a",
        "pcm_s16le",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--out-dir", default="transcriptions/metadata/suspicious-snippet-asr")
    parser.add_argument("--context-seconds", type=float, default=2.0)
    parser.add_argument("--merge-gap-seconds", type=float, default=6.0)
    parser.add_argument("--max-snippet-seconds", type=float, default=75.0)
    parser.add_argument("--max-issues-per-audio", type=int, default=8)
    parser.add_argument("--min-level", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    out_dir = repo / args.out_dir
    snippets_dir = out_dir / "snippets"
    levels = {"clean": 0, "low": 1, "medium": 2, "high": 3}
    min_level = levels[args.min_level]

    review_path = repo / "transcriptions" / "metadata" / "full-transcript-review" / "full-transcript-review.json"
    review = {item["audio_id"]: item for item in json.loads(review_path.read_text(encoding="utf-8"))["items"]}
    episodes = load_episodes(repo / "sun-audio-offline-website.html")

    manifest_items = []
    next_index = 1
    for episode in episodes:
        row = review.get(episode["id"])
        if not row or levels.get(row.get("level", "clean"), 0) < min_level:
            continue

        windows = []
        selected_count = 0
        for issue in row.get("issues", []):
            if issue.get("type") not in ISSUE_TYPES:
                continue
            lines = parse_issue_lines(issue)
            if not lines:
                continue
            bounds = segment_bounds(repo, episode["id"], lines, args.context_seconds)
            if not bounds:
                continue
            start, end = bounds
            windows.append(
                {
                    "start_seconds": start,
                    "end_seconds": end,
                    "issue_types": [issue["type"]],
                    "line_refs": lines[:12],
                    "samples": [str(issue.get("text") or issue.get("sample") or issue.get("term") or "")[:180]],
                }
            )
            selected_count += 1
            if selected_count >= args.max_issues_per_audio:
                break

        for snippet_index, window in enumerate(merge_windows(windows, args.merge_gap_seconds, args.max_snippet_seconds)):
            safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", episode["id"])
            snippet_name = f"{episode['episode']}__{safe_id}__{snippet_index:02d}.wav"
            manifest_items.append(
                {
                    "index": next_index,
                    "audio_id": episode["id"],
                    "episode": episode["episode"],
                    "title": episode["title"],
                    "source": episode["source"],
                    "audio_path": episode["audio"],
                    "snippet_path": str((snippets_dir / snippet_name).relative_to(repo)),
                    "snippet_index": snippet_index,
                    "start_seconds": round(window["start_seconds"], 3),
                    "end_seconds": round(window["end_seconds"], 3),
                    "chunk_index": snippet_index,
                    "issue_types": window["issue_types"],
                    "line_refs": sorted(set(window["line_refs"])),
                    "samples": [sample for sample in window["samples"] if sample][:5],
                    "local_review_level": row["level"],
                    "local_review_severity": row["severity"],
                }
            )
            next_index += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(make_snippet, repo, item) for item in manifest_items]
        for done, future in enumerate(as_completed(futures), 1):
            future.result()
            if done % 20 == 0 or done == len(futures):
                print(f"cut {done}/{len(futures)}")

    manifest = {
        "note": "Only suspicious transcript windows are uploaded for second-pass ASR.",
        "context_seconds": args.context_seconds,
        "min_level": args.min_level,
        "snippet_count": len(manifest_items),
        "audio_count": len({item["audio_id"] for item in manifest_items}),
        "items": manifest_items,
    }
    manifest_path = out_dir / "snippets-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"audio_count": manifest["audio_count"], "snippets": len(manifest_items), "manifest": str(manifest_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
