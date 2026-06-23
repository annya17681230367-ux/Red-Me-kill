# 云服务器部署流程

更新时间：2026-06-24

## 推荐选择

阿里云或腾讯云普通云服务器都可以。

建议规格：

- 系统：Ubuntu 22.04 LTS
- 配置：2 核 4G 起步
- 磁盘：40G 起步
- 网络：开放 22 端口；后续有看板再开放 80/443

第一版云端目标：

- 服务器自动运行日报/周报任务。
- 使用 DeepSeek `deepseek-v4-flash` 做主分析模型。
- 记录 token 和预估费用。
- 保存数据库、报告和图片任务数据。

## 1. 安装环境

登录服务器后执行：

```bash
sudo apt update
sudo apt install -y git ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc > /dev/null
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

执行完后退出服务器重新登录一次，然后验证：

```bash
docker --version
docker compose version
```

## 2. 拉取代码

```bash
git clone https://github.com/annya17681230367-ux/Red-Me-kill.git
cd Red-Me-kill
git checkout codex/roadshow-image-node
```

## 3. 配置文件

创建本地私有配置：

```bash
cp config/settings.example.toml config/settings.toml
cp .env.example .env
```

编辑 `config/settings.toml`：

```toml
[agent]
timezone = "Asia/Shanghai"
database_path = "data/xhs_agent.sqlite3"
reports_dir = "data/reports"
accounts_csv = "config/accounts.csv"
manual_links_csv = "data/manual_links.csv"
knowledge_file = "knowledge/xhs_strategy.md"
browser_collection_enabled = false
hotspot_collection_enabled = false

[llm]
enabled = true
provider = "deepseek"
base_url = "https://api.deepseek.com"
api_key = "你的DeepSeek_API_Key"
model = "deepseek-v4-flash"
timeout_seconds = 45
max_tokens = 1600
temperature = 0.3
input_token_usd_per_million = 0.14
output_token_usd_per_million = 0.28
```

编辑 `.env`：

```bash
XHS_LLM_ENABLED=true
XHS_LLM_PROVIDER=deepseek
XHS_LLM_BASE_URL=https://api.deepseek.com
XHS_LLM_API_KEY=你的DeepSeek_API_Key
XHS_LLM_MODEL=deepseek-v4-flash
XHS_LLM_INPUT_TOKEN_USD_PER_MILLION=0.14
XHS_LLM_OUTPUT_TOKEN_USD_PER_MILLION=0.28
```

注意：

- `config/settings.toml` 和 `.env` 不提交 GitHub。
- 云端第一版关闭浏览器采集和热点搜索采集，因为它们依赖本机 Chrome。
- 后续接小红书正式 API 后，云端就可以不依赖本地电脑采集数据。

## 4. 初始化和测试

```bash
docker compose build
docker compose run --rm xhs-agent python -m xhs_agent init-db
docker compose run --rm xhs-agent python -m xhs_agent model-test
```

成功时会看到：

```text
云端模型：deepseek:deepseek-v4-flash
Token 用量：输入 ...，输出 ...，合计 ...
预估费用：$...
模型总结：...
```

## 5. 启动服务

```bash
docker compose up -d
docker compose logs -f xhs-agent
```

停止服务：

```bash
docker compose down
```

更新代码：

```bash
git pull
docker compose build
docker compose up -d
```

## 6. 查看数据

数据库：

```text
data/xhs_agent.sqlite3
```

报告：

```text
data/reports/
```

图片任务：

```text
image_jobs
generated_images
```

模型调用日志：

```text
model_call_logs
```

## 7. 绑定域名

第一版只有后台任务时，不急着绑定域名。

等看板服务做好后再做：

1. 域名 DNS 添加 A 记录，指向服务器公网 IP。
2. 安装 Nginx 或 Caddy。
3. 配置 HTTPS 证书。
4. 把域名反向代理到看板服务。

## 8. 后续 skill 节点

推荐顺序：

1. DeepSeek 主分析节点：长期稳定跑爆贴分析。
2. Claude skill 节点：复杂策略、业务号深度内容生成。
3. 图片生成节点：根据业务内容生成封面图。
4. 看板节点：展示爆贴、内容、图片、token 成本、bug 记录。
