"""
Brigade Meta Leads — Dashboard Generator
Fetches all leads from Meta API and generates a self-contained HTML dashboard.
Runs after every sync via GitHub Actions.
"""

import requests, os, json
from datetime import datetime, timezone, timedelta
from collections import defaultdict

META_TOKEN = os.environ['META_SYSTEM_USER_TOKEN']
IST        = timezone(timedelta(hours=5, minutes=30))

FORMS = [
    {"property": "Signature",  "sheet": "Signature - Club Membership", "form_id": "1958383678398355", "type": "Club Membership"},
    {"property": "Signature",  "sheet": "Signature - Day Out",         "form_id": "2087614135361752", "type": "Day Out"},
    {"property": "Woodrose",   "sheet": "Woodrose - Club Membership",  "form_id": "2373227253178965", "type": "Club Membership"},
    {"property": "Woodrose",   "sheet": "Woodrose - Social Events",    "form_id": "979047675186445",  "type": "Social Events"},
    {"property": "Regent",     "sheet": "Regent - Club Membership",    "form_id": "1345460640739280", "type": "Club Membership"},
    {"property": "Regent",     "sheet": "Regent - Social Events",      "form_id": "1256247030047629", "type": "Social Events"},
    {"property": "Augusta",    "sheet": "Augusta - Club Membership",   "form_id": "1985356756189741", "type": "Club Membership"},
    {"property": "Augusta",    "sheet": "Augusta - Social Events",     "form_id": "4400562656882365", "type": "Social Events"},
    {"property": "Galaxy",     "sheet": "Galaxy - Club Membership",    "form_id": "1652253566011112", "type": "Club Membership"},
    {"property": "Galaxy",     "sheet": "Galaxy - Social Events",      "form_id": "830344982769325",  "type": "Social Events"},
]

PROPERTIES = ["Signature", "Woodrose", "Regent", "Augusta", "Galaxy"]
COLORS     = {"Signature": "#1a3c6e", "Woodrose": "#6e1a3c", "Regent": "#1a6e3c",
              "Augusta": "#6e4a1a", "Galaxy": "#3c1a6e"}


def fmt_date(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace('+0000', '+00:00'))
        return dt.astimezone(IST).strftime("%-d %b %Y, %-I:%M %p")
    except Exception:
        return iso_str

def fetch_all_leads(form_id):
    leads, url = [], f"https://graph.facebook.com/v21.0/{form_id}/leads"
    params = {"access_token": META_TOKEN, "fields": "created_time,field_data,id", "limit": 100}

    # Get field labels
    r = requests.get(f"https://graph.facebook.com/v21.0/{form_id}",
                     params={"access_token": META_TOKEN, "fields": "questions"})
    label_map = {"full_name": "Name", "phone_number": "Phone", "email": "Email"}
    value_map = {}
    for q in r.json().get("questions", []):
        key = q.get("key", "")
        if key not in label_map:
            label_map[key] = q.get("label", key)
        if q.get("options"):
            value_map[key] = {o["key"]: o["value"] for o in q["options"]}

    while url:
        resp = requests.get(url, params=params)
        data = resp.json()
        if "error" in data:
            print(f"  Error {form_id}: {data['error']['message']}", flush=True)
            return []
        for lead in data.get("data", []):
            row = {"id": lead["id"], "date": fmt_date(lead["created_time"]),
                   "date_raw": lead["created_time"]}
            for field in lead.get("field_data", []):
                col = label_map.get(field["name"], field["name"])
                raw = field["values"][0] if field.get("values") else ""
                row[col] = value_map.get(field["name"], {}).get(raw, raw)
            leads.append(row)
        url    = data.get("paging", {}).get("next")
        params = {}
    return leads


def fetch_all_data():
    data = defaultdict(list)  # property -> list of leads with 'form_type'
    for form in FORMS:
        print(f"  Fetching {form['sheet']}...", flush=True)
        leads = fetch_all_leads(form["form_id"])
        print(f"    → {len(leads)} leads", flush=True)
        for lead in leads:
            lead["form_type"] = form["type"]
            lead["sheet"]     = form["sheet"]
        data[form["property"]].extend(leads)
    return data


