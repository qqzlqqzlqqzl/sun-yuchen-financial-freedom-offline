#!/usr/bin/env python3
"""Chunked rerun for high-risk final website transcripts.

This avoids long-context Whisper hallucinations by transcribing fixed-size
chunks independently. Original raw-json files stay untouched; chunk raw returns
are preserved under metadata/asr-rerun-high-risk-chunked/raw-json.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shutil
import subprocess
import time
from pathlib import Path


BOILERPLATE_PATTERNS = (
    "请不吝点赞",
    "明镜与点点栏目",
    "优优独播剧场",
    "YoYo Television Series Exclusive",
)


def load_episodes(html_path: Path) -> list[dict]:
    html = html_path.read_text(encoding="utf-8")
    match = re.search(r"const episodes = (\[.*?\n\s*\]);", html, re.S)
    if not match:
        raise RuntimeError("Unable to find embedded episodes")
    return json.loads(match.group(1))


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def normalize(text: str) -> str:
    return re.sub(r"[\s,，。.!！?？、;；:：\"“”'‘’\[\]【】()（）\-—_]+", "", text.strip())


def boilerplate_score(text: str) -> int:
    return sum(text.count(pattern) for pattern in BOILERPLATE_PATTERNS)


def repeated_line_score(text: str) -> int:
    score = 0
    previous = ""
    run = 0
    for line in [line.strip() for line in text.splitlines() if line.strip()]:
        current = normalize(line)
        if current and current == previous:
            run += 1
        else:
            score += run
            run = 0
        previous = current
    return score + run


def clean_chunk_text(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(pattern in line for pattern in BOILERPLATE_PATTERNS):
            continue
        if lines and normalize(lines[-1]) == normalize(line):
            continue
        lines.append(line)
    return lines


def should_accept(old_text: str, new_text: str) -> tuple[bool, str]:
    old_chars = len(compact(old_text))
    new_chars = len(compact(new_text))
    old_boiler = boilerplate_score(old_text)
    new_boiler = boilerplate_score(new_text)
    old_repeat = repeated_line_score(old_text)
    new_repeat = repeated_line_score(new_text)

    if new_chars < 80:
        return False, f"new text too short: {new_chars}"
    if old_boiler >= 5 and new_boiler == 0 and new_chars >= 300:
        return True, "chunked rerun removed boilerplate hallucination"
    if old_repeat >= 10 and new_repeat <= max(2, old_repeat // 8) and new_chars >= old_chars * 0.55:
        return True, "chunked rerun reduced repeated lines"
    if old_chars < 1000 and new_chars >= old_chars * 2 and new_boiler == 0:
        return True, "chunked rerun recovered substantially more content"
    return False, f"not clearly better: chars {old_chars}->{new_chars}, boiler {old_boiler}->{new_boiler}, repeat {old_repeat}->{new_repeat}"


def run(cmd: list[str], log_path: Path) -> None:
    with log_path.open("ab") as handle:
        handle.write(("$ " + " ".join(cmd) + "\n").encode("utf-8"))
        subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT, check=True)


def timestamp(ms: int) -> str:
    ms = max(0, ms)
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    seconds = ms // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def detect_silence_points(repo: Path, episode: dict, args: argparse.Namespace) -> list[float]:
    cmd = [
        args.ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-i",
        str(repo / episode["audio"]),
        "-af",
        f"silencedetect=noise={args.silence_noise}:d={args.silence_min_duration}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    text = proc.stderr + "\n" + proc.stdout
    starts: list[float] = []
    points: list[float] = []
    for line in text.splitlines():
        start_match = re.search(r"silence_start: ([0-9.]+)", line)
        if start_match:
            starts.append(float(start_match.group(1)))
            continue
        end_match = re.search(r"silence_end: ([0-9.]+)", line)
        if end_match and starts:
            end = float(end_match.group(1))
            start = starts.pop(0)
            points.append((start + end) / 2.0)
    return sorted(point for point in points if point > 0)


def chunk_windows(repo: Path, episode: dict, args: argparse.Namespace) -> list[tuple[float, float]]:
    duration = float(episode.get("duration_seconds") or 0)
    if duration <= 0:
        return [(0.0, args.target_chunk_seconds)]

    silence_points = detect_silence_points(repo, episode, args)
    windows: list[tuple[float, float]] = []
    start = 0.0
    while start < duration - 0.1:
        remaining = duration - start
        if remaining <= args.max_chunk_seconds:
            window_start = max(0.0, start - args.silence_pad_seconds)
            windows.append((window_start, duration - window_start))
            break

        target = start + args.target_chunk_seconds
        lower = start + args.min_chunk_seconds
        upper = min(duration, start + args.max_chunk_seconds)
        candidates = [point for point in silence_points if lower <= point <= upper]
        cut = min(candidates, key=lambda point: abs(point - target)) if candidates else min(upper, target)
        cut = max(start + 5.0, min(cut, duration))
        window_start = max(0.0, start - args.silence_pad_seconds)
        windows.append((window_start, cut - window_start + args.silence_pad_seconds))
        start = cut

    return windows


def transcribe_chunk(repo: Path, episode: dict, chunk_index: int, start: float, duration: float, args: argparse.Namespace) -> dict:
    item_id = episode["id"]
    out_root = repo / args.out_dir
    chunk_dir = out_root / "tmp" / item_id / f"chunk-{chunk_index:03d}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_root / "logs" / f"{item_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    wav_path = chunk_dir / "audio.wav"
    out_base = chunk_dir / "out"

    run(
        [
            args.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(repo / episode["audio"]),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-codec:a",
            "pcm_s16le",
            str(wav_path),
        ],
        log_path,
    )
    run(
        [
            args.whisper_cli,
            "-m",
            args.model,
            "-f",
            str(wav_path),
            "-l",
            "zh",
            "-t",
            str(args.threads),
            "-bs",
            str(args.beam_size),
            "-bo",
            str(args.best_of),
            "-mc",
            "0",
            "-oj",
            "-ojf",
            "-otxt",
            "-of",
            str(out_base),
            "-sns",
            "-nf",
            "-np",
        ],
        log_path,
    )

    raw = json.loads((chunk_dir / "out.json").read_bytes().decode("utf-8", "replace"))
    raw_store = out_root / "raw-json" / item_id
    raw_store.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chunk_dir / "out.json", raw_store / f"chunk-{chunk_index:03d}.json")
    text = (chunk_dir / "out.txt").read_text(encoding="utf-8", errors="replace")
    return {"chunk_index": chunk_index, "start": start, "duration": duration, "text": text, "raw": raw}


def rerun_episode(repo: Path, episode: dict, review: dict, args: argparse.Namespace) -> dict:
    started = time.time()
    windows = chunk_windows(repo, episode, args)
    chunks: list[dict] = []
    for index, (start, duration) in enumerate(windows):
        chunks.append(transcribe_chunk(repo, episode, index, start, duration, args))

    lines: list[str] = []
    merged_segments: list[dict] = []
    for chunk in chunks:
        start_ms = int(round(chunk["start"] * 1000))
        for line in clean_chunk_text(chunk["text"]):
            if lines and normalize(lines[-1]) == normalize(line):
                continue
            lines.append(line)
        for segment in chunk["raw"].get("transcription", []):
            text = str(segment.get("text") or "").strip()
            if not text or any(pattern in text for pattern in BOILERPLATE_PATTERNS):
                continue
            offsets = segment.get("offsets", {})
            seg_from = start_ms + int(offsets.get("from", 0))
            seg_to = start_ms + int(offsets.get("to", 0))
            merged = {key: value for key, value in segment.items() if key != "tokens"}
            merged["offsets"] = {"from": seg_from, "to": seg_to}
            merged["timestamps"] = {"from": timestamp(seg_from), "to": timestamp(seg_to)}
            merged_segments.append(merged)

    new_text = "\n".join(lines).strip()
    text_path = repo / "transcriptions" / "text" / f"{episode['id']}.txt"
    old_text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
    accepted, reason = should_accept(old_text, new_text)

    if accepted:
        text_path.write_text(new_text + "\n", encoding="utf-8")
        clean_payload = {
            "systeminfo": {"source": "chunked high-risk rerun"},
            "model": {"path": args.model},
            "params": {
                "target_chunk_seconds": args.target_chunk_seconds,
                "min_chunk_seconds": args.min_chunk_seconds,
                "max_chunk_seconds": args.max_chunk_seconds,
                "silence_noise": args.silence_noise,
                "silence_min_duration": args.silence_min_duration,
                "silence_pad_seconds": args.silence_pad_seconds,
                "threads": args.threads,
                "beam_size": args.beam_size,
                "best_of": args.best_of,
                "max_context": 0,
                "suppress_non_speech_tokens": True,
                "no_fallback": True,
            },
            "result": {"language": "zh"},
            "transcription": merged_segments,
        }
        (repo / "transcriptions" / "clean-json" / f"{episode['id']}.json").write_text(
            json.dumps(clean_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "id": episode["id"],
        "episode": episode["episode"],
        "title": episode["title"],
        "source": episode["source"],
        "review_severity": review.get("severity"),
        "status": "accepted" if accepted else "rejected",
        "reason": reason,
        "chunks": len(windows),
        "old_chars": len(compact(old_text)),
        "new_chars": len(compact(new_text)),
        "old_boilerplate": boilerplate_score(old_text),
        "new_boilerplate": boilerplate_score(new_text),
        "old_repeated_lines": repeated_line_score(old_text),
        "new_repeated_lines": repeated_line_score(new_text),
        "seconds": round(time.time() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--website", default="sun-audio-offline-website.html")
    parser.add_argument("--review", default="transcriptions/metadata/full-transcript-review/full-transcript-review.json")
    parser.add_argument("--out-dir", default="transcriptions/metadata/asr-rerun-high-risk-chunked")
    parser.add_argument("--model", default="/Users/aria-score-00/Documents/Codex/2026-05-25/new-chat-3/models/whisper-cpp/ggml-large-v3.bin")
    parser.add_argument("--whisper-cli", default="whisper-cli")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--threads", type=int, default=3)
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--best-of", type=int, default=5)
    parser.add_argument("--min-severity", type=int, default=80)
    parser.add_argument("--only-episode", default="", help="Optional comma-separated episode ids for testing/rerun")
    parser.add_argument("--target-chunk-seconds", type=float, default=75.0)
    parser.add_argument("--min-chunk-seconds", type=float, default=35.0)
    parser.add_argument("--max-chunk-seconds", type=float, default=110.0)
    parser.add_argument("--silence-noise", default="-35dB")
    parser.add_argument("--silence-min-duration", type=float, default=0.45)
    parser.add_argument("--silence-pad-seconds", type=float, default=0.25)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    episodes = load_episodes(repo / args.website)
    review_items = json.loads((repo / args.review).read_text(encoding="utf-8"))["items"]
    review_by_id = {item["audio_id"]: item for item in review_items}
    only = {item.strip() for item in args.only_episode.split(",") if item.strip()}
    targets = [
        episode
        for episode in episodes
        if int(review_by_id.get(episode["id"], {}).get("severity", 0)) >= args.min_severity
        and (not only or episode["episode"] in only)
    ]

    out_root = repo / args.out_dir
    out_root.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(rerun_episode, repo, episode, review_by_id.get(episode["id"], {}), args): episode
            for episode in targets
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            results.append(result)
            print(json.dumps({"done": index, "total": len(targets), **result}, ensure_ascii=False), flush=True)

    results.sort(key=lambda row: row["episode"])
    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": "Chunked safer Whisper rerun for high-risk final website transcripts; original raw-json unchanged.",
        "targets": len(targets),
        "accepted": sum(1 for row in results if row["status"] == "accepted"),
        "rejected": sum(1 for row in results if row["status"] == "rejected"),
        "failed": sum(1 for row in results if row["status"] == "failed"),
        "elapsed_seconds": round(time.time() - started, 3),
        "items": results,
    }
    (out_root / "rerun-results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ["targets", "accepted", "rejected", "failed", "elapsed_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
