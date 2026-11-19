"""端到端测试：装载 → 建模 → 数据质量 → 问答评测。运行：python -m unittest discover -s tests -t ."""
import json, sqlite3, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dw import ingest, run, dq, export
        cls.n_raw, _ = ingest.main()
        run.run()
        cls.summary, cls.tests = dq.main()
        export.main()
        cls.con = sqlite3.connect(ROOT / "warehouse.db")

    def test_every_file_loaded(self):
        # 回归测试：9 月文件的数据不在默认 sheet，曾经只读到 4 行
        rows = dict(self.con.execute("SELECT source_file, count(*) FROM raw_bond_lodgements GROUP BY 1").fetchall())
        self.assertEqual(len(rows), 13)
        self.assertTrue(all(n > 20000 for n in rows.values()), rows)

    def test_no_error_level_failures(self):
        self.assertEqual(self.summary["errors_failing"], [])

    def test_fact_keeps_every_row(self):
        self.assertEqual(self.con.execute("SELECT count(*) FROM fct_lodgement").fetchone()[0], self.n_raw)

    def test_region_column_not_the_broken_one(self):
        # 回归测试：上游 SA4_NAME_2021 整列都是 Sutherland
        r = self.con.execute("SELECT region FROM dim_postcode WHERE postcode = 2031").fetchone()[0]
        self.assertEqual(r, "Sydney - Eastern Suburbs")

    def test_year_is_not_a_postcode(self):
        out = subprocess.check_output(["node", str(ROOT / "assistant/cli.js"), "How many new leases in NSW in September 2026?"], text=True)
        self.assertNotIn('"postcode"', out)

    def test_eval_floor_and_parity(self):
        from assistant import run_eval
        res = run_eval.main()
        self.assertGreaterEqual(res["dev"]["metrics"]["acc"], 0.9)
        for k in ("dev", "holdout", "holdout2"):
            a, b = res[k]["metrics"]["parity"].split("/")
            self.assertEqual(a, b, f"{k}: 浏览器结果与 SQLite 不一致")


if __name__ == "__main__":
    unittest.main()
