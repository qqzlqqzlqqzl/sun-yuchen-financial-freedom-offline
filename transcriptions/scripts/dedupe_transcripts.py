#!/usr/bin/env python3
"""Clean duplicated segments in offline transcript text outputs.

The goal is to stabilize known failure modes from ASR segmentation:
1) Repeated lines copied multiple times.
2) Immediate repeated phrase chunks in a single line.

This keeps raw JSON unchanged and only updates .txt (and optionally .srt) files
in-place. A JSON report is printed and can be written to disk with --report.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


SRT_TIMING_RE = re.compile(r"^(\d+:\d+:\d+,\d+|\d+:\d+:\d+\.\d{3}) -->")
NOISE_LINES = {
    "优优独播剧场——YoYo Television Series Exclusive",
    "请不吝点赞 转发 打赏支持明镜与点点栏目",
    "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
}


@dataclass
class FileStats:
    path: str
    original_chars: int
    output_chars: int
    line_dedup_count: int
    inline_dedup_count: int
    noise_removed_count: int


def collapse_sentence_repeats(text: str) -> tuple[str, int]:
    """Remove consecutive duplicate sentence-like chunks separated by punctuation."""

    # Preserve delimiters and strip duplicated adjacent chunks.
    chunks = re.split(r"([。！？!?；;，,\n])", text)
    if len(chunks) <= 1:
        return text, 0

    out: list[str] = []
    removed = 0
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        delim = chunks[i + 1] if i + 1 < len(chunks) else ""

        # Compare with previous if both chunks are plain content (skip newline-like separators)
        if not chunk.strip():
            out.append(chunk)
            if delim:
                out.append(delim)
            i += 2
            continue

        if out:
            # Reconstruct previous content chunk for comparison
            prev = out[-2] if len(out) >= 2 else ""
            if chunk == prev and len(chunk) >= 14:
                removed += 1
                # Skip duplicated chunk only; keep one copy + delimiter.
                if delim:
                    out.append(delim)
                i += 2
                continue

        out.append(chunk)
        if delim:
            out.append(delim)
        i += 2

    return "".join(out), removed


def collapse_repeated_chunks(text: str, *, min_len: int = 12, max_len: int = 120) -> tuple[str, int]:
    """Collapse immediate repeated char chunks.

    Example: "abcabcabc" -> "abc". The repeat length is inferred greedily.
    """

    if len(text) < 2 * min_len:
        return text, 0

    result: list[str] = []
    i = 0
    n = len(text)
    removed = 0

    while i < n:
        matched = False
        # Longest chunk first keeps longer phrase boundaries first.
        upper = min(max_len, n - i - 1)
        for ln in range(upper, min_len - 1, -1):
            first = text[i : i + ln]
            second = text[i + ln : i + 2 * ln]
            if first != second:
                continue

            end = i + 2 * ln
            while end + ln <= n and text[end : end + ln] == first:
                end += ln

            result.append(first)
            removed += 1
            i = end
            matched = True
            break

        if not matched:
            result.append(text[i])
            i += 1

    return "".join(result), removed


def clean_text(text: str) -> tuple[str, int, int, int]:
    """Return (clean_text, line_dedup, inline_dedup, noise_removed)."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned_lines: list[str] = []
    line_dedup = 0
    prev = None

    for line in lines:
        if line in NOISE_LINES:
            # Noise footer / unrelated watermark.
            line = ""
        if not line:
            continue
        if prev is not None and line == prev:
            line_dedup += 1
            continue
        cleaned_lines.append(line)
        prev = line

    # Re-join so sentence-level duplicate reduction can inspect punctuation context.
    joined = "\n".join(cleaned_lines)
    joined, sentence_repeats = collapse_sentence_repeats(joined)
    collapsed, inline_removed = collapse_repeated_chunks(joined)

    noise_removed = len(lines) - len(cleaned_lines)
    return collapsed.strip(), line_dedup + sentence_repeats, inline_removed, noise_removed


def clean_single_line(line: str) -> str:
    """Lightweight cleanup for one subtitle line."""
    line = line.strip()
    if not line or line in NOISE_LINES:
        return ""
    cleaned, _, _ = clean_text(line)
    return cleaned


def process_files(base: Path, *, apply: bool, report_path: Path | None = None, include_srt: bool = False):
    manifest = base / "metadata" / "audio-manifest.json"
    if not manifest.exists():
        raise SystemExit(f"audio manifest not found: {manifest}")

    text_root = base / "text"
    if not text_root.exists():
        raise SystemExit(f"text root not found: {text_root}")

    srt_root = base / "srt" if include_srt else None

    changed: list[FileStats] = []
    unchanged = 0
    total = 0

    for path in sorted(text_root.glob("*.txt")):
        total += 1
        original = path.read_text(encoding="utf-8", errors="replace")
        cleaned, line_dedup, inline_dedup, noise_removed = clean_text(original)
        if cleaned != original:
            changed.append(
                FileStats(
                    path=str(path.relative_to(base)),
                    original_chars=len(original),
                    output_chars=len(cleaned),
                    line_dedup_count=line_dedup,
                    inline_dedup_count=inline_dedup,
                    noise_removed_count=noise_removed,
                )
            )
            if apply:
                path.write_text(cleaned + "\n", encoding="utf-8")
        else:
            unchanged += 1

        if include_srt and srt_root:
            # Mirror line-level duplicate cleanup for subtitles as a soft pass.
            srt_path = srt_root / (path.stem + ".srt")
            if srt_path.exists():
                srt_original = srt_path.read_text(encoding="utf-8", errors="replace")
                # For subtitle files we only collapse repeated blocks in text lines,
                # keeping timing metadata stable by preserving each line.
                srt_lines = srt_original.splitlines()
                for i, srt_line in enumerate(srt_lines):
                    if SRT_TIMING_RE.match(srt_line):
                        continue
                    if i in (0,):
                        continue
                    fixed = clean_single_line(srt_line)
                    if fixed and fixed != srt_line:
                        srt_lines[i] = fixed
                    elif not fixed:
                        srt_lines[i] = ""
                srt_clean = "\n".join(srt_lines).rstrip() + "\n"
                if srt_clean != srt_original and apply:
                    srt_path.write_text(srt_clean, encoding="utf-8")

    payload = {
        "base": str(base),
        "mode": "apply" if apply else "dry-run",
        "files_changed": len(changed),
        "files_unchanged": unchanged,
        "total_files": total,
        "changed_files": [
            {
                "path": item.path,
                "original_chars": item.original_chars,
                "output_chars": item.output_chars,
                "delta_chars": item.original_chars - item.output_chars,
                "line_dedup_removed": item.line_dedup_count,
                "inline_dedup_removed": item.inline_dedup_count,
                "noise_removed_lines": item.noise_removed_count,
            }
            for item in changed
        ],
    }

    if report_path:
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=".", help="Base directory containing transcriptions/, defaults to current directory")
    p.add_argument("--apply", action="store_true", help="Write cleaned text back to disk")
    p.add_argument("--report", default="", help="Optional json report path")
    p.add_argument("--srt", action="store_true", help="Also clean subtitle files in srt/ (best-effort)")
    return p.parse_args()


def main():
    args = parse_args()
    base = Path(args.base).resolve()
    report_path = Path(args.report) if args.report else None
    if report_path:
        report_path = report_path.expanduser().resolve()
    process_files(base, apply=args.apply, report_path=report_path, include_srt=args.srt)


if __name__ == "__main__":
    main()
