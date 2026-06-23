# 路演演示路径

更新时间：2026-06-24

## 演示目标

展示小红书运营系统已经具备：

- GitHub 代码记录。
- 云端模型接入能力。
- 爆贴分析能力。
- 三个业务号封面图任务节点。
- 路演测试和维护文档。

## 演示顺序

### 1. 展示 GitHub 分支

打开 GitHub 仓库并切换到：

```text
codex/roadshow-image-node
```

重点展示：

- `README.md`
- `docs/roadshow-implementation-plan.md`
- `docs/code-inventory.md`
- `MAINTENANCE.md`
- `src/xhs_agent/image_generation.py`
- `src/xhs_agent/llm.py`

讲法：

> 代码已经记录到 GitHub，API Key 和真实业务数据不进入仓库，只通过配置或云端环境变量接入。

### 2. 展示云端模型配置

展示 `README.md` 里的云端模型配置：

```bash
export XHS_LLM_ENABLED=true
export XHS_LLM_PROVIDER=deepseek
export XHS_LLM_BASE_URL=https://api.deepseek.com
export XHS_LLM_API_KEY=你的DeepSeekKey
export XHS_LLM_MODEL=deepseek-v4-flash
export XHS_LLM_INPUT_TOKEN_USD_PER_MILLION=0.14
export XHS_LLM_OUTPUT_TOKEN_USD_PER_MILLION=0.28
```

讲法：

> 第一版长期主分析模型使用 DeepSeek `deepseek-v4-flash`，用于爆贴分析、标题优化、正文结构建议和评论区动作。系统会记录 input/output token 和预估成本。Claude 后续作为 skill 节点插入复杂内容生成环节，不影响主链路。

### 3. 演示模型测试命令

配置好 Key 后运行：

```bash
scripts/xhs-agent.sh model-test
```

期望看到：

```text
云端模型：deepseek:deepseek-v4-flash
Token 用量：输入 ...，输出 ...，合计 ...
预估费用：$...
模型总结：...
建议动作：
- ...
```

讲法：

> 这个命令会真实请求云端模型，让模型分析一条留学生小红书爆贴样例，并返回结构化运营建议。

### 4. 演示图片生成任务节点

运行：

```bash
scripts/xhs-agent.sh generate-images --limit 3
```

讲法：

> 图片节点会从爆贴数据中生成三个业务号的封面图任务。图片 API 配好后，会继续生成图片链接或图片文件。

### 5. 展示路演和维护材料

展示：

- `docs/roadshow-implementation-plan.md`
- `docs/roadshow-feedback.md`
- `MAINTENANCE.md`

讲法：

> 3 人 3 天测试、真实 bug、第一次路演反馈和后期维护策略都已经形成文档模板，后续按记录迭代。

## 如果 Claude Console 暂时打不开

讲法：

> 当前主分析链路不依赖 Claude Console。第一版先用 DeepSeek 稳定跑分析和 token 计费。Claude 后续以 skill 节点接入，用于高价值内容生成和策略优化。
