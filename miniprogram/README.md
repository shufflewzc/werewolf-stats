# 狼人杀赛事微信小程序

这是基于现有网站公开 JSON 接口搭建的原生微信小程序前端。

## 当前页面

- 首页：读取 `/api/dashboard`
- 赛事：读取 `/api/competitions`
- 战队：读取 `/api/teams`
- 选手：读取 `/api/players`

## 本地调试

1. 先启动网站后端，默认端口为 `8000`。
2. 用微信开发者工具导入 `miniprogram/` 目录。
3. 开发者工具里勾选“不校验合法域名、web-view、TLS 版本以及 HTTPS 证书”。
4. 如需切换后端地址，修改 `config.js` 的 `apiBaseUrl`。

## 上线前

- 把 `config.js` 中的本地地址换成 HTTPS 正式域名。
- 在微信公众平台配置 request 合法域名。
- 把 `project.config.json` 里的 `appid` 换成你的小程序 AppID。
- 后端服务需要配置 `WECHAT_MINIPROGRAM_APPID` 和 `WECHAT_MINIPROGRAM_SECRET`，用于把 `wx.login` 的 code 换成 openid。
- 本地联调如果暂时不想请求微信接口，可以设置 `WECHAT_MINIPROGRAM_DEV_OPENID` 模拟 openid。
- 当前小程序支持微信登录自动创建账号；选手身份在“我的”页通过中文名搜索绑定。
- 网页端登录已改为“小程序扫码确认登录”：网页显示二维码，小程序“我的”页扫码确认后网页自动登录；服务器不需要配置网页开放平台参数。
