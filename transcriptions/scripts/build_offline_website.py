#!/usr/bin/env python3
"""Rebuild the embedded episode dataset in sun-audio-offline-website.html.

The website includes an inline `episodes` array. This script regenerates that
array from the transcriptions manifest + per-file transcript text and writes it
back to the HTML.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def to_timecode(seconds: float) -> str:
    total = int(max(0.0, seconds))
    mins = total // 60
    secs = total % 60
    return f"{mins}:{secs:02d}"


def extract_episode_name(filename: str) -> str:
    # Keep Chinese/English title + topic text, remove leading episode number blocks.
    title = filename.rsplit(".", 1)[0]
    title = re.sub(r"^\d+\s*-\s*\d+\s*", "", title)
    title = re.sub(r"^\d+\s*", "", title)
    title = title.strip(" -")
    return title


def extract_episode_id(filename: str) -> str:
    m = re.match(r"^(\d{3})", filename)
    return m.group(1) if m else filename[:3]


def make_dataset(repo_root: Path):
    manifest = repo_root / "transcriptions" / "metadata" / "audio-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    items = data["items"]

    # Prefer official source when duplicate episodes exist.
    by_episode = {}
    for item in items:
        ep = extract_episode_id(item["filename"])
        existing = by_episode.get(ep)
        if existing is None:
            by_episode[ep] = item
            continue
        if existing["source"] != "official-vimeo-m4a-partial" and item["source"] == "official-vimeo-m4a-partial":
            by_episode[ep] = item

    text_root = repo_root / "transcriptions" / "text"
    episodes = []
    for ep, item in sorted(by_episode.items(), key=lambda kv: kv[0]):
        text_path = text_root / f"{item['id']}.txt"
        transcript = text_path.read_text(encoding="utf-8", errors="replace").strip()
        source = item["source"]
        folder = "wavlake-mp3" if source == "wavlake-mp3" else "official-vimeo-m4a-partial" if source == "official-vimeo-m4a-partial" else source
        audio = f"{folder}/{item['filename']}"

        episodes.append(
            {
                "episode": ep,
                "id": item["id"],
                "title": extract_episode_name(item["filename"]),
                "source": source,
                "duration": to_timecode(float(item.get("duration_seconds", 0.0))),
                "duration_seconds": float(item.get("duration_seconds", 0.0)),
                "audio": audio,
                "transcript": transcript,
                "transcriptLen": len(transcript),
            }
        )

    episodes_sorted = sorted(episodes, key=lambda e: (int(e["episode"]), 0 if e["source"] == "official-vimeo-m4a-partial" else 1, e["id"]))
    return episodes_sorted


def replace_episodes_block(html: str, episodes) -> str:
    payload = json.dumps(episodes, ensure_ascii=False, indent=2)
    payload = "    const episodes = " + payload + ";"

    # Match the full const episodes block only.
    pattern = re.compile(r"\s*const episodes = \[.*?\n\s*\];", re.S)
    if not pattern.search(html):
        raise RuntimeError("Unable to find `const episodes = [...]` block in html")
    replacement = lambda _match: "\n" + payload
    return pattern.sub(replacement, html)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default=".", help="Repository root containing github-upload and transcriptions directories")
    p.add_argument("--website", default="github-upload/sun-audio-offline-website.html", help="HTML file path to update")
    p.add_argument("--report", default="github-upload/transcriptions/metadata/website-rebuild.json", help="Optional report output")
    args = p.parse_args()

    repo = Path(args.repo).resolve()
    episodes = make_dataset(repo)
    website = repo / args.website
    html = website.read_text(encoding="utf-8")
    updated = replace_episodes_block(html, episodes)
    website.write_text(updated, encoding="utf-8")

    report = {
        "website": str(website),
        "episodes": len(episodes),
        "sources": {
            "official-vimeo-m4a-partial": sum(1 for e in episodes if e["source"] == "official-vimeo-m4a-partial"),
            "wavlake-mp3": sum(1 for e in episodes if e["source"] == "wavlake-mp3"),
        },
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
