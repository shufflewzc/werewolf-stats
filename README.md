# 狼人杀赛季/个人生涯管理系统

###最近参加了一些狼人杀的比赛，发现目前没有一套比较全面的电子化积分系统，目前的比赛要么通过Excel，要么人工计算。感觉比较落后，搓了一套积分系统。

### 我是程序员，不是美工，界面肯定不会太好看了。欢迎各位狼人杀爱好者同时是美工的选手进行二开。

### 核心逻辑是记录选手生涯，但是不同比赛数据不冲突。本站采用的是“赛季档案”思路。

### 每个赛季都为独立档案，ID，照片，战队，比赛，赛季都是独一无二的。但是选手个人可以将这些数据绑定到个人生涯中。展现了个人生涯参加不同比赛的不同数据和荣誉。



VIBE了一个面向狼人杀竞技赛事的数据仓库与管理后台，用来维护战队、队员、照片路径、比赛记录，并生成类似职业体育数据页的统计结果。

当前项目既支持：

- 数据校验与统计报表生成
- 本地网站形式的公开展示与后台录入
- `SQLite` 作为主存储的统一数据管理

---

## 项目解决的核心痛点

狼人杀赛事的计分和资料管理往往分散在 Excel、聊天记录、图片素材和人工口径里，一旦比赛进入多赛季、多地区、多战队协作阶段，就会出现几个明显问题：

- **赛季数据容易互相污染**：同一选手可能跨赛事、跨赛季、跨战队参赛，传统表格很难同时保留赛季档案和个人生涯视角。
- **人工统计成本高且容易出错**：胜率、站边率、得分率、场均得分、存活率、排行榜等指标需要反复汇总，人工维护不适合长期赛事。
- **赛事资料缺少统一入口**：战队、队员、头像、队标、比赛结果、赛程、荣誉和审核流程分散管理，公开展示和后台录入经常脱节。
- **补录和批量导入门槛高**：线下赛事经常先用 Excel 收集结果，再人工录入到展示页；本项目把模板导入、校验、保存和统计串成一条链路。
- **公开内容生产依赖人工整理**：比赛日报、赛季总结、个人/战队赛季总结可以基于已录入的真实数据生成初稿，减少赛事运营的重复劳动。

因此，这个项目的核心目标不是只做一个比分表，而是建立一套“赛季独立、人物可贯通、数据可校验、页面可发布”的狼人杀竞技赛事数据系统。

---

## 核心逻辑流

系统主流程围绕 `SQLite` 主库展开：

1. **建档**：维护赛事、赛季、战队、队员、门派、照片和队标等基础资料。
2. **录入/导入**：通过后台页面单场录入，或通过 Excel 模板批量导入比赛结果、选手维度数据、战队维度数据、队员头像和战队图标。
3. **校验**：保存前后使用统一校验逻辑检查 ID、阵营、胜负、选手归属、比赛字段和权限范围，降低脏数据进入主库的概率。
4. **持久化**：所有核心业务数据写入 `data/werewolf_stats.db`，旧版 JSON 仅作为迁移来源，不再作为运行时主存储。
5. **统计聚合**：按赛事、赛季、比赛日、战队、选手等维度计算胜率、站边率、得分率、场均得分、存活率、排行榜和战队汇总。
6. **展示与管理**：公开页面通过 JSON 接口渲染首页、赛事页、系列赛页、比赛日页、赛程页、门派页、战队页和选手页；登录后台负责编辑、审核、认领、导入和账号权限。
7. **可选 AI 内容生成**：在配置 AI 接口后，系统会把已校验的真实比赛数据整理成提示词，生成比赛日报、赛季总结、选手赛季总结或战队赛季总结，并保存为站内内容。

### 关于长链推理和多 Agent 协作

当前项目的核心业务逻辑是**确定性数据处理**：录入、校验、持久化、聚合统计和页面渲染都由本地 Python 代码完成，不依赖长链推理来决定比赛结果或统计口径。

AI 能力目前定位为**单模型内容生成辅助**：它读取系统已经汇总好的真实数据，生成适合发布的中文总结。提示词明确要求不能虚构事实，生成结果也可以由管理员手动保存或重生成。项目内暂未实现多 Agent 协作、Agent 工作流编排、自动裁判推理或基于 LLM 的数据判定链路。

---

## 功能概览

### 当前支持

