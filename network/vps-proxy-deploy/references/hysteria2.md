# Hysteria2(速度,UDP)

基于 QUIC/UDP,弱网、高丢包、移动网络下速度和稳定性优于 TCP 协议。作为 Reality 之外的第二条腿。

## 证书:自签即可
Hysteria2 需要 TLS,但客户端可以 `skip-cert-verify`,所以**自签证书**就够,不用真域名:

```bash
mkdir -p /etc/sing-box/cert
openssl ecparam -genkey -name prime256v1 -out /etc/sing-box/cert/key.pem
openssl req -new -x509 -days 3650 -key /etc/sing-box/cert/key.pem \
  -out /etc/sing-box/cert/cert.pem -subj "/CN=bing.com"
```

## 服务端配置(追加到 `/etc/sing-box/config.json` 的 inbounds 数组)

```json
{
  "type": "hysteria2",
  "tag": "hy2-in",
  "listen": "::",
  "listen_port": 8882,
  "users": [
    { "password": "<HY2_PASSWORD>" }
  ],
  "tls": {
    "enabled": true,
    "alpn": ["h3"],
    "certificate_path": "/etc/sing-box/cert/cert.pem",
    "key_path": "/etc/sing-box/cert/key.pem"
  }
}
```

> 端口 8882 记得在 `ufw` 放行 **UDP**:`ufw allow 8882/udp`。
> 改完 `sing-box check -C /etc/sing-box && systemctl restart sing-box`。

## 客户端参数(mihomo / Clash.Meta)

```yaml
- name: "🇭🇰 我的节点-hy2"
  type: hysteria2
  server: <VPS_IP>
  port: 8882
  password: <HY2_PASSWORD>
  sni: bing.com
  skip-cert-verify: true
  up: "50 Mbps"      # 按你的带宽填,影响拥塞控制
  down: "200 Mbps"
```

## 分享链接(hysteria2 URI,给 Shadowrocket 等)

```
hysteria2://<HY2_PASSWORD>@<VPS_IP>:8882?insecure=1&sni=bing.com#我的节点-hy2
```

## 验证
```bash
curl -x socks5h://127.0.0.1:7891 https://www.cloudflare.com/cdn-cgi/trace | grep '^ip='
```
hy2 走 UDP,若客户端连不上先确认 `ufw` 放的是 **udp** 不是 tcp,以及运营商没把该 UDP 端口 QoS 掉(换个高位端口试)。
