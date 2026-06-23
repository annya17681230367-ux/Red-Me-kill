# 小红书运营代码资产清单

更新时间：2026-06-23

## 当前结论

当前项目已经是一个 Python 版小红书运营分析 Agent，已有基础链路：

微信/手动链接收集 -> 小红书笔记采集 -> SQLite 存档 -> 规则/LLM 分析 -> 日报/周报生成 -> 企业微信/微信/飞书推送 -> 本地定时运行。

目前还没有完成的路演目标包括：

- 高级模型分层接入。
- 根据爆贴分析生成三个业务号内容。
- 出图/改图节点第一版已接入：`generate-images` 可生成图片任务，配置 API 后可继续出图。
- 数据看板。
- 云服务器部署。
- 3 人 3 天真实测试记录。
- 路演反馈修改记录。
- 维护策略文档。

## 代码入口

| 文件 | 作用 | 当前状态 |
|---|---|---|
| `src/xhs_agent/cli.py` | 命令行主入口，负责同步、日报、周报、定时、微信导入、浏览器采集 | 已有 |
| `src/xhs_agent/__main__.py` | Python 模块启动入口 | 已有 |
| `scripts/xhs-agent.sh` | 本地运行脚本 | 已有 |
| `scripts/install_launch_agent.sh` | macOS 后台定时任务安装脚本 | 已有 |
| `scripts/start-wechat-collector.sh` | 微信复制收集入口脚本 | 已有 |
| `scripts/install_wechat_collector.sh` | 微信收集后台任务安装脚本 | 已有 |

## 核心业务模块

| 文件 | 作用 | 当前状态 |
|---|---|---|
| `src/xhs_agent/config.py` | 读取 `settings.toml`、账号表、手动链接、微信文本链接 | 已有 |
| `src/xhs_agent/models.py` | 账号、笔记、快照、分析结果等数据结构 | 已有 |
| `src/xhs_agent/repository.py` | SQLite 数据库建表、账号/链接/笔记/快照写入和查询 | 已有 |
| `src/xhs_agent/xhs_api.py` | 小红书 Ark API 适配层，缺少实际 `note_method` / `account_method` 时返回占位数据 | 已有，待补 API 方法 |
| `src/xhs_agent/xhs_browser.py` | 通过 Chrome 登录态读取小红书笔记内容和互动数据 | 已有 |
| `src/xhs_agent/xhs_hotspots.py` | 按留学生关键词采集小红书搜索热点 | 已有 |
| `src/xhs_agent/analysis.py` | 本地规则分析笔记质量、标题、正文、转化和复用动作 | 已有 |
| `src/xhs_agent/llm.py` | DeepSeek/Ollama 分析增强调用 | 已有，待升级模型分层 |
| `src/xhs_agent/image_generation.py` | 爆贴内容进入三个业务号封面图任务，并调用图片生成 API | 本次新增 |
| `src/xhs_agent/reports.py` | 生成日报/周报 Markdown、HTML、PDF | 已有 |
| `src/xhs_agent/messaging.py` | 企业微信、微信公众号、飞书报告发送聚合 | 已有 |
| `src/xhs_agent/feishu.py` | 飞书 API 消息读取/发送 | 已有 |
| `src/xhs_agent/wechat_capture.py` | 从微信复制内容导入小红书链接 | 已有 |
| `src/xhs_agent/scheduler.py` | 本地日报/周报定时运行 | 已有 |
| `src/xhs_agent/xhs_parse.py` | 小红书链接/内容解析辅助 | 已有 |

## 配置和知识库

| 文件 | 作用 | 是否应提交 GitHub |
|---|---|---|
| `config/settings.example.toml` | 配置模板，不含真实密钥 | 是 |
| `config/accounts.example.csv` | 账号表模板 | 是 |
| `config/accounts.csv` | 当前真实账号表 | 需要确认是否含敏感信息，谨慎提交 |
| `config/manual_links.example.csv` | 手动链接模板 | 是 |
| `knowledge/xhs_strategy.md` | 小红书运营规则知识库 | 是 |
| `knowledge/marketing_calendar.md` | 营销节点/日历 | 是 |

真实 API Key、Webhook、App Secret 应只放在 `config/settings.toml` 或服务器环境变量里，不提交 GitHub。

## 文档

| 文件 | 作用 | 当前状态 |
|---|---|---|
| `README.md` | 项目说明、安装、配置、运行方式 | 已有 |
| `docs/cloud-rewrite-plan.md` | 云端重写和任务化架构蓝图 | 已有，未纳入 Git |
| `docs/integration-notes.md` | 飞书、小红书 API 集成备注 | 已有 |
| `docs/roadshow-implementation-plan.md` | 路演前实现计划和验收标准 | 本次新增 |
| `docs/roadshow-feedback.md` | 第一次路演反馈修改记录模板 | 本次新增 |
| `docs/wechat-wecom-deployment.md` | 微信/企业微信部署说明 | 已有 |
| `docs/xhs_weekly_report_template.md` | 周报模板 | 已有 |
| `docs/code-inventory.md` | 当前代码资产清单 | 本次新增 |
| `MAINTENANCE.md` | 后期代码维护策略 | 本次新增 |