- 战队资料维护：战队 ID、名称、简称、队标、成员、备注
- 队员资料维护：队员 ID、展示名、头像、别名、状态
- 标准化比赛记录：赛季、赛段、轮次、局次、阵营胜负、个人表现
- 自动统计指标：胜率、站边率、得分率、场均得分、存活率
- 自动生成排行榜：队员榜、战队汇总、可视化报表
- 登录版网站：支持浏览、编辑、认领、审核、导入等操作

### 适用场景

- 线下狼人杀赛事数据归档
- 赛季型战队与选手资料管理
- 比赛结果补录与赛季维度统计
- 面向公开页面的展示型数据站

---

## 存储方式

当前系统已经升级为 `SQLite` 主存储，数据库文件为：

- `data/werewolf_stats.db`

网站、校验脚本和报表脚本现在都直接读写 `SQLite`，不再依赖运行时自动同步 `JSON` 文件。

如果你手头还有旧版 `JSON` 数据，需要显式执行一次迁移：

```bash
python3 scripts/migrate_json_to_sqlite.py
```

迁移完成后，`SQLite` 会成为唯一主存储。

---

## 项目结构

```text
.
|-- assets/
|   |-- players/
|   `-- teams/
|-- data/
|   `-- werewolf_stats.db
|-- reports/
|   |-- dashboard.html
|   |-- player_leaderboard.json
|   |-- player_leaderboard.md
|   |-- team_summary.json
|   `-- team_summary.md
|-- schemas/
|   |-- match.schema.json
|   |-- player.schema.json
|   `-- team.schema.json
`-- scripts/
    |-- web/
    |   |-- features/
    |   `-- README.md
    |-- generate_stats.py
    |-- migrate_json_to_sqlite.py
    |-- sqlite_store.py
    |-- validate_data.py
    `-- web_app.py
