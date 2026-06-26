# 狼人杀赛事微信小程序

这是基于现有网站公开 JSON 接口搭建的原生微信小程序前端。

## 当前页面

- 首页：读取 `/api/dashboard`
- 赛事：读取 `/api/competitions`
- 门派：读取 `/api/guilds`
- 选手：读取 `/api/players`

## 本地调试

1. 先启动网站后端，默认端口为 `8000`。
2. 用微信开发者工具导入 `miniprogram/` 目录。
3. 开发者工具里勾选“不校验合法域名、web-view、TLS 版本以及 HTTPS 证书”。
4. 如需切换到本地后端，修改 `config.js`：

```js
const activeApiEnv = "local";

module.exports = {
  activeApiEnv,
  allowLocalApi: true,
  apiBaseUrl: apiPresets[activeApiEnv] || apiPresets.production,
  apiPresets
};
```

## 上线前

- 先在项目根目录执行：

```bash
node scripts/check_miniprogram_release.js
```

- 确认 `config.js` 使用 `activeApiEnv = "production"`，并且 `allowLocalApi = false`。
- 当前正式接口地址为 `https://wolf.fakerclaw.indevs.in`。
- 在微信公众平台配置 request 合法域名。
- 把 `project.config.json` 里的 `appid` 换成你的小程序 AppID。
- 后端服务需要配置 `WECHAT_MINIPROGRAM_APPID` 和 `WECHAT_MINIPROGRAM_SECRET`，用于把 `wx.login` 的 code 换成 openid。
- 本地联调如果暂时不想请求微信接口，可以同时设置 `WECHAT_MINIPROGRAM_DEV_OPENID` 和 `ALLOW_WECHAT_DEV_LOGIN=1` 模拟 openid；生产环境不要开启。
- 当前小程序支持微信登录自动创建账号；选手身份在“我的”页通过中文名搜索绑定。
- 网页端登录已改为“小程序扫码确认登录”：网页显示二维码，小程序“我的”页扫码确认后网页自动登录；服务器不需要配置网页开放平台参数。
- 请求层会统一处理网络超时、临时 5xx 重试、后端错误信息和登录过期；如果接口返回 `X-Request-ID`，错误提示会带请求编号，方便对照服务器日志。
