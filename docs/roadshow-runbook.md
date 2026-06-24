# 路演操作流程

## 1. 先证明云端在运行

在服务器项目目录执行：

```bash
cd /root/Red-Me-kill
docker compose ps
```

成功标准：

- `xhs-agent` 是 `Up`
- `xhs-dashboard` 是 `Up`

## 2. 生成演示数据和日报

```bash
docker compose run --rm xhs-agent python -m xhs_agent seed-demo
```

成功标准：

- 显示写入 3 条爆贴样例。
- 显示日报 HTML 路径。
- 显示图片任务新增数量。

## 3. 测试模型 Token 统计

```bash
docker compose run --rm xhs-agent python -m xhs_agent model-test
```

成功标准：

- 显示 DeepSeek 模型名称。
- 显示输入、输出、合计 Token。
- 显示预估费用。
- 显示模型总结和建议动作。

## 4. 启动看板

```bash
docker compose up -d --build
```

打开：

```text
http://47.86.44.159:8000
```

如果已开放 `80` 端口，也可以直接打开：

```text
http://47.86.44.159
```

成功标准：

- 能看到小红书运营 AI 看板。
- 能看到爆贴数据、模型调用、图片任务、日报/周报文件。
- Claude Skill 节点显示“已预留，待 Claude Key 开启”。

## 5. 测试社媒助手接口

```bash
curl -X POST http://127.0.0.1:8000/api/social-links \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.xiaohongshu.com/explore/demo-roadshow-link","sender_name":"social-assistant"}'
```

成功标准：

```json
{"ok": true, "added": 1}
```

## 6. 路演讲法

## 6. 接入图片 API

路演前最快接入 SiliconFlow 图片接口。在服务器项目目录执行：

```bash
cat >> .env <<'EOF'
XHS_IMAGE_ENABLED=true
XHS_IMAGE_PROVIDER=siliconflow
XHS_IMAGE_BASE_URL=https://api.siliconflow.cn/v1
XHS_IMAGE_API_KEY=替换成你的图片APIKey
XHS_IMAGE_MODEL=Kwai-Kolors/Kolors
EOF
docker compose up -d --build
docker compose run --rm xhs-agent python -m xhs_agent generate-images --limit 3
```

成功标准：

- 显示 `生成成功` 大于 0。
- 看板里的图片任务状态变为 completed。
- `data/generated_images` 里出现图片文件，或 `generated_images` 表里出现图片链接。

## 7. 路演讲法

可以按这个顺序讲：

1. 这是云端运行的小红书运营 AI 系统，不依赖本地电脑。
2. 系统会沉淀小红书链接、爆贴数据、日报周报、图片任务和模型调用记录。
3. 主分析模型已接 DeepSeek，并且能看到每次调用的 Token 和费用。
4. 图片生成节点已经接入，当前先生成任务，后续接入图片 API 后直接出图。
5. 看板已经能展示运行状态、内容样例、报告产物和成本。
6. 社媒助手后续只要调用 `/api/social-links`，就能把链接输入系统。
7. Claude Skill 节点已预留，后续拿到 Claude Key 后作为高级内容生成节点启用。
