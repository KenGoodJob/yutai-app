#!/bin/sh
# 公開前に実行：index.html の APP_VERSION と version.json を現在時刻（日本時間14桁）にそろえる
set -e
cd "$(dirname "$0")/.."
V=$(TZ=Asia/Tokyo date +%Y%m%d%H%M%S)
sed -i "s/^const APP_VERSION='[0-9]\{14\}';/const APP_VERSION='$V';/" index.html
printf '{"version":"%s"}\n' "$V" > version.json
grep -q "APP_VERSION='$V'" index.html
echo "$V"
