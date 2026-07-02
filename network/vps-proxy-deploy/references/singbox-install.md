# 安装 sing-box 1.14 + systemd + 密钥生成

## 版本是生死线

**必须 `sing-box 1.14.0-alpha.29`**,不要用官方一键脚本默认装的 `1.13.x`。

- **为什么**:1.13.x 的 Reality 与 mihomo / Clash.Meta 的 alpha 内核**完全不兼容**。客户端会连不上,服务端/客户端日志刷:
  ```
  REALITY: processed invalid connection
  ```
  **换 UUID、换密钥都没用**,纯粹是版本问题。1.14.0-alpha.29 是实测与 mihomo alpha 核互通的版本。
- **生成 Reality 密钥也要用 1.14 的二进制**,不同版本密钥处理有差异。

## 安装方式

### 方式 A:从已知可用的机器直接拷贝二进制(最稳)
如果手上已有一台跑着正确版本的机器,直接把二进制拷过去,版本 100% 一致:

```bash
# 从源机 srchost 把二进制传到目标机 dsthost(经本地中转,SFTP 不可用时用 cat 管道)
ssh srchost 'cat /usr/bin/sing-box' | ssh dsthost 'cat > /usr/bin/sing-box && chmod +x /usr/bin/sing-box'
ssh dsthost '/usr/bin/sing-box version'   # 确认 1.14.0-alpha.29
```

### 方式 B:从 GitHub Releases 下指定版本
到 `github.com/SagerNet/sing-box/releases` 找 `v1.14.0-alpha.29`,下对应架构(通常 `linux-amd64`)的 tar:

```bash
cd /tmp
VER=1.14.0-alpha.29
wget https://github.com/SagerNet/sing-box/releases/download/v${VER}/sing-box-${VER}-linux-amd64.tar.gz
tar xzf sing-box-${VER}-linux-amd64.tar.gz
install -m755 sing-box-${VER}-linux-amd64/sing-box /usr/bin/sing-box
sing-box version
```

## 生成密钥材料(用 1.14 二进制)

```bash
# Reality 公私钥对
sing-box generate reality-keypair
# 输出:
#   PrivateKey: <REALITY_PRIVATE_KEY>   → 写进服务端 config
#   PublicKey:  <REALITY_PUBLIC_KEY>    → 给客户端用

# UUID(VLESS 用户 id;Reality 和 CDN 的 ws 复用同一个)
sing-box generate uuid          # → <UUID>

# shortId(Reality 短 id,1~8 字节 hex)
sing-box generate rand --hex 8  # → <SHORT_ID>

# Hysteria2 口令(随便一段强随机)
openssl rand -base64 16         # → <HY2_PASSWORD>
```

把生成的值填进 `/etc/sing-box/config.json`(见 reality.md / hysteria2.md / argo-cdn.md 的模板),**记录到本地私密处,不要提交进 git**。

## systemd 服务

```ini
# /etc/systemd/system/sing-box.service
[Unit]
Description=sing-box service
After=network.target nss-lookup.target

[Service]
# 关键坑:官方模板常带 User=sing-box / DynamicUser,会导致 status=217/USER 起不来。
# 直接用 root 跑最省事。
User=root
ExecStart=/usr/bin/sing-box -C /etc/sing-box run
Restart=on-failure
RestartSec=3
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
```

```bash
mkdir -p /etc/sing-box
# 把 config.json 放到 /etc/sing-box/config.json(-C 指目录,自动读该目录下 *.json)
sing-box check -C /etc/sing-box     # 校验配置语法
systemctl daemon-reload
systemctl enable --now sing-box
systemctl status sing-box --no-pager
journalctl -u sing-box -n 50 --no-pager   # 看有没有 217/USER 或 REALITY invalid
```

> `-C /etc/sing-box` 指的是**目录**,sing-box 会合并该目录下所有 `.json`。也可以 `-c /etc/sing-box/config.json` 指单文件。本手册用单文件 `config.json` 承载所有 inbound。
