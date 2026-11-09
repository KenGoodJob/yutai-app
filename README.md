# yutai-app

個人用の株主優待検索ツール「優待サーチ」のリポジトリです。表示ページは GitHub Pages(`index.html`)で、収集データ(`data/`)を直接読みます。

## 使い方(iPadのSafariから)

- 収集は手動のみです(自動実行はしません)
- 表示ページで未取得の月(点線のチップ)を押すと取得、「取り直す」で表示中の月を最新にします。初回だけ、Actions の Read and write 権限を持つ yutai-app 専用のトークンを表示ページに保存します(端末のブラウザ内のみ。リポジトリには入れない)
- **Actions** タブ → 「優待データ収集」→ **Run workflow** からも実行できます
- 終わると `data/YYYY-MM.json` と `data/index.json` が更新され、表示ページにそのまま反映されます

## 中身

- `index.html` … 表示ページ
- `version.json` … 最新の版番号。開いている版が古いと、表示ページが「新しい版があります」と知らせる
- `scripts/bump-version.sh` … 公開前に実行し、`index.html` の `APP_VERSION` と `version.json` を現在時刻(日本時間14桁)にそろえる
- `scripts/collect.py` … 96ut.com から指定月の売建リストと各銘柄の優待ページを取得(1件ごとに1〜2秒空ける)
- `.github/workflows/collect.yml` … 収集(手動実行。表示ページからも起動)
- `.github/workflows/index.yml` … `data/` を変更したときに目次を作り直す
- `data/` … 収集結果。`index.json` が目次
- `samples/` … 読み取り調整用の元HTML(必要なときだけ保存)
