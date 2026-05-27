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

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
RESOURCE_ID = os.environ.get("VOLC_RESOURCE_ID", "volc.bigasr.auc")
PENDING_STATUSES = {"20000001", "20000002"}


def request_json(url, api_key, request_id, body, sequence=None, timeout=120):
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": request_id,
    }
    if sequence is not None:
        headers["X-Api-Sequence"] = sequence
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
        return {
            "http_status": resp.status,
            "api_status": resp.headers.get("X-Api-Status-Code"),
            "api_message": resp.headers.get("X-Api-Message"),
            "tt_logid": resp.headers.get("X-Tt-Logid"),
            "response": json.loads(payload) if payload else {},
        }


def call_with_retry(fn):
    last = None
    for attempt in range(4):
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            last = {
                "ok": False,
                "http_status": exc.code,
                "api_status": exc.headers.get("X-Api-Status-Code"),
                "api_message": exc.headers.get("X-Api-Message"),
                "tt_logid": exc.headers.get("X-Tt-Logid"),
                "response_text": raw,
            }
        except Exception as exc:
            last = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
        if attempt < 3:
            time.sleep(1.5 * (attempt + 1))
    return last


def recognize(item, api_key, poll_interval, max_wait):
    snippet = PATH_ROOT / item["snippet_path"]
    request_id = str(uuid.uuid4())
    body = {
        "user": {"uid": "codex-repetition-audit"},
        "audio": {
            "format": snippet.suffix.lstrip(".") or "wav",
            "data": base64.b64encode(snippet.read_bytes()).decode("ascii"),
        },
        "request": {
            "model_name": "bigmodel",
            "language": "zh-CN",
            "enable_itn": True,
            "enable_punc": True,
            "show_utterances": True,
        },
    }

    submit = call_with_retry(
        lambda: request_json(SUBMIT_URL, api_key, request_id, body, sequence="-1")
    )
    if submit.get("api_status") != "20000000":
        return {"ok": False, "request_id": request_id, "submit": submit, "queries": []}

    queries = []
    started = time.time()
    while True:
        query = call_with_retry(lambda: request_json(QUERY_URL, api_key, request_id, {}))
        queries.append(query)
        status = query.get("api_status")
        response = query.get("response", {})
        if status == "20000000" and response.get("result"):
            return {
                "ok": True,
                "request_id": request_id,
                "submit": submit,
                "queries": queries,
                "response": response,
            }
        if status not in PENDING_STATUSES:
            return {
                "ok": False,
                "request_id": request_id,
                "submit": submit,
                "queries": queries,
                "response": response,
            }
        if time.time() - started > max_wait:
            return {
                "ok": False,
                "request_id": request_id,
                "submit": submit,
                "queries": queries,
                "timeout": True,
            }
        time.sleep(poll_interval)


def main():
    api_key = os.environ.get("VOLC_API_KEY")
    if not api_key:
        raise SystemExit("VOLC_API_KEY is required")
    workers = int(os.environ.get("VOLC_WORKERS", "6"))
    poll_interval = float(os.environ.get("VOLC_POLL_INTERVAL", "2"))
    max_wait = float(os.environ.get("VOLC_MAX_WAIT", "300"))

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = manifest["items"] if isinstance(manifest, dict) else manifest
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(recognize, item, api_key, poll_interval, max_wait): item
            for item in items
        }
        for done, future in enumerate(concurrent.futures.as_completed(future_map), 1):
            item = future_map[future]
            result = future.result()
            response = result.get("response", {})
            text = response.get("result", {}).get("text", "")
            record = {
                **item,
                "volc_ok": result.get("ok", False),
                "volc_status": (
                    result.get("queries", [{}])[-1].get("api_status")
                    if result.get("queries")
                    else result.get("submit", {}).get("api_status")
                ),
                "volc_message": (
                    result.get("queries", [{}])[-1].get("api_message")
                    if result.get("queries")
                    else result.get("submit", {}).get("api_message")
                ),
                "volc_logid": (
                    result.get("queries", [{}])[-1].get("tt_logid")
                    if result.get("queries")
                    else result.get("submit", {}).get("tt_logid")
                ),
                "volc_text": text,
                "request_id": result.get("request_id"),
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
        "note": "Volcengine standard ASR audit for suspicious repeated transcript snippets. API key is not stored.",
        "source_manifest": str(MANIFEST.relative_to(AUDIT_ROOT)),
        "resource_id": RESOURCE_ID,
        "api_kind": "standard_submit_query",
        "count": len(results),
        "ok_count": sum(1 for r in results if r["volc_ok"]),
        "elapsed_seconds": round(time.time() - started, 3),
        "items": results,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["count", "ok_count", "elapsed_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
