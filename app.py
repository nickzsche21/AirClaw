import streamlit as st
import streamlit.components.v1
import requests
import base64
import os

# ── KEYS ──────────────────────────────────────────────────────────────────────
import base64 as _b64
EL_KEY   = _b64.b64decode("c2tfY2FiZTdlNzdjODA2N2ZhYzkxZDZmZGU0YmJjNDYxYjg5NGY2MTczNTNmYzkzMmEz").decode()
GROQ_KEY = _b64.b64decode("Z3NrX05UZ2NXNmswTTJWeVNiTXZuZVB4V0dkeWIzRlloa29VZjVwb0dpam55OWJrUndSRDRQQ2Q=").decode()

AGENTS = {
    "Aria": {
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "color": "#E2D9F3", "accent": "#A78BFA", "cls": "aria", "emoji": "🎯",
        "role": "Orchestrator", "tagline": "Routes · Synthesizes · Commands",
        "system": "You are Aria, an intelligent AI orchestrator. Warm, sharp, authoritative. 2-3 sentences max. Naturally mention handing off when routing.",
        "keywords": []
    },
    "Rex": {
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "color": "#D0EEFF", "accent": "#38BDF8", "cls": "rex", "emoji": "💻",
        "role": "Code Specialist", "tagline": "Debugs · Builds · Ships",
        "system": "You are Rex, an elite software engineer. Direct, precise, no fluff. Include concise code when relevant. Max 3-4 sentences.",
        "keywords": ["code","python","javascript","function","bug","error","debug","program","script","api","database","algorithm","syntax","class","loop","array","compile","runtime","git","deploy","react","css","html","typescript","sql","bash"]
    },
    "Lex": {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "color": "#CCFCE8", "accent": "#34D399", "cls": "lex", "emoji": "⚖️",
        "role": "Legal Specialist", "tagline": "IPC · CrPC · Constitution",
        "system": "You are Lex, a brilliant Indian legal specialist. Authoritative, precise. Cite IPC/CrPC/Constitution when relevant. Max 3-4 sentences.",
        "keywords": ["law","legal","ipc","section","court","statute","act","rights","contract","criminal","civil","judge","advocate","petition","bail","verdict","constitution","crpc","fir","arrest","offence","punishment","lawyer","case","judgment","article"]
    },
    "Max": {
        "voice_id": "ErXwobaYiN019PkySvjV",
        "color": "#FFE4C8", "accent": "#FB923C", "cls": "max", "emoji": "🔬",
        "role": "Research Specialist", "tagline": "Science · History · Economics",
        "system": "You are Max, a deep research specialist. Synthesize complex topics into sharp insights. Science, history, economics, tech. Max 3-4 sentences.",
        "keywords": ["research","explain","what is","how does","why","history","science","data","compare","difference","study","facts","tell me","who is","when did","where is","economics","politics","medicine","physics","biology","what happened"]
    }
}

GROQ_MODELS = ["llama-3.1-8b-instant","llama3-8b-8192","mixtral-8x7b-32768","gemma-7b-it"]

def detect(text):
    t = text.lower()
    for name, info in AGENTS.items():
        if name == "Aria": continue
        if any(w in t for w in info["keywords"]):
            return name
    return "Aria"

def groq_call(agent_name, question, context=""):
    system = AGENTS[agent_name]["system"]
    if context: system += f"\n\nPrior context: {context}"
    for model in GROQ_MODELS:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":question}],
                      "max_tokens": 180, "temperature": 0.75},
                timeout=20
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            else:
                st.caption(f"⚠️ Groq [{model}] {r.status_code}: {r.text[:150]}")
        except Exception as e:
            st.caption(f"⚠️ Groq [{model}] error: {e}")
            continue
    return None

def tts(text, voice_id):
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": EL_KEY, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_monolingual_v1",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=20
        )
        return r.content if r.status_code == 200 else None
    except: return None

def scribe(audio_bytes):
    try:
        r = requests.post("https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": EL_KEY},
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            data={"model_id": "scribe_v1"}, timeout=30)
        if r.status_code == 200:
            return r.json().get("text","").strip()
    except: pass
    return None

def play(audio_bytes, label=""):
    if not audio_bytes: return
    st.markdown('<div class="voice-pulse"></div>', unsafe_allow_html=True)
    b64 = base64.b64encode(audio_bytes).decode()
    if label:
        st.markdown(f'<div class="vtag">🔊 {label}</div>', unsafe_allow_html=True)
    streamlit.components.v1.html(
        f'<audio autoplay style="display:none"><source src="data:audio/mpeg;base64,{b64}" type="audio/mpeg"></audio>',
        height=0
    )

