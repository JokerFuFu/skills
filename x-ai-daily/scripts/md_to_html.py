#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md_to_html.py — 把日报 Markdown 转成单文件 HTML 报告（图片 base64 内嵌，可独立分享）。

依赖 pandoc。图片以相对路径写在 md 里即可，--embed-resources 会把它们内嵌进 HTML。

用法: md_to_html.py <input.md> [output.html]   (省略输出则同名 .html)
"""
import sys, os, subprocess, re

def main():
    if len(sys.argv) < 2:
        print("用法: md_to_html.py <input.md> [output.html]"); return 2
    src = os.path.abspath(sys.argv[1])
    if not os.path.exists(src):
        print(f"找不到 {src}"); return 1
    out = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".html"
    css = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.css")
    src_dir = os.path.dirname(src)

    # 标题：取 md 第一个 # 标题，回退文件名
    title = os.path.splitext(os.path.basename(src))[0]
    try:
        for line in open(src, encoding="utf-8"):
            m = re.match(r"#\s+(.+)", line.strip())
            if m:
                title = m.group(1).strip(); break
    except Exception:
        pass

    cmd = [
        "pandoc", src, "-f", "gfm", "-t", "html5",
        "--standalone", "--embed-resources",
        "--resource-path", src_dir,
        "--metadata", f"title={title}",
        "-c", css,
        "--wrap", "none",
        "-o", out,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        print("需要 pandoc：brew install pandoc"); return 1
    except subprocess.TimeoutExpired:
        print("pandoc 超时"); return 1
    if r.returncode != 0:
        print("pandoc 失败:", (r.stderr or "")[:500]); return 1

    # 把正文塞进 .report 容器（pandoc 默认 body 直挂内容），简单包一层便于 CSS 控宽
    try:
        html = open(out, encoding="utf-8").read()
        if '<body>' in html and 'class="report"' not in html:
            html = html.replace('<body>', '<body><div class="report">', 1)
            html = html.replace('</body>', '</div></body>', 1)
            open(out, "w", encoding="utf-8").write(html)
    except Exception:
        pass

    print(out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