```

### Web 层拆分

- `scripts/web_app.py`
  兼容入口、共享工具和路由分发
- `scripts/web/features/`
  按业务模块拆分页面和处理器
- `assets/dashboard-app.js` / `assets/dashboard-app.css`
  新版首页前端资源，使用浏览器拉取后端 JSON 接口渲染
- `assets/series-app.js`
  新版系列赛专题页前端资源，使用浏览器拉取后端 JSON 接口渲染
- `assets/day-app.js`
  新版比赛日页面前端资源，使用浏览器拉取后端 JSON 接口渲染
- `assets/schedule-app.js`
  新版赛事场次页前端资源，使用浏览器拉取后端 JSON 接口渲染
- `assets/guilds-app.js` / `assets/guilds-app.css`
  新版门派列表页前端资源，使用浏览器拉取后端 JSON 接口渲染

### 当前前后端分离落点

- `GET /dashboard`
  新版首页前端壳，浏览器通过接口拉取数据再渲染
- `GET /api/dashboard`
  首页聚合接口，返回赛区/系列赛/赛事/赛季筛选、榜单、比赛日等 JSON 数据
- `GET /dashboard/legacy`
  保留旧版服务端直出首页，便于回退和对照
- `GET /competitions`
  新版比赛页面前端壳，浏览器通过接口拉取地区赛事列表和赛季详情
- `GET /api/competitions`
  比赛页面聚合接口，返回地区赛事站点、赛季榜单、AI 总结和比赛日等 JSON 数据
- `GET /competitions/legacy`
  保留旧版服务端直出比赛页面，便于回退和对照
- `GET /guilds`
  新版门派列表页前端壳，浏览器通过接口拉取门派概览和管理入口信息
- `GET /api/guilds`
  门派列表聚合接口，返回门派卡片、统计指标和管理跳转入口
- `GET /guilds/legacy`
  保留旧版服务端直出门派列表页，便于回退和对照
- `GET /series/<slug>`
  新版系列赛专题页前端壳，浏览器通过接口拉取赛季入口和地区赛事页概览
- `GET /api/series/<slug>`
  系列赛专题聚合接口，返回赛季切换、覆盖地区和地区赛事入口 JSON 数据
- `GET /series/<slug>/legacy`
  保留旧版服务端直出系列赛专题页，便于回退和对照
- `GET /days/<played_on>`
  新版比赛日页面前端壳，浏览器通过接口拉取当天战队日榜、AI 日报和比赛结果明细
- `GET /api/days/<played_on>`
  比赛日聚合接口，返回当天概览、AI 日报、战队日榜和逐场比赛 JSON 数据
- `GET /days/<played_on>/legacy`
  保留旧版服务端直出比赛日页面，便于回退和对照
- `GET /schedule`
  新版赛事场次页前端壳，浏览器通过接口拉取当前赛事赛季下的比赛日和场次列表
- `GET /api/schedule`
  赛事场次聚合接口，返回赛事切换、赛季切换和按比赛日分组的场次 JSON 数据
- `GET /schedule/legacy`
  保留旧版服务端直出赛事场次页，便于回退和对照
- 当前已拆出的模块
  门派、个人中心、战队操作等

---

## 数据设计

### `teams`

保存战队主数据。

| 字段 | 说明 |
| --- | --- |
| `team_id` | 战队唯一 ID |
| `name` | 战队名称 |
| `short_name` | 战队简称 |
| `logo` | 战队队标或图片路径 |
| `active` | 是否仍在使用 |
| `founded_on` | 建队日期 |
| `members` | 当前队员 ID 列表 |
| `notes` | 备注 |

### `players`

保存队员资料。

| 字段 | 说明 |
| --- | --- |
| `player_id` | 队员唯一 ID |
| `display_name` | 展示名 |
| `team_id` | 当前所属战队 |
| `photo` | 队员照片路径 |
| `aliases` | 别名列表 |
| `active` | 是否活跃 |
| `joined_on` | 加入数据库日期 |
| `notes` | 备注 |

### `matches` / `match_players`

保存标准化赛事对局记录。

| 字段 | 说明 |
| --- | --- |
| `match_id` | 对局唯一 ID |
| `season` | 赛季名 |
| `stage` | 比赛阶段，如 `regular_season` |
| `round` | 轮次 |
| `game_no` | 该轮第几局 |
| `exclude_from_team_scores` | 是否抽局；为 `true` 时比赛保留、个人得分照常计算，但不计入战队总分 |
| `played_on` | 日期 |
| `table_label` | 台次或房间号 |
| `format` | 板型，如 `classic-12` |
| `duration_minutes` | 对局时长 |
| `winning_camp` | 胜利阵营，支持 `villagers`、`werewolves`、`third_party`、`draw` |
| `players` | 每位上场队员的对局记录 |
| `notes` | 备注 |

单个队员对局记录字段：

| 字段 | 说明 |
| --- | --- |
| `player_id` | 队员 ID |
| `team_id` | 本局代表的战队 |
| `seat` | 座位号 |
| `role` | 角色名 |
| `camp` | 所属阵营 |
| `survived` | 是否存活到结束 |
| `result` | 个人胜负 |
| `points_earned` | 本局得分 |
| `points_available` | 本局满分 |
| `stance_pick` | 本局站边结果，支持 `villagers`、`werewolves`、`third_party`、`none` |
| `stance_correct` | 站边是否正确 |
| `notes` | 备注 |

---

## 统计口径

- 胜率 `win_rate` = 胜场 / 出场
- 站边率 `stance_rate` = 正确站边场次 / 有明确站边场次
- 得分率 `score_rate` = 累计得分 / 累计可得分
- 场均得分 `average_points` = 累计得分 / 出场
- 存活率 `survival_rate` = 存活场次 / 出场

战队汇总按“战队队员总出场表现”统计，不假设狼人杀一定存在严格的战队对战胜负表。

---

## 快速开始

### 1. 校验数据

```bash
python3 scripts/validate_data.py
```

### 2. 生成统计报表

```bash
python3 scripts/generate_stats.py
```

输出文件位于：

- `reports/dashboard.html`
- `reports/player_leaderboard.json`
- `reports/player_leaderboard.md`
- `reports/team_summary.json`
- `reports/team_summary.md`

生成后可以直接打开：

- `reports/dashboard.html`

如果想通过本地地址访问，也可以运行：

```bash
python3 -m http.server
```

然后访问：

- [http://localhost:8000/reports/dashboard.html](http://localhost:8000/reports/dashboard.html)

---

## 登录版网站

如果你想使用“可登录、可编辑”的网站版本，运行：

```bash
python3 scripts/web_app.py
```

启动后访问：

- [http://localhost:8000](http://localhost:8000)

### 默认账号

- 用户名：`admin`
- 密码：`admin123`

### 登录后可以做什么

- 查看首页和比赛列表
- 进入比赛页面，再查看该比赛下的战队与队员
- 进入战队页面，查看按赛事、赛季整理的比赛数据
- 点击“编辑比赛”进入比赛编辑页，并保存到 `data/werewolf_stats.db`
- 进入战队相关页面，创建新战队、申请加入已有战队、发起转会申请
- 由目标战队负责人在相应页面审核加入申请和转会申请
- 在没有历史比赛记录且没有待处理申请时，退出当前战队
- 使用 `admin` 进入账号管理页面，新增或删除登录账号
- 在首页和队员页按赛事切换查看统计
- 在单一比赛口径下查看战队战绩和排名
- 在队员页同时查看综合统计和分赛事统计

### 当前也支持公开注册

注册流程：

1. 打开 `/register`
2. 填写用户名、显示名称、密码
3. 完成简单加法验证码
4. 注册后即可登录

## 1Panel 部署

如果你使用 `1Panel` 的 `Python 运行环境` 部署，推荐按下面配置。

### 1. 工作目录

将运行目录设置为项目根目录：

```text
/app
```

线上服务器请替换成你自己的实际绝对路径，只要该目录下能看到：

- `wsgi.py`
- `requirements.txt`
- `scripts/`
- `data/`

### 2. 环境变量

推荐先按 `.env.production.example` 在 `1Panel` 里逐项填写环境变量。正式环境不要把真实 `.env` 提交到仓库。

最少需要确认这些变量：

```bash
APP_DIR=/app
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats'
ENABLE_POSTGRES_WRITES=1
WECHAT_MINIPROGRAM_APPID='你的小程序AppID'
WECHAT_MINIPROGRAM_SECRET='你的小程序Secret'
WEB_LOGIN_BASE_URL='https://wolf.metauniverse-cn.xyz'
COOKIE_SECURE=1
```

其中 `APP_DIR` 要和服务器上的项目目录一致；如果 1Panel 的项目目录不是 `/app`，请改成实际路径。

### 3. 安装依赖

在 `1Panel` 的安装命令或初始化命令中填写：

```bash
pip install -r requirements.txt
```

如果运行环境里已经装过依赖，也可以手动补装：

```bash
pip install gunicorn
```

### 4. 启动命令

不要再直接使用：

```bash
python3 scripts/web_app.py
```

推荐改为内置生产启动脚本：

```bash
sh scripts/start_production.sh
```

这条脚本会自动完成依赖安装、生产配置检查、PostgreSQL 表结构升级、运行时结构检查、smoke 和日志清理，最后再启动 `gunicorn`。

如果你的 1Panel 环境不能执行脚本，再使用备用启动命令：

```bash
gunicorn -w 2 -k gthread --threads 4 -t 120 -b 0.0.0.0:8000 wsgi:app
```

这条命令的含义：

- `wsgi:app` 使用仓库内置的生产入口
- `-w 2` 启动 2 个 worker，避免单请求卡住整站
- `--threads 4` 给每个 worker 额外线程，提高并发余量
- `-t 120` 将超时时间设为 120 秒，减少慢请求直接被杀掉
- `-b 0.0.0.0:8000` 监听 `8000` 端口，方便 `1Panel/OpenResty` 反代

### 5. 上线前检查

每次正式发布前，推荐在服务器项目目录先跑：

```bash
python3 scripts/pre_deploy_check.py
```

它会串起生产配置、综合发布体检和备份可读性验证。检查未通过时不要启动或重启正式服务，先按提示修正。

正式运营库如果已经有赛事数据，可以加上严格小程序数据检查：

```bash
python3 scripts/pre_deploy_check.py --require-miniprogram-data
```

上传微信小程序前，推荐在本地项目根目录先跑：

```bash
node scripts/check_miniprogram_release.js
```

它会检查正式接口域名、小程序 AppID、页面路径、tabBar 图标、JS 语法和本地地址风险。综合发布体检还会额外检查小程序依赖的后端 API 字段契约。

### 6. 端口配置

建议应用监听端口保持为：

```text
8000
```

`1Panel` 网站反向代理继续转发到：

```text
127.0.0.1:8000
```

一般不需要额外改业务代码里的端口。

### 7. 推荐的 1Panel 填写方式

如果你的 `Python 运行环境` 页面里有类似字段，可以这样填：

- 运行目录：项目根目录
- 安装命令：`pip install -r requirements.txt`
- 启动命令：`sh scripts/start_production.sh`
- 监听端口：`8000`

建议同时配置 `.env.production.example` 里的环境变量。核心项如下：

```bash
APP_DIR=/app
DATABASE_URL=postgresql://user:password@host:5432/werewolf_stats
ENABLE_POSTGRES_WRITES=1
WECHAT_MINIPROGRAM_APPID=你的小程序AppID
WECHAT_MINIPROGRAM_SECRET=你的小程序Secret
WEB_LOGIN_BASE_URL=https://wolf.metauniverse-cn.xyz
COOKIE_SECURE=1
MAX_REQUEST_BODY_BYTES=52428800
MAX_EXCEL_UPLOAD_BYTES=10485760
MAX_EXCEL_SHEET_ROWS=2000
MAX_ZIP_UPLOAD_BYTES=52428800
MAX_ZIP_IMAGE_COUNT=300
SECURITY_HEADERS_ENABLED=1
CSRF_PROTECTION_ENABLED=1
```

本地 HTTP 调试网页登录时，可以临时设置 `COOKIE_SECURE=0`。

### 8. 常见问题

如果仍然出现 `502` 或 `504`，优先检查：

- Python 运行环境是否真的执行了 `sh scripts/start_production.sh`
- 当前工作目录是否为项目根目录，而不是 `scripts/`
- `requirements.txt` 是否已经安装成功
- `1Panel` 反向代理目标是否仍然是 `127.0.0.1:8000`
- `DATABASE_URL`、`WECHAT_MINIPROGRAM_APPID`、`WECHAT_MINIPROGRAM_SECRET` 是否已经填入服务器环境变量
- Python 运行环境日志里是否有报错或进程退出记录

### 9. 健康检查

服务提供两个健康检查接口：

```text
/healthz
/readyz
```

- `/healthz`：只确认 Python 服务进程可响应
- `/readyz`：检查当前运行数据库是否可连接、是否已初始化、`schema_version` 是否达标、关键表是否存在，并返回关键表行数；SQLite 模式会额外执行 `PRAGMA quick_check`

反向代理或平台探活优先使用：

```text
http://127.0.0.1:8000/readyz
```

默认 `/readyz` 不写入数据库。如果要在发布验证时额外确认写入链路，可以临时访问：

```text
http://127.0.0.1:8000/readyz?write=1
```

写入探针会在 `app_meta` 中写入并删除一个临时标记，成功后不会留下数据。

### 10. 数据备份

可以使用内置脚本创建 SQLite 一致性备份，并默认打包上传头像/队标：

```bash
python3 scripts/backup_sqlite.py
```

默认输出到：

```text
data/backups/
```

默认保留最近 14 份数据库备份和资源备份。只备份数据库可执行：

```bash
python3 scripts/backup_sqlite.py --no-assets
```

Linux 服务器上可以用 cron 每天凌晨备份一次：

```cron
15 3 * * * cd /app && python3 scripts/backup_sqlite.py >> app.log 2>&1
```

备份后建议定期做恢复验证。SQLite 环境可以直接执行：

```bash
python3 scripts/backup_restore_check.py
```

正式 PostgreSQL 环境会使用 `pg_dump` 生成备份，并用 `pg_restore --list` 验证备份可读取：

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' \
python3 scripts/backup_restore_check.py
```

