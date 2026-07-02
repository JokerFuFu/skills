# skills

我的 [Claude Code](https://claude.com/claude-code) **skill 合集**,按**类别**组织——每个类别是一个母目录,各自收录一组相关的 skill。这个仓库会持续生长,陆续加入新的类别。

## 类别

| 类别 | 内容 | 数量 |
|---|---|---|
| [**routines/**](routines/) | bb-browser 驱动的论坛/社媒每日 routine(NodeSeek / x.com / chiphell):热帖日报、口碑评价、AI 日报、回帖、求捞等 | 7 |
| [**network/**](network/) | 网络 / 代理基建:海外主机代理节点部署(sing-box · Reality / Hysteria2 / Argo CDN)、主机加固、客户端导入、订阅聚合、排障 | 1 |
| *(更多类别陆续加入)* | | |

每个类别目录下都有自己的 `README.md`,说明该类别的依赖、安装与用法——具体看对应类别。

## 什么是 skill

一个 skill 就是一个目录,核心是 `SKILL.md`:

```
<skill-name>/
└── SKILL.md          # YAML frontmatter(name + description) + 正文(给模型的操作说明)
    └── (可选) scripts/ / adapters/ / references/ / assets/ 等随附资源
```

`description` 决定 Claude 何时自动触发这个 skill;正文是触发后加载的详细指引。详见官方文档 [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills)。

## 怎么用

把需要的 skill 目录软链或复制到 skill 搜索路径,Claude Code 即会按 `description` 自动触发:

```bash
# 全局可用
ln -s "$PWD/routines/nodeseek-daily" ~/.claude/skills/nodeseek-daily
# 或仅在某个项目里可用
ln -s "$PWD/routines/nodeseek-daily" /path/to/project/.claude/skills/nodeseek-daily
```

部分 skill 需要额外依赖或一次性安装(如 `routines/` 里的 bb-browser 适配器)——按该**类别 README** 的说明做。

---

*个人自用,按现状提供。涉及账号/自动化的 skill 请先读懂其行为、确认合规后再启用。*