## 数据和产物

| 路径 | 内容 | 是否应提交 GitHub |
|---|---|---|
| `data/xhs_agent.sqlite3` | 本地数据库 | 否 |
| `data/manual_links.csv` | 手动收集的小红书链接 | 否，可能含业务数据 |
| `data/wechat_messages.txt` | 微信聊天文本 | 否，可能含隐私 |
| `data/reports/` | 日报/周报产物 | 否，可挑选脱敏样例 |
| `data/hotspots/` | 每日热点采集产物 | 否，可挑选脱敏样例 |
| `tmp/` | PDF 渲染检查图片等临时文件 | 否 |

`.gitignore` 已经排除了数据库、日志、报告、热点、微信文本、手动链接、虚拟环境和临时 Python 文件。

## 当前 Git 状态

当前分支：`main`

已修改但未提交：

- `src/xhs_agent/messaging.py`
  - 企业微信上传文件时，根据文件扩展名自动判断 MIME 类型。
- `src/xhs_agent/reports.py`
  - 日报/周报新增爆贴结构分析、内容评分、热点联动、选题建议、作者汇总和 PDF 兼容处理。
- `src/xhs_agent/xhs_browser.py`
  - 浏览器采集时尝试从页面正文提取作者/账号。
- `src/xhs_agent/cli.py`
  - 新增 `generate-images` 命令。
- `src/xhs_agent/config.py`
  - 新增 `[image_generation]` 配置。
- `src/xhs_agent/repository.py`
  - 新增图片任务和图片结果表。
- `src/xhs_agent/image_generation.py`
  - 新增 AI 图片生成节点。
- `README.md`
  - 增加 AI 图片生成节点使用说明。
- `config/settings.example.toml`
  - 增加图片生成 API 配置模板。

未纳入 Git：

- `docs/cloud-rewrite-plan.md`
- `docs/code-inventory.md`
- `docs/roadshow-implementation-plan.md`
- `docs/roadshow-feedback.md`
- `MAINTENANCE.md`
- `src/xhs_agent/image_generation.py`
- `tmp/`

建议：`tmp/` 不提交；文档确认后提交。

## 现有数据库结构

当前 SQLite 表：

- `accounts`：账号信息。
- `feishu_links`：从飞书/微信/手动表收集到的小红书链接。
- `note_metrics`：笔记当前指标。
- `note_metric_snapshots`：每次刷新后的笔记历史快照。
- `account_snapshots`：账号粉丝、关注、获赞收藏、笔记数、线索数快照。

下一阶段需要新增：

- `target_accounts`：三个业务号定位、人设、内容边界。
- `viral_analyses`：爆贴深度分析结果。
- `business_contents`：按三个业务号生成的选题、标题、正文、封面文案。
- `image_jobs`：出图/改图任务。
- `generated_images`：生成图片、版本、提示词、来源内容。
- `model_call_logs`：模型调用记录、成本、耗时、失败原因。
- `user_test_logs`：3 人 3 天测试记录和真实 bug。
- `roadshow_feedback`：第一次路演建议和修改状态。

## API 接入现状

已预留：

- 小红书 Ark API：`xhs_api.base_url`、`api_key`、`app_id`、`note_method`、`account_method`。
- DeepSeek：`llm.provider = "deepseek"`。
- Ollama 本地模型：`llm.provider = "ollama"`。
- 企业微信机器人 Webhook。
- 微信公众号客服消息。
- 飞书应用。

待完成：

- 确认小红书具体查询方法 `note_method` 和 `account_method`。
- 增加更高级模型配置，例如按任务区分“分析模型、内容生成模型、质检模型”。
- 增加图片生成/改图 API 配置。
- 增加模型调用日志，记录每次请求的任务、模型、耗时、结果和错误。

## 下一阶段开发顺序

1. 整理 GitHub 仓库
   - 确认不提交密钥、数据库、微信记录、真实客户隐私。
   - 提交代码、配置模板、知识库、文档。

2. 补齐高级模型分层
   - 普通清洗用低成本模型或规则。
   - 爆贴分析、业务号生成、选题判断用高级模型。
   - 图片提示词和审核单独记录。

3. 新增三个业务号内容生成
   - 输入：学生号爆贴和爆贴分析。
   - 输出：三个业务号各自的标题、正文、封面文案、发布建议。

4. 新增出图/改图节点
   - 输入：业务内容和封面提示词。
   - 输出：图片文件、版本记录、生成状态。

5. 新增数据看板
   - 总览、爆贴库、业务号内容库、图片库、任务状态、测试 bug 页面。

6. 云端部署
   - 第一版建议 Docker Compose。
   - 数据库建议 PostgreSQL。
   - 定时任务在云端运行，本地只看结果。

7. 路演验收
   - 至少 3 人连续使用超过 3 天。
   - 记录真实 bug 和修复状态。
   - 根据第一次路演建议修改。
   - 补齐 `MAINTENANCE.md`。
