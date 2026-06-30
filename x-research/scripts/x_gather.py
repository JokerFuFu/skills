#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
x_gather.py — x.com（Twitter）AI 热帖取数

三路取数后聚合去重、按互动量排序，输出结构化 JSON，供 x-ai-daily skill 合成日报：
  1) 话题搜索：一组 AI 关键词（带 min_faves + since 过滤）取 top 热推
  2) For You：首页推荐流里的 AI 内容
  3) AI 大V列表：盯一批 KOL 账号的近期高赞推

前提：bb-browser 控制的 Chrome 必须已登录 x.com（否则 twitter 适配器返回未登录错误，
本脚本会输出 login_required，让上层提示登录）。

用法: x_gather.py daily [--days N] [--per-query C] [--kol-count C] [--top K] [--min-faves N]
依赖: 全局 bb-browser + 社区 twitter 适配器。
"""
import sys, re, argparse
from datetime import datetime, timedelta, timezone
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from bb_common import run_adapter, ensure_daemon, list_tab_ids, close_new_tabs, emit

# grift / 带货 / 搬运 / 卖号 / 课程推销 降噪（多语言）
SPAM_RE = re.compile(
    r"(每天赚|日赚|月入|日入|被动收入|躺赚|包赚|教你赚|搬运(?:内容|赚)|卖号|三分钟卖|加微信|进群领|薅羊毛教程|割韭菜"
    r"|gana[rs]?\b[^.]{0,30}\$|puedes ganar|te enseñ|prompts que te pagan|dinero"
    r"|make \$\d|\bearn \$|\$\d+\s*(?:/|per|por|al)\s*(?:day|d[ií]a|week|hora)|passive income|side hustle|recurring clients)",
    re.I)

def is_noise(text):
    """grift 带货推 或 去链接/@后过短的低信号推 -> 丢弃。"""
    t = text or ""
    if SPAM_RE.search(t):
        return True
    stripped = re.sub(r"https?://\S+|@\w+|#\w+|\s+", " ", t).strip()
    return len(stripped) < 12

# 英文话题搜索（新模型 / 产品 / 理念·范式 / 应用层）。query 会追加 min_faves + since + 去回复。
AI_QUERIES = [
    "(AI OR LLM) (launch OR release OR announcing OR introducing OR open-source OR open source)",
    "(Claude OR GPT OR Gemini OR Llama OR Qwen OR DeepSeek OR Mistral OR Grok OR Kimi) (model OR release OR benchmark OR SOTA)",
    "(AI agent OR agentic OR reasoning OR RAG OR multimodal OR fine-tuning OR scaling laws OR paradigm)",
    "(AI product OR AI app OR AI agent OR AI startup) (launch OR shipped OR demo OR PMF OR users)",
    "(AI UX OR product design OR prompt OR eval OR agent) (pattern OR playbook OR lesson OR \"how we\")",
]

# 中文话题搜索（国内模型 + 国内 AI 产品/研究）。用 lang:zh + 较低 min_faves（中文圈互动量偏低）。
CN_QUERIES = [
    "(通义 OR Qwen OR Kimi OR 智谱 OR GLM OR DeepSeek OR 豆包 OR 文心 OR MiniMax OR 阶跃 OR 月之暗面 OR 面壁) (模型 OR 发布 OR 开源 OR 评测 OR 升级)",
    "(AI产品 OR AI应用 OR 智能体 OR Agent OR 大模型 OR 多模态) (发布 OR 上线 OR 体验 OR 实测 OR 复盘)",
]

# AI 大V 名单：实验室 + 应用/Agent + 产品builder（贴合 PM/设计师定位）+ 国内 AI。可按需增删。
KOL_ACCOUNTS = [
    # 实验室 / 研究
    "karpathy", "sama", "AnthropicAI", "OpenAI", "GoogleDeepMind", "demishassabis",
    "AndrewYNg", "_akhaliq", "_jasonwei", "alexalbert__",
    # 应用层 / Agent / 工程
    "swyx", "hwchase17", "omarsar0",
    # 产品 builder（AI 应用层 PM/设计师视角）
    "rauchg", "amasad", "mckaywrigley",
    # 国内 AI（模型 + 产品 + 设计）
    "dotey", "op7418", "vista8", "JustinLin610",
]

def parse_age_hours(created_at):
    """Twitter created_at -> 距今小时；解析失败返回 None（不因此丢弃）。"""
    if not created_at:
        return None
    try:
        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return None

def looks_login_error(r):
    e = (r.get("error") or "") + (r.get("hint") or "")
    return ("ct0" in e) or ("log in" in e.lower()) or ("登录" in e)

def cmd_daily(a):
    ensure_daemon()
    before = list_tab_ids()
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%d")
        tweets = {}          # id -> tweet（去重）
        sources = []         # 记录每路来源是否成功
        login_errors = 0
        calls = 0

        def absorb(r, src):
            nonlocal login_errors, calls
            calls += 1
            if "error" in r:
                if looks_login_error(r):
                    login_errors += 1
                sources.append({"src": src, "error": r.get("error")})
                return
            tws = r.get("tweets", [])
            sources.append({"src": src, "count": len(tws)})
            for t in tws:
                tid = t.get("id")
                if not tid or tid in tweets:
                    continue
                if t.get("in_reply_to"):          # 跳过纯回复
                    continue
                if is_noise(t.get("text")):       # 跳过带货/搬运/低信号
                    continue
                t["_src"] = src
                tweets[tid] = t

        # 1) 英文话题搜索
        for q in AI_QUERIES:
            full = f"{q} min_faves:{a.min_faves} since:{since} -filter:replies lang:en"
            sys.stderr.write(f"→ 搜索: {q[:40]}... \n")
            absorb(run_adapter("twitter/search", full, a.per_query, "top"), f"search:{q[:24]}")

        # 1b) 中文话题搜索（国内模型/产品，lang:zh + 较低阈值）
        for q in CN_QUERIES:
            full = f"{q} min_faves:{a.cn_min_faves} since:{since} -filter:replies lang:zh"
            sys.stderr.write(f"→ 中文搜索: {q[:30]}... \n")
            absorb(run_adapter("twitter/search", full, a.per_query, "top"), f"cn:{q[:18]}")

        # 2) For You
        sys.stderr.write("→ For You 推荐流 ...\n")
        absorb(run_adapter("twitter/for_you", a.per_query), "for_you")

        # 3) AI 大V
        for h in KOL_ACCOUNTS:
            sys.stderr.write(f"→ KOL @{h} ...\n")
            absorb(run_adapter("twitter/tweets", h, a.kol_count), f"kol:{h}")

        # 全部因未登录失败 -> 提示登录
        if login_errors and login_errors >= calls:
            emit({"kind": "x_ai_daily", "login_required": True,
                  "hint": "bb-browser 控制的 Chrome 未登录 x.com，请先在该 Chrome 登录后重试。",
                  "sources": sources})
            return 2

        # 过滤时效 + 排序（likes + 2*retweets）
        items = list(tweets.values())
        for t in items:
            age = parse_age_hours(t.get("created_at"))
            t["age_hours"] = round(age, 1) if age is not None else None
            t["score"] = (t.get("likes") or 0) + 2 * (t.get("retweets") or 0)
        # 时效：保留 age<=days*24+6 的（解析失败的保留，交给上层判断）
        cutoff = a.days * 24 + 6
        fresh = [t for t in items if t.get("age_hours") is None or t["age_hours"] <= cutoff]
        fresh.sort(key=lambda t: t.get("score", 0), reverse=True)
        top = fresh[:a.top]

        emit({
            "kind": "x_ai_daily",
            "params": {"days": a.days, "per_query": a.per_query, "kol_count": a.kol_count,
                       "top": a.top, "min_faves": a.min_faves, "since": since},
            "queries": AI_QUERIES, "kol_accounts": KOL_ACCOUNTS,
            "collected": len(items), "returned": len(top),
            "sources": sources,
            "tweets": top,
        })
        return 0
    finally:
        close_new_tabs(before, domains=("x.com", "twitter.com"))

def cmd_search(a):
    """按需关键词检索：自由问题/关键词 → 多 query × top/latest → 去重去噪排序 → 抓前 K 原创推的线程回复 → 结构化 JSON。
    供 x-research skill 合成带引用的中文总结。无登录则优雅返回 login_required。"""
    ensure_daemon()
    before = list_tab_ids()
    try:
        queries = [a.query] + (a.query_extra or [])
        since = ""
        if a.days and a.days > 0:
            since = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%d")
        types = ["top", "latest"] if a.type == "both" else [a.type]

        tweets = {}          # id -> tweet（去重）
        sources = []
        login_errors = 0
        calls = 0

        def absorb(r, src):
            nonlocal login_errors, calls
            calls += 1
            if "error" in r:
                if looks_login_error(r):
                    login_errors += 1
                sources.append({"src": src, "error": r.get("error")})
                return
            tws = r.get("tweets", [])
            sources.append({"src": src, "count": len(tws)})
            for t in tws:
                tid = t.get("id")
                if not tid or tid in tweets:
                    continue
                if is_noise(t.get("text")):       # 跳过带货/搬运/低信号
                    continue
                t["_src"] = src
                tweets[tid] = t

        # 每个 query 跑 top 与/或 latest 两路（latest 抓时效、top 抓高赞共识）
        for q in queries:
            suffix = ""
            if a.min_faves and a.min_faves > 0:
                suffix += f" min_faves:{a.min_faves}"
            if since:
                suffix += f" since:{since}"
            full = (q + suffix).strip()
            for ty in types:
                sys.stderr.write(f"→ 搜索[{ty}]: {q[:50]} ...\n")
                absorb(run_adapter("twitter/search", full, a.count, ty), f"search[{ty}]:{q[:30]}")

        # 全部因未登录失败 -> 提示登录
        if login_errors and login_errors >= calls:
            emit({"kind": "x_search", "login_required": True,
                  "hint": "bb-browser 控制的 Chrome 未登录 x.com，请先在该 Chrome 登录 <X_HANDLE> 后重试。",
                  "queries": queries, "sources": sources})
            return 2

        items = list(tweets.values())
        for t in items:
            age = parse_age_hours(t.get("created_at"))
            t["age_hours"] = round(age, 1) if age is not None else None
            t["score"] = (t.get("likes") or 0) + 2 * (t.get("retweets") or 0)
        items.sort(key=lambda t: t.get("score", 0), reverse=True)

        # 对排名靠前的原创推（非回复）抓取线程回复，捕捉讨论与不同观点
        threads = []
        if a.threads and a.threads > 0:
            roots = [t for t in items if not t.get("in_reply_to")][:a.threads]
            for t in roots:
                sys.stderr.write(f"→ 线程 @{t.get('author')} {t.get('id')} ...\n")
                r = run_adapter("twitter/thread", t.get("id"))
                if "error" in r:
                    threads.append({"root_id": t.get("id"), "root_author": t.get("author"),
                                    "root_url": t.get("url"), "error": r.get("error")})
                    continue
                tl = r.get("tweets", [])
                replies = [x for x in tl[1:] if not is_noise(x.get("text"))][:a.reply_count]
                threads.append({
                    "root_id": t.get("id"), "root_author": t.get("author"),
                    "root_url": t.get("url"), "root_text": t.get("text"),
                    "reply_count": len(replies),
                    "replies": [{"author": x.get("author"), "text": x.get("text"),
                                 "likes": x.get("likes"),
                                 "url": "https://x.com/%s/status/%s" % (x.get("author") or "_", x.get("id"))}
                                for x in replies],
                })

        top = items[:a.top]
        emit({
            "kind": "x_search",
            "params": {"queries": queries, "count": a.count, "type": a.type, "threads": a.threads,
                       "reply_count": a.reply_count, "min_faves": a.min_faves, "days": a.days,
                       "since": since or None, "top": a.top},
            "collected": len(items), "returned": len(top),
            "sources": sources,
            "tweets": top,
            "threads": threads,
        })
        return 0
    finally:
        close_new_tabs(before, domains=("x.com", "twitter.com"))

def main():
    ap = argparse.ArgumentParser(description="x.com AI 取数：daily 日报 / search 按需检索")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--days", type=int, default=1, help="取最近几天（默认 1）")
    d.add_argument("--per-query", type=int, default=25, help="每个搜索/For You 取多少条（默认 25）")
    d.add_argument("--kol-count", type=int, default=10, help="每个 KOL 取多少条（默认 10）")
    d.add_argument("--top", type=int, default=35, help="最终保留 Top 多少条（默认 35）")
    d.add_argument("--min-faves", type=int, default=600, help="英文搜索最低点赞阈值（默认 600）")
    d.add_argument("--cn-min-faves", type=int, default=120, help="中文搜索最低点赞阈值（默认 120，中文圈互动量偏低）")
    d.set_defaults(func=cmd_daily)

    s = sub.add_parser("search", help="按需关键词检索 + 线程回复（供 x-research 总结）")
    s.add_argument("query", help="主搜索词/问题关键词（自由文本，可含 x 高级搜索语法，如 OR、引号短语）")
    s.add_argument("--query", dest="query_extra", action="append",
                   help="附加搜索词（可多次传，建议覆盖 EN/CN 变体与同义词）")
    s.add_argument("--count", type=int, default=30, help="每次搜索取多少条（max 50，默认 30）")
    s.add_argument("--type", choices=["top", "latest", "both"], default="both",
                   help="搜索类型：top 高赞 / latest 最新 / both 两路都跑（默认 both）")
    s.add_argument("--threads", type=int, default=6, help="对排名前 K 条原创推抓取线程回复（默认 6，0=不抓）")
    s.add_argument("--reply-count", type=int, default=15, help="每条线程最多保留回复数（默认 15）")
    s.add_argument("--min-faves", type=int, default=0, help="最低点赞过滤（默认 0=不过滤，niche 话题互动低）")
    s.add_argument("--days", type=int, default=0, help="只取最近 N 天（默认 0=不限时间）")
    s.add_argument("--top", type=int, default=40, help="最终返回 top 多少条推文（默认 40）")
    s.set_defaults(func=cmd_search)

    a = ap.parse_args()
    sys.exit(a.func(a))

if __name__ == "__main__":
    main()
