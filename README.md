# NSW 租金数据仓库 + 问数小工具

个人练习项目。数据来自 NSW Fair Trading 公开的租房押金登记（2025-10 至 2026-10，约 34 万条新签租约）。

做了三件事：

1. **分层建模**：raw → staging → marts，SQL 文件 + 一个简单的 `ref()` 依赖运行器（`dw/run.py`），数据库用 SQLite。
2. **数据质量测试**：15 条（`dw/dq.py`）。实际遇到的问题：
   - 2026-09 的 Excel 默认 sheet 是字段说明，按默认读取会漏掉整月数据，改成按表头找数据 sheet；
   - 公开邮编参考表的 `SA4_NAME_2021` 列有误，改用 `sa4name`；
   - 租金异常值（< 80 或 > 5000）打标隔离，不删除。
3. **问数小工具**：把中文/英文问题解析成固定结构的查询条件，再用模板生成 SQL（`assistant/engine.js`）。评测题集和结果在 `assistant/` 和 `results/`。


## 运行

```bash
pip install openpyxl
python -m dw.ingest
python -m dw.run
python -m dw.dq
python -m unittest discover -s tests -t .
```

## 已知局限

- 只有新签租约，没有面积、房龄等信息；
- 郊区按邮编近似；
- 规则解析覆盖不到的问法会答错（见评测结果）。
