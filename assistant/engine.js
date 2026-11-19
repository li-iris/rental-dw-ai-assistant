/* 租金问答引擎：自然语言 → 受约束的查询意图（JSON）→ SQL（展示与核对用）+ 在列式数据上执行。
 * 设计原则：
 *  1. 语言理解只输出「意图」，不直接写 SQL —— 指标、维度、过滤条件都只能取语义层里定义好的值，SQL 由模板生成，不会出现注入或编造字段。
 *  2. 规则先解析；规则拿不准（没识别出地区 / 指标）时，页面可以把问题交给大模型，但大模型也只能返回同一个 JSON 结构，返回后照样过校验。
 *  3. 资料外的问题（房价、预测、其他州、个人信息）直接拒答；地名对不上就反问，不猜。
 *  4. 小样本保护：分组样本少于 30 条的不参与排名，单点查询会提示样本量。
 * 同一份文件在 Node（评测）和浏览器（页面）里运行。
 */
(function (root) {
  const DW = ["Flat/Unit", "House", "Terrace/Townhouse"];
  const DW_ZH = { "Flat/Unit": "公寓", "House": "独立屋", "Terrace/Townhouse": "联排" };
  const METRIC_ZH = { median: "周租金中位数", mean: "周租金均值", count: "新签租约数", p25: "周租金 25 分位", p75: "周租金 75 分位" };
  const MIN_N = 30;
  const CN = { 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6 };
  const MONTH_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
  // 常用中文地名 → 英文（华人常用叫法）
  const ALIAS = {
    "兰德维克": "Randwick", "肯辛顿": "Kensington", "金斯福德": "Kingsford", "帕拉马塔": "Parramatta", "好市围": "Hurstville", "车士活": "Chatswood",
    "宝活": "Burwood", "史卓菲": "Strathfield", "罗兹": "Rhodes", "麦觉理": "Macquarie Park", "艾斯菲": "Ashfield", "坎普西": "Campsie",
    "利物浦": "Liverpool", "黑镇": "Blacktown", "邦迪": "Bondi", "曼利": "Manly", "北悉尼": "North Sydney", "悉尼市区": "Sydney", "CBD": "Sydney",
    "纽卡斯尔": "Newcastle", "卧龙岗": "Wollongong", "中央海岸": "Central Coast", "宾士镇": "Bankstown", "赫斯特维尔": "Hurstville", "绿谷": "Green Valley",
  };
  const REGION_ALIAS = { "东区": "Sydney - Eastern Suburbs", "内西区": "Sydney - Inner West", "北岸": "Sydney - North Sydney and Hornsby", "北海滩": "Sydney - Northern Beaches", "西南区": "Sydney - South West", "市中心": "Sydney - City and Inner South" };
  const OUT = [
    [/房价|买房|售价|成交价|首付|贷款|按揭|sale price|house price|buy(ing)? a|mortgage/i, "这份数据只有租房押金登记，没有买卖成交价，回答不了房价问题。"],
    [/预测|明年|将来|会不会涨|会涨吗|会跌吗|forecast|predict|next year/i, "这份数据只记录已经发生的租约，不做预测。可以问「过去一年的走势」。"],
    [/墨尔本|布里斯班|珀斯|阿德莱德|堪培拉|维州|昆州|melbourne|brisbane|perth|adelaide|canberra|victoria|queensland/i, "数据只覆盖新南威尔士州（NSW）。"],
    [/房东|姓名|名字|电话|门牌|具体地址|landlord|phone|address of/i, "数据是匿名汇总的登记信息，没有、也不应该查询个人信息。"],
    [/工资|薪资|收入|天气|股票|汇率|salary|weather|stock/i, "这个助手只回答 NSW 租房市场的问题。"],
  ];

  function Engine(meta, fact) {
    this.meta = meta;
    this.N = meta.rows;
    const dv = new DataView(fact.buffer || fact, fact.byteOffset || 0);
    this.m = new Uint8Array(this.N); this.p = new Uint16Array(this.N); this.d = new Uint8Array(this.N); this.b = new Int8Array(this.N); this.r = new Uint16Array(this.N);
    for (let i = 0, o = 0; i < this.N; i++, o += 7) { this.m[i] = dv.getUint8(o); this.p[i] = dv.getUint16(o + 1, true); this.d[i] = dv.getUint8(o + 3); this.b[i] = dv.getInt8(o + 4); this.r[i] = dv.getUint16(o + 5, true); }
    const P = meta.postcodes;
    this.pc = P;
    // 地名索引：郊区名 → 邮编；LGA → 邮编集合；区域 → 邮编集合
    this.sub = new Map(); this.lga = new Map(); this.reg = new Map();
    P.forEach((x, i) => {
      for (const s of x.suburbs) { const k = s.toLowerCase(); if (!this.sub.has(k)) this.sub.set(k, new Set()); this.sub.get(k).add(i); }
      if (x.lga) { const k = x.lga.replace(/ \(NSW\)$/, "").toLowerCase(); if (!this.lga.has(k)) this.lga.set(k, new Set()); this.lga.get(k).add(i); }
      if (x.region) { const k = x.region.toLowerCase(); if (!this.reg.has(k)) this.reg.set(k, new Set()); this.reg.get(k).add(i); }
    });
    // 同名时默认取郊区（更精确）；问题里说了「市 / council / LGA」才取地方政府区
    this.names = [...this.sub.keys()].map(k => ["suburb", k]).concat([...this.lga.keys()].map(k => ["lga", k])).filter(([, k]) => k.length >= 4).sort((a, b) => b[1].length - a[1].length);
  }

  Engine.prototype.latest = function () { return this.meta.months.length - 1; };
  Engine.prototype.monthLabel = function (i) { const [y, m] = this.meta.months[i].split("-"); return `${y} 年 ${+m} 月`; };

  /* ---------- 1. 语言 → 意图 ---------- */
  Engine.prototype.parse = function (q0) {
    const q = q0.trim(), ql = q.toLowerCase(), trace = [];
    for (const [rx, why] of OUT) if (rx.test(q)) return { status: "REFUSE", reason: why, trace: ["范围检查：命中资料外问题"] };
    const it = { metric: "median", area: null, dwelling: null, bedrooms: null, months: null, group_by: null, compare: null, order: null, limit: null };
    // 指标
    if (/平均|均值|average|mean/i.test(q)) it.metric = "mean";
    if (/多少(套|个|单|份)|数量|租约数|租出去|新签|成交量|多少人|how many|number of|lodgements|volume/i.test(q)) it.metric = "count";
    if (/最便宜的那?四分之一|25\s*分位|下四分位|p25|入门价/i.test(q)) it.metric = "p25";
    if (/最贵的那?四分之一|75\s*分位|上四分位|p75|高端价/i.test(q)) it.metric = "p75";
    // 房型
    const dws = [];
    if (/公寓|单元房|unit|flat|apartment/i.test(q)) dws.push("Flat/Unit");
    if (/独立屋|独栋|别墅|house(?!hold)/i.test(q) || /(?<![公寓租])房子/.test(q)) dws.push("House");
    if (/联排|排屋|townhouse|terrace|semi/i.test(q)) dws.push("Terrace/Townhouse");
    if (dws.length) it.dwelling = [...new Set(dws)];
    // 卧室
    const bm = q.match(/([0-6一二两三四五六])\s*(房|居|室|卧|睡房|bed(room)?s?|br\b|b\b)/i);
    if (bm) it.bedrooms = [CN[bm[1]] ?? +bm[1]];
    if (/studio|开间|单间公寓|0\s*房|零居/i.test(q)) it.bedrooms = [0];
    // 时间
    const L = this.latest();
    let mm = q.match(/(20\d\d)\s*年\s*(\d{1,2})\s*月/) || null, mi = null;
    if (mm) mi = this.meta.months.indexOf(`${mm[1]}-${String(+mm[2]).padStart(2, "0")}`);
    else if ((mm = q.match(/(?<!\d)(\d{1,2})\s*月(份)?/))) { const k = this.meta.months.map((x, i) => [x, i]).filter(([x]) => +x.slice(5) === +mm[1]).map(([, i]) => i); mi = k.length ? k[k.length - 1] : -1; }
    else { const en = MONTH_EN.findIndex(n => ql.includes(n) || ql.includes(n.slice(0, 3) + " ")); if (en >= 0) { const yr = (q.match(/20\d\d/) || [])[0]; const k = this.meta.months.map((x, i) => [x, i]).filter(([x]) => +x.slice(5) === en + 1 && (!yr || x.startsWith(yr))).map(([, i]) => i); mi = k.length ? k[k.length - 1] : -1; } }
    if (mi === -1) return { status: "REFUSE", reason: `数据只覆盖 ${this.monthLabel(0)} 到 ${this.monthLabel(L)}。`, trace: ["时间检查：月份不在数据范围内"] };
    if (mi != null) it.months = [mi, mi];
    if (/同比|去年同期|比去年|year[- ]on[- ]year|yoy|vs last year/i.test(q)) it.compare = "yoy";
    else if (/环比|比上个?月|month[- ]on[- ]month|mom\b/i.test(q)) it.compare = "mom";
    // 分组 / 排名
    if (/趋势|走势|每个?月|逐月|过去一年|近一年|这一年|过去12个月|trend|monthly|over the (past|last) year/i.test(q)) it.group_by = "month";
    else if (/哪(个|些)(区|地方|郊区|邮编|地区)|排名|排行|最贵|最便宜|top\s*\d*|cheapest|most expensive|highest|lowest/i.test(q)) {
      it.group_by = /大区|区域|region/i.test(q) ? "region" : /郊区|邮编|suburb|postcode/i.test(q) ? "postcode" : "lga";
      it.order = /最便宜|最低|cheapest|lowest|便宜/i.test(q) ? "asc" : "desc";
      const n = q.match(/(?:top|前)\s*(\d+)/i); it.limit = n ? +n[1] : 5;
    } else if (/按房型|房型(之间|对比|比较)|公寓和独立屋|独立屋和公寓|公寓.*(vs|对比|比较|还是).*(独立屋|房子)|(独立屋|房子).*(vs|对比|比较|还是).*公寓|by dwelling|unit vs house|house vs unit/i.test(q)) { it.group_by = "dwelling"; it.dwelling = null; }
    else if (/按卧室|几房|不同卧室|各(种)?户型|by bedroom/i.test(q)) { it.group_by = "bedrooms"; it.bedrooms = null; }
    else if (/各(个)?大区|按区域|by region/i.test(q)) it.group_by = "region";
    // 地区（最长匹配；中文别名优先）
    let area = null;
    if (/greater sydney|大悉尼/i.test(q) || (/悉尼|sydney/i.test(q) && ["lga", "region", "postcode"].includes(it.group_by))) area = { level: "gsyd", name: "Greater Sydney" };
    if (!area) for (const [zh, en] of Object.entries(REGION_ALIAS)) if (q.includes(zh)) { area = { level: "region", name: en }; break; }
    if (!area) for (const [zh, en] of Object.entries(ALIAS)) if (q.includes(zh)) { const k = en.toLowerCase(); area = this.sub.has(k) ? { level: "suburb", name: en } : this.lga.has(k) ? { level: "lga", name: en } : null; if (area) break; }
    const wantLga = /市(?!区|中心|场)|council|city of|\blga\b|地方政府/i.test(q);
    if (!area) for (const [lv, k] of (wantLga ? this.names.filter(x => x[0] === "lga").concat(this.names) : this.names)) { const rx = new RegExp(`(^|[^a-z])${k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^a-z])`, "i"); if (rx.test(q)) { const after = q.slice(q.toLowerCase().indexOf(k) + k.length); if (/^\s+[A-Z][a-z]+/.test(after) && !/^\s+(Council|City|LGA|Unit|House|Flat|Apartment|Townhouse|Studio|Rent|Rental|Trend|Median|Average|In|For|Vs|And|Or)\b/i.test(after)) { return { status: "CLARIFY", reason: `「${k.replace(/\b\w/g, c => c.toUpperCase())}${after.match(/^\s+[A-Z][a-z]+/)[0]}」不在 NSW 邮编表里，是不是指 ${k.replace(/\b\w/g, c => c.toUpperCase())}？`, intent: it, trace: ["地区识别：疑似未收录的地名"] }; } area = { level: lv, name: k.replace(/\b\w/g, c => c.toUpperCase()) }; break; } }
    let pcm = q.match(/(?:邮编|postcode)\s*(2\d{3})(?!\d)/i) || q.match(/(?<![\d年])(2\d{3})(?![\d年])/);
    if (pcm && !/邮编|postcode/i.test(pcm[0]) && /^20[2-3]\d$/.test(pcm[1]) && new RegExp(`(${MONTH_EN.join("|")}|${MONTH_EN.map(m => m.slice(0, 3)).join("|")}|月|year)\\W*${pcm[1]}|${pcm[1]}\\s*(年|年度)`, "i").test(q)) pcm = null;
    if (pcm) { const i = this.pc.findIndex(x => x.pc === +pcm[1]); if (i >= 0) area = { level: "postcode", name: pcm[1] }; }
    if (!area && /大悉尼|悉尼|sydney/i.test(q)) area = { level: "gsyd", name: "Greater Sydney" };
    if (!area && /新州|全州|nsw|new south wales|全澳/i.test(q)) area = { level: "nsw", name: "NSW" };
    if (!area && !it.group_by) {
      const m = q.match(/(?:在|in)\s*([A-Za-z][A-Za-z ]{2,}|[一-龥]{2,4})(?:的|租|两|一|三|$)/);
      return { status: "CLARIFY", reason: m ? `没有在 NSW 邮编表里找到「${m[1].trim()}」。请换成英文郊区名或邮编（如 Randwick、2031）。` : "请说明想看哪个地区（郊区名、邮编，或「悉尼」「全州」）。", intent: it, trace: ["地区识别：未匹配"] };
    }
    if (!area) area = { level: "nsw", name: "NSW" };
    it.area = area;
    // 默认时间口径：趋势/环比/同比按需要；小地区单点用最近 3 个月，大地区用最近 1 个月
    if (!it.months) {
      if (it.group_by === "month") it.months = [0, L];
      else if (it.compare) it.months = [L, L];
      else it.months = ["suburb", "postcode"].includes(area.level) ? [L - 2, L] : [L, L];
    }
    if (it.compare === "yoy" && it.months[1] - 12 < 0) return { status: "REFUSE", reason: "同比需要去年同月的数据，这个月份没有。", trace: [] };
    trace.push(`意图：${JSON.stringify(it)}`);
    return { status: "OK", intent: it, trace };
  };

  /* ---------- 2. 校验（规则和大模型的输出都要过） ---------- */
  Engine.prototype.validate = function (it) {
    const errs = [];
    if (!METRIC_ZH[it.metric]) errs.push("metric");
    if (it.dwelling && !it.dwelling.every(x => DW.includes(x))) errs.push("dwelling");
    if (it.bedrooms && !it.bedrooms.every(x => Number.isInteger(x) && x >= 0 && x <= 10)) errs.push("bedrooms");
    if (!it.months || it.months.length !== 2 || it.months[0] < 0 || it.months[1] > this.latest() || it.months[0] > it.months[1]) errs.push("months");
    if (it.group_by && !["month", "region", "lga", "postcode", "dwelling", "bedrooms"].includes(it.group_by)) errs.push("group_by");
    if (it.compare && !["yoy", "mom"].includes(it.compare)) errs.push("compare");
    if (!it.area || !["suburb", "postcode", "lga", "region", "gsyd", "nsw"].includes(it.area.level)) errs.push("area");
    else if (it.area.level !== "nsw" && it.area.level !== "gsyd" && !this.areaSet(it.area)) errs.push("area.name");
    return errs;
  };
  Engine.prototype.areaSet = function (a) {
    const k = String(a.name).toLowerCase();
    if (a.level === "suburb") return this.sub.get(k) || null;
    if (a.level === "lga") return this.lga.get(k) || null;
    if (a.level === "region") return this.reg.get(k) || null;
    if (a.level === "postcode") { const i = this.pc.findIndex(x => x.pc === +a.name); return i >= 0 ? new Set([i]) : null; }
    if (a.level === "gsyd") return new Set(this.pc.map((x, i) => x.gsyd ? i : -1).filter(i => i >= 0));
    return null;
  };

  /* ---------- 3. 意图 → SQL（给人看、给测试核对） ---------- */
  const q1 = s => `'${String(s).replace(/'/g, "''")}'`;
  Engine.prototype.where = function (it, mFrom, mTo) {
    const w = ["is_analysable"], a = it.area;
    if (a.level === "suburb") w.push(`postcode IN (${[...this.areaSet(a)].map(i => this.pc[i].pc).join(", ")})  -- ${a.name}`);
    if (a.level === "postcode") w.push(`postcode = ${+a.name}`);
    if (a.level === "lga") w.push(`lga IN (${[...new Set([...this.areaSet(a)].map(i => this.pc[i].lga))].map(q1).join(", ")})`);
    if (a.level === "region") w.push(`region = ${q1(this.pc[[...this.areaSet(a)][0]].region)}`);
    if (a.level === "gsyd") w.push("is_greater_sydney = 1");
    if (it.dwelling) w.push(`dwelling IN (${it.dwelling.map(q1).join(", ")})`);
    if (it.bedrooms) w.push(`bedrooms IN (${it.bedrooms.join(", ")})`);
    const M = this.meta.months;
    w.push(mFrom === mTo ? `month = '${M[mFrom]}'` : `month BETWEEN '${M[mFrom]}' AND '${M[mTo]}'`);
    return w;
  };
  const AGG = { median: "median(weekly_rent)", mean: "round(avg(weekly_rent), 1)", count: "count(*)", p25: "percentile(weekly_rent, 25)", p75: "percentile(weekly_rent, 75)" };
  const GCOL = { month: "month", region: "region", lga: "lga", postcode: "postcode", dwelling: "dwelling", bedrooms: "bedrooms" };
  Engine.prototype.sql = function (it) {
    const [a, b] = it.months;
    if (it.compare) {
      const prev = it.compare === "yoy" ? b - 12 : b - 1;
      return `SELECT\n  (SELECT ${AGG[it.metric]} FROM fct_lodgement WHERE ${this.where(it, b, b).join("\n     AND ")}) AS current,\n  (SELECT ${AGG[it.metric]} FROM fct_lodgement WHERE ${this.where(it, prev, prev).join("\n     AND ")}) AS previous`;
    }
    const w = this.where(it, a, b).join("\n  AND ");
    if (!it.group_by) return `SELECT ${AGG[it.metric]} AS value, count(*) AS n\nFROM fct_lodgement\nWHERE ${w}`;
    const g = GCOL[it.group_by];
    let s = `SELECT ${g}, ${AGG[it.metric]} AS value, count(*) AS n\nFROM fct_lodgement\nWHERE ${w}\nGROUP BY ${g}`;
    if (it.order) s += `\nHAVING count(*) >= ${MIN_N}\nORDER BY value ${it.order.toUpperCase()}, ${g}\nLIMIT ${it.limit || 5}`;
    else s += it.group_by === "bedrooms" ? `\nORDER BY bedrooms IS NULL, bedrooms` : `\nORDER BY ${g}`;
    return s;
  };

  /* ---------- 4. 在列式数据上执行（与 SQLite 语义一致：median/percentile 为线性插值） ---------- */
  function pct(arr, p) { if (!arr.length) return null; arr.sort((x, y) => x - y); const k = (arr.length - 1) * p, f = Math.floor(k), c = Math.ceil(k); return f === c ? arr[f] : arr[f] + (arr[c] - arr[f]) * (k - f); }
  function agg(metric, v) { if (metric === "count") return v.length; if (!v.length) return null; if (metric === "mean") return Math.round(v.reduce((s, x) => s + x, 0) / v.length * 10) / 10; return pct(v, metric === "median" ? .5 : metric === "p25" ? .25 : .75); }
  Engine.prototype.select = function (it, mFrom, mTo) {
    const A = it.area.level === "nsw" ? null : this.areaSet(it.area);
    const D = it.dwelling ? new Set(it.dwelling.map(x => DW.indexOf(x))) : null, B = it.bedrooms ? new Set(it.bedrooms) : null;
    const out = [];
    for (let i = 0; i < this.N; i++) {
      const m = this.m[i]; if (m < mFrom || m > mTo) continue;
      if (A && !A.has(this.p[i])) continue; if (D && !D.has(this.d[i])) continue; if (B && !B.has(this.b[i])) continue;
      out.push(i);
    }
    return out;
  };
  Engine.prototype.key = function (g, i) {
    const P = this.pc[this.p[i]];
    return g === "month" ? this.meta.months[this.m[i]] : g === "region" ? P.region : g === "lga" ? P.lga : g === "postcode" ? P.pc : g === "dwelling" ? DW[this.d[i]] : (this.b[i] < 0 ? null : this.b[i]);
  };
  Engine.prototype.execute = function (it) {
    const [a, b] = it.months;
    if (it.compare) {
      const prev = it.compare === "yoy" ? b - 12 : b - 1;
      const cur = this.select(it, b, b).map(i => this.r[i]), pre = this.select(it, prev, prev).map(i => this.r[i]);
      return { kind: "compare", current: agg(it.metric, cur), previous: agg(it.metric, pre), n_cur: cur.length, n_prev: pre.length, cur_label: this.monthLabel(b), prev_label: this.monthLabel(prev) };
    }
    const rows = this.select(it, a, b);
    if (!it.group_by) { const v = rows.map(i => this.r[i]); return { kind: "single", value: agg(it.metric, v), n: v.length }; }
    const G = new Map();
    for (const i of rows) { const k = this.key(it.group_by, i); if (!G.has(k)) G.set(k, []); G.get(k).push(this.r[i]); }
    let out = [...G.entries()].map(([k, v]) => ({ key: k, value: agg(it.metric, v), n: v.length }));
    if (it.order) { out = out.filter(x => x.n >= MIN_N).sort((x, y) => (it.order === "asc" ? x.value - y.value : y.value - x.value) || (String(x.key) < String(y.key) ? -1 : 1)).slice(0, it.limit || 5); }
    else out.sort((x, y) => (x.key === null) - (y.key === null) || (x.key < y.key ? -1 : x.key > y.key ? 1 : 0));
    return { kind: "group", rows: out };
  };

  /* ---------- 5. 组织回答 ---------- */
  Engine.prototype.describe = function (it) {
    const parts = [];
    const a = it.area; parts.push(a.level === "nsw" ? "全 NSW" : a.level === "gsyd" ? "大悉尼" : a.level === "postcode" ? `邮编 ${a.name}` : a.level === "region" ? `${a.name}（大区）` : a.name);
    if (it.bedrooms) parts.push(it.bedrooms.map(x => x === 0 ? "开间" : `${x} 房`).join("/"));
    if (it.dwelling) parts.push(it.dwelling.map(x => DW_ZH[x]).join("/"));
    const [m0, m1] = it.months;
    const t = it.compare ? "" : m0 === m1 ? this.monthLabel(m0) : `${this.monthLabel(m0)}–${this.monthLabel(m1)}`;
    return { scope: parts.join(" · "), time: t, metric: METRIC_ZH[it.metric] };
  };
  const money = v => v == null ? "—" : `${Math.round(v).toLocaleString("en-AU")} 澳元/周`;
  Engine.prototype.answer = function (it, res) {
    const d = this.describe(it), fmt = it.metric === "count" ? (v => v == null ? "—" : `${v.toLocaleString("en-AU")} 份`) : money;
    if (res.kind === "single") {
      if (!res.n) return { text: `${d.scope}，${d.time}没有符合条件的租约。`, warn: "可以放宽条件（去掉房型 / 卧室数，或换成更大的地区）。" };
      return { text: `${d.scope}，${d.time}：${d.metric} ${fmt(res.value)}（样本 ${res.n} 份新签租约）。`, warn: res.n < MIN_N && it.metric !== "count" ? `样本只有 ${res.n} 份，结果波动大，建议放宽到更大地区或更长时间。` : null };
    }
    if (res.kind === "compare") {
      if (res.current == null || res.previous == null || !res.n_prev) return { text: `${d.scope}：比较所需的数据不足。`, warn: null };
      const ch = (res.current - res.previous) / res.previous * 100;
      return { text: `${d.scope}：${d.metric} ${res.cur_label} ${fmt(res.current)}，${res.prev_label} ${fmt(res.previous)}，${it.compare === "yoy" ? "同比" : "环比"} ${ch >= 0 ? "+" : ""}${ch.toFixed(1)}%。`, warn: Math.min(res.n_cur, res.n_prev) < MIN_N && it.metric !== "count" ? "其中一期样本少于 30 份，变化幅度仅供参考。" : null };
    }
    if (!res.rows.length) return { text: `${d.scope}：没有样本量足够（≥ ${MIN_N} 份）的分组。`, warn: null };
    const head = it.order ? `${d.scope}，${d.time}，${d.metric}${it.order === "asc" ? "最低" : "最高"}的 ${res.rows.length} 个（只比较样本 ≥ ${MIN_N} 份的）：` : `${d.scope}，${d.time}，按${{ month: "月份", region: "大区", lga: "地方政府区", postcode: "邮编", dwelling: "房型", bedrooms: "卧室数" }[it.group_by]}：`;
    const lab = k => it.group_by === "dwelling" ? DW_ZH[k] : it.group_by === "bedrooms" ? (k === null ? "未知" : k === 0 ? "开间" : `${k} 房`) : String(k);
    return { text: head, rows: res.rows.map(x => ({ label: lab(x.key), value: x.value, shown: fmt(x.value), n: x.n })), warn: null };
  };

  Engine.prototype.ask = function (q, llmIntent) {
    let p = llmIntent ? { status: "OK", intent: llmIntent, trace: ["意图来自大模型（已过校验）"] } : this.parse(q);
    if (p.status !== "OK") return p;
    const errs = this.validate(p.intent);
    if (errs.length) return { status: "CLARIFY", reason: `没法确定：${errs.join("、")}。`, intent: p.intent, trace: p.trace.concat(["校验失败：" + errs.join(",")]) };
    const res = this.execute(p.intent);
    return { status: "OK", intent: p.intent, sql: this.sql(p.intent), result: res, answer: this.answer(p.intent, res), trace: p.trace };
  };

  /* 交给大模型时用的提示词：只允许返回同一个 JSON 结构 */
  Engine.prototype.llmPrompt = function (q) {
    const M = this.meta.months;
    return `你是一个把租房问题转成查询意图的解析器。只输出 JSON，不要解释。\n可用字段：\n- metric: "median"|"mean"|"count"|"p25"|"p75"\n- area: {"level":"suburb"|"postcode"|"lga"|"region"|"gsyd"|"nsw","name":英文郊区名/邮编/LGA 名/SA4 名}\n- dwelling: null 或 ["Flat/Unit","House","Terrace/Townhouse"] 的子集\n- bedrooms: null 或整数数组（0 表示开间）\n- months: [起,止] 月份下标，0=${M[0]}，${M.length - 1}=${M[M.length - 1]}\n- group_by: null|"month"|"region"|"lga"|"postcode"|"dwelling"|"bedrooms"\n- compare: null|"yoy"|"mom"\n- order: null|"asc"|"desc"，limit: null|整数\n数据只有 NSW 租房押金登记（新签租约的周租金），没有房价、没有预测、没有个人信息；问到这些时输出 {"refuse": "原因"}。\n问题：${q}`;
  };

  if (typeof module !== "undefined") module.exports = { Engine, MIN_N };
  else root.RentEngine = Engine;
})(typeof window !== "undefined" ? window : globalThis);
