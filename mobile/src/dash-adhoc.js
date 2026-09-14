/* Abu Hashem mobile — namespace Q: the ad-hoc query engine.

   Every other section answers ONE question with a fixed grouping. This one
   takes the question as data — period, filters, a dimension to group by, and
   the measures wanted — so a new business question does not need a new
   section. The whole module is pure: it takes `window.DASH.lines` and a spec,
   and returns rows. No React, no DOM, no reading of app state. That is what
   makes it testable with node and what keeps the UI from acquiring arithmetic.

   Four things about THIS data shape the engine, and each one is a rule that
   would be silently wrong if reversed:

   1. Customers group by `customer_code`, never by name. 84 codes in the
      current extract carry more than one spelling of the same customer
      («ثلاجة السيد الوكيل القرين» / «ثلجه السيد الوكيل القرين»), so grouping
      by name splits one customer into several rows and every ranking built on
      it is wrong. The code is the identity; the name is a label chosen for it.

   2. `boxes` is null on 232 lines and zero on none. Null there means the item
      is sold by weight and was never counted in boxes — it is not a zero.
      Summing it as zero would invent a measurement, so every box total carries
      the count of lines that had none and reports `null` when none did.

   3. Bonus lines carry quantity and (almost) no money: 415 lines, 24,305
      units, 740.00 EGP spread over a single line. So bonus is never folded
      into revenue by default, and regular and bonus quantities are BOTH
      accumulated on every group regardless of mode — that is what makes
      "regular versus bonus" a comparison rather than two separate reports.

   4. There is no customer type in the source. Not blank — absent: no field in
      window.DASH, window.DASH_DATA or the margin payload names a segment,
      channel or tier, and `city` is filled for 9 customers of 371. The nearest
      real classification is ABC/XYZ from customer_pareto, which is derived
      from revenue concentration and demand variability, and it is offered
      under a name that says so rather than under "customer type". */
