#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REPLACEMENTS = [
    ("孙宇辰", "孙宇晨", "Justin Sun name typo"),
    ("孙雨晨", "孙宇晨", "Justin Sun name typo"),
    ("孙玉晨", "孙宇晨", "Justin Sun name typo"),
    ("孙益晨", "孙宇晨", "Justin Sun name typo"),
    ("孙远晨", "孙宇晨", "Justin Sun name typo"),
    ("孙宇权", "孙宇晨", "Justin Sun name typo"),
    ("孙宇诚", "孙宇晨", "Justin Sun name typo"),
    ("孙宇春", "孙宇晨", "Justin Sun name typo"),
    ("孙逸臣", "孙宇晨", "Justin Sun name typo"),
    ("宇辰", "宇晨", "Justin Sun given-name typo"),
    ("财务自由", "财富自由", "course term normalization"),
    ("吴小波", "吴晓波", "person name typo"),
    ("波长链", "波场链", "blockchain term typo"),
    ("矛头孙宇晨", "孙宇晨", "phrase cleanup after name correction"),
    ("矛头苦干的孙宇晨", "埋头苦干的孙宇晨", "phrase cleanup after name correction"),
    ("伊隆马斯作为", "伊隆马斯克作为", "Elon Musk name typo"),
    ("company interest", "compound interest", "compound interest quote typo"),
    ("heat and the soul", "heart and soul", "compound interest quote typo"),
    ("扎克伯和", "扎克伯格和", "Zuckerberg name typo"),
]


def apply_replacements(text):
    counts = []
    for old, new, reason in REPLACEMENTS:
        n = text.count(old)
        if n:
            text = text.replace(old, new)
            counts.append({"from": old, "to": new, "count": n, "reason": reason})
    return text, counts


def merge_counts(total, file_path, counts):
    for item in counts:
        key = (item["from"], item["to"], item["reason"])
        entry = total.setdefault(
            key,
            {"from": item["from"], "to": item["to"], "reason": item["reason"], "count": 0, "files": []},
        )
        entry["count"] += item["count"]
        entry["files"].append({"path": str(file_path.relative_to(ROOT)), "count": item["count"]})


def update_text_like(subdir, suffix, total):
    for path in sorted((ROOT / subdir).glob(f"*{suffix}")):
        original = path.read_text(encoding="utf-8", errors="replace")
        fixed, counts = apply_replacements(original)
        if fixed != original:
            path.write_text(fixed, encoding="utf-8")
            merge_counts(total, path, counts)


def update_clean_json(total):
    for path in sorted((ROOT / "clean-json").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        local_counts = []
        for segment in data.get("transcription", []):
            if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
                continue
            fixed, counts = apply_replacements(segment["text"])
            if fixed != segment["text"]:
                segment["text"] = fixed
                changed = True
                local_counts.extend(counts)
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            merge_counts(total, path, local_counts)


def main():
    total = {}
    update_text_like("text", ".txt", total)
    update_text_like("srt", ".srt", total)
    update_clean_json(total)

    report = {
        "note": "Applied only high-confidence glossary/proper-noun corrections. raw-json is preserved unchanged.",
        "corrected_file_groups": ["text", "srt", "clean-json"],
        "raw_json_preserved": True,
        "replacements": sorted(total.values(), key=lambda x: (x["from"], x["to"])),
    }
    out = ROOT / "metadata" / "glossary-corrections.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