def play_queue(items):
    clips, labels = [], []
    for audio_bytes, label in items:
        if not audio_bytes: continue
        clips.append(base64.b64encode(audio_bytes).decode())
        labels.append(label or "")
    if not clips: return
    for label in labels:
        if label:
            st.markdown(f'<div class="vtag">🔊 {label}</div>', unsafe_allow_html=True)
    js_array = "[" + ",".join(f'"{c}"' for c in clips) + "]"
    streamlit.components.v1.html(f"""
    <script>
    (function(){{
        var clips = {js_array}, i = 0;
        function playNext() {{
            if (i >= clips.length) return;
            var a = new Audio("data:audio/mpeg;base64," + clips[i++]);
            a.onended = playNext; a.onerror = playNext;
            a.play().catch(playNext);
        }}
        playNext();
    }})();
    </script>
    """, height=0)

# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="VocalClaw", page_icon="🎙️", layout="centered", initial_sidebar_state="collapsed")
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:ital,wght@0,300;0,400;0,500;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap');

*,*::before,*::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ────────────────────────────────────────────────────
   CINEMATIC BACKGROUND — Unsplash image + dark overlay
   This is the ONLY method that reliably works on
   Streamlit Cloud (no CORS, no CSP issues).
──────────────────────────────────────────────────── */
.stApp {
    background:
        linear-gradient(180deg,
            rgba(3,3,14,0.78) 0%,
            rgba(3,3,18,0.88) 60%,
            rgba(3,3,14,0.95) 100%),
        url("https://images.unsplash.com/photo-1534796636912-3b95b3ab5986?w=1920&q=85&auto=format&fit=crop")
        center center / cover no-repeat fixed !important;
}

[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
section[data-testid="stSidebar"] {
    background: transparent !important;
}

.block-container { max-width: 700px !important; padding: 0 1.5rem 6rem !important; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(167,139,250,0.25); border-radius: 2px; }

/* ── PARTICLES + CURSOR GLOW (position:fixed within markdown iframe) ── */
#vc-canvas {
    position: fixed;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    pointer-events: none;
    z-index: 9997;
}
#vc-cursor {
    position: fixed;
    width: 260px; height: 260px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(167,139,250,0.18) 0%, transparent 68%);
    pointer-events: none;
    transform: translate(-50%, -50%);
    z-index: 9998;
    left: 50vw; top: 50vh;
    transition: left 0.05s linear, top 0.05s linear;
}

/* ── HERO ── */
.hero {
    text-align: center; padding: 4rem 0 2.5rem; position: relative;
    animation: heroUp 1s cubic-bezier(0.16,1,0.3,1) both;
}
@keyframes heroUp {
    from { opacity: 0; transform: translateY(32px); }
    to   { opacity: 1; transform: translateY(0); }
}
.hero-eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(167,139,250,0.08); border: 1px solid rgba(167,139,250,0.22);
    color: #A78BFA !important; font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.55rem; letter-spacing: 0.22em; padding: 5px 18px;
    border-radius: 2px; text-transform: uppercase; margin-bottom: 1.8rem;
}
.hero-name {
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: clamp(5.5rem, 16vw, 9rem);
    letter-spacing: 0.05em; line-height: 0.85;
    background: linear-gradient(155deg, #ffffff 5%, rgba(185,155,255,1) 50%, rgba(100,215,255,0.9) 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    margin-bottom: 0.6rem;
    filter: drop-shadow(0 0 100px rgba(167,139,250,0.35));
}
.hero-line {
    width: 40px; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(167,139,250,0.55), transparent);
    margin: 1.2rem auto;
}
.hero-sub {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.58rem; letter-spacing: 0.24em;
    color: rgba(255,255,255,0.22) !important; text-transform: uppercase; margin-bottom: 3rem;
}

/* ── STATS ── */
.stats { display: flex; justify-content: center; gap: 3.5rem; margin-bottom: 3.5rem; }
.stat-n { font-family: 'Bebas Neue', sans-serif !important; font-size: 2.8rem; letter-spacing: 0.04em; display: block; line-height: 1; }
.stat-l { font-family: 'JetBrains Mono', monospace !important; font-size: 0.5rem; letter-spacing: 0.18em; color: rgba(255,255,255,0.18) !important; text-transform: uppercase; display: block; margin-top: 4px; }

