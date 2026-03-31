# 更新日志

当前版本：`v1.0.2`

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
