#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
x_post.py — x.com 回帖发布网关（防封护栏，确定性强制，不靠模型自觉）

把"是否真发"这件事从模型手里拿走：限量 / 同号冷却 / 最小间隔 / 随机抖动 / 总开关
全部在这里强制。模型只负责"挑帖 + 起草"，发布交给本网关。

用法:
  x_post.py status                         查看今日已发/剩余/配置
  x_post.py post <tweet_id> <author> <<<"回帖正文"   （正文从 stdin 读，避免转义问题）
     或  x_post.py post <tweet_id> <author> --text "回帖正文"

返回 JSON。mode=draft 时一律拒发（返回 refused: mode_draft）。
配置 data/x_reply_config.json，日志 data/x_reply_log.json。
"""
import sys, os, json, time, random, subprocess, argparse
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "data", "x_reply_config.json")
LOG = os.path.join(ROOT, "data", "x_reply_log.json")

def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def now():
    return datetime.now(timezone.utc)

def cfg():
    return load_json(CFG, {"mode": "draft", "daily_cap": 3, "per_account_cooldown_days": 3,
                           "min_gap_minutes": 45, "jitter_seconds": [5, 40]})

def log():
    d = load_json(LOG, {})
    d.setdefault("suggested", [])
    d.setdefault("posted", [])   # [{id, author, ts(iso), reply_id}]
    return d

def posted_in_last(d, hours):
    cut = now() - timedelta(hours=hours)
    out = []
    for p in d["posted"]:
        try:
            if datetime.fromisoformat(p["ts"]) >= cut:
                out.append(p)
        except Exception:
            pass
    return out

def cmd_status(a):
    c, d = cfg(), log()
    today = posted_in_last(d, 24)
    last = max((p["ts"] for p in d["posted"]), default=None)
    print(json.dumps({
        "mode": c.get("mode"), "daily_cap": c.get("daily_cap"),
        "posted_24h": len(today), "remaining_today": max(0, c.get("daily_cap", 3) - len(today)),
        "cooldown_days": c.get("per_account_cooldown_days"), "min_gap_minutes": c.get("min_gap_minutes"),
        "last_post_ts": last, "total_posted": len(d["posted"])
    }, ensure_ascii=False, indent=2))
    return 0

def cmd_post(a):
    c, d = cfg(), log()
    text = a.text if a.text is not None else sys.stdin.read()
    text = (text or "").strip()
    tid = "".join(ch for ch in str(a.tweet_id) if ch.isdigit())
    author = (a.author or "").lstrip("@")

    def refuse(reason, **extra):
        print(json.dumps({"refused": reason, "tweet_id": tid, **extra}, ensure_ascii=False)); return 0

    if not tid:   return refuse("bad_tweet_id")
    if not text:  return refuse("empty_text")
    if len(text) > 270: return refuse("too_long", length=len(text))

    # 总开关：draft 一律不发
    if c.get("mode") != "auto":
        return refuse("mode_draft", hint="把 data/x_reply_config.json 的 mode 改成 auto 才会真发")

    # 去重：已发过这条
    if any(p["id"] == tid for p in d["posted"]):
        return refuse("already_replied_this_tweet")

    # 日上限
    today = posted_in_last(d, 24)
    if len(today) >= c.get("daily_cap", 3):
        return refuse("daily_cap_reached", posted_24h=len(today), cap=c.get("daily_cap", 3))

    # 同号冷却
    cd_days = c.get("per_account_cooldown_days", 3)
    if author and cd_days:
        cut = now() - timedelta(days=cd_days)
        for p in d["posted"]:
            try:
                if p.get("author", "").lower() == author.lower() and datetime.fromisoformat(p["ts"]) >= cut:
                    return refuse("account_cooldown", author=author, cooldown_days=cd_days)
            except Exception:
                pass

    # 最小间隔
    gap = c.get("min_gap_minutes", 45)
    if gap and d["posted"]:
        try:
            last_ts = max(datetime.fromisoformat(p["ts"]) for p in d["posted"])
            if now() - last_ts < timedelta(minutes=gap):
                return refuse("min_gap_not_elapsed", min_gap_minutes=gap)
        except Exception:
            pass

    # 随机抖动（拟人，避免整点齐发）
    lo, hi = (c.get("jitter_seconds") or [5, 40])[:2]
    time.sleep(random.uniform(lo, hi))

    # 经真实浏览器会话发布
    cmd = ["bb-browser", "site", "twitter/reply", tid, text, "yes", "--json"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        data = json.loads((out.stdout or "").strip() or "{}")
    except Exception as e:
        return refuse("post_call_failed", detail=str(e))
    res = data.get("result", data)
    if not res.get("ok"):
        print(json.dumps({"posted": False, "tweet_id": tid, "adapter": res}, ensure_ascii=False)); return 0

    d["posted"].append({"id": tid, "author": author, "ts": now().isoformat(),
                        "reply_id": res.get("posted_id"), "text": text[:120]})
    if tid not in d["suggested"]:
        d["suggested"].append(tid)
    save_json(LOG, d)
    print(json.dumps({"posted": True, "tweet_id": tid, "reply_url": res.get("url"),
                      "posted_24h": len(posted_in_last(d, 24)), "cap": c.get("daily_cap", 3)},
                     ensure_ascii=False))
    return 0

def main():
    ap = argparse.ArgumentParser(description="x.com 回帖发布网关（防封护栏）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p = sub.add_parser("post")
    p.add_argument("tweet_id")
    p.add_argument("author")
    p.add_argument("--text", default=None, help="回帖正文（省略则从 stdin 读）")
    p.set_defaults(func=cmd_post)
    a = ap.parse_args()
    sys.exit(a.func(a))

if __name__ == "__main__":
    main()
