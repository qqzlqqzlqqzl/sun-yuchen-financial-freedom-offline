#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


PROMPT = (
    "以下是孙宇晨《财富自由革命之路》在喜马拉雅上的中文口播音频。"
    "常见词包括孙宇晨、财富自由、喜马拉雅、创业、投资、区块链、比特币、互联网、波场、TRON。"
)


def run(cmd, log_path=None):
    started = time.time()
    if log_path:
        with open(log_path, "ab") as log:
            log.write(("$ " + " ".join(map(str, cmd)) + "\n").encode("utf-8"))
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    else:
        proc = subprocess.run(cmd)
    return proc.returncode, time.time() - started


def valid_json(path):
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8", "replace"))
        return isinstance(data, dict) and "transcription" in data
    except Exception:
        return False


def write_clean_json(raw_path, clean_path):
    data = json.loads(Path(raw_path).read_bytes().decode("utf-8", "replace"))
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    clean_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def transcribe_one(item, args, root):
    item_id = item["id"]
    src = root / item["path"]
    raw_json = root / "transcriptions" / "raw-json" / f"{item_id}.json"
    clean_json = root / "transcriptions" / "clean-json" / f"{item_id}.json"
    text = root / "transcriptions" / "text" / f"{item_id}.txt"
    srt = root / "transcriptions" / "srt" / f"{item_id}.srt"
    log = root / "transcriptions" / "logs" / f"{item_id}.log"
    tmp_dir = root / "transcriptions" / "tmp" / item_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if raw_json.exists() and text.exists() and valid_json(raw_json):
        if not clean_json.exists():
            write_clean_json(raw_json, clean_json)
        return {"id": item_id, "status": "skipped", "seconds": 0}

    out_base = tmp_dir / "out"
    audio_in = src
    converted = None

    with open(log, "ab") as lf:
        lf.write(("\n=== START " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n").encode("utf-8"))
        lf.write(json.dumps(item, ensure_ascii=False).encode("utf-8") + b"\n")

    if src.suffix.lower() == ".m4a":
        converted = tmp_dir / "audio.wav"
        code, elapsed = run(
            [
                args.ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                str(src),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(converted),
            ],
            log,
        )
        if code != 0:
            return {"id": item_id, "status": "ffmpeg_failed", "seconds": elapsed}
        audio_in = converted

    cmd = [
        args.whisper_cli,
        "-m",
        args.model,
        "-f",
        str(audio_in),
        "-l",
        "zh",
        "-t",
        str(args.threads),
        "-bs",
        str(args.beam_size),
        "-bo",
        str(args.best_of),
        "-oj",
        "-ojf",
        "-otxt",
        "-osrt",
        "-of",
        str(out_base),
        "--prompt",
        PROMPT,
    ]
    code, elapsed = run(cmd, log)
    if code != 0:
        return {"id": item_id, "status": "whisper_failed", "seconds": elapsed}

    produced = {
        tmp_dir / "out.json": raw_json,
        tmp_dir / "out.txt": text,
        tmp_dir / "out.srt": srt,
    }
    for src_path, dst_path in produced.items():
        if not src_path.exists():
            return {"id": item_id, "status": f"missing_{src_path.suffix}", "seconds": elapsed}
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))

    if not valid_json(raw_json):
        return {"id": item_id, "status": "invalid_json", "seconds": elapsed}
    write_clean_json(raw_json, clean_json)

    if converted and args.keep_wav is False:
        try:
            converted.unlink()
        except FileNotFoundError:
            pass

    try:
        tmp_dir.rmdir()
    except OSError:
        pass

    return {"id": item_id, "status": "done", "seconds": elapsed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="transcriptions/metadata/audio-manifest.json")
    parser.add_argument("--model", default="models/whisper-cpp/ggml-large-v3.bin")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--best-of", type=int, default=5)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--whisper-cli", default="whisper-cli")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--keep-wav", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    with open(root / args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    items = manifest["items"]
    if args.limit:
        items = items[: args.limit]

    status_path = root / "transcriptions" / "metadata" / "run-status.jsonl"
    status_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        json.dumps(
            {
                "event": "start",
                "items": len(items),
                "workers": args.workers,
                "threads": args.threads,
                "model": args.model,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    counts = {}
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(transcribe_one, item, args, root) for item in items]
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            counts[result["status"]] = counts.get(result["status"], 0) + 1
            result["completed"] = i
            result["total"] = len(items)
            result["elapsed_total_seconds"] = round(time.time() - started, 2)
            with open(status_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(json.dumps(result, ensure_ascii=False), flush=True)

    print(json.dumps({"event": "finish", "counts": counts}, ensure_ascii=False), flush=True)
    return 0 if not any(k.endswith("failed") or k.startswith("missing") or k == "invalid_json" for k in counts) else 1


if __name__ == "__main__":
    sys.exit(main())
