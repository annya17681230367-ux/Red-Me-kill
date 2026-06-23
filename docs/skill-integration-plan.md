# 小红书 Skill 接入判断

更新时间：2026-06-24

## 当前结论

第一阶段不建议直接接“自动发布”。先接图文生成能力，发布仍保留人工确认。

推荐顺序：

1. DeepSeek 主分析模型：爆贴拆解、标题/正文/评论区建议。
2. 业务号内容生成节点：把学生号爆贴转成 3 个业务号内容。
3. `guizang-social-card-skill`：把内容渲染成小红书图文卡片。
4. `Auto-Redbook-Skills`：作为备选渲染器和发布能力参考，不先启用自动发布。
5. Claude skill：后续插入复杂内容生成和高级策略节点。

## Auto-Redbook-Skills

仓库：

```text
https://github.com/comeonzhj/Auto-Redbook-Skills
```

适合做：

- 小红书笔记文案生成。
- 1080×1440 图文卡片渲染。
- 多主题图片输出。
- 作为“快速出图”备选节点。

先不建议做：

- 自动发布。
- Cookie 托管。

原因：

- 自动发布需要小红书 Cookie，存在账号安全和平台风控风险。
- 我们当前路演目标是证明分析、生成、出图和看板闭环，不需要一开始就自动发布。

推荐接入位置：

```text
业务号内容生成
-> Auto-Redbook-Skills 渲染封面/正文卡
-> 进入图片库
-> 人工确认
```

## guizang-social-card-skill

仓库：

```text
https://github.com/op7418/guizang-social-card-skill
```

适合做：

- 小红书图文组图。
- 公众号封面对。
- 瑞士风/电子杂志风视觉卡片。
- 文章、攻略、产品测评、教程拆页。
- 单文件 HTML 渲染 PNG。

优势：

- 视觉系统更完整。
- 适合“精品攻略”“数据拆解”“方法论”类内容。
- 有校验脚本，可检查溢出、字号和布局碰撞。

注意：

- 该仓库使用 AGPL-3.0 license，后续如果深度集成到商业系统，需要单独评估开源协议影响。

推荐接入位置：

```text
业务号内容生成
-> guizang-social-card-skill 生成 3-9 张小红书图文卡
-> 图片任务/图片结果入库
-> 看板展示
-> 人工确认发布
```

## 和当前流程图的对应关系

用户提供的流程图是 4 层：

```text
分析
-> 匹配
-> 生成
-> 发布
-> 沉淀
```

当前项目对应：

- 分析：DeepSeek + `analysis.py` + `llm.py`
- 匹配：`knowledge/marketing_calendar.md` + 后续营销日历结构化
- 生成：业务号内容生成节点 + `image_generation.py`
- 发布：第一版只做人工确认，不自动发布
- 沉淀：SQLite 数据库 + 报告 + 后续知识库回写

## 推荐第一版落地方案

先做：

```text
爆贴数据
-> DeepSeek 分析
-> 三个业务号内容
-> guizang-social-card-skill 渲染图文卡
-> generated_images 入库
-> 看板/报告展示
```

暂缓：

```text
自动发布
Cookie 托管
批量发布
无人审核
```

## 后续 Claude Skill 插入点

Claude 不作为第一版主分析模型，而作为高级 skill 节点：

```text
DeepSeek 初筛分析
-> Claude skill 深度改写/策略判断
-> 图文卡片生成
-> 人工确认
```

适合 Claude 的任务：

- 三个业务号差异化内容生成。
- 高价值爆贴深度复盘。
- 封面文案和图文结构优化。
- 路演材料、客户案例、内容策略总结。
