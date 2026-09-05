# AGENTS.md — andyyippro/rule

公开的 Clash/Mihomo 代理分流规则 + 配置仓库。
**30 秒速答**：①**是什么**——给 Clash/Mihomo 用的代理分流规则与主配置；②**技术栈**——YAML 配置 + GitHub Actions + 阿里云 OSS 自动发布；③**改哪里**——原版改 `nmi.full.yaml`，OSS 独立副本改 `nmi-oss.full.yaml`，站点规则仍共用根目录 `*.list`；**绝不手改两份公开 nmi 产物**。

## 我的协作风格（务必遵守）
- 🚫 **未经我明确指令，绝不 `git commit` / `git push` / 上传 GitHub 或 OSS**（含会触发 push 的 `publish.ps1`）。改动先只在本地，等我说「提交 / 推送 / 发布」。
- **先给方案再动手**；不确定时列选项让我选，别猜。
- 大改动先问，小修可直接做。
- 回复用**中文**；别说「好的，我很乐意」这类客套。
- **每次回复都称呼我为【大神】。**

## 安全红线（硬规则）
- 密钥只在 `nmi.full.yaml`、`nmi-oss.full.yaml`（均 gitignored）和 GitHub Secrets——**绝不进这个公开仓库**。
- 原版只改 `nmi.full.yaml`，OSS 副本只改 `nmi-oss.full.yaml`；`nmi.yaml` / `nmi-oss.yaml` 都是脱敏产物，**不可手改**。
- 不删/移两份真身里的 `#__SECRET_START__` / `#__SECRET_END__` 标记；公开 OSS 副本必须保留唯一 `#__NODES_OSS__` 与节点 SHA-256 注释。
- 仓库**必须保持公开**（jsdelivr 拉 `.list`）。
- 永不提交：`nmi.full.yaml`、`nmi-oss.full.yaml`、`.nodes.hash`、`.Codex/settings.local.json`、`Codex.local.md`、`CLAUDE.local.md`、`MEMORY.md`。

## Do NOT（除非我明确要求）
- 不动 `nmi.yaml` 头部的「版本号 / 更新时间」（见文件头维护要求）。
- **只改必需处**：不碰无关策略组 / 规则，不做无关重构。
- 不把 `HongKongSites.list` / `SingaporeSites.list` / `Direct.list` / `UpdateHosts.list` 当作 nmi 的规则源——**nmi 不引用它们**，改了不生效。
- 原版沿用 `publish.ps1` + `.github/workflows/publish.yml`，不得让 OSS 副本改动或替代它们。

## 发布闭环（改配置 → 上线）
> 全程只在本地，**我说「发布」才 push**。
1. 改 `nmi.full.yaml`（真身，含密钥 + 标记）→ 本地导入 Clash 测试。
2. 派生脱敏版：用 `publish.ps1` 同款 strip（按 `#__SECRET_START/END__` 标记切，输出 **LF / UTF-8 无 BOM**）生成 `nmi.yaml`。
3. **只有改了节点（密钥区）**才 `gh secret set NMI_SECRET_BLOCK`（base64）+ 更新 `.nodes.hash`；只改规则跳过。
4. `git add nmi.yaml *.list` → commit → **push（需我指令）**。
5. CI（`publish.yml`）解码 `NMI_SECRET_BLOCK` 拼回真身 → YAML 校验 → `ossutil` 传 OSS（`--acl public-read`）。
6. 验证：`gh run watch <id>` 绿灯；`curl` OSS 与本地 `nmi.full.yaml`（去两行标记）`diff` 应**零漂移**。
7. OpenClash 刷新订阅生效。
- 一键替代：`.\publish.ps1 "说明"`（自动做 2–4，但它会 push——**需我指令**）。

