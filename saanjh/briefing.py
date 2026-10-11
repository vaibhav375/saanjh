"""Tonight's one-page briefing for a district's field officers, as a PDF (fpdf2, pure Python, built in Lambda).

Inputs are the same JSON the page reads: the night (tonight.json / results), the noon plan, and the district
season record (districts.json). District membership is point-in-polygon on the bundled district outlines.
"""
import numpy as np
from fpdf import FPDF

INK, MUTED, EMBER, CYAN, RULE = (16, 30, 40), (100, 120, 132), (201, 71, 42), (23, 120, 160), (220, 226, 230)


def _inside(lat, lon, geom):
    """True if the point lies in any outer ring of the (Multi)Polygon."""
    hit = False
    for poly in geom["coordinates"]:
        r = np.array(poly[0], float)
        x0, y0, x1, y1 = r[:, 0], r[:, 1], np.roll(r[:, 0], -1), np.roll(r[:, 1], -1)
        c = ((y0 > lat) != (y1 > lat)) & (lon < (x1 - x0) * (lat - y0) / np.where(y1 == y0, 1e-12, y1 - y0) + x0)
        hit ^= bool(c.sum() % 2)
    return hit


def _ascii(s):
    return str(s).replace("µ", "u").replace("–", "-").replace("—", "-").replace("’", "'").encode("latin-1", "replace").decode("latin-1")


class _Doc(FPDF):
    def header(self):
        self.set_fill_color(7, 19, 28)
        self.rect(0, 0, 210, 16, "F")
        self.set_xy(12, 4)
        self.set_text_color(244, 162, 89)
        self.set_font("Helvetica", "B", 13)
        self.cell(40, 8, "SAANJH")
        self.set_text_color(234, 241, 244)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 8, "Evening farm-fire briefing - Punjab & Haryana", align="R")
        self.ln(14)

    def footer(self):
        self.set_y(-14)
        self.set_text_color(*MUTED)
        self.set_font("Helvetica", "", 7.5)
        self.multi_cell(0, 3.6, _ascii(
            "Targeting and early-warning tool, not for enforcement against individuals: the grid is 2-4 km and never "
            "identifies farmers or plots. Fires from GK-2A (KMA via NOAA Open Data on AWS); official count = VIIRS at "
            "the ~13:30 pass. Smoke values are the modelled farm-fire share of PM2.5. Saanjh, built on AWS."))


def build(district, night, plan, dist_record):
    """PDF bytes. district = feature from districts.json geo; night/plan may be None."""
    name, geom = district["properties"]["name"], district["geometry"]
    inside = lambda la, lo: _inside(la, lo, geom)
    pdf = _Doc(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()
    pdf.set_margins(12, 18, 12)
    day = (night or plan or {}).get("day", "")

    def h(text, size=15, color=INK):
        pdf.set_text_color(*color)
        pdf.set_font("Helvetica", "B", size)
        pdf.multi_cell(0, size * 0.48, _ascii(text))
        pdf.ln(1)

    def p(text, size=9.5, color=MUTED):
        pdf.set_text_color(*color)
        pdf.set_font("Helvetica", "", size)
        pdf.multi_cell(0, size * 0.5, _ascii(text))
        pdf.ln(1.5)

    def table(head, rows, widths):
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*MUTED)
        for t, w in zip(head, widths):
            pdf.cell(w, 6, _ascii(t), border="B")
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for r in rows:
            for i, (t, w) in enumerate(zip(r, widths)):
                pdf.set_text_color(*(EMBER if t == "MISSED" else CYAN if t == "counted" else INK))
                pdf.cell(w, 6, _ascii(t), border="B" if False else 0)
            pdf.ln()
        pdf.ln(3)

    pdf.set_x(12)
    h(f"{name} - {day}", 20)
    if dist_record:
        s25, s24 = dist_record["y2025"], dist_record["y2024"]
        chg = lambda x: "n/a" if x is None else f"{x * 100:+.0f}%"
        p(f"Season record: official count {s24['official_fires']} fires (2024) -> {s25['official_fires']} (2025), "
          f"{chg(dist_record['official_change'])}. Fire energy GK-2A saw: {s24['fire_energy_tj']} -> {s25['fire_energy_tj']} TJ, "
          f"{chg(dist_record['energy_change'])}. In 2025, {round((s25['missed_share'] or 0) * 100)}% of it came from fires "
          f"that started after the satellites' 13:30 pass.", 9.5, INK)

    # 1. Teams
    h("1. Where to send field teams (noon plan)", 12)
    if plan:
        g = plan["grid"]
        tot = max(sum(plan["expected_harm"]), 1)
        mine = [(i, t) for i, t in enumerate(plan["teams"], 1)
                if inside(g["lat0"] + (t["row"] + 0.5) * g["d"], g["lon0"] + (t["col"] + 0.5) * g["d"])]
        if mine:
            p("Each block is a ~33 km patrol area placed where tonight's fires are likely and their smoke would reach the most people.")
            table(["Team", "Block centre (lat, lon)", "Share of tonight's expected smoke harm"],
                  [[f"#{i}", f"{plan['grid']['lat0'] + (t['row'] + 0.5) * g['d']:.2f}, {g['lon0'] + (t['col'] + 0.5) * g['d']:.2f}",
                    f"{t['share'] * 100:.1f}%"] for i, t in mine], [18, 70, 90])
        else:
            p("No team block of the regional plan falls in this district tonight.")
    else:
        p("No noon plan for this night.")

    # 2. Fires
    h("2. Fires tonight in this district", 12)
    fires = [(k, f) for k, f in enumerate((night or {}).get("fires", []), 1) if inside(f["lat"], f["lon"])]
    if fires:
        tot = (night["stats"]["harm_total"] or 1)
        table(["Rank", "Near", "First seen (IST)", "Peak MW", "PM2.5 kg", "Official count", "Exposure share"],
              [[f"#{k}", f["near"], f["first_ist"], f"{f['frp_peak']:.0f}", f"{f['pm25_kg']:.0f}",
                "counted" if f["counted"] else "MISSED", f"{f['harm'] / tot * 100:.1f}%"] for k, f in fires[:14]],
              [14, 44, 28, 18, 20, 26, 26])
    else:
        p("None of tonight's 50 highest-harm fires is in this district.")

    # 3. Towns
    h("3. Farm smoke reaching towns in this district", 12)
    mine = [t for t in (night or {}).get("towns", []) if "lat" in t and inside(t["lat"], t["lon"])]
    towns = [t for t in mine if t.get("arrives_ist")]  # towns the farm smoke actually reaches (>= 5 ug/m3)
    dow = (night or {}).get("day") and __import__("datetime").date.fromisoformat(night["day"]).strftime("%a")
    when = lambda x: "-" if not x else x[-5:] if x[:3] == dow else x  # weekday only when it isn't this date
    if towns:
        table(["Town", "Smoke from (IST)", "Heaviest (IST)", "Peak ug/m3", "Chance > 25"],
              [[t["town"], when(t.get("arrives_ist")), when(t.get("peak_ist")), f"{t['peak_ugm3']:.0f}",
                f"{round(t.get('p_alert', 0) * 100)}%" if "p_alert" in t else "-"] for t in towns], [40, 34, 32, 30, 30])
        p("Schools: before tomorrow's morning assembly, check the local PM2.5 reading (CPCB Sameer app); "
          "if it is above 90, hold assembly indoors.", 9.5, INK)
    elif mine:
        p(f"Little or no farm smoke expected in this district's towns ({', '.join(t['town'] for t in mine)}).")
    else:
        p("No Saanjh town in this district.")
    return bytes(pdf.output())