服务器需要先安装 PostgreSQL client 工具，确保能执行：

```bash
pg_dump --version
pg_restore --version
```

如果你准备了一个空的恢复测试库，可以做真正的恢复演练。注意：测试库会被 `pg_restore --clean --if-exists` 清理后重建，不要填正式库：

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' \
python3 scripts/backup_restore_check.py \
  --restore-test-database-url 'postgresql://user:password@host:5432/werewolf_stats_restore_test'
```

恢复演练会在测试库恢复备份后执行结构检查、运行时 smoke，并对比业务表、日志表和 AI 任务表等关键表行数。
脚本会拒绝把备份恢复到与正式库相同的连接串；测试库名称也需要包含 `restore`、`test`、`staging`、`sandbox`、`scratch` 或 `rehearsal` 这类安全标识，降低误操作风险。

### 11. PostgreSQL 迁移演练

正式运行建议使用 PostgreSQL。SQLite 兼容逻辑仍保留，主要用于本地开发、迁移对照和应急回滚。

目标表结构：

```text
scripts/postgres_schema.sql
```

迁移脚本：

```text
scripts/migrate_sqlite_to_postgres.py
```

迁移前先安装 PostgreSQL Python 驱动：

```bash
python3 -m pip install 'psycopg[binary]>=3,<4'
```

先做 dry-run，确认 SQLite 源库表和行数：

```bash
python3 scripts/migrate_sqlite_to_postgres.py
```

准备好 PostgreSQL 数据库后，设置连接串：

```bash
export DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats'
```

向空 PostgreSQL 库导入并校验行数：

```bash
python3 scripts/migrate_sqlite_to_postgres.py --apply --truncate
```

代码升级后，先补 PostgreSQL 表结构，再做运行时结构检查：

```bash
python3 scripts/apply_postgres_schema.py
python3 scripts/check_runtime_schema.py
python3 scripts/check_postgres_indexes.py --strict
```

`apply_postgres_schema.py` 只更新表结构、索引和 `schema_version`，不会清空数据。`check_runtime_schema.py` 会检查核心表、初始化状态和 schema version，`check_postgres_indexes.py` 会检查高频页面需要的 PostgreSQL 关键索引，适合作为启动前检查。

建议迁移顺序：

1. 先执行 `python3 scripts/backup_sqlite.py` 备份 SQLite 和上传资源
2. 创建测试 PostgreSQL 库
3. 执行预检脚本确认环境和连接串
4. 在测试 PostgreSQL 库执行迁移
5. 检查脚本输出的每张表行数是否一致
6. 用运行时烟测脚本检查连接和核心表
7. 运行 PostgreSQL 回归脚本
8. 在测试环境打开 PostgreSQL 只读/写入验证模式，检查公开页面和后台保存
9. 最后安排正式停机窗口做最终迁移

运行时数据库适配底座：

```text
scripts/db_runtime.py
```

烟测脚本：

```bash
python3 scripts/runtime_db_smoke.py
```

如果设置了 `DATABASE_URL`，烟测会连接 PostgreSQL；否则默认检查 SQLite。

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' python3 scripts/runtime_db_smoke.py
```

