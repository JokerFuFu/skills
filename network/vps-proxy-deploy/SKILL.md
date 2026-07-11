---
name: vps-proxy-deploy
description: 在海外 VPS 上从零部署科学上网/翻墙代理节点的完整手册 —— sing-box 内核 + VLESS+Reality(TCP 443)、Hysteria2(UDP)、Cloudflare Argo 隧道 CDN 中转(隐藏源站 IP),外加 VPS 系统加固、OpenClash/Clash/Shadowrocket 客户端导入、Sub-Store 订阅聚合。当用户提到"配代理节点、搭 VPS 翻墙、装 sing-box、Reality/Hysteria2/hy2、Argo/cloudflared 隧道、加固服务器、节点连不上/被墙/握手失败、客户端导入、订阅聚合"等场景时都应使用本 skill,即使没明说"部署节点"也要主动触发。这是一份生产级、可直接照做的多协议节点部署实操指南。
---

# VPS 代理节点部署手册

在一台海外 VPS 上部署高抗封锁、高速、可隐藏源站 IP 的翻墙代理节点。本手册是多机部署实践沉淀的实操流程,拿来即可照做。

> **凭据约定**:本仓库(私有)里所有 `<占位符>`(UUID、Reality 公私钥、shortId、Hysteria2 口令、CF API Token、连接器 Token、SSH 私钥路径)都是占位,**真实密钥永远不写进任何 git 仓库**,按文中命令现场生成、只留在服务器 `/etc/sing-box/` 和本地。

## 什么时候用哪套协议(先读这里)

三套协议不是二选一,而是**同一台机上都开、按线路质量分工**:

| 协议 | 传输 | 端口 | 定位 | 什么时候用 |
|---|---|---|---|---|
| **VLESS + Reality** | TCP | 443 | 主力抗封锁 | 首选。借真大厂 TLS 指纹伪装,免域名免证书,抗主动探测最强 |
| **Hysteria2** | QUIC / UDP | 8882 | 主打速度 | 弱网、移动网络、大带宽下载;UDP 被 QoS 时的补充 |
| **VLESS + WS + Argo CDN** | TCP over CF | 443(经 CF) | 保底 + 隐藏 IP | 源站 IP 被针对性干扰时的保底通道;客户端连 CF 边缘,VPS 真实 IP 全程不暴露 |

**选路经验(极重要,踩过 2 小时坑)**:并非所有 VPS 都能跑通 Reality TCP。**部分线路(实测:某些「中国 → 美东」线路)会干扰 Reality 的 TLS 握手**,同样的配置换到香港 / 美西等线路却完全正常 —— 这是**路径问题不是配置问题**。这种机器 TCP 直连跑不通就**只开 CDN 中转**(经 Cloudflare 边缘绕开被干扰的直连路径)。部署后务必按 [references/troubleshooting.md](references/troubleshooting.md) 的方法逐协议验证出口。

## 标准部署流程(6 步)

按顺序做。每步的完整命令 / 配置见对应 reference 文件。

### 第 1 步:VPS 系统加固
先把机器锁死再装服务。见 [references/hardening.md](references/hardening.md)。要点:
- SSH 改**高位端口**(如 39000)、**仅密钥登录**、禁密码登录、禁 root 密码登录。
- `ufw` 只放行 SSH 端口 + 443(+ Hysteria2 的 UDP 端口)。
- 装 `fail2ban`、校准 NTP、设时区 `Asia/Shanghai`、开 BBR 拥塞控制。

### 第 2 步:装 sing-box(版本是生死线)
**必须用 `sing-box 1.14.0-alpha.29`**,不能用官方脚本默认装的 1.13.x。
- 原因:1.13.x 的 Reality 实现与 mihomo(Clash.Meta)alpha 内核**100% 不兼容**,客户端日志会刷 `REALITY: processed invalid connection`,**换密钥也没用**,纯版本问题。
- **生成密钥也必须用 1.14 的二进制**(不同版本密钥格式/曲线处理有别)。
- 装法与服务配置见 [references/singbox-install.md](references/singbox-install.md)。**关键坑**:systemd unit 里**去掉 `User=sing-box` 改用 root 跑**,否则起不来报 `status=217/USER`。

### 第 3 步:配 VLESS + Reality(主力,TCP 443)
见 [references/reality.md](references/reality.md)。单文件 `/etc/sing-box/config.json`,`dest`/`server_name` 借用一个真实可达的大厂站点(`www.microsoft.com`、`www.apple.com` 等)。

### 第 4 步:配 Hysteria2(速度,UDP)
见 [references/hysteria2.md](references/hysteria2.md)。与 Reality 共用同一份 config.json,加一个 inbound。UDP 端口记得在 `ufw` 放行。

### 第 5 步:配 Cloudflare Argo CDN 中转(隐藏源站 IP)
见 [references/argo-cdn.md](references/argo-cdn.md)。sing-box 起一个 `VLESS+WS` inbound 监听 `127.0.0.1:8001`(path 用 uuid 前 8 位,复用 Reality 的 uuid);`cloudflared` 用连接器 token 把 `你的域名` → 本地 8001。客户端连的是 CF 边缘,VPS IP 全程隐藏。

### 第 6 步:客户端导入 + 订阅聚合
见 [references/clients.md](references/clients.md)。OpenClash / Clash 系 / Shadowrocket 各自导入方式 + Sub-Store 把多机场 + 自建节点聚合成一条订阅。

## 验证(每装完一个协议就验一次)
**不要靠"客户端显示已连接"判断成功**,要验真实出口 IP:
- 客户端设 socks5(如 mihomo `127.0.0.1:7891`),`curl -x socks5h://127.0.0.1:7891 https://www.cloudflare.com/cdn-cgi/trace` 看 `ip=` 是否为该 VPS 出口。
- mihomo 的 `/proxies/<名>/delay` 测速 API 在部分环境对所有节点都失败,**别依赖它**,用上面的 socks5 出口法。
- 验 AI(Claude/ChatGPT)走对节点时,注意 `claude.ai` 常有独立分流规则会绕开你临时设的选择链 —— 用通用域名(cloudflare trace)测,或直接确认 Claude 专用组的出口。

完整排障清单见 [references/troubleshooting.md](references/troubleshooting.md)。

## 参考文件索引
- [references/hardening.md](references/hardening.md) —— VPS 加固(SSH/ufw/fail2ban/BBR)
- [references/singbox-install.md](references/singbox-install.md) —— sing-box 1.14 安装 + systemd + 密钥生成
- [references/reality.md](references/reality.md) —— VLESS+Reality TCP 服务端配置
- [references/hysteria2.md](references/hysteria2.md) —— Hysteria2 UDP 服务端配置
- [references/argo-cdn.md](references/argo-cdn.md) —— Cloudflare Argo 隧道 CDN 中转(CF API 建隧道全流程)
- [references/clients.md](references/clients.md) —— OpenClash/Clash/Shadowrocket 导入 + Sub-Store 聚合
- [references/troubleshooting.md](references/troubleshooting.md) —— 真实踩坑与排障清单
