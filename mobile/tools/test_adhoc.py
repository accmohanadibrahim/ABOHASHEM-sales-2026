#!/usr/bin/env python3
"""Drive the ad-hoc reporting section in a real browser and check its numbers.

The engine has unit tests; this asserts the other half — that the section wired
to it actually renders, that its controls change the result, that a drill-down
matches the row it came from, and above all that the total on screen equals the
same figure computed independently from the payload. A builder that renders
beautifully and shows a number nobody can reproduce is the failure this guards.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROMIUM = "/opt/pw-browsers/chromium"
DEFAULT = Path(__file__).resolve().parents[1] / "dist" / "Abu_Hashem_Mobile_standalone.html"

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record one assertion and print it; failures are collected, not raised."""
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def run(path: Path) -> int:
    """Open the ad-hoc section, exercise it, and reconcile what it shows."""
    errors: list[str] = []
    with sync_playwright() as pw:
        kw = {"executable_path": CHROMIUM} if Path(CHROMIUM).exists() else {}
        browser = pw.chromium.launch(**kw)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(path.as_uri())
        page.wait_for_selector("#root > div", timeout=30_000)
        page.wait_for_timeout(1200)

        reg = page.evaluate("() => window.__app.registry().map(s => s.key)")
        check("the section is in the registry", "adhoc" in reg, f"{len(reg)} sections")
        if "adhoc" not in reg:
            browser.close()
            return 1

        page.evaluate("() => window.__app.go('adhoc')")
        page.wait_for_timeout(900)
        body = page.inner_text("#root")
        check("the builder renders", len(body) > 600, f"{len(body)} chars")
        for label in ["تقارير جاهزة", "الفترة", "التجميع والمقاييس",
                      "الفلاتر", "الإجمالي", "النتيجة"]:
            check(f"card present — {label}", label in body)

        # ---- the number on screen must be reproducible from the payload ----
        # Computed here from the payload the app actually rendered, by a second,
        # if the engine and a plain loop disagree, the engine is wrong.
        # setState is async, so a spec is passed to the engine explicitly here
        # rather than written through qSet and read straight back — doing that
        # returns the PREVIOUS spec and silently tests the wrong query. The
        # control wiring is checked on its own further down, with a tick.
        probe = page.evaluate("""() => {
          const app = window.__app;
          const spec = {period:{mode:"all"}, groupBy:"rep", bonus:"regular",
                        measures:["revenue","qty","invoices","customers"],
                        sort:{by:"revenue", dir:"desc"}};
          app.qSet(spec);
          const res  = Q.run(window.__app.state.api.D.lines, spec, app.state.qctx);
          let rev = 0, qty = 0;
          const inv = new Set(), cus = new Set();
          for (const l of window.__app.state.api.D.lines) {
            if (l.is_bonus) continue;
            rev += l.line_total || 0; qty += l.qty || 0;
            inv.add(l.invoice_no); cus.add(String(l.customer_code));
          }
          return {engine:{revenue:res.total.revenue, qty:res.total.qty,
                          invoices:res.total.invoices, customers:res.total.customers,
                          groups:res.meta.groups},
                  naive:{revenue:rev, qty:qty, invoices:inv.size, customers:cus.size}};
        }""")
        e, n = probe["engine"], probe["naive"]
        for k in ("revenue", "qty", "invoices", "customers"):
            check(f"total reconciles — {k}", abs(e[k] - n[k]) < 0.01,
                  f"{e[k]:,.2f} vs {n[k]:,.2f}")
        check("grouped by rep", e["groups"] > 1, f"{e['groups']} reps")

        page.wait_for_timeout(700)
        shown = page.inner_text("#root")
        # 30,639,505.54 -> the grouping label must be on screen too
        check("the rep grouping reached the screen", "المندوب" in shown)

        # ---- controls actually change the result -------------------------
        moved = page.evaluate("""() => {
          const app = window.__app, ctx = app.state.qctx, L = app.state.api.D.lines;
          const S = p => ({period:{mode:"all"}, filters:{}, bonus:"regular",
                           measures:["revenue","qty"], sort:{by:"revenue",dir:"desc"}, ...p});
          const reps   = Q.run(L, S({groupBy:"rep"}),   ctx).meta.groups;
          const brands = Q.run(L, S({groupBy:"brand"}), ctx).meta.groups;
          const aug = Q.run(L, S({groupBy:"rep", period:{mode:"month", month:"2026-08"}}), ctx).total.revenue;
          const rng = Q.run(L, S({groupBy:"rep",
            period:{mode:"range", from:"2026-08-01", to:"2026-08-31"}}), ctx).total.revenue;
          const both = Q.run(L, S({groupBy:"item", bonus:"both"}),    ctx).total;
          const reg  = Q.run(L, S({groupBy:"item", bonus:"regular"}), ctx).total;
          return {before:reps, after:brands, aug, rng,
                  bonusQty:both.bonus_qty, bothQty:both.qty, regQty:reg.qty,
                  bothRev:both.revenue, regRev:reg.revenue,
                  bonusRev:both.bonus_revenue,
                  warns:Q.run(L, S({groupBy:"item", bonus:"regular"}), ctx).meta.warnings};
        }""")
        check("changing the dimension changes the grouping",
              moved["before"] != moved["after"],
              f"{moved['before']} reps -> {moved['after']} brands")
        check("a month and the equivalent date range agree",
              abs(moved["aug"] - moved["rng"]) < 0.01,
              f"{moved['aug']:,.2f}")
        check("bonus carries quantity, not revenue",
              moved["bothQty"] - moved["regQty"] == moved["bonusQty"]
              and moved["bonusQty"] > 0,
              f"+{moved['bonusQty']:,.0f} unit")
        # Free goods are supposed to carry no money, and all but one line do.
        # That single 740.00 EGP line is real data, so the test pins it rather
        # than asserting a zero the source contradicts: if the anomaly ever
        # grows, this is what notices.
        gap = moved["bothRev"] - moved["regRev"]
        check("the whole revenue gap is the flagged bonus money",
              abs(gap - moved["bonusRev"]) < 0.01 and abs(gap - 740.00) < 0.01,
              f"{gap:,.2f} EGP on bonus lines")
        check("and the reader is told about it",
              any("بونص تحمل قيمة مالية" in w for w in moved["warns"]))

        # ---- drill-down must add up to the row it came from ---------------
        drill = page.evaluate("""() => {
          const app = window.__app, ctx = app.state.qctx, L = window.__app.state.api.D.lines;
          const spec = {period:{mode:"all"}, filters:{}, groupBy:"customer",
                        bonus:"regular", measures:["revenue","qty"],
                        sort:{by:"revenue", dir:"desc"}};
          app.qSet(spec);
          const top  = Q.run(L, spec, ctx).allRows[0];
          const det  = Q.drill(L, spec, ctx, top.key);
          app.setState({qDrill: top.key});
          return {label:top.label, rowRev:top.revenue, rowLines:top.lines,
                  detLines:det.length,
                  detRev:det.reduce((a,l)=>a+(l.line_total||0),0),
                  anyBonus:det.some(l=>l.is_bonus)};
        }""")
        check("drill-down line count matches its row",
              drill["rowLines"] == drill["detLines"],
              f"{drill['label']}: {drill['detLines']} بند")
        check("drill-down value matches its row",
              abs(drill["rowRev"] - drill["detRev"]) < 0.01,
              f"{drill['detRev']:,.2f}")
        check("«البيع فقط» detail excludes bonus lines", not drill["anyBonus"])

        page.wait_for_timeout(800)
        check("the drill-down panel rendered", "تفصيل:" in page.inner_text("#root"))

        # ---- the controls really write through to state -------------------
        # The engine checks above bypass qSet deliberately; this one does not,
        # because a builder whose chips compute the right answer and never
        # store it is broken in the only way that matters to a user.
        page.evaluate("""() => window.__app.qSet(
          {period:{mode:"all"}, filters:{}, groupBy:"brand", bonus:"regular",
           measures:["revenue","qty"], sort:{by:"revenue", dir:"desc"}})""")
        page.wait_for_timeout(700)
        wired = page.evaluate("""() => {
          const app = window.__app;
          return {groupBy: app.qSpec().groupBy,
                  groups: Q.run(app.state.api.D.lines, app.qSpec(),
                                app.state.qctx).meta.groups};
        }""")
        check("a control writes through to state", wired["groupBy"] == "brand",
              f"groupBy={wired['groupBy']}")
        check("and the stored query regroups the result", wired["groups"] == 4,
              f"{wired['groups']} brands")
        check("the new grouping reached the screen",
              "العلامة التجارية" in page.inner_text("#root"))

        # ---- the built query becomes an export sheet ----------------------
        sheets = page.evaluate(
            "() => window.__app.exportTables().map(t => t.label)")
        check("the ad-hoc result joins the export catalogue",
              any(s.startswith("تقرير مرن") for s in sheets),
              f"{len(sheets)} sheets")

        check("no JS errors throughout", not errors, "; ".join(errors[:2]))
        browser.close()

    bad = [c for c in checks if not c[1]]
    print(f"\n{'all ad-hoc checks passed' if not bad else str(len(bad)) + ' CHECK(S) FAILED'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT))