const Q = (function(){

/* ---- dimensions -------------------------------------------------------- */
/* `of` returns the grouping KEY (stable, never shown); `name` turns that key
   into what the reader sees. Keeping them apart is what lets customers group
   by code and still read as a name. */
const DIMS = [
  {key:"month",    label:"الشهر",
   of:l=>l.month,                 name:(k,c)=>c.monthName(k)},
  {key:"rep",      label:"المندوب",
   of:l=>l.rep||"",               name:k=>k||"غير محدد"},
  {key:"customer", label:"العميل",
   of:l=>l.customer_code,         name:(k,c)=>c.custName(k)},
  {key:"brand",    label:"العلامة التجارية",
   of:l=>l.brand||"",             name:k=>k||"غير مصنف"},
  {key:"item",     label:"الصنف",
   of:l=>l.item_code,             name:(k,c)=>c.itemName(k)},
  {key:"invoice",  label:"الفاتورة",
   of:l=>l.invoice_no,            name:k=>k},
  {key:"abc",      label:"تصنيف العميل (ABC)",
   of:(l,c)=>c.abcOf(l.customer_code), name:k=>k||"غير مصنّف",
   note:"مشتقّ من تركّز الإيراد — ليس نوع عميل مسجّلًا بالمصدر"},
  {key:"xyz",      label:"ثبات الطلب (XYZ)",
   of:(l,c)=>c.xyzOf(l.customer_code), name:k=>k||"غير مصنّف",
   note:"مشتقّ من تذبذب الطلب — ليس نوع عميل مسجّلًا بالمصدر"},
];

/* ---- measures ---------------------------------------------------------- */
/* `fmt` is a hint for the renderer, not arithmetic. `partial` marks a measure
   that can be incomplete by nature, so the UI knows to show its coverage. */
const MEASURES = [
  {key:"revenue",      label:"الإيراد",            fmt:"egp"},
  {key:"qty",          label:"الكمية",             fmt:"int"},
  {key:"boxes",        label:"الكراتين",           fmt:"int", partial:true},
  {key:"invoices",     label:"عدد الفواتير",       fmt:"int"},
  {key:"customers",    label:"عدد العملاء",        fmt:"int"},
  {key:"lines",        label:"عدد البنود",         fmt:"int"},
  {key:"asp",          label:"متوسط سعر البيع",    fmt:"egp"},
  {key:"regular_qty",  label:"كمية البيع",         fmt:"int"},
  {key:"bonus_qty",    label:"كمية البونص",        fmt:"int"},
  {key:"bonus_share",  label:"نسبة البونص",        fmt:"pct"},
];

const BONUS_MODES = [
  {key:"regular", label:"البيع فقط",   note:"يستبعد بنود البونص من الإيراد والكمية"},
  {key:"bonus",   label:"البونص فقط",  note:"بنود البونص وحدها"},
  {key:"both",    label:"الاثنان معًا", note:"يجمعهما — الكمية تشمل البونص"},
];

/* ---- context: keys -> readable names ----------------------------------- */
/* Built once per payload, not per query. The canonical customer name comes
   from dim_customers when the aggregate payload is present, because that is
   where name variants were already resolved (it carries n_name_variants);
   otherwise the most frequent spelling in the lines wins, which is the same
   rule applied with less evidence. */
function context(D, RD){
  const monthLbl = Object.fromEntries(((D&&D.meta&&D.meta.available_months)||[])
    .map(m=>[m.v, m.l]));

  const canon = new Map(), variants = new Map();
  for(const c of ((RD&&RD.dim_customers)||[]))
    if(c && c.customer_code!=null) canon.set(String(c.customer_code), c.customer_name);

  /* Count spellings per code even when dim_customers supplied the canonical
     one: the count is what lets a report say "this row merges 3 spellings"
     instead of quietly merging them. */
  const seen = new Map();
  for(const l of ((D&&D.lines)||[])){
    const k = String(l.customer_code);
    let m = seen.get(k); if(!m){ m = new Map(); seen.set(k, m); }
    const n = (l.customer_name||"").trim();
    if(n) m.set(n, (m.get(n)||0)+1);
  }
  for(const [k, m] of seen){
    variants.set(k, m.size);
    if(!canon.has(k) && m.size){
      canon.set(k, [...m.entries()].sort((a,b)=>b[1]-a[1])[0][0]);
    }
  }

  const items = new Map();
  for(const l of ((D&&D.lines)||[]))
    if(!items.has(String(l.item_code))) items.set(String(l.item_code), l.item_name);

  const abc = new Map(), xyz = new Map();
  for(const c of ((RD&&RD.customer_pareto)||[])){
    if(c && c.customer_code!=null){
      abc.set(String(c.customer_code), c.abc_class||"");
      xyz.set(String(c.customer_code), c.xyz_class||"");
    }
  }

  return {
    monthName: k => monthLbl[k] || k,
    /* A code with no name anywhere still reads as the code rather than as an
       empty cell — 13 lines carry code 009 with a blank name, and a blank row
       in a ranking is a row nobody can act on. */
    custName: k => canon.get(String(k)) || ("عميل "+k),
    itemName: k => items.get(String(k)) || String(k),
    abcOf:    k => abc.get(String(k)) || "",
    xyzOf:    k => xyz.get(String(k)) || "",
    nameVariants: k => variants.get(String(k)) || 0,
    hasAbc: abc.size > 0,
  };
}

/* ---- period ------------------------------------------------------------ */
/* invoice_date is ISO (YYYY-MM-DD) throughout the payload, so lexical
   comparison IS date comparison; no Date objects, no timezone to get wrong. */
function inPeriod(l, p){
  if(!p || p.mode==="all") return true;
  if(p.mode==="month") return !p.month || p.month==="all" || l.month===p.month;
  if(p.mode==="range"){
    const d = l.invoice_date;
    if(p.from && d < p.from) return false;
    if(p.to   && d > p.to)   return false;
    return true;
  }
  return true;
}

function periodLabel(p, ctx){
  if(!p || p.mode==="all") return "كل الفترات";
  if(p.mode==="month")
    return (!p.month || p.month==="all") ? "كل الفترات" : ctx.monthName(p.month);
  const f = p.from||"البداية", t = p.to||"النهاية";
  return f+" ← "+t;
}

/* ---- filters ----------------------------------------------------------- */
/* Every filter is a LIST. An empty list means "no restriction", which is not
   the same as a list of zero matches — a selection that matches nothing must
   return nothing rather than everything. */
const FILTERS = [
  {key:"rep",      label:"المندوب",           of:l=>l.rep||""},
  {key:"customer", label:"العميل",            of:l=>String(l.customer_code)},
  {key:"brand",    label:"العلامة التجارية",  of:l=>l.brand||""},
  {key:"item",     label:"الصنف",             of:l=>String(l.item_code)},
  {key:"invoice",  label:"الفاتورة",          of:l=>l.invoice_no},
  {key:"abc",      label:"تصنيف العميل (ABC)",of:(l,c)=>c.abcOf(l.customer_code)},
];

function passes(l, spec, ctx){
  for(const F of FILTERS){
    const want = spec.filters && spec.filters[F.key];
    if(!want || !want.length) continue;
    if(want.indexOf(F.of(l, ctx)) === -1) return false;
  }
  return true;
}

/* ---- the scan ---------------------------------------------------------- */
function blank(){
  return {
    rev:0, qty:0,
    boxes:0, boxLines:0, boxMissing:0,
    lines:0,
    pricedRev:0, pricedQty:0,   /* ASP divides these two, not the totals:
                                   a free line has qty and no money, and
                                   letting it into the denominator drags the
                                   average price toward zero. */
    inv:new Set(), cust:new Set(),
  };
}

function feed(a, l){
  a.lines++;
  a.rev += (l.line_total||0);
  a.qty += (l.qty||0);
  if(l.boxes==null) a.boxMissing++; else { a.boxes += l.boxes; a.boxLines++; }
  if((l.qty||0) > 0 && (l.line_total||0) > 0){
    a.pricedRev += l.line_total; a.pricedQty += l.qty;
  }
  a.inv.add(l.invoice_no);
  a.cust.add(String(l.customer_code));
}

/* Regular and bonus are accumulated side by side on every group no matter
   which mode is selected. The mode chooses what the headline measures READ;
   it never decides what was counted. That is the difference between a bonus
   report and a bonus comparison. */
function emit(key, label, reg, bon, mode){
  const pick = mode==="bonus" ? bon : mode==="both" ? null : reg;
  const rev  = pick ? pick.rev  : reg.rev  + bon.rev;
  const qty  = pick ? pick.qty  : reg.qty  + bon.qty;
  const bxL  = pick ? pick.boxLines : reg.boxLines + bon.boxLines;
  const bx   = pick ? pick.boxes    : reg.boxes    + bon.boxes;
  const bxM  = pick ? pick.boxMissing : reg.boxMissing + bon.boxMissing;
  const lns  = pick ? pick.lines : reg.lines + bon.lines;
  const pRev = pick ? pick.pricedRev : reg.pricedRev + bon.pricedRev;
  const pQty = pick ? pick.pricedQty : reg.pricedQty + bon.pricedQty;
  const inv  = pick ? pick.inv  : new Set([...reg.inv,  ...bon.inv]);
  const cus  = pick ? pick.cust : new Set([...reg.cust, ...bon.cust]);
  const totQ = reg.qty + bon.qty;

  return {
    key, label,
    revenue: rev,
    qty,
    /* null, not 0, when nothing in the group was ever counted in boxes. */
    boxes: bxL ? bx : null,
    boxes_missing: bxM,
    invoices: inv.size,
    customers: cus.size,
    lines: lns,
    asp: pQty ? pRev/pQty : null,
    regular_qty: reg.qty,
    bonus_qty: bon.qty,
    bonus_revenue: bon.rev,
    bonus_share: totQ ? bon.qty/totQ : null,
    _inv: inv, _cust: cus,
  };
}

/* ---- run --------------------------------------------------------------- */
/* spec = {period, filters, bonus, groupBy, sort:{by,dir}, limit} */
function run(lines, spec, ctx){
  spec = spec || {};
  const mode = spec.bonus || "regular";
  const dim  = DIMS.find(d=>d.key===(spec.groupBy||"month")) || DIMS[0];

  const groups = new Map();
  const grand = {reg:blank(), bon:blank()};
  let scanned = 0, matched = 0, bonusMoney = 0;

  for(const l of (lines||[])){
    scanned++;
    if(!inPeriod(l, spec.period)) continue;
    if(!passes(l, spec, ctx)) continue;
    matched++;
    if(l.is_bonus && (l.line_total||0) !== 0) bonusMoney += l.line_total;

    const k = String(dim.of(l, ctx));
    let g = groups.get(k);
    if(!g){ g = {reg:blank(), bon:blank()}; groups.set(k, g); }
    const side = l.is_bonus ? "bon" : "reg";
    feed(g[side], l);
    feed(grand[side], l);
  }

  let rows = [...groups.entries()]
    .map(([k, g]) => emit(k, dim.name(k, ctx), g.reg, g.bon, mode));

  /* `lines` already counts only the side the mode reads, so this one test
     drops the groups that have nothing on that side — otherwise «البونص فقط»
     lists every customer who never received one, at zero, and «البيع فقط»
     lists the bonus-only customers the same way. In «الاثنان معًا» no group
     can be empty, so nothing is dropped. */
  rows = rows.filter(r => r.lines > 0);

  const sortBy  = (spec.sort && spec.sort.by)  || "revenue";
  const sortDir = (spec.sort && spec.sort.dir) || "desc";
  rows.sort((a,b)=>{
    const x = a[sortBy], y = b[sortBy];
    /* Missing sorts last in BOTH directions. A null box count is unknown, and
       letting it float to the top of an ascending sort would present "not
       measured" as "the smallest". */
    if(x==null && y==null) return String(a.label).localeCompare(String(b.label),"ar");
    if(x==null) return 1;
    if(y==null) return -1;
    if(typeof x === "string" || typeof y === "string")
      return (sortDir==="asc"?1:-1) * String(x).localeCompare(String(y),"ar");
    return sortDir==="asc" ? x-y : y-x;
  });

  const limited = spec.limit ? rows.slice(0, spec.limit) : rows;
  const total = emit("__total__","الإجمالي", grand.reg, grand.bon, mode);

  return {
    rows: limited,
    allRows: rows,
    total,
    meta: {
      dim: dim.key, dimLabel: dim.label, dimNote: dim.note||null,
      mode, measures: spec.measures || ["revenue","qty","invoices","customers"],
      periodLabel: periodLabel(spec.period, ctx),
      scanned, matched,
      groups: rows.length, shown: limited.length,
      warnings: warn(rows, total, mode, dim, ctx, bonusMoney),
    },
  };
}

/* ---- warnings ---------------------------------------------------------- */
/* Not decoration. Each of these marks a place where a reader would otherwise
   take an incomplete number for a complete one. */
function warn(rows, total, mode, dim, ctx, bonusMoney){
  const w = [];
  if(!total.lines) w.push("لا توجد بنود مطابقة لهذه الشروط.");
  if(total.boxes_missing)
    w.push(total.boxes_missing+" بندًا بلا عدد كراتين (تُباع بالوزن) — مستبعدة من مجموع الكراتين ولم تُعامَل كصفر.");
  if(mode!=="bonus" && bonusMoney)
    w.push("بنود بونص تحمل قيمة مالية "+bonusMoney.toFixed(2)+" ج.م — البونص يُفترض بلا قيمة، فهذه حالة تستحق المراجعة.");
  if(dim.key==="customer"){
    const merged = rows.filter(r=>ctx.nameVariants(r.key) > 1).length;
    if(merged)
      w.push(merged+" عميلًا يحمل أكثر من صيغة اسم بالمصدر — التجميع على كود العميل، والاسم المعروض هو الصيغة المعتمدة.");
  }
  if(dim.note) w.push(dim.note+".");
  return w;
}

/* ---- pivot: dimension × month ------------------------------------------ */
/* "Compare across months" is a different shape from a grouped table, not a
   different filter: one measure, rows = dimension, columns = months. Built
   from the same scan rules so a pivot cell and a grouped row agree. */
function pivot(lines, spec, ctx, measure){
  const dim = DIMS.find(d=>d.key===(spec.groupBy||"customer")) || DIMS[2];
  const months = [...new Set((lines||[])
    .filter(l=>inPeriod(l, spec.period) && passes(l, spec, ctx))
    .map(l=>l.month))].sort();

  const cells = new Map();
  for(const l of (lines||[])){
    if(!inPeriod(l, spec.period) || !passes(l, spec, ctx)) continue;
    const rk = String(dim.of(l, ctx));
    let r = cells.get(rk);
    if(!r){ r = new Map(); cells.set(rk, r); }
    let g = r.get(l.month);
    if(!g){ g = {reg:blank(), bon:blank()}; r.set(l.month, g); }
    feed(g[l.is_bonus?"bon":"reg"], l);
  }

  const mode = spec.bonus || "regular";
  const rows = [...cells.entries()].map(([rk, byMonth])=>{
    const cellsOut = {}; let tot = 0;
    for(const m of months){
      const g = byMonth.get(m);
      const v = g ? emit(rk, "", g.reg, g.bon, mode)[measure] : null;
      cellsOut[m] = v;
      if(typeof v === "number") tot += v;
    }
    return {key:rk, label:dim.name(rk, ctx), cells:cellsOut, total:tot};
  }).sort((a,b)=>b.total-a.total);

  return {months, rows, measure,
          meta:{dimLabel:dim.label, periodLabel:periodLabel(spec.period, ctx)}};
}

/* ---- drill-down -------------------------------------------------------- */
/* The lines behind one grouped row — the same predicate the row was built
   from, plus the row's own key, so a summary and its detail can never
   disagree about what was counted. */
function drill(lines, spec, ctx, groupKey){
  const dim = DIMS.find(d=>d.key===(spec.groupBy||"month")) || DIMS[0];
  const mode = spec.bonus || "regular";
  return (lines||[]).filter(l =>
    inPeriod(l, spec.period) && passes(l, spec, ctx) &&
    String(dim.of(l, ctx)) === String(groupKey) &&
    (mode==="both" || (mode==="bonus" ? l.is_bonus : !l.is_bonus)));
}

/* ---- option lists for the pickers -------------------------------------- */
/* Read off the data rather than hard-coded, so a rep or brand that appears in
   a future extract shows up without an edit here. Sorted by weight: the
   options a user reaches for first are the ones with the most behind them. */
function options(lines, ctx){
  const tally = (of) => {
    const m = new Map();
    for(const l of (lines||[])){
      const k = of(l, ctx); if(k==null || k==="") continue;
      m.set(String(k), (m.get(String(k))||0) + (l.line_total||0));
    }
    return [...m.entries()].sort((a,b)=>b[1]-a[1]).map(e=>e[0]);
  };
  return {
    rep:      tally(l=>l.rep).map(v=>[v, v]),
    brand:    tally(l=>l.brand).map(v=>[v, v]),
    customer: tally(l=>String(l.customer_code)).map(v=>[v, ctx.custName(v)]),
    item:     tally(l=>String(l.item_code)).map(v=>[v, ctx.itemName(v)]),
    invoice:  [...new Set((lines||[]).map(l=>l.invoice_no))].sort().map(v=>[v, v]),
    abc:      ctx.hasAbc ? [...new Set((lines||[])
                 .map(l=>ctx.abcOf(l.customer_code)).filter(Boolean))]
                 .sort().map(v=>[v, v]) : [],
  };
}

/* ---- saved presets ----------------------------------------------------- */
/* The five reports the brief names, expressed as specs. They are starting
   points, not fixed reports: opening one fills the builder and every control
   stays live, which is the whole point of the section. */
const PRESETS = [
  {id:"sales_month", label:"أداء المبيعات — شهريًا",
   spec:{period:{mode:"all"}, groupBy:"month", bonus:"regular",
         measures:["revenue","qty","invoices","customers","asp"],
         sort:{by:"key", dir:"asc"}}},
  {id:"sales_rep", label:"المبيعات حسب المندوب",
   spec:{period:{mode:"all"}, groupBy:"rep", bonus:"regular",
         measures:["revenue","qty","invoices","customers","asp"],
         sort:{by:"revenue", dir:"desc"}}},
  {id:"top_customers", label:"أكبر العملاء بالقيمة",
   spec:{period:{mode:"all"}, groupBy:"customer", bonus:"regular",
         measures:["revenue","qty","invoices","lines","asp"],
         sort:{by:"revenue", dir:"desc"}, limit:50}},
  {id:"weak_customers", label:"أضعف العملاء بالقيمة",
   spec:{period:{mode:"all"}, groupBy:"customer", bonus:"regular",
         measures:["revenue","qty","invoices","lines"],
         sort:{by:"revenue", dir:"asc"}, limit:50}},
  {id:"products", label:"أداء الأصناف",
   spec:{period:{mode:"all"}, groupBy:"item", bonus:"regular",
         measures:["revenue","qty","boxes","customers","asp"],
         sort:{by:"revenue", dir:"desc"}}},
  {id:"brands", label:"مساهمة العلامات التجارية",
   spec:{period:{mode:"all"}, groupBy:"brand", bonus:"regular",
         measures:["revenue","qty","boxes","customers","asp"],
         sort:{by:"revenue", dir:"desc"}}},
  {id:"bonus_item", label:"البونص حسب الصنف",
   spec:{period:{mode:"all"}, groupBy:"item", bonus:"both",
         measures:["regular_qty","bonus_qty","bonus_share","revenue"],
         sort:{by:"bonus_qty", dir:"desc"}}},
  {id:"bonus_customer", label:"البونص حسب العميل",
   spec:{period:{mode:"all"}, groupBy:"customer", bonus:"both",
         measures:["regular_qty","bonus_qty","bonus_share","revenue"],
         sort:{by:"bonus_qty", dir:"desc"}}},
  {id:"bonus_rep", label:"توزيع البونص حسب المندوب",
   spec:{period:{mode:"all"}, groupBy:"rep", bonus:"both",
         measures:["regular_qty","bonus_qty","bonus_share","customers"],
         sort:{by:"bonus_qty", dir:"desc"}}},
  {id:"invoices", label:"تفصيل الفواتير",
   spec:{period:{mode:"all"}, groupBy:"invoice", bonus:"both",
         measures:["revenue","qty","boxes","lines","customers"],
         sort:{by:"revenue", dir:"desc"}}},
];

return {DIMS, MEASURES, FILTERS, BONUS_MODES, PRESETS,
        context, options, run, pivot, drill, periodLabel, inPeriod};
})();

/* node-side tests import this; the browser build just defines the global. */
if(typeof module !== "undefined" && module.exports) module.exports = {Q};
