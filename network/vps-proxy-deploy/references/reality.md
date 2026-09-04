# VLESS + Reality(主力,TCP 443)

抗封锁主力。借用一个真实大厂 HTTPS 站点的 TLS 指纹做伪装,**不需要自己的域名、不需要证书**,主动探测者看到的就是在访问那个大厂站点。

## 选 `dest` / `server_name`(伪装目标)
选一个**在该 VPS 上能正常 443 访问、且支持 TLS1.3 + H2** 的境外大站。

### ⚠️ 首选 `www.apple.com`,不要用 `www.apple.com`
实测数据(同一批机器、同构配置):拿 `www.apple.com` 作握手目标时 **12 次连接失败 3 次
(25% 失败率)**,表现为客户端延迟测试报 error、服务端刷 `REALITY: processed invalid connection`;
换成 `www.apple.com` 后一次打通、失败率归零。

这个坑极其隐蔽 —— 密钥、short_id、UUID 全都正确,hysteria2 和 CDN 中转同时正常,
唯独 Reality 不通,很容易误判成版本或密钥问题(见 troubleshooting.md 第 1 条)。

推荐顺序:`www.apple.com` > `www.cloudflare.com` > `www.amazon.com`。

要求:目标站与你 VPS 的地理/网络"看起来合理",且稳定。别选国内站或会被墙的站。

## 服务端配置(`/etc/sing-box/config.json` 的 inbound)

```json
{
  "inbounds": [
    {
      "type": "vless",
      "tag": "vless-reality-in",
      "listen": "::",
      "listen_port": 443,
      "users": [
        { "uuid": "<UUID>", "flow": "xtls-rprx-vision" }
      ],
      "tls": {
        "enabled": true,
        "server_name": "www.apple.com",
        "reality": {
          "enabled": true,
          "handshake": {
            "server": "www.apple.com",
            "server_port": 443
          },
          "private_key": "<REALITY_PRIVATE_KEY>",
          "short_id": ["<SHORT_ID>"]
        }
      }
    }
  ]
}
```

> `flow: xtls-rprx-vision` 是 Reality 的标配流控;客户端务必用同样的 flow。
> `server_name` 与 `handshake.server` 用同一个伪装域名。

## 客户端参数(给 mihomo / Clash.Meta)

```yaml
- name: "🇭🇰 我的节点-Reality"
  type: vless
  server: <VPS_IP>          # 直连用真实 IP;若走 CDN 见 argo-cdn.md
  port: 443
  uuid: <UUID>
  network: tcp
  tls: true
  udp: true
  flow: xtls-rprx-vision
  servername: www.apple.com     # = 服务端 server_name
  reality-opts:
    public-key: <REALITY_PUBLIC_KEY>  # = generate 出的 PublicKey
    short-id: <SHORT_ID>
  client-fingerprint: chrome
```

## 分享链接(VLESS URI,给 Shadowrocket / v2ray 系)

```
vless://<UUID>@<VPS_IP>:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.apple.com&fp=chrome&pbk=<REALITY_PUBLIC_KEY>&sid=<SHORT_ID>&type=tcp#我的节点-Reality
```

## 验证
```bash
# 客户端接上后,验出口是不是这台 VPS:
curl -x socks5h://127.0.0.1:7891 https://www.cloudflare.com/cdn-cgi/trace | grep '^ip='
```

**如果连不上 / 日志报 `REALITY: processed invalid connection`**:99% 是 sing-box 版本不对(见 singbox-install.md,必须 1.14.0-alpha.29)。若版本对还不通,考虑是**线路干扰了 TLS 握手**(见 troubleshooting.md),这台改走 CDN。
