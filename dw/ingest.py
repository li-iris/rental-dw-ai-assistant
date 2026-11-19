"""原始层：把 NSW Fair Trading 每月的押金登记 xlsx 和邮编参考表原样装进 SQLite（raw_ 表），不做任何清洗。

每行保留来源文件名和装载时间，出了问题能追到是哪个月的文件。
"""
import csv, glob, re, sqlite3, datetime
from pathlib import Path
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse.db"


HEADER = ("lodgement date", "postcode", "dwelling type", "bedrooms", "weekly rent")
SHEET_LOG = []


def pick_data_sheet(wb, f):
    """不能假设数据在第一个 sheet：2026 年 9 月的文件把「字段说明」放在了第一个 sheet。
    逐个 sheet 找表头完全匹配 5 个字段的那一个。"""
    for ws in wb.worksheets:
        for i, r in enumerate(ws.iter_rows(values_only=True, max_row=10)):
            if tuple(str(v).strip().lower() for v in r[:5] if v is not None) == HEADER:
                SHEET_LOG.append(dict(file=Path(f).name, sheet=ws.title, sheet_index=wb.worksheets.index(ws)))
                return ws
    raise ValueError(f"{f}: 没找到数据 sheet（表头不匹配）")


def load_bonds(con):
    con.execute("DROP TABLE IF EXISTS raw_bond_lodgements")
    con.execute("""CREATE TABLE raw_bond_lodgements(
        lodgement_date TEXT, postcode TEXT, dwelling_type TEXT, bedrooms TEXT, weekly_rent TEXT,
        source_file TEXT, source_row INTEGER, loaded_at TEXT)""")
    now = datetime.datetime.now().isoformat(timespec="seconds")
    n = 0
    for f in sorted(glob.glob(str(ROOT / "data/raw/rentalbond_lodgements_*.xlsx"))):
        ws = pick_data_sheet(openpyxl.load_workbook(f, read_only=True), f)
        rows = ws.iter_rows(values_only=True)
        header_at = None
        batch = []
        for i, r in enumerate(rows, 1):
            r = tuple(r) + (None,) * max(0, 5 - len(r))
            if header_at is None:
                if tuple(str(v).strip().lower() for v in r[:5] if v is not None) == HEADER:
                    header_at = i
                continue
            if not any(v is not None for v in r[:5]):
                continue
            d = r[0].date().isoformat() if isinstance(r[0], datetime.datetime) else (None if r[0] is None else str(r[0]))
            batch.append((d, *[None if v is None else str(v).strip() for v in r[1:5]], Path(f).name, i, now))
        con.executemany("INSERT INTO raw_bond_lodgements VALUES (?,?,?,?,?,?,?,?)", batch)
        n += len(batch)
    return n


def load_postcodes(con):
    con.execute("DROP TABLE IF EXISTS raw_postcodes")
    rows = list(csv.DictReader(open(ROOT / "data/ref/au_postcodes_nsw_subset.csv", encoding="utf-8")))
    cols = list(rows[0])
    con.execute(f"CREATE TABLE raw_postcodes({', '.join(c + ' TEXT' for c in cols)})")
    con.executemany(f"INSERT INTO raw_postcodes VALUES ({','.join('?' * len(cols))})", [tuple(r[c] for c in cols) for r in rows])
    return len(rows)


def main():
    con = sqlite3.connect(DB)
    n1, n2 = load_bonds(con), load_postcodes(con)
    con.commit()
    import json
    (ROOT / "results").mkdir(exist_ok=True)
    json.dump(SHEET_LOG, open(ROOT / "results/ingest_sheets.json", "w"), ensure_ascii=False, indent=1)
    print(f"raw_bond_lodgements {n1} rows · raw_postcodes {n2} rows → {DB.name}")
    return n1, n2


if __name__ == "__main__":
    main()
