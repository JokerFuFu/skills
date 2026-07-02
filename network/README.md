# network — 网络 / 代理基建 skill

本类别收录**网络基础设施**相关的 skill:海外主机上的代理节点部署、系统加固、客户端接入与订阅聚合等。每个 skill 一个子目录,**自包含**(`SKILL.md` + 随附 `references/`),拿来即可照做。

> ⚠️ **仅用于个人自用的合法网络优化(跨境访问技术资源等)**。所有密钥 / 口令 / Token 在文档中一律为 `<占位符>`,**真实凭据不入库**,按文中命令现场生成。启用前请理解每步行为并确认合规。

## 目录结构

```
network/
└── vps-proxy-deploy/
    ├── SKILL.md              # 总览 + 协议选型 + 部署流程 + 验证
    └── references/           # 分模块细则(渐进式披露)
        ├── hardening.md      # 主机加固:SSH 高位端口/仅密钥、ufw、fail2ban、BBR
        ├── singbox-install.md# sing-box 1.14 安装(版本兼容性是生死线)+ systemd + 密钥生成
        ├── reality.md        # VLESS+Reality(TCP 443)主力抗封锁
        ├── hysteria2.md      # Hysteria2(UDP)主打速度
        ├── argo-cdn.md       # Cloudflare Argo 隧道 CDN 中转,隐藏源站地址
        ├── clients.md        # OpenClash / Clash 系 / Shadowrocket 导入 + Sub-Store 聚合
        └── troubleshooting.md# 排障:Reality 握手失败、线路干扰、fake-ip 闪断等真实坑
```

## 这些 skill

| skill | 做什么 | 触发示例 | 是否写操作 |
|---|---|---|---|
| **vps-proxy-deploy** | 在海外主机上从零部署一套代理节点(sing-box:Reality / Hysteria2 / Argo CDN 中转),含主机加固、客户端导入、订阅聚合、排障 | "在 VPS 上配代理节点"、"装 sing-box Reality"、"节点被墙 / 握手失败" | 只读指引(命令由你在自己主机上执行) |

## 依赖

- 一台**海外主机**、可 SSH 登录。
- 服务端内核 **[sing-box](https://github.com/SagerNet/sing-box) 1.14 系列**(版本务必对齐,高版本部分字段有兼容变动)。
- 中转方案可选 **[cloudflared](https://github.com/cloudflare/cloudflared)** + 一个接入 Cloudflare 的域名。

## 安装为 skill

```bash
# 全局可用(软链,跟随本仓库更新)
ln -s "$PWD/network/vps-proxy-deploy" ~/.claude/skills/vps-proxy-deploy
```

装好后 Claude Code 会按 `SKILL.md` 的 `description` 自动触发。
