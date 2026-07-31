#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chiphell_gather.py — chiphell 每日热帖取数（只读，绝不回帖/下注）

扫「自由水世界 2024」(fid 312) 与「电脑讨论(新)」(fid 146) 两个板块，
跳过置顶/公告/禁区，按回复数排热度，读 Top 帖正文，输出结构化 JSON。
供 chiphell-daily skill 合成日报。复用现有 chiphell/forum + chiphell/thread 适配器。

用法: chiphell_gather.py daily [--pages P] [--threads K] [--per-board B]
依赖: 全局 bb-browser，daemon 连真实 Chrome，且已登录你的 chiphell 账号。
     （登录用户名通过环境变量 CHIPHELL_USERNAME 配置，用于从抓到的正文里剔除自己用户名的残留）
"""
import os, sys, re, argparse, json, datetime
from pathlib import Path
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from bb_common import run_adapter, ensure_daemon, list_tab_ids, close_new_tabs, emit

# 自包含：配置/状态放在 skill 目录下的 data/（可用 CHIPHELL_DATA_DIR 覆盖）
DATA = Path(os.environ.get("CHIPHELL_DATA_DIR")
            or (Path(__file__).resolve().parent.parent / "data"))
_ME = os.environ.get("CHIPHELL_USERNAME", "")  # 你的 chiphell 用户名（可选，用于清洗正文里自己用户名的残留）

HIDDEN_RE = re.compile(r"(如果您要查看本帖隐藏内容请回复|回复.{0,6}查看.{0,6}隐藏内容|隐藏内容.{0,6}回复)")

# ---- 小工具:JSON 读写 / 日期 ----
def load_json(path, default):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except Exception:
        return default

def save_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")

def today_str():
    return datetime.date.today().isoformat()

def parse_created(s):
    """'2022-7-8 16:16' / '2022-7-8' -> date;无法解析返回 None。"""
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(s))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None

def age_days(created_str):
    d = parse_created(created_str)
    return None if d is None else (datetime.date.today() - d).days

# ---- 热榜常青/连载帖过滤 ----
# 配置(用户可编辑,脚本只读):data/chiphell_hot_filter.json
# 状态(脚本读写,记录每日 top-K 出现):data/chiphell_hot_history.json
DEFAULT_HOT_FILTER = {
    "max_age_days": 14,                 # 建帖超过 N 天的帖从热榜剔除(水区"今日热点"多≤4天、连载常青≥20天)
    "manual_block": [],                 # 永久屏蔽的帖 id(如常年置顶的打卡贴),按需自己加
    "persist_days": 3,                  # 近 window 天内进过 top-K ≥ persist_days 天 → "天天在榜"自动屏蔽
    "persist_window_days": 7,
    "top_k_track": 15,                  # 每日按回复数记录前 K 个进 history 供连续霸榜判定
}

def evergreen_reasons(t, cfg, history, today):
    """返回该帖被判为常青/连载的原因列表(空=不屏蔽)。"""
    tid = str(t.get("id"))
    reasons = []
    if tid in set(cfg.get("manual_block", [])):
        reasons.append("manual")
    max_age = cfg.get("max_age_days")
    a = age_days(t.get("created"))
    if max_age is not None and a is not None and a > max_age:
        reasons.append(f"age>{max_age}d({a}d)")
    window = cfg.get("persist_window_days", 7)
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=window)).isoformat()
    days = {d for d in history.get(tid, {}).get("days", []) if d >= cutoff and d != today}
    if len(days) >= cfg.get("persist_days", 3):
        reasons.append(f"persist({len(days)}d)")
    return reasons

def record_hot_history(pool, cfg, history, today):
    """把今日按回复数的 top-K(pool 已降序)记进 history,并按窗口修剪。"""
    window = cfg.get("persist_window_days", 7)
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=window)).isoformat()
    for t in pool[: cfg.get("top_k_track", 15)]:
        tid = str(t.get("id"))
        h = history.setdefault(tid, {"title": t.get("title"), "days": []})
        h["title"] = t.get("title")
        if today not in h["days"]:
            h["days"].append(today)
    for tid in list(history):
        history[tid]["days"] = [d for d in history[tid]["days"] if d >= cutoff]
        if not history[tid]["days"]:
            del history[tid]

# ---- 出售区关注(想买的物品/想看的地区) ----
# 配置(可编辑):data/chiphell_sale_watch.json ;状态(去重):data/chiphell_sale_seen.json
DEFAULT_SALE_WATCH = {
    # 物品关注:想买的具体东西 → 命中会推送 +(auto_reply 开时)自动回帖排队
    "keywords": [],          # 例:["显示器", "4090", "ThinkPad"]；留空=不做物品关注
    # 地区关注:只按地区看看有什么 → 命中只推微信/进日报,【绝不自动回帖】
    #（地区帖卖的是各种东西,不是你想要的具体物品,自动回帖=骚扰卖家/灌水）
    "regions": [],           # 例:["北京"]；只按地区看看在卖什么，留空=不做地区关注
    "boards": [{"fid": "26", "name": "玩家出售发布区"}],
    "pages": 3,
    "auto_reply": False,            # 缺配置时失败安全:默认不自动回帖(写操作)
    "auto_reply_text": "有意，排队，联系看看",
    "auto_reply_max_per_run": 2,
}

# 地区命中:标题前缀 [北京]/【北京】 或正文开头的地区标记;用词边界避免"南京"误配"北京"之类
def region_match(title, regions):
    """返回命中的地区词(取第一个);只认标题里的地区标记,避免正文里顺口提到的城市。"""
    t = title or ""
    m = re.match(r"^\s*[\[【\(（]\s*([^\]】\)）]{1,12})\s*[\]】\)）]", t)
    prefix = m.group(1) if m else ""
    for rg in regions:
        rg = str(rg).strip()
        if not rg:
            continue
        if rg in prefix:            # 主判据:地区标记在标题前缀里([北京] / [北京朝阳] 都算)
            return rg
    return None

def clean_excerpt(s):
    """清洗 chiphell/thread 的 body_excerpt，并判断是否「回复可见」隐藏帖。
    返回 (text, hidden)。hidden=True 时正文被回复门挡住，只读流程绝不回帖去看。"""
    s = s or ""
    hidden = bool(HIDDEN_RE.search(s))
    s = re.sub(r"replyreload\s*\+=[^;]*;", " ", s)                       # 脚本残留
    s = re.sub(r"\S+\.(?:jpg|png|gif|jpeg)\s*\([^)]*\)\s*下载附件\s*[\d\-: ]*", " ", s, flags=re.I)  # 附件块
    s = re.sub(r"下载次数:\s*\d+", " ", s)
    s = HIDDEN_RE.sub(" ", s)
    s = re.sub(r"(?:^|\s)上传(?=\s|$)", " ", s)                          # 上传按钮残留
    if _ME:
        s = re.sub(r"\b" + re.escape(_ME) + r"\b", " ", s)                 # 当前登录名残留
    s = re.sub(r"\s+", " ", s).strip()
    return s, hidden

BOARDS = [
    {"fid": "312", "name": "自由水世界 2024"},
    {"fid": "146", "name": "电脑讨论(新)"},
]

def hot_pool(threads):
    """跳过置顶/公告/禁区，按回复数降序返回全部候选(不截断)。"""
    pool = [t for t in threads
            if not t.get("sticky") and not t.get("announce")
            and t.get("kind") != "forbidden"]
    pool.sort(key=lambda t: t.get("replies", 0) or 0, reverse=True)
    return pool

def sale_watch(sale_cfg, seen, today):
    """扫出售板块,收集两类命中(均去重进 new_hits):
      - match_type='item'  标题含关注物品词(keywords) → 可自动回帖排队
      - match_type='region' 标题地区标记命中关注地区(regions) → 【只推送/进日报,绝不自动回帖】
    同时命中两类时算 item(物品优先,可回帖)。"""
    keywords = [k for k in sale_cfg.get("keywords", []) if str(k).strip()]
    regions = [r for r in sale_cfg.get("regions", []) if str(r).strip()]
    ignore_ids = {str(i) for i in sale_cfg.get("ignore_ids", [])}
    pages = sale_cfg.get("pages", 3)
    hits, new_hits, errors = [], [], []
    if not keywords and not regions:
        return {"keywords": [], "regions": [], "hits": [], "new_hits": [],
                "errors": ["no keywords/regions configured"]}
    for board in sale_cfg.get("boards", []):
        fid, bname = str(board.get("fid")), board.get("name") or board.get("fid")
        sys.stderr.write(f"→ 扫出售区 {bname} (fid {fid}) {pages} 页 找关注物品/地区 ...\n")
        forum = run_adapter("chiphell/forum", fid, pages)
        if "error" in forum:
            errors.append({"fid": fid, "name": bname, "error": forum.get("error"),
                           "logged_in": forum.get("logged_in")})
            continue
        for t in forum.get("threads", []):
            title = t.get("title") or ""
            if str(t.get("id")) in ignore_ids:      # 版块模板/示例帖等,永不关注
                continue
            matched = [kw for kw in keywords if kw.lower() in title.lower()]
            rg = region_match(title, regions)
            if not matched and not rg:
                continue
            rec = {"id": str(t.get("id")), "title": title, "url": t.get("url"),
                   "author": t.get("author"), "board": bname,
                   "match_type": "item" if matched else "region",
                   "keyword": matched[0] if matched else rg,
                   "region": rg}
            hits.append(rec)
            if rec["id"] not in seen:
                new_hits.append({**rec, "first_seen": today})
                seen[rec["id"]] = {"title": title, "url": t.get("url"),
                                   "match_type": rec["match_type"], "keyword": rec["keyword"],
                                   "region": rg, "board": bname, "first_seen": today}
    n_item = sum(1 for h in hits if h["match_type"] == "item")
    sys.stderr.write(f"   出售区关注:命中 {len(hits)} 条(物品 {n_item} / 地区 {len(hits)-n_item};其中新 {len(new_hits)} 条)\n")
    return {"keywords": keywords, "regions": regions,
            "hits": hits, "new_hits": new_hits, "errors": errors,
            # 自动回帖开关+措辞(护栏由 SKILL 执行;缺配置默认不回)
            # 注意:只有 match_type=='item' 的命中才可回帖;region 命中一律只推送。
            "auto_reply": bool(sale_cfg.get("auto_reply", False)),
            "auto_reply_text": sale_cfg.get("auto_reply_text") or DEFAULT_SALE_WATCH["auto_reply_text"],
            "auto_reply_max_per_run": int(sale_cfg.get("auto_reply_max_per_run", 2) or 2),
            "push_max_region": int(sale_cfg.get("push_max_region", 5) or 5)}

def cmd_daily(a):
    ensure_daemon()
    before = list_tab_ids()
    hot_cfg = load_json(DATA / "chiphell_hot_filter.json", DEFAULT_HOT_FILTER)
    history = load_json(DATA / "chiphell_hot_history.json", {})
    today = today_str()
    try:
        out_boards = []
        for b in BOARDS:
            sys.stderr.write(f"→ 扫 {b['name']} (fid {b['fid']}) {a.pages} 页 ...\n")
            forum = run_adapter("chiphell/forum", b["fid"], a.pages)
            if "error" in forum:
                out_boards.append({**b, "error": forum.get("error"), "hint": forum.get("hint"),
                                   "logged_in": forum.get("logged_in")})
                continue
            threads = forum.get("threads", [])
            pool = hot_pool(threads)
            record_hot_history(pool, hot_cfg, history, today)   # 记今日 top-K 供连续霸榜判定(不影响今日判定)
            kept, dropped = [], []
            for t in pool:
                reasons = evergreen_reasons(t, hot_cfg, history, today)
                if reasons:
                    dropped.append({"id": t.get("id"), "title": t.get("title"),
                                    "replies": t.get("replies"), "created": t.get("created"),
                                    "reason": ",".join(reasons)})
                else:
                    kept.append(t)
            hot = kept[:a.per_board]
            sys.stderr.write(f"   命中 {len(threads)} 帖，过滤常青/连载 {len(dropped)} 个，取热度 Top {len(hot)} 读正文 ...\n")
            read = []
            for i, t in enumerate(hot[:a.threads], 1):
                tid = t.get("id")
                sys.stderr.write(f"   [{b['fid']} {i}/{min(len(hot), a.threads)}] thread-{tid} ...\n")
                det = run_adapter("chiphell/thread", tid)
                if "error" in det:
                    read.append({"id": tid, "title": t.get("title"), "url": t.get("url"),
                                 "replies": t.get("replies"), "error": det.get("error")})
                    continue
                body, hidden = clean_excerpt(det.get("body_excerpt"))
                det["body"] = body
                det["hidden_content"] = hidden
                det.pop("body_excerpt", None)
                det["list_replies"] = t.get("replies")
                det["list_kind"] = t.get("kind")
                read.append(det)
            out_boards.append({**b, "logged_in": forum.get("logged_in"),
                               "scanned": len(threads), "hot_list": hot,
                               "hot_dropped": dropped, "threads": read})

        # 出售区关注——独立于两大板块,命中由 skill 推送通知
        sale_cfg = load_json(DATA / "chiphell_sale_watch.json", DEFAULT_SALE_WATCH)
        seen = load_json(DATA / "chiphell_sale_seen.json", {})
        sw = sale_watch(sale_cfg, seen, today)
        save_json(DATA / "chiphell_sale_seen.json", seen)       # 立即落去重(即使微信推送失败也不重复报;命中同样进日报)
        save_json(DATA / "chiphell_hot_history.json", history)

        emit({
            "kind": "chiphell_daily",
            "params": {"pages": a.pages, "threads": a.threads, "per_board": a.per_board},
            "boards": out_boards,
            "sale_watch": sw,
        })
        return 0
    finally:
        close_new_tabs(before, domains=("chiphell.com",))

def main():
    ap = argparse.ArgumentParser(description="chiphell 每日热帖取数（只读）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--pages", type=int, default=2, help="每板块扫几页（默认 2）")
    d.add_argument("--threads", type=int, default=5, help="每板块读几个热帖正文（默认 5）")
    d.add_argument("--per-board", type=int, default=8, help="每板块热度榜保留条数（默认 8）")
    d.set_defaults(func=cmd_daily)
    a = ap.parse_args()
    sys.exit(a.func(a))

if __name__ == "__main__":
    main()
