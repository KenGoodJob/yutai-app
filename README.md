# yutai-app

個人用の株主優待検索ツール「優待サーチ」のリポジトリです。表示ページは GitHub Pages(`index.html`)で、収集データ(`data/`)を直接読みます。

## 使い方(iPadのSafariから)

- 毎月1日 9:07(日本時間)に当月分を自動で収集します
- ほかの月は **Actions** タブ → 「優待データ収集」→ **Run workflow** で権利月を選んで実行します
- 終わると `data/YYYY-MM.json` と `data/index.json` が更新され、表示ページにそのまま反映されます

## 中身

- `index.html` … 表示ページ
- `version.json` … 最新の版番号。開いている版が古いと、表示ページが「新しい版があります」と知らせる
- `scripts/bump-version.sh` … 公開前に実行し、`index.html` の `APP_VERSION` と `version.json` を現在時刻(日本時間14桁)にそろえる
- `scripts/collect.py` … 96ut.com から指定月の売建リストと各銘柄の優待ページを取得(1件ごとに1〜2秒空ける)
- `.github/workflows/collect.yml` … 収集(毎月1日の自動実行と手動実行)
- `.github/workflows/index.yml` … `data/` を変更したときに目次を作り直す
- `data/` … 収集結果。`index.json` が目次
- `samples/` … 読み取り調整用の元HTML(必要なときだけ保存)
