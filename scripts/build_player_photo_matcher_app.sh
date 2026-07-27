#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/macos/PlayerPhotoMatcher"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BUILD_DIR="$ROOT_DIR/build/player-photo-matcher-$TIMESTAMP"
PREVIOUS_DIR="$ROOT_DIR/build/player-photo-matcher-previous"
DIST_DIR="$ROOT_DIR/dist"
APP_NAME="选手头像匹配器"
APP_DIR="$DIST_DIR/$APP_NAME.app"
ZIP_PATH="$DIST_DIR/$APP_NAME-macOS-arm64.zip"
TOOLS_DIR="$ROOT_DIR/build/player-photo-matcher-tools"
PYINSTALLER="$TOOLS_DIR/bin/pyinstaller"

mkdir -p "$BUILD_DIR" "$PREVIOUS_DIR" "$DIST_DIR"
if [ -e "$APP_DIR" ]; then
  mv "$APP_DIR" "$PREVIOUS_DIR/$APP_NAME-$TIMESTAMP.app"
fi
if [ -e "$ZIP_PATH" ]; then
  mv "$ZIP_PATH" "$PREVIOUS_DIR/$APP_NAME-macOS-arm64-$TIMESTAMP.zip"
fi

mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

if [ ! -x "$PYINSTALLER" ]; then
  echo "[build] preparing standalone Python packager"
  python3 -m venv "$TOOLS_DIR"
  "$TOOLS_DIR/bin/python" -m pip install \
    --disable-pip-version-check \
    pyinstaller
fi

echo "[build] packaging standalone matching engine"
"$PYINSTALLER" \
  --noconfirm \
  --clean \
  --onefile \
  --name player-photo-matcher-cli \
  --distpath "$BUILD_DIR/helper-dist" \
  --workpath "$BUILD_DIR/helper-work" \
  --specpath "$BUILD_DIR" \
  "$ROOT_DIR/scripts/filter_player_photo_zip.py"

echo "[build] compiling SwiftUI app"
xcrun swiftc \
  -swift-version 5 \
  -parse-as-library \
  -O \
  -target arm64-apple-macos13.0 \
  -framework SwiftUI \
  -framework AppKit \
  "$SOURCE_DIR/PlayerPhotoMatcherApp.swift" \
  -o "$APP_DIR/Contents/MacOS/PlayerPhotoMatcher"

echo "[build] copying resources"
cp "$SOURCE_DIR/Info.plist" "$APP_DIR/Contents/Info.plist"
cp "$ROOT_DIR/scripts/filter_player_photo_zip.py" \
  "$APP_DIR/Contents/Resources/filter_player_photo_zip.py"
cp "$BUILD_DIR/helper-dist/player-photo-matcher-cli" \
  "$APP_DIR/Contents/Resources/player-photo-matcher-cli"
chmod 755 "$APP_DIR/Contents/Resources/player-photo-matcher-cli"

echo "[build] generating app icon"
xcrun swift \
  "$SOURCE_DIR/GenerateAppIcon.swift" \
  "$BUILD_DIR/AppIcon-1024.png"
mkdir -p "$BUILD_DIR/AppIcon.iconset"
sips -z 16 16 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_16x16.png" >/dev/null
sips -z 32 32 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_32x32.png" >/dev/null
sips -z 64 64 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_128x128.png" >/dev/null
sips -z 256 256 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_256x256.png" >/dev/null
sips -z 512 512 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$BUILD_DIR/AppIcon-1024.png" \
  --out "$BUILD_DIR/AppIcon.iconset/icon_512x512.png" >/dev/null
cp "$BUILD_DIR/AppIcon-1024.png" \
  "$BUILD_DIR/AppIcon.iconset/icon_512x512@2x.png"
iconutil -c icns "$BUILD_DIR/AppIcon.iconset" \
  -o "$APP_DIR/Contents/Resources/AppIcon.icns"

echo "[build] validating and signing app"
plutil -lint "$APP_DIR/Contents/Info.plist"
codesign --force --deep --sign - "$APP_DIR"
codesign --verify --deep --strict "$APP_DIR"

echo "[build] creating distribution zip"
ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$ZIP_PATH"
unzip -t "$ZIP_PATH" >/dev/null

echo "[build] done: $APP_DIR"
echo "[build] zip:  $ZIP_PATH"
