# 更新日志

当前版本：`v1.0.5`

## v1.0.5 - 2026-04-01

- 删除 `Proxy / Domain` 规则及对应远程规则提供者配置。
- 删除 `Sex / Domain` 规则及对应远程规则提供者配置。
- 删除不再使用的 `Sex` 策略组。

## v1.0.4 - 2026-04-01

- 删除 `UBI / Domain`、`Nintend / Domain` 游戏规则及对应远程规则提供者配置。
- 删除 `Crunchyroll / Domain`、`Popcorn / Domain` 流媒体规则及对应远程规则提供者配置。
- 删除 `Direct / Domain`、`Private / Domain` 国内规则及对应远程规则提供者配置。
- 删除未再使用的 `Block / Domain` 远程规则提供者配置。

## v1.0.3 - 2026-04-01

- 新增 `更新专用` 策略组，放置在 `proxy-groups` 末尾。
- 新增 `DOMAIN-SUFFIX,zodnext.com,更新专用` 规则。
- 将 `更新专用` 规则放到国内规则之前，确保优先于 `Direct / Domain`、`China / Domain`、`China / IP` 等规则命中。
- 保持 `proxy-providers` 区域不变，未添加远程 `Update / Domain` 规则提供者。

## v1.0.2 - 2026-04-01

- 将 `Claude` 规则从远程 `RULE-SET` 改为 Mihomo 原生规则：
  `GEOSITE,anthropic,AI`
- 删除不再使用的 `Claude / Domain` 远程规则提供者配置。
- 删除 `Groq` 相关规则及远程规则提供者配置。
- 删除 `Crypto` 策略组。
- 删除 `OKX`、`Bybit`、`Binance` 三条指向 `Crypto` 的规则及对应远程规则提供者配置。
- 删除 `Nvidia` 策略组。
- 删除 `RULE-SET,Nvidia / Domain,Nvidia` 规则。
- 删除 `Nvidia / Domain` 远程规则提供者配置。

## v1.0.1 - 2026-04-01

- 将 `clasmi.yaml` 重命名为 `cmi.yaml`。
- 将 `Test / Domain` 的规则源从 `gh-proxy.com` 调整为 `cdn.jsdelivr.net`：
  `https://cdn.jsdelivr.net/gh/liandu2024/clash@main/list/Check.list`
- 将 `ChatGPT` 规则从远程 `RULE-SET` 改为 Mihomo 原生规则：
  `GEOSITE,openai,AI`
- 删除不再使用的 `ChatGPT / Domain` 远程规则提供者配置。
- 当前这套 `ChatGPT` 改法已确认可以正常使用。
