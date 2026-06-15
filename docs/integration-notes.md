# 集成备注

## 飞书

- 目标群：学管部小红书发帖群
- 用户提供的飞书登录 ID：17681230367
- 当前状态：该 ID 不能直接作为飞书开放平台应用参数使用。

正式自动读取群消息仍需要：

- 飞书开放平台应用 `app_id`
- 飞书开放平台应用 `app_secret`
- 目标群 `chat_id`
- 机器人加入目标群并具备读取消息、发送消息权限

如果只能使用个人网页登录，需要用户在本机手动完成验证码登录；该方式更适合临时处理，不建议作为稳定自动化方案。

## 小红书

- 文档入口：https://agora.xiaohongshu.com/doc/ios
- Ark 接口：https://ark.xiaohongshu.com/ark/open_api/v3/common_controller
- 已配置 `app_id = xiaohongshu-cli`
- 当前缺少具体查询方法：
  - `note_method`
  - `account_method`

在缺少 method 的情况下，可以先通过 `data/manual_links.csv` 输入小红书链接或笔记 ID，系统会先收录并生成待抓取日报。
