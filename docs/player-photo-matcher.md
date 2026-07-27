# 赛季选手头像匹配工具

`scripts/filter_player_photo_zip.py` 用来从一个包含大量无关图片的文件夹中，筛选出指定赛季已经存在的选手头像。工具不会修改原图片或数据库，只会生成：

- `matched-player-photos.zip`：文件名已转换为 `player_id.扩展名`，可直接在后台“压缩包批量导入赛季队员头像”处上传。
- `matched-player-photos-preview.html`：带缩略图的本地核对页。
- `matched-player-photos-report.csv`：适合筛选、排序的详细匹配结果。

## 直接读取线上 S2 名单

```bash
python3 scripts/filter_player_photo_zip.py \
  --folder "/你的头像文件夹" \
  --from-site \
  --competition "京城大师赛广州公开赛" \
  --season "S2"
```

`S2` 会自动解析为线上唯一一个以 `S2` 结尾的完整赛季名。工具会递归扫描所有子文件夹。

## 使用后台导出的名单

先在比赛管理页的头像导入区域点击“导出本赛季队员名单”，然后执行：

```bash
python3 scripts/filter_player_photo_zip.py \
  --folder "/你的头像文件夹" \
  --roster "/下载目录/赛季队员名单.csv"
```

## 匹配规则

- `player_id.png`、`选手名.jpg` 会直接匹配。
- `战队名-选手名-头像.png`、`选手名 (1).jpg` 等常见文件名可以识别。
- 文件夹名包含战队名时，可用于区分同名选手。
- 同一选手命中多张图片、同名歧义和仅有近似猜测的图片不会进入 ZIP。
- `.png`、`.jpg`、`.jpeg`、`.webp`、`.gif` 与网站上传格式一致；其他文件会跳过。
- 空图片、伪装扩展名或超过网站单张 5 MB 限制的图片不会进入 ZIP。

先打开 HTML 预览，只在结果正确后上传 ZIP。若出现“同一选手多图”，请从源文件夹移走多余图片后重新运行。

## macOS 图形应用

构建原生 Mac 应用：

```bash
sh scripts/build_player_photo_matcher_app.sh
```

应用会生成在：

```text
dist/选手头像匹配器.app
```

双击应用后选择图片文件夹，赛事和赛季默认填写为“京城大师赛广州公开赛 / S2”。匹配结束后，可以在应用内直接打开 HTML 预览、CSV 核对表或在 Finder 中找到 ZIP。

应用使用系统原生 SwiftUI 界面，头像匹配引擎已经封装在应用内，不要求使用者另外安装 Python。当前构建目标是 Apple 芯片 Mac（arm64）和 macOS 13 及以上版本。首次构建时需要联网下载一次 PyInstaller；构建完成后的应用可离线启动，读取线上选手名单时仍需要网络。

当同一位选手匹配到多张图片时，App 会显示“请选择正确头像”：

1. 在每组选手下点击正确图片，金色边框和“已选择”表示当前选择。
2. 可以再次点击同组的另一张图片改选。
3. 所有组都完成选择后，“应用选择并生成最终 ZIP”按钮才会启用。
4. 点击按钮后，App 会把每组选中的图片与自动匹配图片一起写入最终 ZIP；未选图片不会进入压缩包，也不会从原文件夹删除。
