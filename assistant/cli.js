// 用法：node assistant/cli.js "问题"   或   node assistant/cli.js --batch questions.json > out.json
const fs = require("fs"), path = require("path");
const { Engine } = require("./engine.js");
const W = path.join(__dirname, "..", "web");
const eng = new Engine(JSON.parse(fs.readFileSync(path.join(W, "meta.json"))), fs.readFileSync(path.join(W, "fact.bin")));
if (process.argv[2] === "--batch") {
  const qs = JSON.parse(fs.readFileSync(process.argv[3]));
  const out = qs.map(x => { const r = eng.ask(x.q); return { id: x.id, q: x.q, status: r.status, intent: r.intent || null, sql: r.sql || null, result: r.result || null, reason: r.reason || null }; });
  process.stdout.write(JSON.stringify(out));
} else {
  const r = eng.ask(process.argv.slice(2).join(" "));
  console.log(r.status, r.reason || ""); if (r.intent) console.log(JSON.stringify(r.intent)); if (r.sql) console.log(r.sql); if (r.answer) console.log(r.answer.text, (r.answer.rows || []).map(x => x.label + " " + x.shown + " (n=" + x.n + ")").join(" | "), r.answer.warn || "");
}
