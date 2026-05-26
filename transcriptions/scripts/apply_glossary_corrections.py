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
    ("孙云辰", "孙宇晨", "Justin Sun name typo, confirmed by Volcengine ASR audit"),
    ("孙允辰", "孙宇晨", "Justin Sun name typo, confirmed by Volcengine ASR audit"),
    ("孙云诚", "孙宇晨", "Justin Sun name typo, confirmed by Volcengine ASR audit"),
    ("孙允诚", "孙宇晨", "Justin Sun name typo, confirmed by Volcengine ASR audit"),
    ("孙俊成", "孙宇晨", "Justin Sun name typo, confirmed by Volcengine ASR audit"),
    ("孙云群", "孙宇晨", "Justin Sun name typo, confirmed by Volcengine ASR audit"),
    ("宇辰", "宇晨", "Justin Sun given-name typo"),
    ("雨晨", "宇晨", "Justin Sun given-name typo, confirmed as name mentions by Volcengine ASR audit"),
    ("财务自由", "财富自由", "course term normalization"),
    ("吴小波", "吴晓波", "person name typo"),
    ("冯伦", "冯仑", "person name typo, confirmed by Volcengine ASR audit"),
    ("波长链", "波场链", "blockchain term typo"),
    ("一道用车", "易到用车", "ride-hailing brand typo, confirmed by Volcengine ASR audit"),
    ("一道冲", "易到充", "ride-hailing brand typo, confirmed by Volcengine ASR audit"),
    ("异道", "易到", "ride-hailing brand typo, confirmed by Volcengine ASR audit"),
    ("区分期", "趣分期", "company name typo, confirmed by Volcengine ASR audit"),
    ("区分企业", "趣分期", "company name typo, confirmed by Volcengine ASR audit"),
    ("区链集团", "趣店集团", "company name typo, confirmed by Volcengine ASR audit"),
    ("区电之前", "趣店之前", "company name typo, confirmed by Volcengine ASR audit context"),
    ("罗明", "罗敏", "person name typo, confirmed by Volcengine ASR audit"),
    ("罗米啊", "罗敏啊", "person name typo, confirmed by Volcengine ASR audit context"),
    ("校园代", "校园贷", "finance term typo, confirmed by Volcengine ASR audit"),
    ("陆飞你莫属", "录《非你莫属》", "show title typo, confirmed by Volcengine ASR audit"),
    ("住板家", "住百家", "company name typo, confirmed by Volcengine ASR audit"),
    ("著版家", "住百家", "company name typo, confirmed by Volcengine ASR audit"),
    ("张恒德", "张亨德", "person name typo, confirmed by Volcengine ASR audit and public references"),
    ("明智维新", "明治维新", "historical term typo, confirmed by Volcengine ASR audit"),
    ("萨特斯", "萨特", "Sartre name typo, confirmed by Volcengine ASR audit"),
    ("他人祭地狱", "他人即地狱", "Sartre quote typo, confirmed by Volcengine ASR audit"),
    ("矛头孙宇晨", "孙宇晨", "phrase cleanup after name correction"),
    ("矛头苦干的孙宇晨", "埋头苦干的孙宇晨", "phrase cleanup after name correction"),
    ("伊隆马斯作为", "伊隆马斯克作为", "Elon Musk name typo"),
    ("伊罗曼斯作为", "Elon Musk作为", "Elon Musk name typo, confirmed by Volcengine ASR audit"),
    ("伊罗曼斯克", "伊隆马斯克", "Elon Musk name typo, confirmed by Volcengine ASR audit"),
    ("伊罗马斯克", "伊隆马斯克", "Elon Musk name typo, confirmed by Volcengine ASR audit"),
    ("鱼龙马斯克", "Elon Musk", "Elon Musk name typo, confirmed by Volcengine ASR audit"),
    ("网站叫ready,就是r-e-d-d-i-t", "网站叫Reddit,就是r-e-d-d-i-t", "Reddit name typo, confirmed by Volcengine ASR audit"),
    ("ready对应的是知乎", "Reddit对应的是知乎", "Reddit name typo, confirmed by Volcengine ASR audit"),
    ("ready和twitter", "Reddit和Twitter", "Reddit/Twitter capitalization, confirmed by Volcengine ASR audit"),
    ("4chan,ready", "4chan,Reddit", "Reddit name typo, confirmed by Volcengine ASR audit"),
    ("twitter", "Twitter", "Twitter capitalization, confirmed by Volcengine ASR audit"),
    ("facebook", "Facebook", "Facebook capitalization, confirmed by Volcengine ASR audit"),
    ("snapchat", "Snapchat", "Snapchat capitalization, confirmed by Volcengine ASR audit"),
    ("linkin", "LinkedIn", "LinkedIn name typo, confirmed by Volcengine ASR audit"),
    ("叫做prime", "叫做pride", "seven deadly sins term typo, confirmed by Volcengine ASR audit"),
    ("符合prime", "符合pride", "seven deadly sins term typo, confirmed by Volcengine ASR audit"),
    ("prime这一点", "pride这一点", "seven deadly sins term typo, confirmed by Volcengine ASR audit"),
    ("做last", "做lust", "seven deadly sins term typo, confirmed by context"),
    ("last就是性欲", "lust就是性欲", "seven deadly sins term typo, confirmed by context"),
    ("last,对吧", "lust,对吧", "seven deadly sins term typo, confirmed by context"),
    ("四研创业公司", "四家创业公司", "word typo verified by Volcengine ASR audit and duplicate transcript"),
    ("富利是第八大世界奇迹", "复利是第八大世界奇迹", "compound interest term typo, confirmed by Volcengine ASR audit"),
    ("company interest", "compound interest", "compound interest quote typo"),
    ("heat and the soul", "heart and soul", "compound interest quote typo"),
    ("扎克伯和", "扎克伯格和", "Zuckerberg name typo"),
    ("默默", "陌陌", "Momo app name typo, confirmed by Volcengine ASR audit"),
    ("陌陌无闻", "默默无闻", "restore common phrase after Momo app normalization"),
    ("默默无闻", "默默无闻", "idempotent common phrase preservation"),
    ("陌陌物资", "陌陌市值", "Momo market-cap typo, confirmed by Volcengine ASR audit"),
    ("黄正式", "黄正世", "person name typo, confirmed by semantic-flow Volcengine audit and public references"),
    ("黄正士", "黄正世", "person name typo, confirmed by semantic-flow Volcengine audit and public references"),
    ("黄正仕", "黄正世", "person name typo, confirmed by semantic-flow Volcengine audit and public references"),
    ("吴星宇", "武星宇", "person name typo, confirmed by semantic-flow Volcengine audit and public references"),
    ("五星宇", "武星宇", "person name typo, confirmed by semantic-flow Volcengine audit and public references"),
    ("武新宇", "武星宇", "person name typo, confirmed by semantic-flow Volcengine audit"),
    ("沐妍", "慕岩", "person name typo, confirmed by semantic-flow Volcengine audit and public references"),
    ("莫言一会我会问他", "慕岩一会会问他", "person name typo and phrase repair from semantic-flow audit"),
    ("张欧德", "张亨德", "person name typo, confirmed by recurring guest context"),
    ("山上朝顶", "时代浪潮点", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("柳暗发明", "柳暗花明", "idiom repair confirmed by semantic-flow Volcengine audit"),
    ("给你装上了", "给你撞上了", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("scientific定律", "serendipity定律", "English term repair confirmed by semantic-flow Volcengine audit"),
    ("scientific的几率", "serendipity的几率", "English term repair confirmed by semantic-flow Volcengine audit"),
    ("scientific啊,比较密集的", "serendipity比较密集的", "English term repair confirmed by semantic-flow Volcengine audit"),
    ("森林代理", "The Dip", "English book-title repair from semantic-flow Volcengine audit"),
    ("一孤岛的全部都过来了", "一股脑地全部都过来了", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("死记应被", "死记硬背", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("叫自控高考", "叫自控力。高考", "sentence-boundary repair confirmed by semantic-flow Volcengine audit"),
    ("他的内容为难度", "它的内容有点多", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("录去秀丝区块", "撸起袖子去干", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("知行的行长", "支行的行长", "bank branch title repair confirmed by semantic-flow Volcengine audit"),
    ("不笑那个谁谁谁", "不孝那个谁谁谁", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("那个那个谁谁谁不笑", "那个那个谁谁谁不孝", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("掏粉的", "掏粪男孩,鹿晗", "celebrity reference repair confirmed by semantic-flow Volcengine audit"),
    ("特效嘉宾", "特邀嘉宾", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("收费责任感", "社会责任感", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("大家真的吃两百块钱", "大家真的这两百块钱", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("大家真的是两百块钱", "大家真的这两百块钱", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("我就这么丧心病狂", "我觉得这么丧心病狂", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("不会过了", "不为过了", "idiom repair confirmed by semantic-flow Volcengine audit"),
    ("官至省不及", "官至省部级", "phrase repair from semantic context"),
    ("甚至国不得", "甚至", "phrase repair from semantic context"),
    ("培养民里", "培养皿里", "Matrix reference repair confirmed by semantic-flow Volcengine audit"),
    ("醒外的人", "醒过来的人", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("变成外星的围剿", "要面临外星的围剿", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("醒了到面临外星的围剿", "醒了要面临外星的围剿", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("这个Centrality又发生", "这个事情又发生", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("所以我们才能做这个对比", "所以我们才能做这个review啊", "phrase repair confirmed by semantic-flow Volcengine audit"),
    ("回家了,", "", "semantic-discontinuity hallucination removed after semantic-flow Volcengine audit"),
    ("由 Amara.org 社群提供的字幕", "", "silent hallucination removed after semantic-flow Volcengine audit"),
    ("你你你你你你你你你你你你你你你你你你你你你你你你你你你", "", "silent hallucination removed after semantic-flow Volcengine audit"),
    ("并且要确认是否正确实现公务员的权益", "", "silent hallucination removed after semantic-flow Volcengine audit"),
    ("好,我们下个礼拜再聊吧。", "", "silent hallucination removed after semantic-flow Volcengine audit"),
    (
        "所以我觉得王尔德这个话是非常重要的,所以我觉得王尔德这句话是非常重要的,所以我觉得王尔德这句话是非常重要的,所以我觉得王尔德这句话是非常重要的,所以我觉得王尔德这句话是非常重要的,所以我觉得王尔德这句话是非常重要的,",
        "",
        "silent hallucination removed after semantic-flow Volcengine audit",
    ),
    (
        "当然有个前提条件哦,就是我们这边有一个公司的公司,就是我们的公司的公司。",
        "当然有个前提条件哦,",
        "semantic discontinuity repaired after semantic-flow Volcengine audit",
    ),
    (
        "大家可以把我这个演讲本发到朋友圈就可以了。",
        "大家可以把我这个演讲发到朋友圈就可以了。",
        "phrase repair from semantic context",
    ),
    (
        "因为这可能是唯一一个关系之一",
        "因为这可能是唯一一个关系中",
        "semantic discontinuity repaired after semantic-flow Volcengine audit",
    ),
    ("那么我们就来看这个问题", "", "semantic discontinuity removed after semantic-flow Volcengine audit"),
    (
        "我们这个节目的目的也达到了,从二十四年以来,我们这个节目的目的也达到了,从二十四年以来,我们这个节目的目的也达到了,我们这个节目的目的也达到了,我们这个节目的目的也达到了。",
        "当这个过程完成的时候,我觉得这个节目本身也可以取得它的升华。因为我们的听众和读者是真正依靠着自己三观上的修炼实现的精神自由,而且通过这种精神自由实打实地实现了财富自由,又用这种财富自由捍卫着自己精神自由的时候,我们这个节目的目的也达到了。",
        "repeated hallucination repaired after semantic-flow Volcengine audit",
    ),
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
        "note": "Applied only high-confidence glossary/proper-noun and semantic-flow corrections. raw-json is preserved unchanged.",
        "corrected_file_groups": ["text", "srt", "clean-json"],
        "raw_json_preserved": True,
        "replacements": sorted(total.values(), key=lambda x: (x["from"], x["to"])),
    }
    out = ROOT / "metadata" / "glossary-corrections.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
