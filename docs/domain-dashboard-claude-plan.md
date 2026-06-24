# 云端看板、域名和 Claude Skill 节点计划

更新时间：2026-06-24

## 当前已完成

- 云服务器已部署 Docker 服务。
- DeepSeek `deepseek-v4-flash` 已接入并记录 Token 和预估费用。
- 新增云端看板服务：默认端口 `8000`。
- 新增社媒助手输入接口：`POST /api/social-links`。
- Claude Skill 节点已预留在看板和配置中，待 Claude API Key 可用后开启。

## 看板地址

服务器公网访问：

```text
http://47.86.44.159:8000
```

看板展示：

- 爆贴数据总数
- 社媒助手输入链接数
- 图片生成任务数
- 已生成图片数
- 模型调用次数
- Token 用量和预估费用
- 日报/周报产物
- Claude Skill 节点状态

## 社媒助手接口预留

后续社媒助手把小红书链接推给系统时，调用：

```http
POST /api/social-links
Content-Type: application/json
```

请求体：

```json
{
  "url": "https://www.xiaohongshu.com/explore/xxx",
  "sender_name": "social-assistant"
}
```

返回：

```json
{
  "ok": true,
  "added": 1,
  "url": "https://www.xiaohongshu.com/explore/xxx"
}
```

## Claude Skill 节点状态

当前状态：已预留，未启用。

原因：

- 当前没有 Claude API Key。
- 主模型已先用 DeepSeek 跑通，适合长期低成本分析。
- Claude Skill 适合作为后续高级节点：复杂内容生成、风格迁移、长文本策略和视觉卡片结构化。

启用方式：

```toml
[llm]
enabled = true
provider = "anthropic"
anthropic_base_url = "https://api.anthropic.com"
api_key = "你的 Claude API Key"
model = "claude-3-5-sonnet-latest"
```

启用后需要重启服务：

```bash
docker compose up -d --build
```

## 域名绑定步骤

前提：你需要先买好域名，例如：

```text
xhs-agent.com
```

1. 到域名 DNS 管理页面新增解析：

```text
类型：A
主机记录：dashboard
记录值：47.86.44.159
```

2. 等解析生效后，访问：

```text
http://dashboard.xhs-agent.com:8000
```

3. 正式版本建议再加 Nginx/Caddy，把端口隐藏成：

```text
https://dashboard.xhs-agent.com
```

路演前如果没有域名，直接使用公网 IP 展示即可。

