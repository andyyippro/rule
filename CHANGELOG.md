# 更新日志

当前版本：`v1.0.1`

## v1.0.1 - 2026-04-01

- 将 `clasmi.yaml` 重命名为 `cmi.yaml`。
- 将 `Test / Domain` 的规则源从 `gh-proxy.com` 调整为 `cdn.jsdelivr.net`：
  `https://cdn.jsdelivr.net/gh/liandu2024/clash@main/list/Check.list`
- 将 `ChatGPT` 规则从远程 `RULE-SET` 改为 Mihomo 原生规则：
  `GEOSITE,openai,AI`
- 删除不再使用的 `ChatGPT / Domain` 远程规则提供者配置。
- 当前这套 `ChatGPT` 改法已确认可以正常使用。