预检脚本：

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' \
python3 scripts/postgres_preflight.py --require-wechat
```

预检会检查 SQLite 源库、PostgreSQL 连接、核心表、初始化标记、微信小程序环境变量和生产 Cookie 配置。

运行时回归脚本：

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' \
python3 scripts/postgres_runtime_regression.py --allow-write
```

该脚本会临时写入并清理测试数据，用来检查用户、登录会话、meta、审核申请、维度数据、AI 任务、访问日志和 AI 对话记录。若还要验证整体资料重写保存路径，可在测试库加：

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' \
python3 scripts/postgres_runtime_regression.py --allow-write --include-rewrite
```

核心读取验证模式：

```bash
export DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats'
export ENABLE_POSTGRES_READS=1
```

打开后，`sqlite_store.py` 内的核心读取函数会通过 `scripts/db_runtime.py` 读取 PostgreSQL，包括用户、门派、战队、选手、比赛和赛季维度统计。不开 `ENABLE_POSTGRES_READS=1` 时，网站仍然默认读取 SQLite。

账号写入验证模式：

```bash
export DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats'
export ENABLE_POSTGRES_WRITES=1
```

打开后，账号资料、微信登录自动创建账号、微信绑定资料、网页登录会话、小程序登录会话、扫码登录临时状态、比赛录入、选手/战队/门派维护、维度数据保存、审核申请、AI 任务和访问日志会写入 PostgreSQL。`ENABLE_POSTGRES_WRITES=1` 会自动让读取也走 PostgreSQL，避免读写分库。

生产启动命令建议直接使用内置脚本。脚本会先安装依赖、检查生产配置、升级表结构、检查运行时数据库、执行 smoke，最后启动服务：

```bash
sh scripts/start_production.sh
```

如果 `production_config_check.py` 或 `check_runtime_schema.py` 未通过，不要启动服务，先按提示补环境变量、表结构或连接串。

上线前推荐先跑一键检查。它会串起生产配置、综合发布体检和备份可读性验证：

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' \
ENABLE_POSTGRES_WRITES=1 \
WECHAT_MINIPROGRAM_APPID='你的 AppID' \
WECHAT_MINIPROGRAM_SECRET='你的 Secret' \
WEB_LOGIN_BASE_URL='https://wolf.metauniverse-cn.xyz' \
COOKIE_SECURE=1 \
python3 scripts/pre_deploy_check.py
```

