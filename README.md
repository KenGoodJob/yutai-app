# yutai-app

個人用の株主優待検索ツール「優待サーチ」のデータ収集用リポジトリです。

## 使い方(iPadのSafariから)

1. このリポジトリの **Actions** タブ → 「優待データ収集」を開く
2. **Run workflow** を押し、権利月を選んで実行
3. 終わると `data/YYYY-MM.json` が更新される
4. そのJSONを表示ページの「データ管理」から取り込む

## 中身

- `scripts/collect.py` … 96ut.com から指定月の売建リストと各銘柄の優待ページを取得(1件ごとに1〜2秒空ける)
- `.github/workflows/collect.yml` … 手動実行のワークフロー(定期実行はしない)
- `data/` … 収集結果。`index.json` が目次
- `samples/` … 読み取り調整用の元HTML(必要なときだけ保存)
