"""CSS for the dark theme. Injected once by streamlit_app.py.

Palette: background #0B1220, cards #172338, accent #14B8A6, green #22C55E, red #EF4444,
text #E5E7EB, secondary text #94A3B8. Selectors use Streamlit's data-testid attributes and
the st-key-<name> classes of keyed containers, which are the stable hooks."""

CSS = """
:root {
  --bg: #0B1220; --card: #172338; --card-2: #1D2B45; --accent: #14B8A6;
  --green: #22C55E; --red: #EF4444; --blue: #38BDF8; --amber: #F59E0B;
  --text: #E5E7EB; --muted: #94A3B8; --border: rgba(148, 163, 184, 0.16); --radius: 16px;
}

/* ---------- page ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"] {
  font-family: Inter, "Segoe UI", system-ui, -apple-system, sans-serif;
  color: var(--text);
}
.stApp {
  background: radial-gradient(1100px 480px at 88% -12%, rgba(20, 184, 166, 0.12), transparent 60%),
              radial-gradient(900px 400px at -5% 0%, rgba(56, 189, 248, 0.07), transparent 55%), var(--bg);
}
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1180px; padding-top: 1.2rem; padding-bottom: 7rem; }
h1, h2, h3, h4 { letter-spacing: -0.01em; }
hr { border-color: var(--border); }
[data-testid="stCaptionContainer"], .stCaption { color: var(--muted); }

/* ---------- brand header ---------- */
.rg-header {
  display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
  padding: 18px 22px; margin-bottom: 1.1rem; border: 1px solid var(--border); border-radius: var(--radius);
  background: linear-gradient(135deg, #172338 0%, #123049 58%, #0F3D45 100%);
}
.rg-brand { display: flex; align-items: center; gap: 14px; }
.rg-logo {
  width: 46px; height: 46px; border-radius: 13px; display: grid; place-items: center; flex: none;
  background: linear-gradient(135deg, var(--accent), #0EA5E9); color: #04222A;
  font-weight: 800; letter-spacing: 0.04em; box-shadow: 0 6px 18px rgba(20, 184, 166, 0.28);
}
.rg-logo-sm { width: 34px; height: 34px; border-radius: 10px; font-size: 0.8rem; }
.rg-title { font-size: 1.55rem; font-weight: 750; line-height: 1.1; letter-spacing: -0.015em; }
.rg-title-sm { font-size: 1.15rem; }
.rg-tagline { color: var(--muted); font-size: 0.9rem; margin-top: 3px; }
.rg-side-brand { display: flex; align-items: center; gap: 10px; margin: 0.2rem 0 1rem; }

/* ---------- chips and status ---------- */
.rg-chips { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 6px 0; }
.rg-chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; border-radius: 999px;
  border: 1px solid var(--border); background: rgba(11, 18, 32, 0.55); color: var(--muted); font-size: 0.78rem;
}
.rg-chip b { color: var(--text); font-weight: 600; }
.rg-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.rg-dot-ok { background: var(--green); } .rg-dot-warn { background: var(--amber); } .rg-dot-info { background: var(--accent); }
.rg-footer { margin-top: 10px; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: #0E1729; border-right: 1px solid var(--border); }
.rg-section {
  font-size: 0.72rem; font-weight: 650; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--muted); margin: 18px 0 8px;
}
[data-testid="stSidebar"] .stButton > button {
  width: 100%; text-align: left; justify-content: flex-start; white-space: normal; line-height: 1.35;
  background: var(--card); color: var(--text); border: 1px solid var(--border); border-radius: 12px;
  padding: 10px 12px; font-size: 0.86rem; transition: border-color .15s, transform .15s, background .15s;
}
[data-testid="stSidebar"] .stButton > button:hover {
  border-color: var(--accent); background: var(--card-2); transform: translateY(-1px);
}
[data-testid="stSidebar"] [role="radiogroup"] { gap: 6px; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 6px 14px; cursor: pointer;
}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  background: rgba(20, 184, 166, 0.16); border-color: var(--accent);
}

/* ---------- empty state ---------- */
.rg-hero { padding: 26px 6px 8px; }
.rg-hero-title { font-size: 1.9rem; font-weight: 750; letter-spacing: -0.02em; line-height: 1.15; max-width: 760px; }
.rg-hero-text { color: var(--muted); max-width: 720px; margin: 10px 0 22px; line-height: 1.6; }
.rg-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; }
.rg-tile {
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; border-top: 3px solid var(--accent);
}
.rg-tile-burn { border-top-color: var(--red); } .rg-tile-water { border-top-color: var(--blue); } .rg-tile-veg { border-top-color: var(--green); }
.rg-tile-title { font-weight: 650; margin-bottom: 6px; }
.rg-tile-text { color: var(--muted); font-size: 0.88rem; line-height: 1.5; }
.rg-hero-note { color: var(--muted); font-size: 0.82rem; margin-top: 18px; }

/* ---------- chat ---------- */
[data-testid="stChatMessage"] { background: transparent; border: none; padding: 0.3rem 0; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.8rem 1rem;
}
[data-testid="stChatMessageAvatarUser"] { background: var(--card-2); }
[data-testid="stChatMessageAvatarAssistant"] { background: linear-gradient(135deg, var(--accent), #0EA5E9); }
[data-testid="stBottom"] > div { background: linear-gradient(to top, var(--bg) 72%, transparent); }
[data-testid="stChatInput"] {
  background: var(--card); border: 1px solid var(--border); border-radius: 18px; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.28);
}
[data-testid="stChatInput"]:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.2); }
[data-testid="stChatInput"] textarea { color: var(--text); }
[data-testid="stChatInput"] button { background: var(--accent); color: #04222A; border-radius: 12px; }

/* ---------- progress stepper ---------- */
.rg-stepcard { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 14px 12px; margin-bottom: 12px; }
.rg-stepper { display: flex; }
.rg-step { flex: 1; text-align: center; position: relative; }
.rg-step:not(:last-child)::after {
  content: ""; position: absolute; top: 15px; left: calc(50% + 20px); right: calc(-50% + 20px); height: 2px; background: var(--border);
}
.rg-step.done:not(:last-child)::after { background: var(--accent); }
.rg-dotn {
  width: 30px; height: 30px; border-radius: 50%; display: inline-grid; place-items: center; font-size: 0.8rem; font-weight: 700;
  background: #0F1A2E; border: 2px solid var(--border); color: var(--muted);
}
.rg-step.done .rg-dotn { background: var(--accent); border-color: var(--accent); color: #04222A; }
.rg-step.active .rg-dotn { border-color: var(--accent); color: var(--accent); animation: rgpulse 1.4s ease-in-out infinite; }
.rg-step.failed .rg-dotn { background: var(--red); border-color: var(--red); color: #fff; }
.rg-steplabel { display: block; margin-top: 7px; font-size: 0.78rem; color: var(--muted); }
.rg-step.done .rg-steplabel, .rg-step.active .rg-steplabel { color: var(--text); }
.rg-stepnote { text-align: center; color: var(--muted); font-size: 0.82rem; margin-top: 10px; }
@keyframes rgpulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.5); } 50% { box-shadow: 0 0 0 9px rgba(20, 184, 166, 0); } }

/* ---------- metric cards ---------- */
[data-testid="stMetric"] {
  background: var(--card); border: 1px solid var(--border); border-top: 3px solid var(--accent);
  border-radius: 14px; padding: 14px 16px; height: 100%;
}
[data-testid="stMetricLabel"] p { color: var(--muted); font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.07em; }
[data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 720; letter-spacing: -0.01em; }
[data-testid="stMetricDelta"] { color: var(--muted) !important; font-size: 0.8rem; }
[data-testid="stMetricDelta"] svg { display: none; }
[class*="st-key-m_loss_"] [data-testid="stMetric"] { border-top-color: var(--red); }
[class*="st-key-m_loss_"] [data-testid="stMetricValue"] { color: var(--red); }
[class*="st-key-m_gain_"] [data-testid="stMetric"] { border-top-color: var(--green); }
[class*="st-key-m_gain_"] [data-testid="stMetricValue"] { color: var(--green); }
[class*="st-key-m_net_pos_"] [data-testid="stMetric"] { border-top-color: var(--green); }
[class*="st-key-m_net_neg_"] [data-testid="stMetric"] { border-top-color: var(--red); }
[class*="st-key-m_rain_"] [data-testid="stMetric"] { border-top-color: var(--blue); }
[class*="st-key-m_rain_"] [data-testid="stMetricValue"] { color: var(--blue); }

/* ---------- report card ---------- */
[class*="st-key-report_"], [class*="st-key-map_card_"] {
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px 24px; margin-top: 14px;
}
.rg-report-title { font-size: 1.12rem; font-weight: 700; letter-spacing: -0.01em; }
[class*="st-key-report_"] ul { padding-left: 1.1rem; }
[class*="st-key-report_"] li { margin: 5px 0; line-height: 1.55; }
[class*="st-key-report_"] strong { color: #F3F4F6; }
.rg-insight {
  border-left: 3px solid var(--accent); background: rgba(20, 184, 166, 0.09); padding: 12px 16px;
  border-radius: 0 12px 12px 0; line-height: 1.6;
}
.rg-limits { color: var(--muted); padding-left: 1.1rem; margin: 0; }
.rg-limits li { margin: 4px 0; }

/* ---------- map card ---------- */
[class*="st-key-map_card_"] iframe { border-radius: 12px; border: 1px solid var(--border); }
.rg-legend { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 10px; color: var(--muted); font-size: 0.82rem; }
.rg-sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.rg-sw-loss { background: var(--red); } .rg-sw-gain { background: var(--green); }
.rg-sw-none { background: transparent; border: 1px dashed var(--muted); }

/* ---------- buttons, alerts ---------- */
[data-testid="stDownloadButton"] button {
  background: transparent; color: var(--accent); border: 1px solid var(--accent); border-radius: 10px;
}
[data-testid="stDownloadButton"] button:hover { background: rgba(20, 184, 166, 0.12); }
[data-testid="stAlert"] { border-radius: 12px; }
@media (max-width: 760px) {
  .rg-title { font-size: 1.25rem; } .rg-hero-title { font-size: 1.5rem; }
  [class*="st-key-report_"], [class*="st-key-map_card_"] { padding: 14px 14px; }
}
"""
