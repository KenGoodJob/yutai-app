"""96ut.com から指定月の株主優待データを集めて data/YYYY-MM.json を作る。

使い方:
    python scripts/collect.py --month 4 [--terms 420] [--limit 0] [--samples 3]

- 取得は1件ごとに1〜2秒空ける(相手サイトへの負担を抑えるため)
- 1銘柄の取得に失敗しても止めず、その銘柄は優待内容なしで出力する
- --samples 件数分の元HTMLを samples/ に保存する(読み取りの調整用)
"""

import argparse
import datetime as dt
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = "https://96ut.com"
LIST_URL = BASE + "/yuutai/uritate.php?term={term}"
STOCK_URL = BASE + "/stock/yutai.php?code={code}"
BROKERS = ["松井", "eスマ", "SBI", "楽天", "GMO", "日興"]
# 見出しの表記ゆれ(左が正式名)
BROKER_ALIASES = {
    "松井": ["松井"],
    "eスマ": ["eスマ", "ｅスマ", "スマート", "岡三"],
    "SBI": ["SBI", "ＳＢＩ"],
    "楽天": ["楽天"],
    "GMO": ["GMO", "ＧＭＯ"],
    "日興": ["日興", "SMBC"],
}
CODE_RE = re.compile(r"^[0-9][0-9A-Z]{3}$")
JST = dt.timezone(dt.timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent

session = requests.Session()
session.headers["User-Agent"] = "yutai-app-collector/1.0 (personal use, low frequency)"


def polite_sleep():
    time.sleep(random.uniform(1.0, 2.0))


def fetch(url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    return r.text


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def to_int(s):
    m = re.search(r"[\d,]+", s or "")
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------- 売建リスト

def broker_of(header_text):
    for name, keys in BROKER_ALIASES.items():
        if any(k in header_text for k in keys):
            return name
    return None


def parse_list(html, month, day):
    """売建リストを読み、銘柄ごとの dict を返す。"""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_idx, colmap = None, {}
        for i, tr in enumerate(rows[:5]):
            cells = [clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
            found = {}
            for j, t in enumerate(cells):
                b = broker_of(t)
                if b and b not in found.values():
                    found[j] = b
            if len(found) >= 3:
                header_idx, colmap = i, found
                head_cells = cells
                break
        if header_idx is None:
            continue
        # その他の列の位置
        kind_col = next((j for j, t in enumerate(head_cells) if "貸借" in t or "制度" in t), None)
        month_col = next((j for j, t in enumerate(head_cells) if "月" in t and ("優待" in t or "権利" in t)), None)
        for tr in rows[header_idx + 1:]:
            cells = tr.find_all(["th", "td"])
            if len(cells) < 3:
                continue
            texts = [clean(c.get_text(" ")) for c in cells]
            code, name = None, ""
            for c in cells:
                for a in c.find_all("a", href=True):
                    q = parse_qs(urlparse(a["href"]).query)
                    if "code" in q and CODE_RE.match(q["code"][0]):
                        code = code or q["code"][0]
                        t = clean(a.get_text(" "))
                        if t and not CODE_RE.match(t) and not name:
                            name = t
            if not code:
                for t in texts:
                    m = re.match(r"^([0-9][0-9A-Z]{3})\b", t)
                    if m:
                        code = m.group(1)
                        break
            if not code:
                continue
            if not name:
                for t in texts:
                    if t and code not in t and not broker_of(t) and t not in ("貸借", "制度"):
                        name = t
                        break
            kind = ""
            if kind_col is not None and kind_col < len(texts):
                kind = "貸借" if "貸借" in texts[kind_col] else ("制度" if "制度" in texts[kind_col] else texts[kind_col])
            else:
                kind = next((t for t in texts if t in ("貸借", "制度")), "")
            months = [month]
            if month_col is not None and month_col < len(texts):
                ms = [int(x) for x in re.findall(r"(\d{1,2})月", texts[month_col]) if 1 <= int(x) <= 12]
                if ms:
                    months = sorted(set(ms))
            b = []
            for name_b in BROKERS:
                j = next((k for k, v in colmap.items() if v == name_b), None)
                if j is None or j >= len(texts):
                    b.append(None)
                else:
                    t = texts[j]
                    b.append("" if t in ("-", "－", "×", "✕") else t)
            item = {"c": code, "n": name, "k": kind, "m": months, "b": b}
            if day != "末":
                item["d"] = day
            items.append(item)
    # 重複を除く(同じコードは最初のものを残す)
    seen, out = set(), []
    for it in items:
        if it["c"] in seen:
            continue
        seen.add(it["c"])
        out.append(it)
    parse_list.raw = len(items)
    return out, soup


def other_terms(soup, month):
    """売建リストのページ内にある、同じ月の別権利日(例: 420)へのリンクを探す。"""
    terms = set()
    for a in soup.find_all("a", href=True):
        q = parse_qs(urlparse(a["href"]).query)
        t = (q.get("term") or [""])[0]
        m = re.fullmatch(rf"{month}(\d{{2}})", t)
        if m and 1 <= int(m.group(1)) <= 31:
            terms.add(t)
    return terms


# ---------------------------------------------------------------- 個別ページ

def parse_stock(html):
    """個別優待ページから優待内容などを読む。見つからない項目は空のまま。

    ページは <tr> の中に <th>ラベル</th><td>値</td> が1組以上並ぶ形。
    """
    soup = BeautifulSoup(html, "html.parser")
    out = {"t": "", "desc": "", "tiers": [], "times": None, "long": "", "note": "", "v": None, "cap": None, "name": ""}

    title = clean(soup.title.get_text(" ")) if soup.title else ""
    m = re.match(r"^(.+?)\([0-9][0-9A-Z]{3}\)の株主優待", title)
    if m:
        out["name"] = m.group(1).strip()

    pairs = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        for a, b in zip(cells, cells[1:]):
            if a.name == "th" and b.name == "td":
                pairs.append((clean(a.get_text(" ")), clean(b.get_text(" "))))

    tiers, arrive, comment = [], "", ""
    for label, v in pairs:
        if re.fullmatch(r"[\d,]+株(以上|未満)?.*", label) and len(label) <= 20:
            if v and [label, v] not in tiers:
                tiers.append([label, v])
        elif label == "優待内容":
            mm = re.search(r"優待回数：\s*年\s*(\d+)\s*回", v)
            if mm:
                out["times"] = int(mm.group(1))
                # 回数の後〜最初の「N株以上」までを補足説明として残す
                rest = v[mm.end():]
                cut = re.search(r"[\d,]+株(以上|未満)", rest)
                desc = (rest[: cut.start()] if cut else rest).strip()
                out["desc"] = desc[:200]
        elif label == "タイプ":
            out["t"] = v
        elif label.startswith("到着時期"):
            arrive = v
        elif label == "長期優遇":
            mm = re.search(r"長期条件等：\s*(.+?)(?:\s*長期認定|$)", v)
            if mm and mm.group(1).strip() not in ("", "-", "なし"):
                out["long"] = mm.group(1).strip()
        elif label == "コメント":
            comment = v
        elif label == "必要資金":
            out["cap"] = to_int(v)
        elif label.startswith("優待価値"):
            out["v"] = to_int(v)
    out["tiers"] = tiers
    notes = []
    if arrive:
        notes.append("到着: " + arrive)
    if comment:
        notes.append(comment)
    out["note"] = " / ".join(notes)
    if not out["long"]:
        joined = " ".join(t[1] for t in tiers)
        mm = re.search(r"(継続保有(?:期間)?\s*\d+\s*(?:年|ヶ月|か月|カ月)以上|\d+\s*(?:年|ヶ月|か月|カ月)以上(?:継続)?保有)", joined)
        if mm:
            out["long"] = mm.group(1)
    return out


def parse_broker_updated(soup):
    """売建リスト上部の「最終更新」行を {証券会社: 日時} で返す。"""
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        head = [clean(c.get_text(" ")) for c in rows[0].find_all(["th", "td"])]
        if not head or head[0] != "証券会社":
            continue
        for tr in rows[1:]:
            cells = [clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
            if cells and cells[0] == "最終更新":
                res = {}
                for h, v in zip(head[1:], cells[1:]):
                    b = broker_of(h)
                    if b:
                        res[b] = v
                return res
    return {}


# ---------------------------------------------------------------- 本体

def prune_old(data_dir, today, keep):
    """権利月が過ぎたファイルと、同じ月の古い年のファイルを消す。消したファイル名を返す。"""
    removed = []
    files = sorted(data_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].json"))
    newest = {}
    for fp in files:
        y, m = int(fp.stem[:4]), int(fp.stem[5:7])
        newest[m] = max(newest.get(m, 0), y)
    for fp in files:
        if fp.name == keep:
            continue
        y, m = int(fp.stem[:4]), int(fp.stem[5:7])
        if (y, m) < (today.year, today.month) or y < newest[m]:
            fp.unlink()
            removed.append(fp.name)
    return removed


def build_index(data_dir):
    """data/ にあるファイルから index.json を作り直す(消した月は目次からも消える)。"""
    months = []
    for fp in sorted(data_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except ValueError:
            continue
        its = d.get("items", [])
        months.append({"file": fp.name, "month": d.get("month"), "asof": d.get("asof", ""),
                       "at": d.get("at", ""), "count": len(its), "withYutai": sum(1 for x in its if x.get("t") or x.get("tiers"))})
    (data_dir / "index.json").write_text(json.dumps({"months": months}, ensure_ascii=False, indent=1), encoding="utf-8")


def target_year(month, today):
    return today.year if month >= today.month else today.year + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", type=int, default=0, help="権利月(0または省略=日本時間の当月)")
    ap.add_argument("--terms", default="", help="追加の権利日 term(例: 420)。カンマ区切り")
    ap.add_argument("--limit", type=int, default=0, help="個別ページの取得件数の上限(0=全件、試験用)")
    ap.add_argument("--samples", type=int, default=0, help="保存する元HTMLの件数(個別ページ)")
    ap.add_argument("--index-only", action="store_true", help="目次の作り直しだけ行う")
    ap.add_argument("--list-only", action="store_true", help="売建リストだけ読んで件数を出す(データは書かない。調査用)")
    args = ap.parse_args()
    if args.index_only:
        (ROOT / "data").mkdir(exist_ok=True)
        build_index(ROOT / "data")
        return
    now = dt.datetime.now(JST)
    today = now.date()
    month = args.month or today.month
    if not 1 <= month <= 12:
        sys.exit("month は1〜12")
    sample_dir = ROOT / "samples"
    if args.samples:
        sample_dir.mkdir(exist_ok=True)

    # 1) 売建リスト(月末+別権利日)
    # 手入力の権利日は「月+2桁の日」(例: 4月20日 → 420)だけ受け付ける。
    # URLや保存ファイル名に使うため、それ以外の文字(../ など)は捨てる
    extra = []
    for t in (t.strip() for t in args.terms.split(",")):
        m = re.fullmatch(rf"{month}(\d{{2}})", t)
        if m and 1 <= int(m.group(1)) <= 31:
            extra.append(t)
        elif t:
            print(f"権利日の指定を無視しました(形式が違う): {t!r}")
    terms = [f"{month}end"] + extra
    done, items, log, updated = set(), [], [], {}
    while terms:
        term = terms.pop(0)
        if term in done:
            continue
        done.add(term)
        day = "末" if term.endswith("end") else int(term[len(str(month)):])
        url = LIST_URL.format(term=term)
        try:
            html = fetch(url)
        except Exception as e:  # noqa: BLE001
            log.append(f"一覧取得失敗 {term}: {e}")
            polite_sleep()
            continue
        if args.samples:
            (sample_dir / f"list-{term}.html").write_text(html, encoding="utf-8")
        got, soup = parse_list(html, month, day)
        if not updated:
            updated = parse_broker_updated(soup)
        have = {it["c"] for it in items}
        dup = [it["c"] for it in got if it["c"] in have]
        log.append(f"一覧 {term}: {len(got)}件(表の行 {parse_list.raw}、ページ内の重複 {parse_list.raw - len(got)}、他の権利日と重複 {len(dup)}{': ' + ','.join(dup[:20]) if dup else ''})")
        items += [it for it in got if it["c"] not in have]
        for t in sorted(other_terms(soup, month)):
            if t not in done and t not in terms:
                terms.append(t)
        polite_sleep()

    if args.list_only:
        write_summary([f"## 売建リストのみ({month}月、データは書いていません)", f"- 銘柄数: {len(items)}"] + [f"- {x}" for x in log])
        return

    # 2) 個別ページ
    fail = 0
    targets = items if not args.limit else items[: args.limit]
    for i, it in enumerate(targets):
        url = STOCK_URL.format(code=it["c"])
        try:
            html = fetch(url)
            if i < args.samples:
                (sample_dir / f"stock-{it['c']}.html").write_text(html, encoding="utf-8")
            info = parse_stock(html)
            page_name = info.pop("name")
            # 一覧の名前が省略(…)されていれば個別ページの名前を使う
            if page_name and (not it["n"] or it["n"].endswith(("…", "..."))) and len(page_name) <= 60:
                it["n"] = page_name
            for k, v in info.items():
                it[k] = v
        except Exception as e:  # noqa: BLE001
            fail += 1
            log.append(f"個別取得失敗 {it['c']}: {e}")
        print(f"[{i + 1}/{len(targets)}] {it['c']} {it['n']}", flush=True)
        polite_sleep()

    for it in items:
        it.setdefault("t", "")
        it.setdefault("desc", "")
        it.setdefault("tiers", [])
        it.setdefault("times", None)
        it.setdefault("long", "")
        it.setdefault("note", "")
        it.setdefault("v", None)
        it.setdefault("cap", None)

    # 3) 読み取りの点検。おかしければ前回のデータを残して失敗にする
    with_t = sum(1 for it in items if it["t"] or it["tiers"])
    t_ok = sum(1 for it in targets if it["t"] or it["tiers"])
    cap_ok = sum(1 for it in targets if it["cap"])
    missing_b = [b for i, b in enumerate(BROKERS) if items and all((it.get("b") or [None] * 6)[i] is None for it in items)]
    reason, detail = "", ""
    if not items:
        reason, detail = "list", "売建リストから銘柄が1件も読めませんでした(サイトの停止、URLや表の作りの変更)"
    elif targets and (t_ok * 2 < len(targets) or cap_ok * 2 < len(targets)):
        reason, detail = "stock", f"個別ページがほとんど読めませんでした(優待内容 {t_ok}/{len(targets)}、必要資金 {cap_ok}/{len(targets)})"
    elif missing_b:
        reason, detail = "broker", "証券会社の列が読めませんでした: " + "、".join(missing_b)
    if reason:
        abort_keep(reason, detail, items, with_t, fail_count=fail, log=log)

    year = target_year(month, today)
    data = {"asof": today.isoformat(), "at": now.strftime("%Y-%m-%d %H:%M"), "month": month, "brokers": BROKERS,
            "brokerUpdated": [updated.get(b, "") for b in BROKERS], "items": items}
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    fname = f"{year}-{month:02d}.json"
    (data_dir / fname).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # 4) 古いデータの削除と目次
    removed = prune_old(data_dir, today, keep=fname)
    if removed:
        log.append("削除: " + ", ".join(removed))
    build_index(data_dir)

    write_summary([f"## {fname}", f"- 銘柄数: {len(items)}", f"- 優待内容あり: {with_t}", f"- 個別取得失敗: {fail}"] + [f"- {x}" for x in log])


def write_summary(lines):
    print("\n".join(lines))
    env = __import__("os").environ
    with open(Path(env.get("GITHUB_STEP_SUMMARY", "/dev/null")), "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def abort_keep(reason, detail, items, with_t, fail_count, log):
    """データを書かずに終了する。原因の種類は表示ページが読めるよう step の出力 reason に入れる。"""
    write_summary(["## 失敗(前回のデータはそのまま)", f"- {detail}", f"- 銘柄数: {len(items)}",
                   f"- 優待内容あり: {with_t}", f"- 個別取得失敗: {fail_count}"] + [f"- {x}" for x in log]
                  + ["- 調べるときは samples に元HTMLを保存して再実行(入力 samples に件数)"])
    out = __import__("os").environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"reason={reason}\n")
    sys.exit(detail)


if __name__ == "__main__":
    main()
