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
    """Play a single audio clip (solo mode)."""
    if not audio_bytes: return
    b64 = base64.b64encode(audio_bytes).decode()
    if label:
        st.markdown(f'<div class="vtag">🔊 {label}</div>', unsafe_allow_html=True)
    streamlit.components.v1.html(
        f'<audio autoplay style="display:none"><source src="data:audio/mpeg;base64,{b64}" type="audio/mpeg"></audio>',
        height=0
    )

def play_queue(items):
    """Play a list of (audio_bytes, label) sequentially — one after another via JS onended chain."""
    clips = []
    labels = []
    for audio_bytes, label in items:
        if not audio_bytes: continue
        clips.append(base64.b64encode(audio_bytes).decode())
        labels.append(label or "")
    if not clips: return

    # Show all labels
    for label in labels:
        if label:
            st.markdown(f'<div class="vtag">🔊 {label}</div>', unsafe_allow_html=True)

    # Build JS array of base64 clips and chain via onended
    js_array = "[" + ",".join(f'"{c}"' for c in clips) + "]"
    html = f"""
    <script>
    (function(){{
        var clips = {js_array};
        var i = 0;
        function playNext() {{
            if (i >= clips.length) return;
            var a = new Audio("data:audio/mpeg;base64," + clips[i++]);
            a.onended = playNext;
            a.onerror = playNext;
            a.play().catch(playNext);
        }}
        playNext();
    }})();
    </script>
    """
    streamlit.components.v1.html(html, height=0)

