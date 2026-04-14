# Excel Templates

- `match-result-upload-template.xlsx`: 比赛结果批量补录模板
- `dimension-stats-upload-template-jcds.xlsx`: 京城大师赛维度模板，包含：
- `team-logo-upload-template.xlsx`: 赛季战队图标批量导入模板，表头为 `战队名称`、`战队logo`；`战队logo` 列支持直接插入图片
- `player-photo-upload-template.xlsx`: 赛季队员头像批量导入模板，表头为 `选手姓名`、`选手头像`；`选手头像` 列支持直接插入图片
  - `单日选手个人维度数据`
  - `单日选手战队维度数据 `

Regenerate it with:

```powershell
python scripts/generate_match_result_excel_template.py
```
