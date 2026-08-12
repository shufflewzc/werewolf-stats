# 后端运行与维护

## 数据库

生产环境以 PostgreSQL 为唯一主库。`scripts/apply_postgres_schema.py` 会先应用可重复执行的基准结构，再按顺序记录 `scripts/migrations/` 下尚未执行的编号迁移。

版本 6 增加：

- 仓库数据版本与乐观并发控制；
- 扫码登录、限流、幂等、导入任务和导入快照独立表；
- 选手自动建档来源字段；
- 阵容和队长引用约束；
- 常用赛事、选手、战队查询索引。

## 定时清理

运行：

```bash
PYTHONPATH=scripts python3 scripts/cleanup_runtime_state.py
```

默认保留 90 天访问日志、365 天审计日志、30 天导入快照，并至少保留最近 20 个成功导入批次。首次从旧版本升级时增加 `--purge-legacy-web-login`，删除 `app_meta` 中遗留的扫码令牌。

部署脚本会安装 `werewolf-stats-maintenance.timer`，默认每天凌晨执行一次。

## Excel 导入 Worker

Excel 文件先保存到 `data/import-jobs/`，任务状态写入 `import_jobs`。Web 进程不再自行启动后台线程。

部署脚本会安装并启动：

```text
werewolf-stats-import-worker.service
```

Worker 使用数据库行锁领取任务；异常退出超过 10 分钟后，其他 Worker 可以重新领取。任务成功或失败后会删除临时 Excel 文件。

## 健康检查

- `/healthz`：仅检查进程存活。
- `/readyz`：检查数据库连接、必需表和 Schema 版本，不执行大表 `COUNT(*)`。
- `/ops`：管理员查看数据规模、缓存命中、错误和慢请求等详细信息。

## 代理与客户端 IP

应用只在直接来源为本机回环地址时信任 `X-Forwarded-For`，因此 Nginx 必须设置：

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Real-IP $remote_addr;
```

外部直接请求即使伪造该请求头，也不会覆盖真实来源地址。

`deploy/nginx/werewolf-runtime-http.conf` 应放在 `http` 作用域，
`werewolf-public-api-location.conf` 和 `werewolf-public-html-location.conf`
应放在站点的 TLS `server` 作用域。公开 HTML 只缓存匿名 GET/HEAD，
携带登录 Cookie 的后台页面会绕过缓存。

`werewolf-default-server.conf` 应作为独立站点启用，用于在 TLS 握手或
HTTP 请求阶段拒绝非正式域名的流量。公开页面和 API 同时限制单 IP
请求速率与并发数，并直接拒绝已确认会造成资源耗尽的爬虫。

公开只读 API 默认由 Nginx `limit_req` 限流，避免每次读取都写数据库。
登录、小程序绑定等敏感接口仍使用 PostgreSQL 共享限流。
只有不使用 Nginx 时才设置 `REQUEST_RATE_LIMIT_PUBLIC_API_ENABLED=1`。
