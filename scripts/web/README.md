# Web 模块结构

当前 Web 层采用“兼容入口 + 功能模块”结构：

- `scripts/web_app.py`
  兼容入口，保留 WSGI 启动、共享工具函数、路由分发和历史兼容点。
- `scripts/web/features/`
  按业务域拆分的页面与处理器模块。

当前已经拆出的模块：

- `guilds.py`
  门派公开页、门派管理页、门派相关提交处理。
- `profile.py`
  个人中心页面、个人资料保存、门派创建入口。
- `team_center.py`
  战队操作中心、赛季身份展示、成员审核与移除处理。

后续新增页面时，优先遵循下面的规则：

- 共享基础能力继续放在 `web_app.py`
  例如 `RequestContext`、`layout()`、数据加载保存、权限判断、通用表单工具。
- 页面渲染与表单处理优先放进 `scripts/web/features/`
  按“一个业务域一个模块”继续拆分。
- 路由入口继续从 `web_app.py` 分发
  这样可以保持现有启动方式不变，降低重构风险。
- 当某个业务域继续增长时，再往下拆子模块
  例如未来可以继续拆成 `features/matches/`、`features/series/`、`features/accounts/`。
