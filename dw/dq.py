"""数据质量测试：每条测试是一句 SQL，返回「不合格的行」。
严重级别：error = 会让结论出错，必须修；warn = 打标后隔离，不进指标；info = 已知现象，记录在案。
每条测试都写了「处理决定」——测试只负责发现，怎么处理是人的判断。
"""
import json, sqlite3, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MONTHS = "january february march april may june july august september october november december".split()

TESTS = [
    # —— 来源层 ——
    dict(id="src_rows_per_file", layer="raw", sev="error", name="每个月度文件都读到了数据（行数 > 1000）",
         sql="SELECT source_file, count(*) AS n FROM raw_bond_lodgements GROUP BY source_file HAVING n < 1000",
         decision="真实发生过：2026 年 9 月的文件打开后默认显示「字段说明」sheet，只读到 4 行。改为按表头匹配找数据 sheet。"),
    dict(id="src_date_in_file_month", layer="raw", sev="error", name="登记日期落在文件对应的月份内",
         sql=None, decision="不在本月的行说明文件串月或日期列错位，需要回查来源。"),
    dict(id="ref_sa4_column_sane", layer="raw", sev="warn", name="参考表 SA4_NAME_2021 列取值多样（NSW 应有 ≥ 20 个 SA4）",
         sql="SELECT 'SA4_NAME_2021' AS col, count(DISTINCT SA4_NAME_2021) AS distinct_values FROM raw_postcodes HAVING distinct_values < 20",
         decision="上游参考表这一列整列都是 'Sydney - Sutherland'（Randwick、纽卡斯尔都被标成 Sutherland）。不用这一列，改用 sa4name，并保留本测试防止回退。"),
    dict(id="dim_region_sane", layer="marts", sev="error", name="维度表实际使用的区域列取值多样（≥ 20 个 SA4）",
         sql="SELECT count(DISTINCT region) AS distinct_regions FROM dim_postcode HAVING distinct_regions < 20",
         decision="必须为 0：确认绕开上游坏列之后，维度表的区域是对的。"),
    # —— 清洗层 ——
    dict(id="stg_not_null_keys", layer="staging", sev="error", name="日期、邮编不为空",
         sql="SELECT * FROM stg_bond_lodgements WHERE lodgement_date IS NULL OR postcode IS NULL", decision="必须为 0。"),
    dict(id="stg_dwelling_code_valid", layer="staging", sev="warn", name="房型编码在 F/H/T/O/U 之内",
         sql="SELECT dwelling_code_raw, bedrooms_raw, weekly_rent_raw, source_file, source_row FROM stg_bond_lodgements WHERE dwelling = 'Invalid'",
         decision="多数是数字（1、3、4），疑似录入时房型和卧室数串列。行数极少，标为 Invalid 不进指标，不猜测原值。"),
    dict(id="stg_rent_unknown", layer="staging", sev="info", name="租金为 U（官方说明：未知）",
         sql="SELECT weekly_rent_raw, source_file, source_row FROM stg_bond_lodgements WHERE weekly_rent IS NULL",
         decision="官方字段说明里 U 表示未知，属预期现象；不进租金指标，但计入租约数量。"),
    dict(id="stg_bedrooms_unknown", layer="staging", sev="info", name="卧室数为 U（未知）",
         sql="SELECT bedrooms_raw FROM stg_bond_lodgements WHERE bedrooms IS NULL", decision="按卧室数分组时归入「未知」，不丢弃。"),
    dict(id="stg_rent_range", layer="staging", sev="warn", name="周租金在 80–5000 澳元之间",
         sql="SELECT dwelling, bedrooms, weekly_rent, postcode, source_file, source_row FROM stg_bond_lodgements WHERE weekly_rent IS NOT NULL AND (weekly_rent < 80 OR weekly_rent > 5000)",
         decision="低于 80 多为车位、储藏间（官方说明 Other 可能包括车位）；高于 5000 有真实豪宅也有多打一个 0 的。中位数对极端值不敏感，但均值会被拉高，所以统一隔离、不进指标。"),
    dict(id="stg_exact_duplicates", layer="staging", sev="info", name="完全相同的行（同日、同邮编、同房型、同卧室、同租金）",
         sql="SELECT lodgement_date, postcode, dwelling_code_raw, bedrooms_raw, weekly_rent_raw, count(*) AS n FROM stg_bond_lodgements GROUP BY 1,2,3,4,5 HAVING n > 1",
         decision="数据没有租约编号，同一栋楼同一天按同价出租多套是正常的，无法判定是重复登记。不去重，记录在案。"),
    # —— 模型层 ——
    dict(id="dim_postcode_unique", layer="marts", sev="error", name="邮编维度主键唯一",
         sql="SELECT postcode, count(*) n FROM dim_postcode GROUP BY postcode HAVING n > 1", decision="必须为 0。"),
    dict(id="fct_postcode_known", layer="marts", sev="warn", name="租约邮编能在维度表里找到",
         sql="SELECT postcode, count(*) AS n FROM fct_lodgement WHERE NOT postcode_known GROUP BY postcode",
         decision="多为只有邮政信箱、没有投递区域的邮编。数量很少，不进区域指标。"),
    dict(id="fct_rowcount_reconciles", layer="marts", sev="error", name="事实表行数 = 原始表行数（清洗不丢行）",
         sql="SELECT (SELECT count(*) FROM raw_bond_lodgements) AS raw_n, (SELECT count(*) FROM fct_lodgement) AS fct_n WHERE raw_n <> fct_n",
         decision="必须为 0：问题行只打标不删除，任何一行都能追到来源文件和行号。"),
    dict(id="mart_volume_anomaly", layer="marts", sev="warn", name="月度租约量与前 3 个月均值相比波动不超过 ±25%",
         sql="""WITH m AS (SELECT month, count(*) n FROM fct_lodgement GROUP BY month),
                w AS (SELECT month, n, avg(n) OVER (ORDER BY month ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS prev3,
                             count(*) OVER (ORDER BY month ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS k FROM m)
                SELECT month, n, round(prev3) AS prev3_avg, round(100.0*(n-prev3)/prev3,1) AS pct FROM w WHERE k = 3 AND abs(n-prev3)/prev3 > 0.25""",
         decision="超出阈值先看是不是装载问题（如 9 月文件），再看季节性（1–2 月是租房旺季）。"),
    dict(id="mart_freshness", layer="marts", sev="warn", name="最新数据月份距今不超过 2 个月",
         sql="SELECT max(month) AS latest FROM fct_lodgement HAVING julianday('now') - julianday(max(month) || '-01') > 62",
         decision="NSW 每月中旬发布上月数据；超过 2 个月没更新要检查抓取任务。"),
]


