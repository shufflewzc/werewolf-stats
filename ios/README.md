# 一颗小草赛事 iOS

原生 SwiftUI 浏览客户端，最低支持 iOS 17，仅面向 iPhone。

当前 1.1 版同步小程序公开浏览功能：城市分组赛事入口、自定义赛段名称、三局预测日期切换和当天预测分享图。微信登录、选手绑定与扫码确认仍由小程序提供。

## 生成工程

```bash
cd ios
xcodegen generate
```

如果 `xcode-select -p` 仍指向 CommandLineTools，可在当前终端先执行：

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
```

默认连接 `https://wolf.metauniverse-cn.xyz`。Debug 调试时可通过启动参数覆盖：

```text
-APIBaseURL http://127.0.0.1:8000
```

签名由本机 Apple Developer Team 管理。Universal Links 上线前，需要在服务端设置 `APPLE_APP_TEAM_ID`。

## 验证

```bash
xcodebuild test \
  -project WerewolfStats.xcodeproj \
  -scheme WerewolfStats \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro'

xcodebuild archive \
  -project WerewolfStats.xcodeproj \
  -scheme WerewolfStats \
  -destination 'generic/platform=iOS' \
  -archivePath build/WerewolfStats.xcarchive
```

TestFlight 归档前，在 Xcode 的 Signing & Capabilities 中选择付费团队；Team ID 和账号凭据不提交到仓库。
