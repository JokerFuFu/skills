# 排障清单(真实踩坑)

## 1. Reality 连不上 / 日志刷 `REALITY: processed invalid connection`
这个报错有三个不同根因,**按下面的顺序查** —— 版本问题显眼、握手目标问题隐蔽,先查隐蔽的。

**判定前提**:如果 hysteria2 / CDN 中转同时是通的,说明机器、防火墙、UUID 都没问题,
问题一定在 Reality 这一层的三要素里:握手目标、内核版本配对、密钥。

### 1a. 握手目标选了 `www.microsoft.com`(最容易漏掉)
实测 12 次失败 3 次(25%)。密钥/short_id/UUID 全对也照样刷 invalid connection。
- **修**:换 `www.apple.com`。服务端 `reality.handshake.server` + `tls.server_name`、
  客户端 `servername`,**三处一起改**;顺手用当前版本二进制**重新生成 keypair**并同步客户端 `public-key`。

### 1b. 服务端与客户端内核版本配对错了
两者要成对,**不能交叉**:

| 服务端 sing-box | 配套客户端内核 |
|---|---|
| `1.13.x` | mihomo / Clash.Meta **正式版**(如 1.19.x) |
| `1.14.0-alpha.x` | **alpha 内核** |

症状与 1a 完全一样(换 UUID/密钥都没用),所以两条要一起排除。
**生成密钥必须用与服务端同版本的二进制。**

### 1c. 都对了还不通
→ 看第 2 条(线路干扰)。

## 2. 同样配置,某台机 Reality TCP 通、某台不通
这是**线路/路径问题,不是配置问题**。实测:**某些「中国 → 美东」线路会干扰 Reality 的 TLS 握手**,而香港、美西等线路同构配置完全正常。
- **判定**:香港/美西能通、只有某台不通,且该台 CDN 中转能通 → 就是直连路径被干扰。
- **修**:这台**放弃 Reality TCP 直连,改走 CDN 中转**(见 argo-cdn.md),并把 `ufw` 的 443/tcp 关掉,只留 SSH。

## 3. sing-box 起不来,`systemctl status` 报 `status=217/USER`
systemd unit 里带了 `User=sing-box` 或 `DynamicUser`,但该用户不存在 / 权限不足。
- **修**:unit 里改 `User=root`(见 singbox-install.md),`daemon-reload` 后重启。

## 4. 节点/探针经 CDN 隧道间歇掉线(530 / 1033 / 闪断)
客户端 **fake-ip 模式**把隧道域名(`*.cfargotunnel.com`、你的中转域名)也分了 fake-ip,导致 cloudflared 无法解析 CF 边缘。
- **修**:把 `+.cfargotunnel.com`、`+.argotunnel.com`、中转域名加进 `fake-ip-filter`。
- Komari 之类探针 agent 首次注册撞上闪断窗口会报 530/1033,`systemctl start` 重试几次赶上好窗口即可。

## 5. Hysteria2 连不上
- `ufw` 放的必须是 **udp**(`ufw allow 8882/udp`),不是 tcp。
- 运营商可能对某些 UDP 端口做 QoS/限速,**换一个高位 UDP 端口**试。
- 客户端 `up/down` 带宽填得离谱会影响拥塞控制,按真实带宽填。

## 6. "客户端显示已连接"但其实没走代理 / 走错节点
- **别信连接状态,验真实出口**:`curl -x socks5h://127.0.0.1:7891 https://www.cloudflare.com/cdn-cgi/trace` 看 `ip=`。
- **mihomo `/proxies/<名>/delay` 测速 API 在部分环境对所有节点都失败**,别拿它当连通性判据,用上面的 socks5 出口法。
- 验 AI 走没走对:`claude.ai`/`chatgpt.com` 常有独立分流规则,会绕开你临时设的选择链 → 直接确认 AI 专用组的出口,或用通用域名测。

## 7. 从 macOS 管内网/推文件的小坑
- macOS 换到非家庭网段时到内网(旁路由/NAS)无路由 → ping 不通、SSH `Connection closed`,不是防火墙封;回家庭网或起 VPN。
- BSD `sed -i` 要写成 `sed -i ''`。
- 部分 VPS 的 SFTP/scp 不可用 → 推文件用 `cat 本地文件 | ssh 目标 'cat > 远端文件'`。
- `pkill -f "关键词"` 可能误杀 SSH 会话自己的 shell(命令串含该关键词)→ 用 `pkill -x 进程名` 按进程名精确匹配。

## 8. 版本/命令速查
- 看 sing-box 版本:`sing-box version`(必须 `1.14.0-alpha.29`)
- 校验配置:`sing-box check -C /etc/sing-box`
- 看日志:`journalctl -u sing-box -n 80 --no-pager` / `journalctl -u cloudflared -n 80 --no-pager`
- 验 BBR:`sysctl net.ipv4.tcp_congestion_control`(应为 `bbr`)