本地已经准备好 PostgreSQL 时，也可以一条命令做完整生产启动演练。它会先跑上线前检查，再临时启动生产服务，访问 `/healthz` 和 `/readyz?write=1`，最后自动停止服务：

```bash
DATABASE_URL='postgresql://werewolf:werewolf@127.0.0.1:5432/werewolf_stats' \
sh scripts/local_production_smoke.sh
```

如果 `8000` 端口被占用，可以临时换端口：

```bash
DATABASE_URL='postgresql://werewolf:werewolf@127.0.0.1:5432/werewolf_stats' \
PORT=8010 \
sh scripts/local_production_smoke.sh
```

本地演练可以放宽微信和 SQLite 限制：

```bash
python3 scripts/pre_deploy_check.py --local --no-assets
```

如果你准备了一个空的 PostgreSQL 恢复测试库，可以加上恢复演练参数。测试库名称建议包含 `restore`、`test` 或 `staging`，避免误恢复到正式库：

```bash
python3 scripts/pre_deploy_check.py \
  --restore-test-database-url 'postgresql://user:password@host:5432/werewolf_stats_restore_test'
```

也可以单独执行生产配置体检：

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' \
ENABLE_POSTGRES_WRITES=1 \
WECHAT_MINIPROGRAM_APPID='你的 AppID' \
WECHAT_MINIPROGRAM_SECRET='你的 Secret' \
WEB_LOGIN_BASE_URL='https://wolf.metauniverse-cn.xyz' \
COOKIE_SECURE=1 \
python3 scripts/production_config_check.py
```

上线前可以先跑一次综合体检。它不会占用 Web 端口，会检查 Python 文件语法、运行时数据库结构、核心后台页面渲染、日志清理确认保护和请求编号追踪：

```bash
python3 scripts/release_check.py
```

也可以单独跑小程序高频接口基准测试。它不会绑定 Web 端口，会直接调用后端 WSGI 入口，输出每个接口的平均耗时和最大耗时：

```bash
python3 scripts/benchmark_miniprogram_api.py --require-data
```

基准测试默认会先预热一次再计时，适合观察缓存生效后的稳态体验。想观察冷启动耗时，可以加 `--warmup-runs 0`。

预测接口带有短缓存。可以单独检查缓存命中和失效链路：

```bash
python3 scripts/check_prediction_cache.py --require-data
```

上线后管理员可以在 `/ops` 查看运维总览，包括 API 耗时、错误请求、近期问题请求和预测缓存命中状态。页面顶部会显示健康评分和告警：错误率 2% 开始提醒、5% 进入异常；慢请求率 5% 开始提醒、10% 进入异常。
管理员也可以通过 `/api/ops` 获取同一份 JSON 健康状态，便于后续接入外部监控；未登录或非管理员访问会返回 403。

正式 PostgreSQL 环境建议带上连接串运行：

```bash
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats' \
ENABLE_POSTGRES_WRITES=1 \
python3 scripts/release_check.py
```

常用启动环境变量：

```bash
APP_DIR=/app
DATABASE_URL='postgresql://user:password@host:5432/werewolf_stats'
HOST=0.0.0.0
PORT=8000
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=120
IMPORT_BACKGROUND_WORKERS=1
INSTALL_REQUIREMENTS=1
RUN_PRODUCTION_CONFIG_CHECK=1
RUN_INDEX_CHECK=1
RUN_LOG_CLEANUP=1
ACCESS_LOG_RETENTION_DAYS=30
AUDIT_LOG_RETENTION_DAYS=365
SLOW_REQUEST_THRESHOLD_MS=1500
ACCESS_LOG_ASYNC_ENABLED=1
ACCESS_LOG_QUEUE_MAX_ENTRIES=5000
ACCESS_LOG_BATCH_SIZE=100
ACCESS_LOG_FLUSH_SECONDS=0.5
REQUEST_RATE_LIMIT_ENABLED=1
REQUEST_RATE_LIMIT_WINDOW_SECONDS=60
REQUEST_RATE_LIMIT_DEFAULT_MAX=120
REQUEST_RATE_LIMIT_SENSITIVE_MAX=30
IDEMPOTENCY_PROTECTION_ENABLED=1
IDEMPOTENCY_PROTECTION_TTL_SECONDS=8
STRUCTURED_ERROR_TRACEBACK=0
SECURITY_HEADERS_ENABLED=1
CSRF_PROTECTION_ENABLED=1
# 可选：覆盖默认 CSP。默认值已兼容当前页面和静态资源。
# CONTENT_SECURITY_POLICY="default-src 'self'; frame-ancestors 'none'; object-src 'none'"
```

比赛 Excel 导入会在 Web 进程内的后台工作线程串行执行，提交后可在“比赛管理 → 导入记录与回滚”查看状态。部署或重启服务前，请确认没有状态为“处理中”的导入批次；正在运行的进程内任务不会跨重启恢复。

脚本默认要求 `DATABASE_URL` 存在，并默认设置 `ENABLE_POSTGRES_WRITES=1`，避免生产环境意外回落到 SQLite。

访问日志和审计日志会随运行增长。生产启动脚本默认会执行一次过期日志清理：

- `ACCESS_LOG_RETENTION_DAYS`：访问日志保留天数，默认 30
- `AUDIT_LOG_RETENTION_DAYS`：操作审计保留天数，默认 365
- `RUN_LOG_CLEANUP=0`：关闭启动时自动清理

也可以手动预览或执行清理：

```bash
python3 scripts/cleanup_logs.py --dry-run
python3 scripts/cleanup_logs.py --access-days 30 --audit-days 365
```

后台的“访问统计”页也提供手动清理入口；每次实际清理会把摘要写入 `app_meta`，方便确认上次清理时间和删除数量。

服务端会把慢请求、5xx 响应、未捕获异常输出为单行 JSON 日志，字段包含 `event`、`level`、`request_id`、`path`、`status_code`、`duration_ms`、`username`、`ip_address` 等。线上排障时可以先用页面上的“请求编号”搜索服务器日志：

```bash
grep 'req_xxxxx' app.log
```

- `SLOW_REQUEST_THRESHOLD_MS`：慢请求阈值，默认 1500 毫秒；设为 `0` 可关闭慢请求日志
- `STRUCTURED_ERROR_TRACEBACK=1`：在结构化异常日志里附带完整堆栈；默认关闭，避免日志过长
- `SECURITY_HEADERS_ENABLED=1`：默认开启安全响应头；生产环境不要关闭
- `CSRF_PROTECTION_ENABLED=1`：默认开启后台浏览器表单 CSRF 防护；生产环境不要关闭
- `CONTENT_SECURITY_POLICY`：可覆盖默认 CSP。默认策略会限制页面嵌套、对象加载和跨源能力，同时兼容当前 Google Fonts、Bootstrap CDN 和站内静态资源

### 12. 当前仓库做过的线上优化

为了减少 `1Panel` 下长时间运行后出现 `504` 的概率，当前仓库已经额外做了两件事：

- 新增 `wsgi.py` 作为生产入口，供 `gunicorn` 直接启动
- 网站读取路径加入短时运行时缓存，保存数据后会自动失效，减少普通页面反复整库校验造成的阻塞
- SQLite 连接默认启用 WAL、busy timeout 和 `synchronous=NORMAL`，降低读写互相阻塞的概率
- 新增 `/healthz`、`/readyz`，方便部署平台和反向代理做健康检查
- 每个请求会自动生成或沿用 `X-Request-ID`，响应头、访问日志和结构化异常日志都会带同一个请求编号，便于线上排障
- 默认开启安全响应头，包括 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`、`Permissions-Policy`、`Cross-Origin-*` 和 HTML CSP
- 登录后的后台 POST 表单会自动注入并校验 CSRF token，防止跨站伪造提交；小程序/API 接口仍按 `session_token` 和接口权限校验
- Excel/zip/图片上传增加大小、行数、数量和文件头校验，避免错误文件拖慢导入或伪装格式绕过校验
- 新增 `scripts/backup_sqlite.py`，用于日常一致性备份
- 新增 `scripts/postgres_schema.sql`、`scripts/migrate_sqlite_to_postgres.py`、`scripts/apply_postgres_schema.py`，用于 PostgreSQL 迁移和表结构升级
- 新增 `scripts/db_runtime.py`、`scripts/runtime_db_smoke.py`、`scripts/check_runtime_schema.py`、`scripts/start_production.sh`，为 PostgreSQL 运行时切换、连接烟测、启动前结构检查和生产启动做适配
- 新增 `scripts/cleanup_logs.py` 和后台日志留存清理，避免访问日志长期堆积拖慢后台查询
- 新增 `scripts/backup_restore_check.py`，用于备份后验证和 PostgreSQL 恢复演练

### 网站数据说明

- 正式运行主库建议使用 PostgreSQL；`data/werewolf_stats.db` 主要用于本地开发、迁移对照和应急回滚
- 用户、战队、队员、比赛、申请数据都保存在运行时数据库中
- 比赛记录支持单独的“赛事名称”字段，例如“京城大师赛广州公开赛”或“LAL广州公开赛”
- 如需从旧 `JSON` 数据迁移，可执行 `python3 scripts/migrate_json_to_sqlite.py`
- 页面中的当前时间按中国时间展示

---

## 备注

- `assets/players/` 和 `assets/teams/` 用来存放头像和队标文件
- 当前仓库支持从空库初始化，适合直接上线后录入正式数据
- 后续可以继续扩展角色专属数据，例如预言家命中率、猎人开枪命中率、女巫救毒收益等

- 欢迎PR 或者tg联系[@cvfaker](https://t.me/cvfaker)