## OSS 独立副本闭环
- `nmi-oss.full.yaml` → `publish-oss-copy.ps1` → `nmi-oss.yaml` → `publish-nmi-oss.yml` → 独立 OSS 对象；脚本会提交并 push，仍须明确授权。
- `publish-oss-copy.ps1 -ValidateOnly` 只在临时目录派生并全量校验，不改工作树、不设置 Secret、不暂存、不提交、不推送；首次对象键用 `-InitializeObjectKey`，正常发布前必须已有唯一当前键。轮换失败时本机同时保留当前 URL 与待同步 URL，必须先用 `-SyncRecordedObjectKey` 收敛，之后才允许发布；push 失败后仅允许按 gitignored 的 `.nmi-oss.pending-push` 所登记 SHA 精确补推送，其他 ahead 提交一律阻断。
- OSS 副本普通发布及对象键操作只允许 `main` 跟踪 `origin/main`，并要求 `origin` 唯一指向 GitHub `andyyippro/rule`；push 固定为 `origin HEAD:refs/heads/main`。`scripts/validate-oss-public-copies.py` 由发布脚本、pre-commit 与 CI 共用，对全部 6 个公开副本统一检查严格 YAML、注释/正文敏感值、URL 映射、OpenAI 专用规则、3600 秒间隔、自链接和 `ipxie` 例外；提交说明也在任何 Secret/commit 动作前通过标准输入检查，错误不回显原文。
- 发布脚本、pre-commit 与 CI 都先用固定安全/恶意 canary 确认共用校验器有效；校验器自身被暂存时，pre-commit 还要求暂存 blob 与工作树一致。固定副本集合同时要求 changelog 使用 `.md`，标题结构只接受唯一固定 ATX H1 和精确 ATX H2 发布章节，拒绝 Setext/HTML 标题及会制造解析差异的控制/行分隔符；所有发布日期逐项校验，`vX.Y.Z` 各段禁止前导零且版本号全局唯一。版本元数据分别按块级和完整行内代码上下文锁定，版本、日期和节点哈希还必须在 `nmi-oss.yaml` 的纯注释头部连续出现且彼此一致。
- OpenAI 专用规则首次上线时，nmi CI 临时调用 `--transition-copy-set`，只接受五份配置“全旧”或“全新”并拒绝部分采用；规则对象和新配置均验证成功后，把 CI 切回严格的 `--copy-set`。过渡参数保留用于可审计回滚，但最终 CI 不得继续使用。
- 普通 `publish-oss-copy.ps1` 始终使用严格校验；只有明确回滚 OpenAI 专用规则时才使用 `-AllowLegacyOpenAIRollback`，该开关仍拒绝部分采用，并可与 `-ValidateOnly` 组合预检，但不得与对象键操作组合。
- 节点块固定为 LF / UTF-8 无 BOM 且末尾不带换行，公开副本和真身各保留唯一 `NMI_OSS_NODES_SHA256`；CI 校验 `NMI_OSS_SECRET_BLOCK` 后才允许覆盖。
- `cmi-oss.yaml` 和 3 份 `-oss.ini` 是独立公开副本；第一方 `.list` 指向 OSS，INI 自身指向对应 GitHub Raw，`ipxie.yaml` 继续使用 jsDelivr。
- `cmi-oss.yaml` 初建时仅额外清理原版已有行尾空格，以通过提交检查；这是无语义的已记录差异，不得借机改动原版或其他配置。
- rule-provider 名称保持不变且不新增 `path`；[Mihomo rule-provider 文档](https://wiki.metacubex.one/config/rule-providers/)说明未配置 `path` 时会按新 URL 的 MD5 使用独立缓存文件。
- 9 个 `.list` 不复制 Git 源文件；`publish-rules-oss.yml` 只创建 OSS 对象副本，旧 `purge-jsdelivr.yml` 继续维护原版 jsDelivr 链路。`OpenAI.list` 只由 OSS 配置副本引用，虽然旧 purge 工作流也会清理其 jsDelivr 缓存，但原版配置行为不变。
- 副本对象键只允许 `subscriptions/<64位小写十六进制>/nmi-oss.yaml`；完整 URL 只记录在 `CLAUDE.local.md`。新 Secret 为 `NMI_OSS_SECRET_BLOCK`、`OSS_NMI_COPY_OBJECT_KEY`。
- 已知边界：9 个规则对象无法原子切换，公开读会产生 GET/流量费用，INI 副本依赖 GitHub Raw 可达性；失败只停用副本，未经授权不删副本文件、OSS 对象或 Secrets。

## 三条传播路径
| 改了什么 | 走哪条 | 生效 |
|---|---|---|
| 节点 / `nmi.yaml` 规则 | push → CI → **OSS** | ~1 分钟 + OpenClash 刷新 |
| `nmi-oss.yaml` 副本 | push → 独立 CI → **独立 OSS 对象** | ~1 分钟 + 独立订阅刷新 |
| `.list` 加/删站点 | push → **jsDelivr purge + OSS 规则副本**（两个独立工作流） | 原版按 24h；OSS 副本按 3600s，或手动刷新 |

> 加新站点通常先进 `ProxyLiteNew.list`（集散中心），按需再分流到地区列表；OpenAI 官方网络清单是专用例外，维护在 `OpenAI.list`，来源与 29 项逐项转换见 `OPENAI-RULES.md`。

## 路由（nmi.yaml）
- 本仓库 4 个 list 经 jsdelivr 进 nmi：`ProxyLiteNew`→所有手动、`Japan`→🎮片商故转、`VendorVideo`→🎬片商视频故转、`LocalDirect`→直连；其余靠 `GEOSITE`/`GEOIP`，`gfw→所有手动`、`cn→直连`、`MATCH→🐟漏网之鱼`。
- OSS nmi 副本额外使用 `OpenAI.list`→🤖 ChatGPT，并必须放在其他业务规则之前；原版 nmi 不引用它。
- 地区策略组用 `filter:` 按**节点名**过滤机场节点（与同名 `.list` 文件无关）。

## 文件地图（指针）
| 文件 | 角色 |
|---|---|
| `nmi.full.yaml` | 生产真身（密钥 + 标记）；**编辑入口**；gitignored |
| `nmi.yaml` | 脱敏产物（committed）；勿手改 |
| `publish.ps1` / `.github/workflows/publish.yml` | 本地发布 / 云端拼回 + 传 OSS |
| `nmi-oss.full.yaml` / `nmi-oss.yaml` | OSS 独立副本真身 / 脱敏产物；真身 gitignored，公开产物勿手改 |
| `publish-oss-copy.ps1` / `.github/workflows/publish-nmi-oss.yml` | OSS 副本本地派生 / 云端校验、拼回与发布 |
| `scripts/validate-oss-public-copies.py` | 供发布脚本、pre-commit、CI 共用的全部公开 OSS 副本安全校验器 |
| `.github/workflows/publish-rules-oss.yml` | 固定上传并逐字节验证 9 个共享 `.list` 的 OSS 对象副本 |
| `.git/hooks/pre-commit` | 防误提交密钥（**本地、未版本管理，重新 clone 需重建**） |
| `*.list` | 共享规则源（jsDelivr 原链路 + OSS 对象副本）；原版 nmi 用 4 个，OSS nmi 另用 OpenAI |
| `OPENAI-RULES.md` | OpenAI 官方清单、29 项逐项转换、GEOSITE 对比和后续更新步骤 |
| `cmi.yaml` / `cmi-oss.yaml` | 原版简化模板 / OSS 独立副本 |
| `MEMORY.md` | **踩坑与经验库**（本地、gitignored） |
| `CLAUDE.local.md` | 本机敏感细节（OSS 地址等），gitignored |

提交信息：英文为主（`Add X to ProxyLiteNew` / `Move X to Y`），复杂改动用中文。

## 长期记忆闭环 🔁
- **`MEMORY.md` 记录历次任务踩的坑和提炼的规则。开始任务前先读它；踩到新坑或总结出新规则，结束后追加一条。** 这就是本仓库的「闭环」——经验只增不丢。
- 本机操作细节（OSS 地址 / Secrets 清单 / 核对命令）见 `CLAUDE.local.md`。
