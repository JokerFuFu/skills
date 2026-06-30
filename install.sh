#!/usr/bin/env bash
# install.sh — 把各 skill 自带的 bb-browser 适配器装到 ~/.bb-browser/sites/，
# 并拉社区 twitter 取数适配器。一次性，幂等。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SITES="$HOME/.bb-browser/sites"

echo "== 检查依赖 =="
for c in bb-browser python3 pandoc; do
  if command -v "$c" >/dev/null 2>&1; then echo "  ✓ $c"; else echo "  ✗ 缺 $c（部分 skill 会不可用）"; fi
done
echo "  (可选) codex —— 仅 x-ai-daily 画信息图用，缺了会自动跳过画图"

echo "== 拉社区取数适配器 (twitter/search|for_you|tweets 等) =="
bb-browser site update 2>&1 | tail -2 || echo "  site update 失败，可稍后手动跑：bb-browser site update"

echo "== 安装各 skill 自带的适配器到 $SITES =="
mkdir -p "$SITES"
# 注意：social update 在前、自带护栏版在后覆盖（如 twitter/reply 是带反下注/防封护栏的私有版）
for d in "$ROOT"/*/adapters/*/; do
  [ -d "$d" ] || continue
  site="$(basename "$d")"
  skill="$(basename "$(dirname "$(dirname "$d")")")"
  mkdir -p "$SITES/$site"
  if cp -f "$d"*.js "$SITES/$site/" 2>/dev/null; then
    echo "  ✓ $site/  ← $skill"
  fi
done

cat <<'EOF'

== 完成。后续提醒 ==
1. bb-browser 必须连本机【真实 Chrome】：先开 Chrome，再 `bb-browser daemon start`。
2. 各 skill 需要的登录与环境变量见各自 SKILL.md：
   - x 系列（x-ai-daily / x-reply-draft / x-research）：Chrome 登录 x.com。
   - chiphell 系列（chiphell-daily / chiphell-rescue）：Chrome 登录 chiphell，并设
     CHIPHELL_USERNAME（你的用户名）；chiphell-rescue 另需 CHIPHELL_SELF_RESCUE、CHIPHELL_FORBIDDEN。
3. 作为 Claude Code skill 使用：把需要的 skill 目录软链或复制到 ~/.claude/skills/ 或项目的 .claude/skills/。
EOF
