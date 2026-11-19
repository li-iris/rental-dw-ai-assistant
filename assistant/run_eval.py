"""评测：问题 → (Node) 引擎解析出意图、生成 SQL、在列式数据上算出结果
          → (Python) 在 SQLite 上执行引擎生成的 SQL 和手写的标准 SQL。
三个指标：
  1. 答对率：生成 SQL 的结果 = 标准 SQL 的结果（拒答 / 反问类看状态是否一致）
  2. 引擎一致性：浏览器里的 JS 执行结果 = SQLite 执行同一条 SQL 的结果（保证页面上的数字和 SQL 对得上）
  3. 拒答 / 反问准确率
"""
import json, sqlite3, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assistant.evalset import DEV, HOLDOUT, HOLDOUT2


def norm(rows):
    out = []
    for r in rows:
        out.append(tuple(round(float(x), 1) if isinstance(x, (int, float)) else x for x in r))
    return out


def js_rows(res):
    if res is None: return None
    if res["kind"] == "single": return [(res["value"],)]
    if res["kind"] == "compare": return [(res["current"], res["previous"])]
    return [(x["key"], x["value"]) for x in res["rows"]]


def strip_n(rows, kind):
    # 生成的 SQL 多带了样本量 n 列，比较时去掉
    if kind == "single": return [r[:1] for r in rows]
    if kind == "group": return [r[:2] for r in rows]
    return rows


def run(name, qs, con):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump([dict(id=i, q=q) for i, q, _ in qs], tmp, ensure_ascii=False); tmp.close()
    out = json.loads(subprocess.check_output(["node", str(ROOT / "assistant/cli.js"), "--batch", tmp.name]))
    rows, ok, parity, parity_n = [], 0, 0, 0
    for (i, q, gold), o in zip(qs, out):
        r = dict(id=i, q=q, status=o["status"], intent=o["intent"], sql=o["sql"], reason=o["reason"])
        if gold in ("REFUSE", "CLARIFY"):
            r["gold"] = gold; r["ok"] = o["status"] == gold
        else:
            g = norm(con.execute(gold).fetchall())
            r["gold"] = "SQL"; r["gold_rows"] = g
            if o["status"] != "OK":
                r["ok"] = False
            else:
                kind = o["result"]["kind"]
                mine = norm(strip_n(con.execute(o["sql"]).fetchall(), kind))
                r["ok"] = mine == g
                r["rows"] = mine
                js = norm(js_rows(o["result"]))
                parity_n += 1; parity += js == mine
                r["parity"] = js == mine
        ok += r["ok"]; rows.append(r)
    n_ref = sum(1 for _, _, g in qs if g in ("REFUSE", "CLARIFY"))
    ref_ok = sum(1 for r in rows if r["gold"] in ("REFUSE", "CLARIFY") and r["ok"])
    false_refuse = sum(1 for r in rows if r["gold"] == "SQL" and r["status"] != "OK")
    m = dict(n=len(qs), acc=round(ok / len(qs), 3), answerable=len(qs) - n_ref,
             answerable_acc=round(sum(r["ok"] for r in rows if r["gold"] == "SQL") / max(1, len(qs) - n_ref), 3),
             refuse_acc=round(ref_ok / max(1, n_ref), 3), false_refuse=false_refuse, parity=f"{parity}/{parity_n}")
    print(f"{name:<8} 答对 {ok}/{len(qs)} = {m['acc']:.0%} · 可答题 {m['answerable_acc']:.0%} · 拒答/反问 {m['refuse_acc']:.0%} · 误拒 {false_refuse} · JS=SQLite {m['parity']}")
    for r in rows:
        if not r["ok"]: print("   ✗", r["id"], r["q"], "→", r["status"], (r.get("reason") or "")[:40], json.dumps(r.get("intent"), ensure_ascii=False)[:160])
    return dict(metrics=m, rows=rows)


def main():
    con = sqlite3.connect(ROOT / "warehouse.db")
    res = {"dev": run("DEV", DEV, con), "holdout": run("HOLDOUT", HOLDOUT, con), "holdout2": run("HOLDOUT2", HOLDOUT2, con)}
    v1 = ROOT / "results/eval_holdout_v1.json"
    if v1.exists(): res["holdout_v1"] = json.load(open(v1, encoding="utf-8"))["holdout"]["metrics"]
    json.dump(res, open(ROOT / "results/eval.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    return res


if __name__ == "__main__":
    main()
