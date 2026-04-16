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
/Users/shufflewzc/Documents/GitHub/werewolf-stats
```

线上服务器请替换成你自己的实际绝对路径，只要该目录下能看到：

- `wsgi.py`
- `requirements.txt`
- `scripts/`
- `data/`

### 2. 安装依赖

在 `1Panel` 的安装命令或初始化命令中填写：

```bash
pip install -r requirements.txt
```

如果运行环境里已经装过依赖，也可以手动补装：

```bash
pip install gunicorn
```

### 3. 启动命令

不要再直接使用：

```bash
python3 scripts/web_app.py
```

请改为：

```bash
gunicorn -w 2 -k gthread --threads 4 -t 120 -b 0.0.0.0:8000 wsgi:app
```

这条命令的含义：

- `wsgi:app` 使用仓库内置的生产入口
- `-w 2` 启动 2 个 worker，避免单请求卡住整站
- `--threads 4` 给每个 worker 额外线程，提高并发余量
- `-t 120` 将超时时间设为 120 秒，减少慢请求直接被杀掉
- `-b 0.0.0.0:8000` 监听 `8000` 端口，方便 `1Panel/OpenResty` 反代

### 4. 端口配置

建议应用监听端口保持为：

```text
8000
```

`1Panel` 网站反向代理继续转发到：

```text
127.0.0.1:8000
```

一般不需要额外改业务代码里的端口。

### 5. 推荐的 1Panel 填写方式

如果你的 `Python 运行环境` 页面里有类似字段，可以这样填：

- 运行目录：项目根目录
- 安装命令：`pip install -r requirements.txt`
- 启动命令：`gunicorn -w 2 -k gthread --threads 4 -t 120 -b 0.0.0.0:8000 wsgi:app`
- 监听端口：`8000`

### 6. 常见问题

如果仍然出现 `502` 或 `504`，优先检查：

- Python 运行环境是否真的已经切换到 `gunicorn`
- 当前工作目录是否为项目根目录，而不是 `scripts/`
- `requirements.txt` 是否已经安装成功
- `1Panel` 反向代理目标是否仍然是 `127.0.0.1:8000`
- Python 运行环境日志里是否有报错或进程退出记录

### 7. 当前仓库做过的线上优化

为了减少 `1Panel` 下长时间运行后出现 `504` 的概率，当前仓库已经额外做了两件事：

- 新增 `wsgi.py` 作为生产入口，供 `gunicorn` 直接启动
- 网站读取路径加入短时运行时缓存，保存数据后会自动失效，减少普通页面反复整库校验造成的阻塞

### 网站数据说明

- 主数据库文件：`data/werewolf_stats.db`
- 用户、战队、队员、比赛、申请数据都保存在同一个 SQLite 数据库中
- 比赛记录支持单独的“赛事名称”字段，例如“京城大师赛广州公开赛”或“LAL广州公开赛”
- 如需从旧 `JSON` 数据迁移，可执行 `python3 scripts/migrate_json_to_sqlite.py`
- 页面中的当前时间按中国时间展示

---

## 备注

- `assets/players/` 和 `assets/teams/` 用来存放头像和队标文件
- 当前仓库支持从空库初始化，适合直接上线后录入正式数据
- 后续可以继续扩展角色专属数据，例如预言家命中率、猎人开枪命中率、女巫救毒收益等

- 欢迎PR 或者tg联系[@cvfaker](https://t.me/cvfaker)
