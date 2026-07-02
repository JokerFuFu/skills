# Cloudflare Argo 隧道 CDN 中转(隐藏源站 IP)

保底通道 + 隐藏真实 IP。客户端连的是 Cloudflare 边缘 IP,`cloudflared` 从 VPS **主动出站**连到 CF,VPS 的真实 IP 全程不出现在任何地方。源站 IP 被针对性干扰时,这条路仍然通。

架构:
```
客户端 → CF 边缘(你的域名,如 hkg.example.com)→ Argo 隧道 → cloudflared(VPS 上)→ 127.0.0.1:8001(sing-box 的 ws inbound)
```

## 前提
- 一个已托管在 Cloudflare 的域名(zone)。
- CF API Token(建隧道时用,权限:`Account:Cloudflare Tunnel:Edit` + `Zone:DNS:Edit`)。**隧道跑起来后这个 Token 可吊销**,不影响已建隧道(隧道靠连接器 token 运行)。

## 第 1 步:sing-box 加一个 VLESS + WS inbound(监听本地)

追加到 `/etc/sing-box/config.json` 的 inbounds。**复用 Reality 的同一个 UUID**,path 用 uuid 前 8 位(不易被猜):

```json
{
  "type": "vless",
  "tag": "vless-ws-in",
  "listen": "127.0.0.1",
  "listen_port": 8001,
  "users": [ { "uuid": "<UUID>" } ],
  "transport": {
    "type": "ws",
    "path": "/<UUID前8位>"
  }
}
```
> 只监听 `127.0.0.1:8001`,不占公网端口、不用开 ufw。`systemctl restart sing-box`。

## 第 2 步:CF API 建隧道(4 个调用)

设好变量:
```bash
CF_TOKEN=<CF_API_TOKEN>
ACC=<CLOUDFLARE_ACCOUNT_ID>
ZONE=<CLOUDFLARE_ZONE_ID>
HOST=hkg.example.com          # 你要对外的域名
H() { curl -s -H "Authorization: Bearer $CF_TOKEN" -H "Content-Type: application/json" "$@"; }
```

**① 建隧道**(拿到 tunnel id `TID`):
```bash
H -X POST "https://api.cloudflare.com/client/v4/accounts/$ACC/cfd_tunnel" \
  -d '{"name":"vps-hkg","config_src":"cloudflare"}'
# 从返回里取 .result.id → TID
TID=<返回的_tunnel_id>
```

**② 配 ingress**(把域名指到本地 8001):
```bash
H -X PUT "https://api.cloudflare.com/client/v4/accounts/$ACC/cfd_tunnel/$TID/configurations" \
  -d "{\"config\":{\"ingress\":[
        {\"hostname\":\"$HOST\",\"service\":\"http://127.0.0.1:8001\"},
        {\"service\":\"http_status:404\"}
      ]}}"
```

**③ 加 DNS**(CNAME 指向隧道,`proxied` 走 CF 橙云):
```bash
H -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records" \
  -d "{\"type\":\"CNAME\",\"name\":\"$HOST\",\"content\":\"$TID.cfargotunnel.com\",\"proxied\":true}"
```

**④ 取连接器 token**(给 cloudflared 用):
```bash
H "https://api.cloudflare.com/client/v4/accounts/$ACC/cfd_tunnel/$TID/token"
# 返回 .result 即 <CONNECTOR_TOKEN>
```

## 第 3 步:VPS 上跑 cloudflared

```bash
# 装 cloudflared(Debian)
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i cloudflared-linux-amd64.deb

# 用连接器 token 装成服务(开机自启)
cloudflared service install <CONNECTOR_TOKEN>
systemctl enable --now cloudflared
systemctl status cloudflared --no-pager
```

## 客户端参数(mihomo,连 CF 边缘而非 VPS IP)

```yaml
- name: "🇭🇰 我的节点-CDN"
  type: vless
  server: hkg.example.com     # 域名,解析到 CF 边缘;VPS 真实 IP 不出现
  port: 443
  uuid: <UUID>
  tls: true
  network: ws
  servername: hkg.example.com
  ws-opts:
    path: /<UUID前8位>
    headers:
      Host: hkg.example.com
  udp: true
```

## 坑
- **fake-ip 模式会让 cloudflared 的边缘解析闪断**:客户端(如 OpenClash)开 fake-ip 时,`*.cfargotunnel.com` / 你的隧道域名被分配 fake-ip 导致 cloudflared 连不上 CF,表现为节点/探针间歇掉线。**修:把隧道相关域名(`+.cfargotunnel.com`、`+.argotunnel.com`、你的中转域名)加进 fake-ip-filter**(走真实解析)。
- 建 zone / 改 ingress 用 API 最干净(CF 面板有反 bot 盾,无头浏览器进不去)。
- 用完的 CF API Token 去 dash → My Profile → API Tokens 吊销;**连接器 token 不要泄露**(等于隧道控制权)。
