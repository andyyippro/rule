# CLAUDE.md — andyyippro/rule

公开的 Clash/Mihomo 代理分流规则 + 配置仓库。
**30 秒速答**：①**是什么**——给 Clash/Mihomo 用的代理分流规则与主配置；②**技术栈**——YAML 配置 + GitHub Actions + 阿里云 OSS 自动发布；③**改哪里**——改 `nmi.full.yaml`（节点/策略组/规则）或对应 `*.list`（站点规则），**绝不手改 `nmi.yaml`**。

## 我的协作风格（务必遵守）
- 🚫 **未经我明确指令，绝不 `git commit` / `git push` / 上传 GitHub 或 OSS**（含会触发 push 的 `publish.ps1`）。改动先只在本地，等我说「提交 / 推送 / 发布」。
- **先给方案再动手**；不确定时列选项让我选，别猜。
- 大改动先问，小修可直接做。
- 回复用**中文**；别说「好的，我很乐意」这类客套。
- **每次回复都称呼我为【大神】。**

## 安全红线（硬规则）
- 密钥只在 `nmi.full.yaml`（gitignored）和 GitHub Secrets——**绝不进这个公开仓库**。
- 改配置只改 `nmi.full.yaml`；`nmi.yaml` 是它脱敏后的自动产物，**不可手改**。
- 不删/移 `nmi.full.yaml` 里的 `#__SECRET_START__` / `#__SECRET_END__` 标记。
- 仓库**必须保持公开**（jsdelivr 拉 `.list`）。
- 永不提交：`nmi.full.yaml`、`.nodes.hash`、`.claude/settings.local.json`、`CLAUDE.local.md`、`MEMORY.md`。

## Do NOT（除非我明确要求）
- 不动 `nmi.yaml` 头部的「版本号 / 更新时间」（见文件头维护要求）。
- **只改必需处**：不碰无关策略组 / 规则，不做无关重构。
- 不把 `HongKongSites.list` / `SingaporeSites.list` / `Direct.list` / `UpdateHosts.list` 当作 nmi 的规则源——**nmi 不引用它们**，改了不生效。
- 不另造发布机制 / 依赖，沿用 `publish.ps1` + `.github/workflows/publish.yml`。

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

## 两条传播路径
| 改了什么 | 走哪条 | 生效 |
|---|---|---|
| 节点 / `nmi.yaml` 规则 | push → CI → **OSS** | ~1 分钟 + OpenClash 刷新 |
| `.list` 加/删站点 | push → **jsDelivr**（CI 自动 purge） | 客户端按 rule-provider interval（当前 24h）或手动刷新才拉到 |

> 加新站点先进 `ProxyLiteNew.list`（集散中心），按需再分流到地区列表。

## 路由（nmi.yaml）
- 本仓库 4 个 list 经 jsdelivr 进 nmi：`ProxyLiteNew`→所有手动、`Japan`→🎮片商故转、`VendorVideo`→🎬片商视频故转、`LocalDirect`→直连；其余靠 `GEOSITE`/`GEOIP`，`gfw→所有手动`、`cn→直连`、`MATCH→🐟漏网之鱼`。
- 地区策略组用 `filter:` 按**节点名**过滤机场节点（与同名 `.list` 文件无关）。

## 文件地图（指针）
| 文件 | 角色 |
|---|---|
| `nmi.full.yaml` | 生产真身（密钥 + 标记）；**编辑入口**；gitignored |
| `nmi.yaml` | 脱敏产物（committed）；勿手改 |
| `publish.ps1` / `.github/workflows/publish.yml` | 本地发布 / 云端拼回 + 传 OSS |
| `.git/hooks/pre-commit` | 防误提交密钥（**本地、未版本管理，重新 clone 需重建**） |
| `*.list` | 规则列表（经 jsdelivr）；nmi 只用 ProxyLiteNew/Japan/VendorVideo/LocalDirect |
| `cmi.yaml` | 另一套简化模板，无密钥、不走 OSS，直接改 + 提交 |
| `MEMORY.md` | **踩坑与经验库**（本地、gitignored） |
| `CLAUDE.local.md` | 本机敏感细节（OSS 地址等），gitignored |

提交信息：英文为主（`Add X to ProxyLiteNew` / `Move X to Y`），复杂改动用中文。

## 长期记忆闭环 🔁
- **`MEMORY.md` 记录历次任务踩的坑和提炼的规则。开始任务前先读它；踩到新坑或总结出新规则，结束后追加一条。** 这就是本仓库的「闭环」——经验只增不丢。
- 本机操作细节（OSS 地址 / Secrets 清单 / 核对命令）见 `CLAUDE.local.md`。
