#!/usr/bin/env python3
import base64
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATH_ROOT = Path(os.environ.get("VOLC_PATH_ROOT", ROOT)).resolve()
AUDIT_ROOT = ROOT / os.environ.get("VOLC_AUDIT_DIR", "review-audio-snippets/glossary-audit")
MANIFEST = AUDIT_ROOT / "snippets-manifest.json"
RAW_DIR = AUDIT_ROOT / "volc-raw-json"
SUMMARY = AUDIT_ROOT / "volc-audit-results.json"

API_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
RESOURCE_ID = "volc.bigasr.auc_turbo"


def recognize(item, api_key):
    snippet = PATH_ROOT / item["snippet_path"]
    request_id = str(uuid.uuid4())
    body = {
        "user": {"uid": "codex-glossary-audit"},
        "audio": {"data": base64.b64encode(snippet.read_bytes()).decode("ascii")},
        "request": {
            "model_name": "bigmodel",
            "language": "zh-CN",
            "enable_itn": True,
            "enable_punc": True,
            "show_utterances": True,
        },
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
        },
        method="POST",
    )

    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                headers = dict(resp.headers)
                payload = resp.read().decode("utf-8", errors="replace")
                data = json.loads(payload) if payload else {}
                return {
                    "ok": headers.get("X-Api-Status-Code") == "20000000",
                    "http_status": resp.status,
                    "api_status": headers.get("X-Api-Status-Code"),
                    "api_message": headers.get("X-Api-Message"),
                    "tt_logid": headers.get("X-Tt-Logid"),
                    "request_id": request_id,
                    "response": data,
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            result = {
                "ok": False,
                "http_status": exc.code,
                "api_status": exc.headers.get("X-Api-Status-Code"),
                "api_message": exc.headers.get("X-Api-Message"),
                "tt_logid": exc.headers.get("X-Tt-Logid"),
                "request_id": request_id,
                "response_text": raw,
            }
        except Exception as exc:
            result = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "request_id": request_id,
            }
        if attempt < 3:
            time.sleep(1.5 * (attempt + 1))
    return result


def main():
    api_key = os.environ.get("VOLC_API_KEY")
    if not api_key:
        raise SystemExit("VOLC_API_KEY is required")
    workers = int(os.environ.get("VOLC_WORKERS", "8"))

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = manifest["items"]
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(recognize, item, api_key): item for item in items}
        for done, future in enumerate(concurrent.futures.as_completed(future_map), 1):
            item = future_map[future]
            result = future.result()
            text = result.get("response", {}).get("result", {}).get("text", "")
            record = {
                **item,
                "volc_ok": result.get("ok", False),
                "volc_status": result.get("api_status"),
                "volc_message": result.get("api_message"),
                "volc_logid": result.get("tt_logid"),
                "volc_text": text,
                "raw_json_path": str((RAW_DIR / f"{item['index']:04d}.json").relative_to(AUDIT_ROOT)),
            }
            (RAW_DIR / f"{item['index']:04d}.json").write_text(
                json.dumps({"item": item, "volc_result": result}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            results.append(record)
            print(f"{done}/{len(items)} #{item['index']:04d} ok={record['volc_ok']} text={text[:80]}")

    results.sort(key=lambda x: x["index"])
    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": "Volcengine flash ASR audit for glossary correction candidates. API key is not stored.",
        "source_manifest": str(MANIFEST.relative_to(AUDIT_ROOT)),
        "resource_id": RESOURCE_ID,
        "count": len(results),
        "ok_count": sum(1 for r in results if r["volc_ok"]),
        "elapsed_seconds": round(time.time() - started, 3),
        "items": results,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["count", "ok_count", "elapsed_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
