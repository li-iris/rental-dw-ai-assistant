"""把 assistant/engine.js 内联进页面（artifact 只允许 CDN 外链脚本），生成 web/index.html。"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "web/index.src.html").read_text(encoding="utf-8")
eng = (ROOT / "assistant/engine.js").read_text(encoding="utf-8")
(ROOT / "web/index.html").write_text(src.replace("/*ENGINE*/", eng), encoding="utf-8")
print("web/index.html", len(src) + len(eng), "bytes")
