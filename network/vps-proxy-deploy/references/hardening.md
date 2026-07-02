# VPS 系统加固

装代理服务**之前**先把机器锁死。以 Debian 11/12 为例(其它发行版命令类似)。

## 1. 基础环境

```bash
# 时区 + NTP
timedatectl set-timezone Asia/Shanghai
apt update && apt install -y chrony curl wget vim ufw fail2ban
systemctl enable --now chrony

# 开 BBR 拥塞控制(提升吞吐)
cat >> /etc/sysctl.conf <<'EOF'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
sysctl -p
# 验证:sysctl net.ipv4.tcp_congestion_control  应为 bbr
```

## 2. SSH 加固(改高位端口 + 仅密钥)

**先在本地生成密钥并把公钥传上去,确认能免密登录之后再禁密码**,否则会把自己锁在门外。

```bash
# 本地:生成专用密钥(如果还没有)
# ssh-keygen -t ed25519 -f ~/.ssh/vm-<别名> -C "vps-<别名>"
# 本地:传公钥
# ssh-copy-id -i ~/.ssh/vm-<别名>.pub -p 22 root@<VPS_IP>
```

服务器 `/etc/ssh/sshd_config`(或 `/etc/ssh/sshd_config.d/99-hardening.conf`):

```
Port 39000
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
```

```bash
systemctl restart ssh   # 或 sshd
```

本地 `~/.ssh/config` 加个别名,以后 `ssh <别名>` 直连:

```
Host <别名>
    HostName <VPS_IP>
    Port 39000
    User root
    IdentityFile ~/.ssh/vm-<别名>
```

## 3. 防火墙(ufw,最小放行)

只开必要端口:SSH 高位端口、Reality 的 443/TCP、Hysteria2 的 UDP 端口。**CDN 中转不占公网端口**(cloudflared 是出站连接,只连本地 8001),所以不用为 CDN 开任何入站口。

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 39000/tcp        # SSH
ufw allow 443/tcp          # VLESS+Reality
ufw allow 8882/udp         # Hysteria2
ufw --force enable
ufw status verbose
```

> 如果某台机器 Reality TCP 跑不通、决定改成 **CDN-only**,就把 `443/tcp` 关掉(`ufw delete allow 443/tcp`),只留 SSH,进一步缩小暴露面。

## 4. fail2ban(抗 SSH 爆破)

装好即用默认 `sshd` jail 就够;若改了 SSH 端口,建 `/etc/fail2ban/jail.local`:

```ini
[sshd]
enabled = true
port = 39000
maxretry = 5
bantime = 1h
```

```bash
systemctl enable --now fail2ban
fail2ban-client status sshd
```

## 加固检查清单
- [ ] `ssh <别名>` 免密能进,密码登录已拒(`PasswordAuthentication no`)
- [ ] `ufw status` 只列出 SSH + 代理端口
- [ ] `sysctl net.ipv4.tcp_congestion_control` = `bbr`
- [ ] `timedatectl` 时区正确、NTP 同步
- [ ] root 面板密码已改新(不写进任何文件,忘了走服务商面板重置)