def date_in_file_month(con):
    bad = []
    for f, mo, n in con.execute("SELECT source_file, substr(lodgement_date,1,7), count(*) FROM raw_bond_lodgements GROUP BY 1,2"):
        name = f.lower()
        mi = next((i for i, m in enumerate(MONTHS) if m in name or m[:3] + "_" in name or m[:4] in name), None)
        yr = next((y for y in ("2024", "2025", "2026") if y in name), None)
        if mi is None or yr is None: continue
        if mo != f"{yr}-{mi + 1:02d}": bad.append((f, mo, n))
    return ["source_file", "month", "n"], bad


def run(con):
    out = []
    for t in TESTS:
        if t["id"] == "src_date_in_file_month":
            cols, rows = date_in_file_month(con)
        else:
            cur = con.execute(t["sql"]); cols = [d[0] for d in cur.description]; rows = cur.fetchall()
        n = len(rows)
        if t["id"] in ("stg_rent_unknown", "stg_bedrooms_unknown", "stg_rent_range", "stg_dwelling_code_valid", "stg_not_null_keys"):
            failing = n
        elif t["id"] in ("stg_exact_duplicates", "fct_postcode_known"):
            failing = sum(r[-1] for r in rows)
        else:
            failing = n
        out.append(dict(id=t["id"], layer=t["layer"], severity=t["sev"], name=t["name"], failing=failing, groups=n,
                        passed=failing == 0, decision=t["decision"], sql=t["sql"] or "(Python：文件名月份 vs 日期月份)",
                        sample=dict(cols=cols, rows=[list(r) for r in rows[:5]])))
    return out


def main(db=ROOT / "warehouse.db"):
    con = sqlite3.connect(db)
    res = run(con)
    total = con.execute("SELECT count(*) FROM fct_lodgement").fetchone()[0]
    usable = con.execute("SELECT count(*) FROM fct_lodgement WHERE is_analysable").fetchone()[0]
    summary = dict(run_at=datetime.datetime.now().isoformat(timespec="seconds"), rows=total, analysable=usable,
                   errors_failing=[r["id"] for r in res if r["severity"] == "error" and not r["passed"]])
    json.dump(dict(summary=summary, tests=res), open(ROOT / "results/dq.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    for r in res:
        print(f"  [{r['severity']:<5}] {'PASS' if r['passed'] else 'FAIL':<4} {r['failing']:>7}  {r['name']}")
    print(f"  可分析 {usable}/{total} = {usable/total:.1%}")
    return summary, res


if __name__ == "__main__":
    main()
