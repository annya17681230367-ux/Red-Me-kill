# 企业微信和微信部署说明

## 当前状态

Agent 已支持三条投递通道：

- 微信：通过复制/导出群消息收集小红书链接。
- 企业微信：通过群机器人 Webhook 发送日报/周报正文。
- 微信公众号/服务号：可选，通过客服消息发送日报/周报摘要。

当前已经启用本地定时任务：

- 每日 21:30：生成小红书账号日报。
- 每周三 15:00：生成小红书账号周报。

## 企业微信

推荐使用企业微信群机器人。

需要你在企业微信群里添加机器人，然后复制 Webhook 地址，填入：

```toml
[wecom]
enabled = true
webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
```

注意：`https://work.weixin.qq.com/wework_admin/common/openBotProfile/...` 是机器人管理资料页，不是消息发送 Webhook，不能直接用于推送日报。

填好后运行：

```bash
scripts/xhs-agent.sh daily
```

如果成功，企业微信群会收到日报正文。长报告会自动分段发送。

## 微信

个人微信普通群没有官方稳定机器人接口，不建议使用私号外挂式自动化。

当前项目支持微信公众号/服务号客服消息。需要：

- 公众号/服务号 `app_id`
- 公众号/服务号 `app_secret`
- 接收人的 `openid`

填入：

```toml
[wechat_official_account]
enabled = true
app_id = "公众号 app_id"
app_secret = "公众号 app_secret"
openids = ["接收人 openid"]
```

注意：微信公众号客服消息通常受用户互动窗口限制。如果需要长期稳定触达，建议后续改成模板消息/订阅消息，或把企业微信客户群作为主要承接群。

## 当前仍需补齐

- 企业微信机器人发送 Webhook，格式为 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`。
- 微信公众号/服务号 app_id、app_secret、openid。
- 小红书 Ark API 的 `note_method` 和 `account_method`。
- 微信群消息导入：把微信群聊天内容复制或导出到 `data/wechat_messages.txt`，系统会自动提取小红书链接。
- DeepSeek API Key：填入 `config/settings.toml` 的 `[llm].api_key`，并把 `[llm].enabled` 改成 `true`。

## 微信群链接收集入口

一次性导入剪贴板：

```bash
scripts/xhs-agent.sh wechat-import-clipboard
```

前台持续监听：

```bash
scripts/start-wechat-collector.sh
```

后台常驻部署：

```bash
scripts/install_wechat_collector.sh
```

触发条件：你在微信里复制的内容中包含 `xiaohongshu.com` 或 `xhslink.com` 链接。系统检测到剪贴板变化后，会自动写入 `data/manual_links.csv`，日报/周报再读取这个表。
