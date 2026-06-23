# 小红书账号运营分析 Agent

这是一个可部署到本地电脑或服务器的自动化工作流，用微信作为小红书链接收集入口，用企业微信/微信作为报告输出载体，定时完成小红书账号内容分析、日报和周报。

## 工作流

1. 从微信群聊天记录文本或手动表读取成员转发的小红书笔记链接。
2. 识别链接、提交人、提交时间，并去重入库。
3. 通过小红书数据 API 抓取账号、笔记、互动、粉丝、私信线索等数据。
4. 使用运营分析规则生成每条笔记的诊断和优化建议。
5. 每日 13:00 分析昨日发布的小红书笔记，刷新互动数据后生成日报并发送企业微信群 PDF。
6. 每周三 15:00 生成运营周报，统计每个账号的发帖量、粉丝变化、互动变化、私信/线索变化，并给出下周策略。

## 目录

```text
config/
  accounts.example.csv      账号信息模板
  settings.example.toml     配置模板
data/
  .gitkeep                  本地数据库和报告输出目录
knowledge/
  xhs_strategy.md           小红书运营分析规则
src/xhs_agent/
  analysis.py               内容分析和运营建议
  cli.py                    命令入口
  config.py                 配置读取
  feishu.py                 飞书消息读取和发送
  models.py                 数据结构
  reports.py                日报/周报生成
  repository.py             SQLite 数据库
  scheduler.py              本地定时器
  xhs_api.py                小红书数据接口适配层
```

## 快速开始

1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 创建配置

```bash
cp config/settings.example.toml config/settings.toml
cp config/accounts.example.csv config/accounts.csv
```

3. 在 `config/settings.toml` 中填写：

```toml
[wechat_input]
enabled = true
transcript_path = "data/wechat_messages.txt"

[xhs_api]
base_url = "https://ark.xiaohongshu.com/ark/open_api/v3/common_controller"
app_id = "xiaohongshu-cli"
api_key = "xxx"
note_method = "填写查询笔记数据的 method"
account_method = "填写查询账号数据的 method"

[wecom]
enabled = true
webhook_url = "企业微信群机器人 Webhook"

[wechat_official_account]
enabled = true
app_id = "公众号/服务号 app_id"
app_secret = "公众号/服务号 app_secret"
openids = ["接收人 openid"]

[llm]
enabled = true
provider = "deepseek"
base_url = "https://api.deepseek.com"
api_key = "DeepSeek API Key"
model = "deepseek-v4-flash"
```

4. 在 `config/accounts.csv` 中填写账号、运营人员、主页链接、赛道。

可以把微信群聊天内容复制或导出到：

```text
data/wechat_messages.txt
```

系统会自动提取其中的小红书链接。也可以先把今晚大家发的小红书链接放进：

```text
data/manual_links.csv
```

字段支持 `url` 或 `note_id`，日报和周报会一起读取。

也可以直接从微信复制群消息后导入：

```bash
scripts/xhs-agent.sh wechat-import-clipboard
```

如果想持续监听复制动作：

```bash
scripts/xhs-agent.sh wechat-watch-clipboard
```

保持这个窗口运行，你在微信里复制包含小红书链接的消息后，系统会自动写入 `data/manual_links.csv`。

更清晰的收集入口：

```bash
scripts/start-wechat-collector.sh
```

如果要部署成后台常驻入口：

```bash
chmod +x scripts/install_wechat_collector.sh
scripts/install_wechat_collector.sh
```

部署后，你每天只需要在微信里复制当天群消息，系统会自动提取小红书链接并存档。

5. 先跑一次周报测试：

```bash
scripts/xhs-agent.sh weekly --dry-run
```

6. 正式启动本地定时任务：

```bash
scripts/xhs-agent.sh run
```

如果要部署成 macOS 后台任务：

```bash
chmod +x scripts/install_launch_agent.sh
scripts/install_launch_agent.sh
```

## 飞书应用需要的能力

飞书应用需要开启机器人能力，并确保机器人已经加入「学管部小红书发帖群」。建议申请这些权限：

