# CLAUDE.md — 项目须知（andyyippro/rule）

公开的 Clash/Mihomo 代理规则 + 配置仓库。**仓库必须保持公开**——`.list` 规则经 jsdelivr `/gh/` 分发，私有库拉不到。
本机操作细节（OSS 下载地址等）见 `CLAUDE.local.md`（本地、不公开）。

## ⚠️ 安全红线（最重要）

- **密钥只存在于 `nmi.full.yaml`（gitignored）和 GitHub Secrets，绝不提交到本公开仓库。**
- **改配置一律编辑 `nmi.full.yaml`，不要手改 `nmi.yaml`**——后者是脱敏产物，由前者自动生成。
- 不要删/移 `nmi.full.yaml` 里的 `#__SECRET_START__` / `#__SECRET_END__` 标记（发布管线靠它界定密钥区）。
- 这些已 gitignore，永不提交：`nmi.full.yaml`、`.nodes.hash`、`.claude/settings.local.json`、`CLAUDE.local.md`。

## 发布管线（nmi 配置如何上线）

```
编辑 nmi.full.yaml（真身，含密钥 + 标记）
   │  publish.ps1  或  Claude 代发
   ├─ 派生脱敏 nmi.yaml（密钥区 → 一行 #__NODES__）
   ├─ 若改了节点：密钥块 base64 → 同步 GitHub Secret NMI_SECRET_BLOCK（并更新 .nodes.hash）
   └─ git commit + push
        ▼
GitHub Actions（.github/workflows/publish.yml）
   解码 NMI_SECRET_BLOCK 拼回真身 → YAML 校验 → ossutil 传阿里云 OSS（--acl public-read）
        ▼
OpenClash 从 OSS 下载（URL 见 CLAUDE.local.md）
```

- push 到 GitHub 的**永远是脱敏版**；含密钥的真身**只在云端拼回并传 OSS**。
- 发布命令：`.\publish.ps1 "提交说明"`（本机需 `gh` 已登录、repo 权限）。
- **Claude 代发**：必须用与 `publish.ps1` **完全相同**的 strip 逻辑生成脱敏版（`#__SECRET_START/END__` 标记定位、LF 行尾、UTF-8 无 BOM），再 commit + push；依赖已配置的本地权限 `Bash(git push:*)`。
  **只有改了节点（密钥区）才需同步 `NMI_SECRET_BLOCK` + `.nodes.hash`；只改规则不用同步。**

## 两条传播路径（务必分清）

| 改了什么 | 走哪条 | 生效 |
|---------|-------|------|
| 节点 / `nmi.yaml` 的策略组·规则 | push → **GitHub Actions → OSS** | 云端约 1 分钟 + OpenClash 刷新 |
| `.list` 里加/删站点 | push → **jsdelivr CDN**（不经 OSS） | jsdelivr 缓存可达十几小时 |

> 日常往 `.list` 加站点走 jsdelivr，**不触发 OSS**。OSS 自动化只服务「改节点」和「改 nmi.yaml 规则结构」。

## 关键文件

| 文件 | 角色 |
|------|------|
| `nmi.full.yaml` | **生产主配置真身**（含密钥 + 标记）；**编辑入口**；gitignored |
| `nmi.yaml` | 脱敏产物（committed）；**勿手改** |
| `publish.ps1` | 本地一键发布 |
| `.github/workflows/publish.yml` | CI：拼回真身 + 校验 + 传 OSS |
| `.git/hooks/pre-commit` | 防误提交密钥（**本地、未版本管理；重新 clone 需重建**） |
| `*.list` | 规则列表（经 jsdelivr） |
| `cmi.yaml` | 另一套简化模板，**无密钥、不走 OSS 管线**，直接编辑 + 提交 |
| `CHANGELOG.md` / `nmi-CHANGELOG.md` | 版本日志 |
| 遗留少改 | `ipxie.yaml`、`qichiyubeifen.ini`、`bei260317.ini`、`README.md` |

## 路由（nmi.yaml）

- 本仓库 4 个 `.list` 经 jsdelivr 进 nmi（`rule-providers` + `rules`）：
  - `ProxyLiteNew.list` → `所有手动`
  - `JapanSites.list`（Japan）→ `🎮 片商故转`
  - `VendorVideoSites.list`（VendorVideo）→ `🎬 片商视频故转`
  - `LocalDirect.list` → `直连`
- 其余分流靠 `GEOSITE`/`GEOIP`（ChatGPT/Claude/YouTube/Google/Telegram…）；`GEOSITE,gfw → 所有手动`，`cn → 直连`，`MATCH → 🐟 漏网之鱼`。
- ⚠️ **`HongKongSites.list` / `SingaporeSites.list` / `Direct.list` / `UpdateHosts.list` 不被 nmi 引用**（供 cmi 或备用）——改它们**不影响 nmi**。
- 地区策略组（香港/日本/新加坡/台湾/美国 的 故转·手动·自动）是用 `filter:` **按节点名正则过滤机场节点**，**与同名 `.list` 文件无关**。
- 加新站点：先进 `ProxyLiteNew.list`（集散中心），按需再分流到地区列表。

## 维护约定

- 提交信息：英文为主（`Add X to ProxyLiteNew`、`Move X to Y`、`Update YYY`），复杂改动用中文。
- **版本号 / CHANGELOG / `nmi.yaml` 头部「更新时间·版本号」：只有用户明确要求时才动**（见 nmi.yaml 头部维护要求）。默认编辑不要碰。

## 发布验证

- `gh run watch <id>` 看 CI 绿灯。
- `curl` OSS 对象（地址见 `CLAUDE.local.md`）→ 与本地 `nmi.full.yaml`（去掉两行标记）`diff` 应**零漂移**。
- 改完 OpenClash 需刷新订阅才生效。

## 已知坑

- OSS bucket 必须**关闭「阻止公共访问」**，否则上传报 `Put public object acl is not allowed`。
- `git push` 会被 auto 模式「数据外泄」分类器拦——已用本地权限 `Bash(git push:*)` 放行。
- OSS 走直连无 CDN；若日后挂 CDN，需在 workflow 加 CDN 刷新步骤。
- CI 失败看 `gh run view <id> --log-failed`。