/* ── AGENT CARDS ── */
.agents { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin-bottom: 2.5rem; }
.agent {
    background: rgba(8,8,28,0.6);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 1.2rem 0.6rem 1.1rem;
    text-align: center; position: relative; overflow: hidden;
    transition: all 0.3s cubic-bezier(0.16,1,0.3,1);
    cursor: default;
    backdrop-filter: blur(24px) saturate(1.5);
    -webkit-backdrop-filter: blur(24px) saturate(1.5);
    box-shadow: 0 4px 28px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.04);
}
.agent::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; border-radius: 14px 14px 0 0; }
.agent.aria::before { background: linear-gradient(90deg, transparent, #A78BFA, transparent); }
.agent.rex::before  { background: linear-gradient(90deg, transparent, #38BDF8, transparent); }
.agent.lex::before  { background: linear-gradient(90deg, transparent, #34D399, transparent); }
.agent.max::before  { background: linear-gradient(90deg, transparent, #FB923C, transparent); }
.agent-glow { position: absolute; top: -20px; left: 50%; transform: translateX(-50%); width: 80px; height: 80px; border-radius: 50%; filter: blur(28px); opacity: 0.1; transition: opacity 0.3s; }
.agent:hover { background: rgba(15,15,40,0.75); border-color: rgba(255,255,255,0.14); transform: translateY(-5px); box-shadow: 0 16px 48px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.07); }
.agent:hover .agent-glow { opacity: 0.45; }
.agent-icon { font-size: 1.5rem; display: block; margin-bottom: 0.5rem; position: relative; z-index: 1; }
.agent-name { font-family: 'Inter', sans-serif !important; font-weight: 600; font-size: 0.9rem; display: block; position: relative; z-index: 1; }
.agent-role { font-family: 'JetBrains Mono', monospace !important; font-size: 0.48rem; color: rgba(255,255,255,0.22) !important; letter-spacing: 0.14em; text-transform: uppercase; display: block; margin-top: 3px; position: relative; z-index: 1; }
.agent-tagline { font-family: 'Inter', sans-serif !important; font-style: italic; font-size: 0.6rem; color: rgba(255,255,255,0.14) !important; display: block; margin-top: 5px; position: relative; z-index: 1; }

.sec { font-family: 'JetBrains Mono', monospace !important; font-size: 0.55rem; letter-spacing: 0.22em; text-transform: uppercase; color: rgba(255,255,255,0.18) !important; display: block; margin-bottom: 0.5rem; }

/* ── BUTTONS ── */
.stButton > button {
    background: rgba(8,8,28,0.5) !important; color: rgba(255,255,255,0.4) !important;
    border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
    font-size: 0.8rem !important; padding: 0.6rem 1rem !important;
    letter-spacing: 0.01em !important;
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: rgba(167,139,250,0.1) !important;
    border-color: rgba(167,139,250,0.3) !important;
    color: #C4B5FD !important;
    transform: translateY(-2px) !important;
}
button[kind="primary"] {
    background: linear-gradient(135deg, #5B21B6 0%, #3730A3 100%) !important;
    color: #fff !important; border: none !important; border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important; font-weight: 600 !important;
    font-size: 0.88rem !important; padding: 0.64rem 1.4rem !important;
    box-shadow: 0 0 0 1px rgba(91,33,182,0.5), 0 4px 28px rgba(91,33,182,0.3) !important;
    transition: all 0.2s ease !important;
}
button[kind="primary"]:hover {
    box-shadow: 0 0 0 1px rgba(91,33,182,0.8), 0 8px 40px rgba(91,33,182,0.5) !important;
    transform: translateY(-2px) !important;
}

.mode-pill {
    border-radius: 8px; padding: 0.6rem 1rem; text-align: center;
    font-family: 'JetBrains Mono', monospace !important; font-size: 0.62rem;
    letter-spacing: 0.1em; margin-bottom: 1.6rem; border: 1px solid;
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
}

/* ── TEXTAREA ── */
.stTextArea textarea {
    background: rgba(8,8,28,0.55) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important; color: #EEEBf8 !important;
    font-family: 'Inter', sans-serif !important; font-size: 0.92rem !important;
    padding: 1rem !important; line-height: 1.68 !important; resize: none !important;
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
}
.stTextArea textarea:focus {
    border-color: rgba(167,139,250,0.4) !important;
    box-shadow: 0 0 0 3px rgba(167,139,250,0.08) !important; outline: none !important;
}
.stTextArea textarea::placeholder { color: rgba(255,255,255,0.13) !important; }
.stTextArea label { display: none !important; }

.stSelectbox > div > div {
    background: rgba(8,8,28,0.55) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important; color: rgba(255,255,255,0.5) !important;
    font-family: 'Inter', sans-serif !important; font-size: 0.84rem !important;
    backdrop-filter: blur(12px);
}
.stSelectbox svg { fill: rgba(255,255,255,0.22) !important; }
.stSelectbox label { color: rgba(255,255,255,0.18) !important; font-family: 'JetBrains Mono', monospace !important; font-size: 0.55rem !important; letter-spacing: 0.18em; text-transform: uppercase; }

/* ── RESPONSE CARDS ── */
.route { background: rgba(167,139,250,0.05); border: 1px solid rgba(167,139,250,0.14); border-radius: 8px; padding: 0.6rem 1rem; margin: 0.8rem 0; font-family: 'JetBrains Mono', monospace !important; font-size: 0.65rem; color: rgba(255,255,255,0.35) !important; letter-spacing: 0.08em; text-align: center; }
.rcard { border-radius: 12px; padding: 1.25rem 1.4rem; margin: 0.7rem 0; position: relative; overflow: hidden; backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); }
.rcard::before { content: ''; position: absolute; top: 0; left: 0; width: 2px; height: 100%; }
.rcard.aria { background: rgba(167,139,250,0.07); border: 1px solid rgba(167,139,250,0.14); } .rcard.aria::before { background: linear-gradient(180deg, #A78BFA, transparent); }
.rcard.rex  { background: rgba(56,189,248,0.07);  border: 1px solid rgba(56,189,248,0.14);  } .rcard.rex::before  { background: linear-gradient(180deg, #38BDF8, transparent); }
.rcard.lex  { background: rgba(52,211,153,0.07);  border: 1px solid rgba(52,211,153,0.14);  } .rcard.lex::before  { background: linear-gradient(180deg, #34D399, transparent); }
.rcard.max  { background: rgba(251,146,60,0.07);  border: 1px solid rgba(251,146,60,0.14);  } .rcard.max::before  { background: linear-gradient(180deg, #FB923C, transparent); }
.rcard-hd { font-family: 'JetBrains Mono', monospace !important; font-size: 0.6rem; font-weight: 500; letter-spacing: 0.14em; margin-bottom: 0.6rem; display: flex; align-items: center; gap: 8px; }
.rcard-hd.aria { color: #A78BFA !important; } .rcard-hd.rex { color: #38BDF8 !important; } .rcard-hd.lex { color: #34D399 !important; } .rcard-hd.max { color: #FB923C !important; }
.rcard-dot { width: 5px; height: 5px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.rcard-dot.aria { background: #A78BFA; } .rcard-dot.rex { background: #38BDF8; } .rcard-dot.lex { background: #34D399; } .rcard-dot.max { background: #FB923C; }
.rcard-body { font-family: 'Inter', sans-serif !important; font-size: 0.92rem; line-height: 1.78; color: rgba(238,235,248,0.82) !important; }

/* ── VOICE PULSE ── */
.voice-pulse {
    position: fixed; bottom: 100px; left: 50%;
    transform: translateX(-50%);
    width: 90px; height: 90px; border-radius: 50%;
    background: radial-gradient(circle, rgba(167,139,250,0.55), rgba(167,139,250,0.05));
    animation: vcpulse 1.4s ease-in-out infinite; z-index: 10000;
    box-shadow: 0 0 50px rgba(167,139,250,0.35);
}
@keyframes vcpulse {
    0%   { transform: translateX(-50%) scale(0.6); opacity: 0.9; }
    50%  { transform: translateX(-50%) scale(1.5); opacity: 0.1; }
    100% { transform: translateX(-50%) scale(0.6); opacity: 0.9; }
}

.vtag { display: inline-flex; align-items: center; gap: 5px; background: rgba(52,211,153,0.06); border: 1px solid rgba(52,211,153,0.16); color: #6EE7B7 !important; font-family: 'JetBrains Mono', monospace !important; font-size: 0.56rem; padding: 3px 10px; border-radius: 3px; letter-spacing: 0.1em; margin: 0.65rem 0 0.2rem; }
.tx { background: rgba(56,189,248,0.05); border: 1px solid rgba(56,189,248,0.12); border-radius: 8px; padding: 0.65rem 0.9rem; margin: 0.5rem 0; font-family: 'Inter', sans-serif !important; font-size: 0.87rem; color: rgba(238,235,248,0.5) !important; font-style: italic; }
.tx-lbl { font-family: 'JetBrains Mono', monospace !important; font-size: 0.54rem; color: #38BDF8 !important; letter-spacing: 0.12em; margin-bottom: 3px; display: block; }
.council { background: linear-gradient(135deg, rgba(251,146,60,0.06), rgba(167,139,250,0.06)); border: 1px solid rgba(251,146,60,0.16); border-radius: 10px; padding: 0.9rem 1.2rem; text-align: center; font-family: 'JetBrains Mono', monospace !important; font-size: 0.65rem; color: #FB923C !important; letter-spacing: 0.12em; margin-bottom: 0.8rem; }
.hist { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 0.55rem 0.85rem; margin-bottom: 0.3rem; display: flex; align-items: center; gap: 0.7rem; }
.hist-a { font-family: 'JetBrains Mono', monospace !important; font-size: 0.54rem; letter-spacing: 0.12em; min-width: 58px; }
.hist-q { font-family: 'Inter', sans-serif !important; font-size: 0.8rem; color: rgba(238,235,248,0.28) !important; font-style: italic; }
.mic-lbl { font-family: 'JetBrains Mono', monospace !important; font-size: 0.55rem; letter-spacing: 0.2em; text-transform: uppercase; color: rgba(255,255,255,0.16) !important; margin-bottom: 0.4rem; display: block; }
.footer { text-align: center; margin-top: 4rem; padding-top: 1.5rem; border-top: 1px solid rgba(255,255,255,0.05); }
.footer-t { font-family: 'JetBrains Mono', monospace !important; font-size: 0.54rem; color: rgba(255,255,255,0.12) !important; letter-spacing: 0.14em; line-height: 2.4; }
.footer-t a { color: rgba(167,139,250,0.35) !important; text-decoration: none; margin: 0 0.5rem; }
#MainMenu, footer, header, .stDeployButton { display: none !important; }
</style>

<!-- ── PARTICLES + CURSOR GLOW ──
     position:fixed within this markdown context overlays the whole viewport ── -->
<canvas id="vc-canvas"></canvas>
<div id="vc-cursor"></div>

<script>
(function() {
    var canvas = document.getElementById('vc-canvas');
    var cursor = document.getElementById('vc-cursor');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var W, H;

    function resize() {
        W = canvas.width  = window.innerWidth;
        H = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    // Cursor tracking
    document.addEventListener('mousemove', function(e) {
        cursor.style.left = e.clientX + 'px';
        cursor.style.top  = e.clientY + 'px';
    });

    // Build particles
    var pts = [];
    for (var i = 0; i < 90; i++) {
        pts.push({
            x:  Math.random() * window.innerWidth,
            y:  Math.random() * window.innerHeight,
            r:  Math.random() * 1.6 + 0.25,
            vy: -(Math.random() * 0.55 + 0.15),
            vx: (Math.random() - 0.5) * 0.12,
            o:  Math.random() * 0.45 + 0.08
        });
    }

    function draw() {
        ctx.clearRect(0, 0, W, H);
        pts.forEach(function(p) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(167,139,250,' + p.o + ')';
            ctx.fill();
            p.x += p.vx;
            p.y += p.vy;
            if (p.y < -4)    { p.y = H + 4; p.x = Math.random() * W; }
            if (p.x < -4)    { p.x = W + 4; }
            if (p.x > W + 4) { p.x = -4; }
        });
        requestAnimationFrame(draw);
    }
    draw();
})();
</script>
""", unsafe_allow_html=True)

# ── STATE ──────────────────────────────────────────────────────────────────────
if "history" not in st.session_state: st.session_state.history = []
if "mode"    not in st.session_state: st.session_state.mode = "solo"

# ── HERO ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div class="hero-eyebrow">⚡ ElevenLabs × Groq × AirClaw &nbsp;·&nbsp; Agentic Summer Buildathon</div>
  <div class="hero-name">VocalClaw</div>
  <div class="hero-line"></div>
  <div class="hero-sub">Voice-In &nbsp;·&nbsp; Voice-Out &nbsp;·&nbsp; Multi-Agent &nbsp;·&nbsp; $0 LLM Cost</div>
  <div class="stats">
    <div><span class="stat-n" style="color:#A78BFA">4</span><span class="stat-l">Agents</span></div>
    <div><span class="stat-n" style="color:#38BDF8">4</span><span class="stat-l">Voices</span></div>
    <div><span class="stat-n" style="color:#34D399">$0</span><span class="stat-l">LLM Cost</span></div>
    <div><span class="stat-n" style="color:#FB923C">∞</span><span class="stat-l">Queries</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── AGENTS ─────────────────────────────────────────────────────────────────────
def agent_card(name, info):
    return (
        '<div class="agent ' + info['cls'] + '">'
        '<div class="agent-glow" style="background:' + info['accent'] + '"></div>'
        '<span class="agent-icon">' + info['emoji'] + '</span>'
        '<span class="agent-name" style="color:' + info['color'] + '">' + name + '</span>'
        '<span class="agent-role">' + info['role'] + '</span>'
        '<span class="agent-tagline">' + info['tagline'] + '</span>'
        '</div>'
    )

agents_html = '<div class="agents">' + ''.join(agent_card(n, i) for n, i in AGENTS.items()) + '</div>'
st.markdown(agents_html, unsafe_allow_html=True)

# ── MODE ───────────────────────────────────────────────────────────────────────
st.markdown('<span class="sec">Mode</span>', unsafe_allow_html=True)
mc1, mc2 = st.columns(2)
with mc1:
    if st.button("🎯  Solo — One Expert Answers", use_container_width=True):
        st.session_state.mode = "solo"
with mc2:
    if st.button("⚡  Council — All 4 Voices Debate", use_container_width=True):
        st.session_state.mode = "council"

if st.session_state.mode == "solo":
    st.markdown('<div class="mode-pill" style="background:rgba(167,139,250,0.06);border-color:rgba(167,139,250,0.18);color:#C4B5FD;">🎯 SOLO MODE — Best agent answers in their voice</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="mode-pill" style="background:rgba(251,146,60,0.06);border-color:rgba(251,146,60,0.18);color:#FDBA74;">⚡ COUNCIL MODE — All 4 voices answer sequentially</div>', unsafe_allow_html=True)

# ── MIC ────────────────────────────────────────────────────────────────────────
st.markdown('<span class="mic-lbl">🎤 Voice Input</span>', unsafe_allow_html=True)
audio_in = st.audio_input("mic", label_visibility="collapsed")

transcript = None
if audio_in:
    with st.spinner("Scribe transcribing..."):
        transcript = scribe(audio_in.getvalue())
    if transcript:
        st.markdown(f'<div class="tx"><span class="tx-lbl">SCRIBE TRANSCRIPT</span>{transcript}</div>', unsafe_allow_html=True)
    else:
        st.caption("Transcription failed — type below instead.")

# ── INPUT ──────────────────────────────────────────────────────────────────────
question = st.text_area("q", value=transcript or "",
    placeholder="Try: 'Explain IPC Section 302'  ·  'Write a Python scraper'  ·  'What caused the 2008 crash'",
    height=95, label_visibility="collapsed")

c1, c2, c3 = st.columns([3, 1.2, 0.7])
with c1: ask = st.button("⚡  Ask VocalClaw", use_container_width=True, type="primary")
with c2: pick = st.selectbox("Agent", ["Auto"] + list(AGENTS.keys()))
with c3:
    if st.button("🗑️", use_container_width=True):
        st.session_state.history = []; st.rerun()

# ── LOGIC ──────────────────────────────────────────────────────────────────────
q = question.strip()

if ask and q:
    chosen = pick if pick != "Auto" else detect(q)
    ctx = " | ".join([f"{h['agent']}: {h['text'][:70]}" for h in st.session_state.history[-3:]])

    if st.session_state.mode == "solo":
        agent = AGENTS[chosen]; cls = agent["cls"]

        if pick == "Auto" and chosen != "Aria":
            st.markdown('<div class="route">🧠 Aria routing → <strong style="color:' + agent["accent"] + '">' + agent["emoji"] + ' ' + chosen + '</strong> · ' + agent["role"] + '</div>', unsafe_allow_html=True)
            with st.spinner("Aria announcing..."):
                ha = tts(f"Routing you to {chosen}, our {agent['role']}.", AGENTS["Aria"]["voice_id"])
            play(ha, f"Aria → {chosen}")

        with st.spinner(f"{chosen} thinking..."):
            text = groq_call(chosen, q, ctx)

        if text:
            st.markdown(
                '<div class="rcard ' + cls + '">'
                '<div class="rcard-hd ' + cls + '"><span class="rcard-dot ' + cls + '"></span>' + chosen.upper() + ' — ' + agent['role'].upper() + '</div>'
                '<div class="rcard-body">' + text + '</div>'
                '</div>',
                unsafe_allow_html=True
            )
            with st.spinner(f"ElevenLabs: {chosen}'s voice..."):
                audio = tts(text, agent["voice_id"])
            play(audio, f"Speaking as {chosen}")
            st.session_state.history.append({"q": q, "agent": chosen, "text": text})
        else:
            st.error("All Groq models failed — see ⚠️ details above.")

    else:
        st.markdown('<div class="council">⚡ COUNCIL IN SESSION — all agents respond, then voices play in order</div>', unsafe_allow_html=True)

        ia_text = f"The council is now in session. All four agents will share their perspective on: {q}"
        council_texts = []
        council_data = []

        for name, agent in AGENTS.items():
            with st.spinner(f"{name} thinking..."):
                text = groq_call(name, f"From your perspective as {agent['role']}, give a sharp 2-sentence take on: {q}", ctx)
            if text:
                st.markdown(
                    '<div class="rcard ' + agent['cls'] + '">'
                    '<div class="rcard-hd ' + agent['cls'] + '"><span class="rcard-dot ' + agent['cls'] + '"></span>' + name.upper() + ' — ' + agent['role'].upper() + '</div>'
                    '<div class="rcard-body">' + text + '</div>'
                    '</div>',
                    unsafe_allow_html=True
                )
                council_texts.append(f"{name}: {text}")
                council_data.append((name, agent, text))

        syn = None
        if council_texts:
            with st.spinner("Aria synthesizing..."):
                syn = groq_call("Aria", f"In 2 sentences, give one final synthesized insight: {' | '.join(council_texts)}")
            if syn:
                st.markdown(
                    '<div class="rcard aria" style="border-color:rgba(167,139,250,0.22) !important">'
                    '<div class="rcard-hd aria"><span class="rcard-dot aria"></span>ARIA — SYNTHESIS</div>'
                    '<div class="rcard-body">' + syn + '</div>'
                    '</div>',
                    unsafe_allow_html=True
                )

            audio_queue = []
            with st.spinner("Generating voices — will play in sequence..."):
                ia = tts(ia_text, AGENTS["Aria"]["voice_id"])
                if ia: audio_queue.append((ia, "Aria — Opening"))
                for name, agent, text in council_data:
                    a = tts(text, agent["voice_id"])
                    if a: audio_queue.append((a, name))
                if syn:
                    syn_a = tts(syn, AGENTS["Aria"]["voice_id"])
                    if syn_a: audio_queue.append((syn_a, "Aria — Synthesis"))

            play_queue(audio_queue)
            st.session_state.history.append({"q": q, "agent": "Council", "text": " | ".join(council_texts)})

elif ask:
    st.warning("Record or type a question first!")

# ── HISTORY ────────────────────────────────────────────────────────────────────
if st.session_state.history:
    st.markdown('<span class="sec" style="margin-top:2.5rem;display:block">Session History</span>', unsafe_allow_html=True)
    for item in reversed(st.session_state.history[-5:]):
        color = AGENTS.get(item["agent"], {}).get("accent", "#888") if item["agent"] != "Council" else "#FB923C"
        st.markdown(
            '<div class="hist"><span class="hist-a" style="color:' + color + '">' + item["agent"].upper() + '</span>'
            '<span class="hist-q">"' + item["q"] + '"</span></div>',
            unsafe_allow_html=True
        )

# ── FOOTER ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer"><div class="footer-t">
  ELEVENLABS SCRIBE + TTS &nbsp;·&nbsp; GROQ LLAMA-3 &nbsp;·&nbsp; AGENTIC SUMMER BUILDATHON 2025
  <br>
  <a href="https://github.com/nickzsche21/VocalClaw_11Labs">GitHub ↗</a>
  <a href="https://elevenlabs.io">ElevenLabs ↗</a>
  <a href="https://groq.com">Groq ↗</a>
  <a href="https://jurixoneai.com">JurixAI ↗</a>
</div></div>
""", unsafe_allow_html=True)
