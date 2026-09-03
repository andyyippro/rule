# OpenAI / ChatGPT 专用规则来源与维护说明

核对日期：2026-09-03

官方来源：<https://help.openai.com/zh-hans-cn/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps>

运行规则：`OpenAI.list`

公开 OSS：<https://cclsst.oss-cn-shenzhen.aliyuncs.com/rules/OpenAI.list>

## 为什么单独维护

OSS 配置副本原先依靠 `GEOSITE,openai` 和 `GEOSITE,category-ai-!cn`。官方清单还包含 SendGrid、Intercom、WorkOS、Stripe、Sentry、Datadog、Apple 和 Cloudflare 等第三方域名，不能假设它们都被当前 GEOSITE 完整覆盖。

这些域名只加入 OSS 配置副本的专用 provider，并统一路由到现有的 `🤖 ChatGPT` 或 `AI` 策略组。原版配置不引用此规则，`ProxyLiteNew.list` 也不复制这些专用条目。

## 官方原始 29 项

```text
*.auth.openai.com
*.chatgpt.com
*.ct.sendgrid.net
*.intercom.io
*.intercomcdn.com
*.oaistatic.com
*.oaiusercontent.com
*.openai.com
*.oaistatsig.com
android.chat.openai.com
auth0.openai.com
cdn.openaimerge.com
cdn.workos.com
challenges.cloudflare.com
chat.openai.com
desktop.chat.openai.com
forwarder.workos.com
humb.apple.com
images.workoscdn.com
ios.chat.openai.com
js.intercomcdn.com
js.stripe.com
o207216.ingest.sentry.io
o33249.ingest.sentry.io
rum.browser-intake-datadoghq.com
setup.auth.openai.com
setup.workos.com
tcr9i.chat.openai.com
workos.imgix.net
```

## 29 项到 20 条规则的映射

| 官方项目 | 最终规则 |
|---|---|
| `*.auth.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `*.chatgpt.com` | `DOMAIN-SUFFIX,chatgpt.com` |
| `*.ct.sendgrid.net` | `DOMAIN-SUFFIX,ct.sendgrid.net` |
| `*.intercom.io` | `DOMAIN-SUFFIX,intercom.io` |
| `*.intercomcdn.com` | `DOMAIN-SUFFIX,intercomcdn.com` |
| `*.oaistatic.com` | `DOMAIN-SUFFIX,oaistatic.com` |
| `*.oaiusercontent.com` | `DOMAIN-SUFFIX,oaiusercontent.com` |
| `*.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `*.oaistatsig.com` | `DOMAIN-SUFFIX,oaistatsig.com` |
| `android.chat.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `auth0.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `cdn.openaimerge.com` | `DOMAIN,cdn.openaimerge.com` |
| `cdn.workos.com` | `DOMAIN,cdn.workos.com` |
| `challenges.cloudflare.com` | `DOMAIN,challenges.cloudflare.com` |
| `chat.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `desktop.chat.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `forwarder.workos.com` | `DOMAIN,forwarder.workos.com` |
| `humb.apple.com` | `DOMAIN,humb.apple.com` |
| `images.workoscdn.com` | `DOMAIN,images.workoscdn.com` |
| `ios.chat.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `js.intercomcdn.com` | `DOMAIN-SUFFIX,intercomcdn.com` |
| `js.stripe.com` | `DOMAIN,js.stripe.com` |
| `o207216.ingest.sentry.io` | `DOMAIN,o207216.ingest.sentry.io` |
| `o33249.ingest.sentry.io` | `DOMAIN,o33249.ingest.sentry.io` |
| `rum.browser-intake-datadoghq.com` | `DOMAIN,rum.browser-intake-datadoghq.com` |
| `setup.auth.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `setup.workos.com` | `DOMAIN,setup.workos.com` |
| `tcr9i.chat.openai.com` | `DOMAIN-SUFFIX,openai.com` |
| `workos.imgix.net` | `DOMAIN,workos.imgix.net` |

`DOMAIN-SUFFIX` 也会匹配根域，因此覆盖范围比官方的 `*.` 写法略大；这是有意选择，用于避免根域请求漏出专用策略。

## 最终 20 条规则

```text
DOMAIN-SUFFIX,chatgpt.com
DOMAIN-SUFFIX,openai.com
DOMAIN-SUFFIX,ct.sendgrid.net
DOMAIN-SUFFIX,intercom.io
DOMAIN-SUFFIX,intercomcdn.com
DOMAIN-SUFFIX,oaistatic.com
DOMAIN-SUFFIX,oaiusercontent.com
DOMAIN-SUFFIX,oaistatsig.com
DOMAIN,cdn.openaimerge.com
DOMAIN,cdn.workos.com
DOMAIN,challenges.cloudflare.com
DOMAIN,forwarder.workos.com
DOMAIN,humb.apple.com
DOMAIN,images.workoscdn.com
DOMAIN,js.stripe.com
DOMAIN,o207216.ingest.sentry.io
DOMAIN,o33249.ingest.sentry.io
DOMAIN,rum.browser-intake-datadoghq.com
DOMAIN,setup.workos.com
DOMAIN,workos.imgix.net
```

## 与现有规则的关系

2026-09-03 核对的 MetaCubeX `geosite/openai` 快照能覆盖官方清单中的 14 项，但它会随上游变化，不能替代本文件的固定官方快照：<https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geosite/openai.yaml>

`ProxyLiteNew.list` 已有 `DOMAIN-SUFFIX,cloudflare.com`，会与 `DOMAIN,challenges.cloudflare.com` 语义重叠。这条共享规则保持不变；OSS 配置必须把 `OpenAI / Domain` 放在其他业务规则之前，依靠从上到下的首条匹配确保该域名进入 ChatGPT/AI 策略组。

## 不在本次范围内

- `wss://ws.chatgpt.com` 已由 `DOMAIN-SUFFIX,chatgpt.com` 覆盖，但网络仍须允许 TCP 443 WebSocket Upgrade。
- ChatGPT 语音使用 UDP 3478 和会变化的 IP 范围，不固化进本域名文件。
- `register.appattest.apple.com` 是 iOS App Attest 的诊断地址，不属于官方 29 项允许清单，因此不加入。
- 本规则只能修正分流策略，不能修复节点波动、DNS、TLS 解密或设备侧问题。

## 更新步骤

1. 重新读取官方帮助页，保存核对日期和完整原始清单。
2. 只对明确的父域后缀做合并；第三方精确主机继续使用 `DOMAIN`。
3. 同一提交更新 `OpenAI.list`、本文档和校验器中的官方快照、映射及数量。
4. 运行共用校验器、YAML/INI 校验、敏感信息扫描和 `git diff --check`。
5. 先发布并逐字节验证 OSS 规则对象，再让配置副本引用它。
6. 重新生成或导入客户端配置，固定同一节点进行 iOS、Android 实际测试。

## 回滚步骤

1. 客户端先切回原版订阅，随后把 nmi OSS 工作流切回 `--transition-copy-set`。
2. 从采用前的公开 `nmi-oss.yaml` 加当前未变化的节点块，重建旧版 `nmi-oss.full.yaml`，并反向恢复其他公开副本和 changelog。
3. 先运行 `publish-oss-copy.ps1 -ValidateOnly -AllowLegacyOpenAIRollback`，通过后再以明确提交说明运行同一回滚开关完成派生和发布。
4. 不手改公开 nmi，不删除 `OpenAI.list`、OSS 对象或 Secrets；清理必须另行授权。
