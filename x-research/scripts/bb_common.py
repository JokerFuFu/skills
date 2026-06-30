# -*- coding: utf-8 -*-
"""bb_common — bb-browser 适配器调用 + 标签清理的共享工具（chiphell / x / nodeseek 取数脚本复用）。"""
import sys, json, subprocess, re

def run_adapter(name, *pos, timeout=120):
    """运行 bb-browser site <name> <位置参数...> --json，返回 result 字典或 {'error':...}。
    注意：捕获 bytes 后用 errors='replace' 解码——bb-browser 对超大输出(如长中文推文)会在 ~64KB 处截断，
    留下半个多字节字符；若用 text=True 的严格 utf-8 解码会直接抛 UnicodeDecodeError 让整轮取数崩溃。
    这里宁可把这一源降级为 'non-json output' 错误，也不让单源拖垮全局。"""
    cmd = ["bb-browser", "site", name] + [str(p) for p in pos] + ["--json"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout)  # bytes，自行解码
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "cmd": " ".join(cmd)}
    raw = (out.stdout or b"").decode("utf-8", "replace").strip()
    if not raw:
        stderr = (out.stderr or b"").decode("utf-8", "replace")
        return {"error": "empty output", "stderr": stderr[:300], "cmd": " ".join(cmd)}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "non-json output", "raw": raw[:300], "cmd": " ".join(cmd)}
    if isinstance(data, dict):
        inner = data.get("result", data)
        if not isinstance(inner, dict):
            return {"error": "unexpected result shape", "raw": str(inner)[:300]}
        # bb-browser 级错误把 error 包成 {"message": "..."}；统一规整为字符串
        if isinstance(inner.get("error"), dict):
            inner["error"] = inner["error"].get("message") or json.dumps(inner["error"], ensure_ascii=False)
        return inner
    return {"error": "unexpected json shape", "raw": str(data)[:300]}

def ensure_daemon():
    try:
        subprocess.run(["bb-browser", "daemon", "start"], capture_output=True, text=True, timeout=60)
    except Exception:
        pass

def list_tab_ids():
    """返回 {short_id: url}（解析 bb-browser tab list）。"""
    try:
        out = subprocess.run(["bb-browser", "tab", "list"], capture_output=True, timeout=20)
    except Exception:
        return {}
    tabs = {}
    for line in (out.stdout or b"").decode("utf-8", "replace").splitlines():
        m = re.search(r"\[([0-9a-f]{3,})\]\s+(\S+)", line)
        if m:
            tabs[m.group(1)] = m.group(2)
    return tabs

DEFAULT_DOMAINS = ("google.", "nodeseek.com", "chiphell.com", "x.com", "twitter.com")

def close_new_tabs(before_ids, domains=DEFAULT_DOMAINS):
    """关闭本次新开、且属于指定域的标签，避免泄漏；不动用户已有标签。"""
    for tid, url in list_tab_ids().items():
        if tid in before_ids:
            continue
        if any(d in url for d in domains):
            try:
                subprocess.run(["bb-browser", "close", "--tab", tid], capture_output=True, text=True, timeout=15)
            except Exception:
                pass

def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
