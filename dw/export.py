"""把可分析的事实行导出成浏览器能直接用的紧凑二进制（每行 7 字节）+ 维度元数据。
浏览器里的问答引擎在这份数据上执行查询；tests 里会用 SQLite 执行同一条 SQL 核对结果一致。
"""
import json, sqlite3, struct, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DW = ["Flat/Unit", "House", "Terrace/Townhouse"]


def main(db=ROOT / "warehouse.db", out=ROOT / "web"):
    con = sqlite3.connect(db)
    months = [r[0] for r in con.execute("SELECT DISTINCT month FROM fct_lodgement ORDER BY 1")]
    pcs = [r for r in con.execute("SELECT postcode, region, district, lga, suburbs, is_greater_sydney FROM dim_postcode ORDER BY postcode")]
    pidx = {p[0]: i for i, p in enumerate(pcs)}
    rows = con.execute("SELECT month, postcode, dwelling, bedrooms, weekly_rent FROM fct_lodgement WHERE is_analysable ORDER BY month, postcode").fetchall()
    buf = bytearray()
    for m, pc, dw, bd, rent in rows:
        buf += struct.pack("<BHBbH", months.index(m), pidx[pc], DW.index(dw), -1 if bd is None else min(bd, 127), int(round(rent)))
    out.mkdir(exist_ok=True)
    (out / "fact.bin").write_bytes(bytes(buf))
    import base64  # artifact 托管只接受文本 / 常见类型，页面用 base64 版本
    (out / "fact.b64.txt").write_text(base64.b64encode(bytes(buf)).decode())
    meta = dict(months=months, dwellings=DW, rows=len(rows), row_bytes=7,
                postcodes=[dict(pc=p[0], region=p[1], district=p[2], lga=p[3], suburbs=(p[4] or "").split("|"), gsyd=p[5]) for p in pcs])
    json.dump(meta, open(out / "meta.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for f in ["dq.json", "lineage.json", "eval.json", "ingest_sheets.json"]:
        if (ROOT / "results" / f).exists(): shutil.copy(ROOT / "results" / f, out / f)
    print(f"fact.bin {len(buf)/1e6:.2f} MB · {len(rows)} rows · {len(pcs)} postcodes · months {months[0]}..{months[-1]}")


if __name__ == "__main__":
    main()