st.set_page_config(page_title="VocalClaw", page_icon="🎙️", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:ital,wght@0,300;0,400;0,500;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
.stApp{background:#06060E !important;background-image:radial-gradient(ellipse 90% 60% at 15% 10%,rgba(167,139,250,0.055) 0%,transparent 60%),radial-gradient(ellipse 70% 50% at 85% 85%,rgba(56,189,248,0.04) 0%,transparent 55%),radial-gradient(ellipse 50% 40% at 50% 50%,rgba(52,211,153,0.025) 0%,transparent 65%) !important;}
.block-container{max-width:700px !important;padding:0 1.5rem 6rem !important}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(167,139,250,0.2);border-radius:2px}
.hero{text-align:center;padding:4rem 0 2.5rem;position:relative}
.hero-eyebrow{display:inline-flex;align-items:center;gap:8px;background:rgba(167,139,250,0.08);border:1px solid rgba(167,139,250,0.2);color:#A78BFA !important;font-family:'JetBrains Mono',monospace !important;font-size:0.55rem;letter-spacing:0.22em;padding:5px 16px;border-radius:2px;text-transform:uppercase;margin-bottom:1.8rem;}
.hero-name{font-family:'Bebas Neue',sans-serif !important;font-size:clamp(5rem,15vw,8.5rem);letter-spacing:0.06em;line-height:0.85;background:linear-gradient(160deg,#ffffff 15%,rgba(167,139,250,0.9) 52%,rgba(56,189,248,0.85) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:0.6rem;filter:drop-shadow(0 0 60px rgba(167,139,250,0.15));}
.hero-line{width:40px;height:1px;background:linear-gradient(90deg,transparent,rgba(167,139,250,0.4),transparent);margin:1.2rem auto;}
.hero-sub{font-family:'JetBrains Mono',monospace !important;font-size:0.58rem;letter-spacing:0.22em;color:rgba(255,255,255,0.18) !important;text-transform:uppercase;margin-bottom:3rem;}
.stats{display:flex;justify-content:center;gap:3.5rem;margin-bottom:3.5rem}
.stat-n{font-family:'Bebas Neue',sans-serif !important;font-size:2.8rem;letter-spacing:0.04em;display:block;line-height:1;}
.stat-l{font-family:'JetBrains Mono',monospace !important;font-size:0.5rem;letter-spacing:0.18em;color:rgba(255,255,255,0.18) !important;text-transform:uppercase;display:block;margin-top:4px;}
.agents{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:2.5rem}
.agent{background:rgba(255,255,255,0.018);border:1px solid rgba(255,255,255,0.055);border-radius:12px;padding:1.1rem 0.6rem 1rem;text-align:center;position:relative;overflow:hidden;transition:border-color 0.2s,background 0.2s;cursor:default;}
.agent::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;border-radius:12px 12px 0 0;}
.agent.aria::before{background:#A78BFA}.agent.rex::before{background:#38BDF8}.agent.lex::before{background:#34D399}.agent.max::before{background:#FB923C}
.agent-glow{position:absolute;top:-30px;left:50%;transform:translateX(-50%);width:60px;height:60px;border-radius:50%;filter:blur(20px);opacity:0.15;transition:opacity 0.2s;}
.agent:hover{background:rgba(255,255,255,0.028);border-color:rgba(255,255,255,0.1)}.agent:hover .agent-glow{opacity:0.28}
.agent-icon{font-size:1.4rem;display:block;margin-bottom:0.4rem;position:relative;z-index:1}
.agent-name{font-family:'Inter',sans-serif !important;font-weight:600;font-size:0.88rem;display:block;position:relative;z-index:1;}
.agent-role{font-family:'JetBrains Mono',monospace !important;font-size:0.5rem;color:rgba(255,255,255,0.22) !important;letter-spacing:0.12em;text-transform:uppercase;display:block;margin-top:2px;position:relative;z-index:1;}
.agent-tagline{font-family:'Inter',sans-serif !important;font-style:italic;font-size:0.62rem;color:rgba(255,255,255,0.15) !important;display:block;margin-top:4px;position:relative;z-index:1;}
.sec{font-family:'JetBrains Mono',monospace !important;font-size:0.55rem;letter-spacing:0.22em;text-transform:uppercase;color:rgba(255,255,255,0.18) !important;display:block;margin-bottom:0.5rem;}
.stButton>button{background:rgba(255,255,255,0.02) !important;color:rgba(255,255,255,0.38) !important;border:1px solid rgba(255,255,255,0.06) !important;border-radius:8px !important;font-family:'Inter',sans-serif !important;font-weight:500 !important;font-size:0.8rem !important;padding:0.6rem 1rem !important;transition:all 0.15s ease !important;letter-spacing:0.01em !important;}
.stButton>button:hover{background:rgba(167,139,250,0.07) !important;border-color:rgba(167,139,250,0.22) !important;color:#C4B5FD !important;}
.mode-pill{border-radius:8px;padding:0.6rem 1rem;text-align:center;font-family:'JetBrains Mono',monospace !important;font-size:0.62rem;letter-spacing:0.1em;margin-bottom:1.6rem;border:1px solid;}
.stTextArea textarea{background:rgba(255,255,255,0.02) !important;border:1px solid rgba(255,255,255,0.07) !important;border-radius:10px !important;color:#EEEBf8 !important;font-family:'Inter',sans-serif !important;font-size:0.92rem !important;padding:1rem !important;line-height:1.68 !important;resize:none !important;}
.stTextArea textarea:focus{border-color:rgba(167,139,250,0.3) !important;box-shadow:0 0 0 3px rgba(167,139,250,0.05) !important;outline:none !important;}
.stTextArea textarea::placeholder{color:rgba(255,255,255,0.13) !important}.stTextArea label{display:none !important}
button[kind="primary"]{background:linear-gradient(135deg,#5B21B6 0%,#3730A3 100%) !important;color:#fff !important;border:none !important;border-radius:8px !important;font-family:'Inter',sans-serif !important;font-weight:600 !important;font-size:0.88rem !important;padding:0.64rem 1.4rem !important;box-shadow:0 0 0 1px rgba(91,33,182,0.5),0 4px 24px rgba(91,33,182,0.22) !important;letter-spacing:0.01em !important;}
button[kind="primary"]:hover{box-shadow:0 0 0 1px rgba(91,33,182,0.7),0 6px 32px rgba(91,33,182,0.38) !important;transform:translateY(-1px) !important;}
.stSelectbox>div>div{background:rgba(255,255,255,0.02) !important;border:1px solid rgba(255,255,255,0.07) !important;border-radius:8px !important;color:rgba(255,255,255,0.5) !important;font-family:'Inter',sans-serif !important;font-size:0.84rem !important;}
.stSelectbox svg{fill:rgba(255,255,255,0.22) !important}.stSelectbox label{color:rgba(255,255,255,0.18) !important;font-family:'JetBrains Mono',monospace !important;font-size:0.55rem !important;letter-spacing:0.18em;text-transform:uppercase;}
.route{background:rgba(167,139,250,0.04);border:1px solid rgba(167,139,250,0.12);border-radius:8px;padding:0.6rem 1rem;margin:0.8rem 0;font-family:'JetBrains Mono',monospace !important;font-size:0.65rem;color:rgba(255,255,255,0.32) !important;letter-spacing:0.08em;text-align:center;}
.rcard{border-radius:12px;padding:1.25rem 1.4rem;margin:0.7rem 0;position:relative;overflow:hidden;}
.rcard::before{content:'';position:absolute;top:0;left:0;width:2px;height:100%;}
.rcard.aria{background:rgba(167,139,250,0.04);border:1px solid rgba(167,139,250,0.1);}.rcard.aria::before{background:linear-gradient(180deg,#A78BFA,transparent);}
.rcard.rex{background:rgba(56,189,248,0.04);border:1px solid rgba(56,189,248,0.1);}.rcard.rex::before{background:linear-gradient(180deg,#38BDF8,transparent);}
.rcard.lex{background:rgba(52,211,153,0.04);border:1px solid rgba(52,211,153,0.1);}.rcard.lex::before{background:linear-gradient(180deg,#34D399,transparent);}
.rcard.max{background:rgba(251,146,60,0.04);border:1px solid rgba(251,146,60,0.1);}.rcard.max::before{background:linear-gradient(180deg,#FB923C,transparent);}
.rcard-hd{font-family:'JetBrains Mono',monospace !important;font-size:0.6rem;font-weight:500;letter-spacing:0.14em;margin-bottom:0.6rem;display:flex;align-items:center;gap:8px;}
.rcard-hd.aria{color:#A78BFA !important}.rcard-hd.rex{color:#38BDF8 !important}.rcard-hd.lex{color:#34D399 !important}.rcard-hd.max{color:#FB923C !important}
.rcard-dot{width:5px;height:5px;border-radius:50%;display:inline-block;flex-shrink:0;}
.rcard-dot.aria{background:#A78BFA}.rcard-dot.rex{background:#38BDF8}.rcard-dot.lex{background:#34D399}.rcard-dot.max{background:#FB923C}
.rcard-body{font-family:'Inter',sans-serif !important;font-size:0.92rem;line-height:1.78;color:rgba(238,235,248,0.75) !important;}
.vtag{display:inline-flex;align-items:center;gap:5px;background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.14);color:#6EE7B7 !important;font-family:'JetBrains Mono',monospace !important;font-size:0.56rem;padding:3px 10px;border-radius:3px;letter-spacing:0.1em;margin:0.65rem 0 0.2rem;}
.tx{background:rgba(56,189,248,0.04);border:1px solid rgba(56,189,248,0.1);border-radius:8px;padding:0.65rem 0.9rem;margin:0.5rem 0;font-family:'Inter',sans-serif !important;font-size:0.87rem;color:rgba(238,235,248,0.48) !important;font-style:italic;}
.tx-lbl{font-family:'JetBrains Mono',monospace !important;font-size:0.54rem;color:#38BDF8 !important;letter-spacing:0.12em;margin-bottom:3px;display:block;}
.council{background:linear-gradient(135deg,rgba(251,146,60,0.05),rgba(167,139,250,0.05));border:1px solid rgba(251,146,60,0.14);border-radius:10px;padding:0.9rem 1.2rem;text-align:center;font-family:'JetBrains Mono',monospace !important;font-size:0.65rem;color:#FB923C !important;letter-spacing:0.12em;margin-bottom:0.8rem;}
.hist{background:rgba(255,255,255,0.012);border:1px solid rgba(255,255,255,0.04);border-radius:8px;padding:0.55rem 0.85rem;margin-bottom:0.3rem;display:flex;align-items:center;gap:0.7rem;}
.hist-a{font-family:'JetBrains Mono',monospace !important;font-size:0.54rem;letter-spacing:0.12em;min-width:58px;}
.hist-q{font-family:'Inter',sans-serif !important;font-size:0.8rem;color:rgba(238,235,248,0.28) !important;font-style:italic;}
.mic-lbl{font-family:'JetBrains Mono',monospace !important;font-size:0.55rem;letter-spacing:0.2em;text-transform:uppercase;color:rgba(255,255,255,0.16) !important;margin-bottom:0.4rem;display:block;}
.footer{text-align:center;margin-top:4rem;padding-top:1.5rem;border-top:1px solid rgba(255,255,255,0.04);}
.footer-t{font-family:'JetBrains Mono',monospace !important;font-size:0.54rem;color:rgba(255,255,255,0.12) !important;letter-spacing:0.14em;line-height:2.4;}
.footer-t a{color:rgba(167,139,250,0.3) !important;text-decoration:none;margin:0 0.5rem;}
#MainMenu,footer,header,.stDeployButton{display:none !important}
</style>
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
with c2: pick = st.selectbox("Agent", ["Auto"]+list(AGENTS.keys()))
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

        # ── Step 1: Generate ALL text first (show cards immediately) ──
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

            # ── Step 2: Generate ALL audio ──
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

            # ── Step 3: ONE iframe, JS chains them via onended ──
            play_queue(audio_queue)
            st.session_state.history.append({"q": q, "agent": "Council", "text": " | ".join(council_texts)})

elif ask:
    st.warning("Record or type a question first!")

# ── HISTORY ────────────────────────────────────────────────────────────────────
if st.session_state.history:
    st.markdown('<span class="sec" style="margin-top:2.5rem;display:block">Session History</span>', unsafe_allow_html=True)
    for item in reversed(st.session_state.history[-5:]):
        color = AGENTS.get(item["agent"],{}).get("accent","#888") if item["agent"]!="Council" else "#FB923C"
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