def leads_by_day(leads, days=30):
    counts = defaultdict(int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for lead in leads:
        try:
            dt = datetime.fromisoformat(lead["date_raw"].replace('+0000', '+00:00'))
            if dt >= cutoff:
                counts[dt.astimezone(IST).strftime("%d %b")] += 1
        except Exception:
            pass
    # Fill all days
    result = {}
    for i in range(days - 1, -1, -1):
        label = (datetime.now(IST) - timedelta(days=i)).strftime("%d %b")
        result[label] = counts.get(label, 0)
    return result


def build_lead_row(lead, extra_cols):
    name  = lead.get("Name", "—")
    phone = lead.get("Phone", "—")
    if phone and not phone.startswith('+') and phone.isdigit() and len(phone) >= 10:
        phone = '+' + phone
    email = lead.get("Email", "—")
    date  = lead.get("date", "—")
    ftype = lead.get("form_type", "—")
    extras = "".join(f"<td>{lead.get(c,'—')}</td>" for c in extra_cols)
    return f"""<tr>
      <td><strong>{name}</strong></td>
      <td>{phone}</td>
      <td>{email or '—'}</td>
      <td>{ftype}</td>
      <td>{date}</td>
      {extras}
    </tr>"""


def get_extra_cols(leads):
    skip = {"id", "date", "date_raw", "form_type", "sheet", "Name", "Phone", "Email"}
    cols = []
    for lead in leads:
        for k in lead:
            if k not in skip and k not in cols:
                cols.append(k)
    return cols


def build_property_section(prop, leads, color):
    total      = len(leads)
    trend      = leads_by_day(leads, 30)
    labels     = list(trend.keys())
    values     = list(trend.values())
    extra_cols = get_extra_cols(leads)

    # Sort leads newest first
    def sort_key(l):
        try:
            return datetime.fromisoformat(l["date_raw"].replace('+0000', '+00:00'))
        except:
            return datetime.min.replace(tzinfo=timezone.utc)
    leads_sorted = sorted(leads, key=sort_key, reverse=True)

    extra_headers = "".join(f"<th>{c}</th>" for c in extra_cols)
    rows          = "".join(build_lead_row(l, extra_cols) for l in leads_sorted)

    # This week
    week_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    this_week   = sum(1 for l in leads if _lead_after(l, week_cutoff))
    today_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    today        = sum(1 for l in leads if _lead_after(l, today_cutoff))

    return f"""
<div class="prop-section" id="prop-{prop.lower()}">
  <div class="prop-header" style="background:{color}">
    <div>
      <div class="prop-name">{prop}</div>
      <div class="prop-sub">{total} total leads</div>
    </div>
    <div class="prop-stats">
      <div class="prop-stat"><div class="ps-val">{total}</div><div class="ps-lbl">Total</div></div>
      <div class="prop-stat"><div class="ps-val">{this_week}</div><div class="ps-lbl">This week</div></div>
      <div class="prop-stat"><div class="ps-val">{today}</div><div class="ps-lbl">Today</div></div>
    </div>
  </div>

  <div class="chart-wrap">
    <canvas id="chart-{prop.lower()}" height="80"></canvas>
  </div>

  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Name</th><th>Phone</th><th>Email</th><th>Form</th><th>Submitted At</th>
        {extra_headers}
      </tr></thead>
      <tbody>{rows if rows else '<tr><td colspan="10" style="text-align:center;color:#9ca3af">No leads yet</td></tr>'}</tbody>
    </table>
  </div>
</div>
<script>
(function(){{
  var ctx = document.getElementById('chart-{prop.lower()}').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {json.dumps(labels)},
      datasets: [{{
        label: 'Leads',
        data: {json.dumps(values)},
        backgroundColor: '{color}cc',
        borderRadius: 4
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 10, font: {{ size: 11 }} }} }},
        y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }}
      }}
    }}
  }});
}})();
</script>"""


def _lead_after(lead, cutoff):
    try:
        dt = datetime.fromisoformat(lead["date_raw"].replace('+0000', '+00:00'))
        return dt >= cutoff
    except:
        return False


def generate(data):
    now_str  = datetime.now(IST).strftime("%-d %b %Y, %-I:%M %p IST")
    total    = sum(len(v) for v in data.values())
    week_cut = datetime.now(timezone.utc) - timedelta(days=7)
    today_cut= datetime.now(timezone.utc) - timedelta(hours=24)
    all_leads= [l for leads in data.values() for l in leads]
    this_week= sum(1 for l in all_leads if _lead_after(l, week_cut))
    today    = sum(1 for l in all_leads if _lead_after(l, today_cut))

    # Nav tabs
    nav = '<button class="tab active" onclick="showProp(\'all\',this)">All Properties</button>'
    nav += "".join(
        f'<button class="tab" onclick="showProp(\'{p.lower()}\',this)" style="--tc:{COLORS[p]}">{p}</button>'
        for p in PROPERTIES
    )

    # Summary donut data
    donut_labels = [p for p in PROPERTIES if data.get(p)]
    donut_values = [len(data.get(p, [])) for p in donut_labels]
    donut_colors = [COLORS[p] for p in donut_labels]

    # Property sections
    sections = ""
    for prop in PROPERTIES:
        leads = data.get(prop, [])
        sections += build_property_section(prop, leads, COLORS[prop])

    # All-properties table (summary)
    all_sorted = sorted(all_leads, key=lambda l: l.get("date_raw", ""), reverse=True)[:50]
    all_rows   = "".join(f"""<tr>
      <td><strong>{l.get('Name','—')}</strong></td>
      <td>{l.get('sheet','—').split(' - ')[0]}</td>
      <td>{l.get('form_type','—')}</td>
      <td>{('+' if (l.get('Phone','') and not l.get('Phone','').startswith('+') and l.get('Phone','').isdigit()) else '') + l.get('Phone','—')}</td>
      <td>{l.get('date','—')}</td>
    </tr>""" for l in all_sorted)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brigade Hospitality — Leads Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#1a1a2e}}
.header{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);color:white;padding:28px 40px;display:flex;justify-content:space-between;align-items:center}}
.header h1{{font-size:1.7rem;font-weight:700;letter-spacing:-.3px}}
.header p{{opacity:.6;font-size:.85rem;margin-top:4px}}
.updated{{background:rgba(255,255,255,.12);padding:6px 14px;border-radius:20px;font-size:.72rem;opacity:.9}}
.container{{max-width:1200px;margin:0 auto;padding:28px 20px}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px}}
.card{{background:white;border-radius:14px;padding:20px 24px;box-shadow:0 2px 10px rgba(0,0,0,.06)}}
.card-val{{font-size:2rem;font-weight:700;color:#0f3460}}
.card-lbl{{font-size:.72rem;text-transform:uppercase;letter-spacing:.8px;color:#9ca3af;margin-top:4px;font-weight:600}}
.donut-card{{background:white;border-radius:14px;padding:20px;box-shadow:0 2px 10px rgba(0,0,0,.06);display:flex;align-items:center;gap:24px}}
.donut-card canvas{{max-width:160px;max-height:160px}}
.donut-legend{{flex:1}}
.dl-row{{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:.84rem}}
.dl-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.dl-name{{flex:1;color:#444}}
.dl-val{{font-weight:700;color:#1a1a2e}}
.nav{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px}}
.tab{{padding:9px 20px;border-radius:10px;border:2px solid #dde3f5;background:white;color:#6b7280;font-size:.84rem;font-weight:600;cursor:pointer;transition:all .2s}}
.tab.active{{background:#0f3460;color:white;border-color:#0f3460}}
.tab:hover:not(.active){{border-color:var(--tc,#0f3460);color:var(--tc,#0f3460)}}
.prop-section{{display:none;background:white;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.07);margin-bottom:20px}}
.prop-section.visible{{display:block}}
.prop-header{{padding:20px 28px;display:flex;justify-content:space-between;align-items:center;color:white}}
.prop-name{{font-size:1.2rem;font-weight:700}}
.prop-sub{{font-size:.8rem;opacity:.75;margin-top:3px}}
.prop-stats{{display:flex;gap:28px}}
.prop-stat{{text-align:center}}
.ps-val{{font-size:1.4rem;font-weight:700}}
.ps-lbl{{font-size:.65rem;opacity:.75;text-transform:uppercase;letter-spacing:.5px}}
.chart-wrap{{padding:20px 28px 10px;border-bottom:1px solid #f3f4f6}}
.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:.84rem}}
th{{background:#1a1a2e;color:white;padding:10px 14px;text-align:left;font-size:.74rem;letter-spacing:.4px;white-space:nowrap}}
td{{padding:9px 14px;border-bottom:1px solid #f3f4f6;white-space:nowrap}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#f8f9ff}}
.all-section{{background:white;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.07)}}
.all-header{{padding:18px 28px;background:#1a1a2e;color:white;font-size:1rem;font-weight:700}}
.footer{{text-align:center;padding:24px;color:#9ca3af;font-size:.72rem}}
@media(max-width:700px){{.summary{{grid-template-columns:repeat(2,1fr)}}.prop-stats{{gap:16px}}}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Brigade Hospitality</h1>
    <p>Meta Ads — Leads Dashboard</p>
  </div>
  <div class="updated">Updated {now_str}</div>
</div>

<div class="container">

  <!-- Summary cards -->
  <div class="summary">
    <div class="card"><div class="card-val">{total}</div><div class="card-lbl">Total Leads</div></div>
    <div class="card"><div class="card-val">{this_week}</div><div class="card-lbl">This Week</div></div>
    <div class="card"><div class="card-val">{today}</div><div class="card-lbl">Last 24 Hours</div></div>
    <div class="card"><div class="card-val">{len([p for p in PROPERTIES if data.get(p)])}</div><div class="card-lbl">Properties Active</div></div>
  </div>

  <!-- Donut chart -->
  <div class="donut-card" style="margin-bottom:28px">
    <canvas id="donut-chart"></canvas>
    <div class="donut-legend">
      <div style="font-size:.85rem;font-weight:700;color:#1a1a2e;margin-bottom:12px">Leads by Property</div>
      {''.join(f'<div class="dl-row"><div class="dl-dot" style="background:{COLORS[p]}"></div><div class="dl-name">{p}</div><div class="dl-val">{len(data.get(p,[]))}</div></div>' for p in PROPERTIES if data.get(p))}
    </div>
  </div>

  <!-- Nav tabs -->
  <div class="nav">{nav}</div>

  <!-- All properties view -->
  <div class="prop-section all-section visible" id="prop-all">
    <div class="all-header">Recent 50 Leads — All Properties</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Name</th><th>Property</th><th>Form</th><th>Phone</th><th>Submitted At</th></tr></thead>
        <tbody>{all_rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Per-property sections -->
  {sections}

</div>

<div class="footer">Brigade Hospitality x Gautami &nbsp;|&nbsp; Auto-updated every 15 minutes</div>

<script>
// Donut chart
new Chart(document.getElementById('donut-chart'), {{
  type: 'doughnut',
  data: {{
    labels: {json.dumps(donut_labels)},
    datasets: [{{
      data: {json.dumps(donut_values)},
      backgroundColor: {json.dumps(donut_colors)},
      borderWidth: 0,
      hoverOffset: 6
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }}
  }}
}});

// Tab switching
function showProp(id, el) {{
  document.querySelectorAll('.prop-section').forEach(s => s.classList.remove('visible'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('prop-' + id).classList.add('visible');
  el.classList.add('active');
}}
</script>
</body>
</html>"""
    return html


if __name__ == '__main__':
    print("Fetching all leads for dashboard...", flush=True)
    data = fetch_all_data()
    total = sum(len(v) for v in data.values())
    print(f"Total leads: {total}", flush=True)
    html = generate(data)
    out  = os.path.join(os.path.dirname(__file__), 'dashboard.html')
    with open(out, 'w') as f:
        f.write(html)
    print(f"Dashboard saved → {out}", flush=True)
