# 客户端导入 + 订阅聚合

## OpenClash(旁路由 / 软路由,mihomo 内核)
把节点写进 OpenClash 的运行配置(如 `/etc/openclash/config/xxx.yaml`)的 `proxies` 段(格式见各协议 reference 的"客户端参数")。

- **改完必须 `重启` 而非 `reload`**:`/etc/init.d/openclash restart`。reload 不会重新生成运行配置,改动不生效。
- **fake-ip 模式**下,凡是"域名类"节点地址(CDN 中转域名、`*.cfargotunnel.com`)都要加进 `fake-ip-filter`,否则拿到 fake-ip 连不上(见 argo-cdn.md 的坑)。
- 分组建议:AI(Claude/ChatGPT)单独一个 `fallback` 组,成员放**低延迟、稳定、不易被风控**的节点(如美西自建 + 备用),规则里 Claude/OpenAI 域名直接指向它;普通流量走按地区的 `url-test`/`select` 组。
- **验证节点走对没有**:`claude.ai` 等常有独立分流规则,会绕开你临时改的"节点选择"链;用通用域名(`cloudflare trace`)测出口,或直接确认 AI 组本身的出口 IP。

## Clash 系(mihomo-party / Clash Verge / ClashX Meta 等,桌面)
直接订阅一条聚合 URL(见下方 Sub-Store),或手动把 `proxies` + `proxy-groups` 粘进配置。桌面客户端一般默认 socks5 在 `127.0.0.1:7891`,验证:
```bash
curl -x socks5h://127.0.0.1:7891 https://www.cloudflare.com/cdn-cgi/trace
```

## Shadowrocket(iOS)
**坑:Shadowrocket 扫「base64 多节点」二维码没反应**,只认:
1. **单节点 URI**(`vless://...` / `hysteria2://...`),或
2. **订阅 URL**(推荐)。

做法:把多个节点 URI 逐行拼接 → base64 → 托管成一个 `.txt`,订阅该 URL:
```
https://<你的域名>/<16位随机>.txt      # 内容 = base64(节点URI 换行拼接)
```
- 二维码内容用 `sub://base64(订阅URL)`(Shadowrocket 的订阅 scheme);扫码无反应就手动 `+ → Subscribe → 粘贴 URL`。
- 改/加节点只改那个 txt,App 下拉更新即可。
- 规则配置(`.conf`)用 `#!MANAGED-CONFIG` 头 + 托管 URL,可每天自动更新;`[Proxy Group]` 用 `policy-regex-filter` 按地区从已加载订阅筛节点(通用,不写死具体节点)。

## Sub-Store 订阅聚合(多机场 + 自建节点合成一条)
用 Sub-Store 把多个机场订阅 + 自建 VPS 节点聚合、去重、改名、按地区/用途分组,输出成各端格式(ClashMeta / Shadowrocket / Surge / sing-box)的**一条订阅**。

- 部署:Docker(`xream/sub-store` 镜像)或 Node 直跑。前端 + 后端,后端 API 挂在一个随机 secret 路径下做访问控制。
- 自建节点做成一条 `local` 订阅(把各 VPS 的 `proxies` 抠出来),机场做成 `remote` 订阅,再合成一个 collection。
- 输出订阅:`.../<secret>/download/collection/<名>?target=ClashMeta`(换 `target=Shadowrocket/Surge/sing-box` 适配其它端)。
- **隐私**:订阅下载链接不能加交互式密码(客户端拉不了),靠**随机长 secret 路径**保护;管理后台可加 basic_auth。**最稳的是只在内网跑**(不暴露公网),客户端在内网更新订阅。
- 详细部署另见本人 `substore` 部署记录(内网 NAS Docker 版)。
