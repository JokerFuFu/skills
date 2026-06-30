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
import os, sys, re, argparse
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from bb_common import run_adapter, ensure_daemon, list_tab_ids, close_new_tabs, emit

_ME = os.environ.get("CHIPHELL_USERNAME", "")  # 你的 chiphell 用户名（可选，用于清洗正文里自己用户名的残留）

HIDDEN_RE = re.compile(r"(如果您要查看本帖隐藏内容请回复|回复.{0,6}查看.{0,6}隐藏内容|隐藏内容.{0,6}回复)")

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
    if _ME:                                                              # 去除当前登录名残留(配 CHIPHELL_USERNAME)
        s = re.sub(r"\b" + re.escape(_ME) + r"\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s, hidden

BOARDS = [
    {"fid": "312", "name": "自由水世界 2024"},
    {"fid": "146", "name": "电脑讨论(新)"},
]

def pick_hot(threads, per_board):
    """跳过置顶/公告/禁区，按回复数降序取前 per_board。"""
    pool = [t for t in threads
            if not t.get("sticky") and not t.get("announce")
            and t.get("kind") != "forbidden"]
    pool.sort(key=lambda t: t.get("replies", 0) or 0, reverse=True)
    return pool[:per_board]

def cmd_daily(a):
    ensure_daemon()
    before = list_tab_ids()
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
            hot = pick_hot(threads, a.per_board)
            sys.stderr.write(f"   命中 {len(threads)} 帖，取热度 Top {len(hot)} 读正文 ...\n")
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
                               "scanned": len(threads), "hot_list": hot, "threads": read})
        emit({
            "kind": "chiphell_daily",
            "params": {"pages": a.pages, "threads": a.threads, "per_board": a.per_board},
            "boards": out_boards,
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
