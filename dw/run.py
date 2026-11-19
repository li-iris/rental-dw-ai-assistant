"""一个极简的 dbt 式运行器：models/**.sql 里用 {{ ref('x') }} 引用上游模型，
按依赖关系拓扑排序后依次在 SQLite 里建表；同时输出血缘（lineage.json）。

用 SQLite 是为了零依赖、可复现；SQL 写法尽量保持标准（CTE + 窗口函数），可以直接迁到 PostgreSQL / dbt。
"""
import json, re, sqlite3, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse.db"
REF = re.compile(r"\{\{\s*ref\(['\"](\w+)['\"]\)\s*\}\}")
SRC = re.compile(r"\b(raw_\w+)\b")


def load_models():
    ms = {}
    for p in sorted((ROOT / "models").rglob("*.sql")):
        sql = p.read_text(encoding="utf-8")
        ms[p.stem] = dict(name=p.stem, layer=p.parent.name, path=str(p.relative_to(ROOT)), sql=sql,
                          deps=sorted(set(REF.findall(sql))), sources=sorted(set(SRC.findall(sql))),
                          doc=(sql.split("\n", 1)[0].lstrip("- ").strip() if sql.startswith("--") else ""))
    return ms


def toposort(ms):
    order, seen, tmp = [], set(), set()
    def visit(n):
        if n in seen: return
        if n in tmp: raise ValueError(f"循环依赖：{n}")
        if n not in ms: raise KeyError(f"ref 了不存在的模型：{n}")
        tmp.add(n)
        for d in ms[n]["deps"]: visit(d)
        tmp.discard(n); seen.add(n); order.append(n)
    for n in ms: visit(n)
    return order


def run(con=None):
    con = con or sqlite3.connect(DB)
    ms = load_models()
    order = toposort(ms)
    log = []
    for n in order:
        m = ms[n]
        body = REF.sub(lambda x: x.group(1), m["sql"])
        t = time.time()
        con.execute(f"DROP TABLE IF EXISTS {n}")
        con.execute(f"CREATE TABLE {n} AS {body}")
        rows = con.execute(f"SELECT count(*) FROM {n}").fetchone()[0]
        log.append(dict(model=n, layer=m["layer"], rows=rows, secs=round(time.time() - t, 2)))
        print(f"  {m['layer']:<8} {n:<28} {rows:>8} rows  {log[-1]['secs']}s")
    con.commit()
    lineage = [dict(name=n, layer=ms[n]["layer"], deps=ms[n]["deps"], sources=ms[n]["sources"], doc=ms[n]["doc"], path=ms[n]["path"]) for n in order]
    (ROOT / "results").mkdir(exist_ok=True)
    json.dump(dict(order=order, models=lineage, run=log), open(ROOT / "results/lineage.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return con, log


if __name__ == "__main__":
    run()
