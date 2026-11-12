# adblock-dns-aggregator

从一手规则源聚合广告/追踪域名，产出 mosdns、AdGuard、dnsmasq、smartdns 四种格式的 lite / full / cn 三档清单，每日由 GitHub Actions 构建并发布到 `output` 分支。

## 它解决什么

直接引用别人的聚合产物有三个绕不开的问题：

1. **父域冗余**：mosdns 等客户端按域名后缀匹配，清单里同时有 `doubleclick.net` 和 `ads.doubleclick.net` 时，后者是死条目，白占内存和加载时间；
2. **白名单表达不了**：拦截集里有父域、想只放行某个子域时，纯 URL 清单做不到；
3. **源组合和更新节奏受制于上游**。

本项目在"后缀匹配"语义下做白名单优先扣除与父域折叠，源清单、白名单、折叠开关都在本仓库里，可自行增删。

## 产物

| 文件 | 格式 |
|---|---|
| `mosdns-lite.txt` / `mosdns-full.txt` / `mosdns-cn.txt` | 纯域名，一行一个 |
| `adguard-lite.txt` / `adguard-full.txt` / `adguard-cn.txt` | `\|\|domain^` |
| `dnsmasq-lite.conf` / `dnsmasq-full.conf` / `dnsmasq-cn.conf` | `address=/domain/0.0.0.0` |
| `smartdns-lite.conf` / `smartdns-full.conf` / `smartdns-cn.conf` | `address /domain/#` |
| `manifest.json` | 生成时间、各源状态与条数、折叠前后条数、sha256 |

档位含义：

- `lite`：中文主力源 + HaGeZi Light，约 15.6 万条；
- `full`：全部启用源，约 34.9 万条；
- `cn`：只含国内源（anti-AD + AWAvenue），约 10.2 万条，供国内用户单独订阅。

国内/国外按**源**划分而不是逐个域名判定：广告域名多挂在 `.com` 或 CDN 下，用 TLD 或社区中国域名表归类误差很大；源级拆分是近似，但可解释、可维护。`cn` 档里仍会混有少量国外广告域名。

产物文件名带格式前缀，因为 mosdns 按 URL 的 basename 落地规则文件，同名会互相覆盖。

## 使用方式

仓库发布在 `output` 分支，可被路由器直接 URL 引用：

```text
# mosdns（ad_source 填 URL）
https://raw.githubusercontent.com/DenzelVincent/adblock-dns-aggregator/output/mosdns-lite.txt

# 国内用户只订国内源
https://raw.githubusercontent.com/DenzelVincent/adblock-dns-aggregator/output/mosdns-cn.txt

# 走 gh-proxy 时在地址前加 https://gh-proxy.com/
```

- **AdGuard Home**：订阅 `https://raw.githubusercontent.com/DenzelVincent/adblock-dns-aggregator/output/adguard-full.txt`
- **dnsmasq**：`conf-file=` 指向 `dnsmasq-lite.conf`
- **smartdns**：`conf-file` 指向 `smartdns-lite.conf`

> mosdns 的 `update_adlist` 在任一 URL 下载失败时会整轮放弃，且按 basename 落地，同一份清单不要同时加两个格式文件。

## 配置

- `config.yaml`：折叠开关、并发、超时、重试、哨兵阈值；
- `sources.yaml`：唯一的源事实来源，`license` 必填；
- `whitelist.txt`：手工放行，一行一个域名，自动覆盖其子域。

白名单始终先于父域折叠生效，且不受 `fold` 开关影响。父域被白名单顶掉后，其下未被白名单覆盖的子域条目若来自其它源，会保留继续生效（宁可漏拦，不可误杀）。

## 默认源

| 源 | 仓库 | 许可证 | 格式 | 档位 |
|---|---|---|---|---|
| anti-AD | [privacy-protection-tools/anti-AD](https://github.com/privacy-protection-tools/anti-AD) | MIT | plain | lite, full, cn |
| AWAvenue-Ads-Rule | [TG-Twilight/AWAvenue-Ads-Rule](https://github.com/TG-Twilight/AWAvenue-Ads-Rule) | GPL-3.0 | adguard | lite, full, cn |
| hagezi-light | [hagezi/dns-blocklists](https://github.com/hagezi/dns-blocklists) | GPL-3.0 | adguard | lite, full |
| hagezi-pro | [hagezi/dns-blocklists](https://github.com/hagezi/dns-blocklists) | GPL-3.0 | adguard | full |
| Cats-Team-AdRules | [Cats-Team/AdRules](https://github.com/Cats-Team/AdRules) | 0BSD | mosdns | full |

只收录允许再分发的源；CC-BY-NC / CC-BY-ND 类源不接受，构建时缺少 `license` 字段直接报错。

## 本地运行

```bash
pip install -r requirements.txt pytest
python -m pytest -q
python -m aggregator --out dist
```

手动覆盖折叠开关：

```bash
python -m aggregator --out dist --no-fold
```

## 构建流程

GitHub Actions 每日 20:00 UTC（北京 04:00）触发：

1. 跑 pytest，失败则不构建；
2. 下载所有源，单源失败只记录不中断；解析出 0 条视同失败；
3. 生成产物与 `manifest.json`；
4. 哨兵：任一产物条数低于上一版 80% 即失败，不推送；
5. 切到 `output` 分支（不存在则建 orphan），单提交强推。强推只作用于该专用分支。

手动触发可用 `fold` 入参覆盖当次折叠开关，`default` 回落到 `config.yaml`。

## 许可证

代码部分为 MIT。产物编译自上表各源，著作权归各原项目，按各自许可证再分发；文件头注明来源与生成信息。