- 获取群组中所有消息
- 获取单聊、群组的历史消息
- 以应用身份发送消息

## 小红书数据 API

当前项目预留了统一适配层 `src/xhs_agent/xhs_api.py`。你的 API 只需要能返回这些字段即可：

- 账号：粉丝数、关注数、获赞收藏数、笔记总数
- 笔记：标题、正文、发布时间、点赞、收藏、评论、分享、浏览、私信/线索数

如果 API 暂时没有私信字段，可以先留空，系统会把「评论+收藏+互动率」作为临时判断指标。

## 报告产物

报告会同时生成 Markdown 和 HTML：

```text
data/reports/daily-YYYY-MM-DD.md
data/reports/daily-YYYY-MM-DD.html
data/reports/weekly-YYYY-MM-DD.md
data/reports/weekly-YYYY-MM-DD.html
```

企业微信群内会直接发送 Markdown 报告正文。长报告会自动分段发送。

## 数据库存档

系统使用 SQLite 存档：

```text
data/xhs_agent.sqlite3
```

从 Agent 执行开始，会持续保存：

- 小红书链接提交记录
- 每条笔记当前指标
- 每次同步的笔记历史快照
- 每个账号的账号数据快照

日报和周报会按日/周输出爆贴榜。爆贴分按点赞、收藏、评论、分享和私信线索加权计算。

## 企业微信和微信

企业微信建议使用群机器人 Webhook，配置 `config/settings.toml` 的 `[wecom]` 后即可随日报/周报发送。

微信个人号没有官方普通群机器人接口。当前项目支持微信公众号/服务号客服消息通道，需要公众号 `app_id`、`app_secret` 和接收人的 `openid`。如果只是普通微信群，建议把企业微信客户群作为承接出口，或通过公众号菜单/客服消息承接。

## DeepSeek 内容分析模型

日报/周报里的内容分析模型可以接入 DeepSeek。配置 `[llm]` 后，每条笔记会先经过本地规则评分，再调用 DeepSeek 生成标题优化、封面建议、正文结构、评论区动作和私信承接建议。

如果 DeepSeek API Key 未配置、网络不可用或模型调用失败，系统会自动回退到本地规则分析，不会中断日报/周报。

如果想使用免费本地模型，可以安装 Ollama 并拉取模型，例如 `ollama pull deepseek-r1:7b`，然后改成：

```toml
[llm]
enabled = true
provider = "ollama"
ollama_base_url = "http://localhost:11434"
model = "deepseek-r1:7b"
```

本地模型不需要 DeepSeek API 余额，但需要本机持续运行 Ollama。

## AI 图片生成节点

系统已预留“爆贴分析后继续生成封面图”的节点。先在 `config/settings.toml` 中配置：

```toml
[image_generation]
enabled = true
provider = "openai_compatible"
base_url = "图片生成 API 地址"
api_key = "图片生成 API Key"
model = "图片生成模型"
output_dir = "data/generated_images"
timeout_seconds = 90
```

运行：

```bash
scripts/xhs-agent.sh generate-images --limit 3
```

这个节点会读取高互动笔记，为三个业务号生成封面图任务，并写入数据库：

- `image_jobs`：图片生成任务、状态、错误原因。
- `generated_images`：生成后的图片链接或本地图片路径。

如果图片 API 还没有配置，系统会先保留待执行任务，方便后续接通 API 后继续生成。

## 小红书浏览器采集

如果小红书 API 没有 `note_method/account_method`，可以用 Chrome 登录态兜底采集标题、正文和可见互动数据。

首次授权：

```bash
scripts/xhs-agent.sh xhs-browser-login
```

在打开的 Chrome 页面里登录小红书。登录完成后运行：

```bash
scripts/xhs-agent.sh xhs-browser-collect
```

它会逐条打开已收集的小红书链接，读取页面可见内容并写入数据库。随后再运行：

```bash
scripts/xhs-agent.sh daily
```

如果 Chrome 拒绝读取页面，请在 Chrome 菜单 `显示/View > 开发者/Developer` 中开启 `Allow JavaScript from Apple Events`。
