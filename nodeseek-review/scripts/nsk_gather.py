#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nsk_gather.py — NodeSeek 取数编排器

把多次 bb-browser 适配器调用打包成一条命令，输出结构化 JSON（供 nodeseek-daily /
nodeseek-review skill 与未来定时任务复用）。

用法:
  nsk_gather.py daily   [--hot N] [--latest M] [--threads K] [--comments C]
  nsk_gather.py review "<关键词>" [--results K] [--comments C]

依赖: 全局 `bb-browser` 命令，且其 daemon 连着真实 Chrome。
"""
import sys, json, subprocess, argparse, time, re

def list_tab_ids():
    """返回当前所有标签的 {short_id: url} 映射（解析 bb-browser tab list）。"""
    try:
        out = subprocess.run(["bb-browser", "tab", "list"], capture_output=True, text=True, timeout=20)
    except Exception:
        return {}
    tabs = {}
    for line in (out.stdout or "").splitlines():
        m = re.search(r"\[([0-9a-f]{3,})\]\s+(\S+)", line)
        if m:
            tabs[m.group(1)] = m.group(2)
    return tabs

def close_new_tabs(before_ids):
    """关闭本次新开、且属于 adapter 抓取域（google / nodeseek）的标签，避免泄漏；不动用户已有标签。"""
    now = list_tab_ids()
    for tid, url in now.items():
        if tid in before_ids:
            continue
        if "google." in url or "nodeseek.com" in url:
            try:
                subprocess.run(["bb-browser", "close", "--tab", tid], capture_output=True, text=True, timeout=15)
            except Exception:
                pass

def run_adapter(name, *pos, timeout=120):
    """运行 bb-browser site <name> <位置参数...> --json，返回 result 字典或 {'error':...}"""
    cmd = ["bb-browser", "site", name] + [str(p) for p in pos] + ["--json"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "cmd": " ".join(cmd)}
    raw = (out.stdout or "").strip()
    if not raw:
        return {"error": "empty output", "stderr": (out.stderr or "")[:300], "cmd": " ".join(cmd)}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "non-json output", "raw": raw[:300], "cmd": " ".join(cmd)}
    # bb-browser 包了一层 {"result": {...}}；适配器错误为 {"error":..., "hint":...}
    if isinstance(data, dict):
        inner = data.get("result", data)
        return inner if isinstance(inner, dict) else {"error": "unexpected result shape", "raw": str(inner)[:300], "cmd": " ".join(cmd)}
    return {"error": "unexpected json shape", "raw": str(data)[:300], "cmd": " ".join(cmd)}

def ensure_daemon():
    try:
        subprocess.run(["bb-browser", "daemon", "start"], capture_output=True, text=True, timeout=60)
    except Exception:
        pass

def gather_threads(posts, comments, key="post_id", limit=None, label="thread"):
    """对帖子列表逐个抓正文+评论，返回 list，附带原列表里的统计字段。"""
    threads = []
    sel = posts if limit is None else posts[:limit]
    for i, p in enumerate(sel, 1):
        pid = p.get(key)
        if not pid:
            continue
        sys.stderr.write(f"  [{label} {i}/{len(sel)}] 抓取 post-{pid} ...\n")
        sys.stderr.flush()
        t = run_adapter("nodeseek/thread", pid, comments)
        if "error" in t:
            threads.append({"post_id": pid, "url": p.get("url"), "title": p.get("title"),
                            "error": t.get("error"), "hint": t.get("hint")})
            continue
        # 把列表里的热度数据并进来（thread 首页只有当页统计）
        t["list_views"] = p.get("views")
        t["list_comments"] = p.get("comments")
        t["list_category"] = p.get("category")
        t["list_score"] = p.get("score")
        threads.append(t)
    return threads

def cmd_daily(a):
    ensure_daemon()
    before = list_tab_ids()
    try:
        sys.stderr.write("→ 抓综合热度列表 ...\n")
        hot = run_adapter("nodeseek/hot", "hot", "", a.hot, 2)
        sys.stderr.write("→ 抓首页最新列表 ...\n")
        latest = run_adapter("nodeseek/hot", "latest", "", a.latest, 1)

        hot_posts = hot.get("posts", []) if "error" not in hot else []
        if not hot_posts:
            print(json.dumps({"kind": "daily", "error": "拿不到热门列表",
                              "adapter_error": hot.get("error"), "adapter_hint": hot.get("hint"),
                              "hot_raw": hot}, ensure_ascii=False, indent=2))
            return 1
        sys.stderr.write(f"→ 抓 Top {a.threads} 热帖正文+评论 ...\n")
        threads = gather_threads(hot_posts, a.comments, limit=a.threads, label="hot")

        print(json.dumps({
            "kind": "daily",
            "params": {"hot": a.hot, "latest": a.latest, "threads": a.threads, "comments": a.comments},
            "hot_list": hot_posts,
            "latest_list": latest.get("posts", []) if "error" not in latest else [],
            "latest_error": latest.get("error") if "error" in latest else None,
            "threads": threads,
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        close_new_tabs(before)

def cmd_review(a):
    ensure_daemon()
    query = (a.query or "").strip()
    # 防御:空/占位关键词直接拒绝,绝不拿空值去搜（与按需 routine 的前置检查一致）
    if not query or query.lower() in ("null", "none", "undefined"):
        print(json.dumps({"kind": "review", "query": a.query,
                          "error": "需要一个非空的搜索关键词", "hint": "用法: nsk_gather.py review \"<关键词>\""},
                          ensure_ascii=False, indent=2))
        return 1
    before = list_tab_ids()
    try:
        return _do_review(a, query)
    finally:
        close_new_tabs(before)

def _do_review(a, query):
    sys.stderr.write(f"→ 搜索 “{query}” ...\n")
    search = run_adapter("nodeseek/search", query, a.results)
    if "error" in search:
        print(json.dumps({"kind": "review", "query": query, "error": search.get("error"),
                          "hint": search.get("hint")}, ensure_ascii=False, indent=2))
        return 1
    results = search.get("results", [])
    if not results:
        print(json.dumps({"kind": "review", "query": query, "error": "无搜索结果"}, ensure_ascii=False, indent=2))
        return 1
    sys.stderr.write(f"→ 抓 {len(results)} 个相关帖正文+评论 ...\n")
    threads = gather_threads(results, a.comments, label="review")
    print(json.dumps({
        "kind": "review",
        "query": query,
        "params": {"results": a.results, "comments": a.comments},
        "search_results": results,
        "threads": threads,
    }, ensure_ascii=False, indent=2))
    return 0

def main():
    ap = argparse.ArgumentParser(description="NodeSeek 取数编排器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("daily", help="每日热帖取数")
    d.add_argument("--hot", type=int, default=12)
    d.add_argument("--latest", type=int, default=8)
    d.add_argument("--threads", type=int, default=8)
    d.add_argument("--comments", type=int, default=25)
    d.set_defaults(func=cmd_daily)

    r = sub.add_parser("review", help="搜索关键词并取相关帖")
    r.add_argument("query", help="搜索关键词")
    r.add_argument("--results", type=int, default=8)
    r.add_argument("--comments", type=int, default=40)
    r.set_defaults(func=cmd_review)

    a = ap.parse_args()
    sys.exit(a.func(a))

if __name__ == "__main__":
    main()
