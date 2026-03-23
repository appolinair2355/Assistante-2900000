"""
Bot Userbot — Sossou Kouamé Apollinaire
Multi-IA | Secrétariat | Organisation | Programme | Mode Furtif | Heure Bénin
"""
import os, re, json, time, asyncio, logging, threading, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

BENIN_TZ = timezone(timedelta(hours=1))

def benin_now() -> datetime:   return datetime.now(BENIN_TZ)
def benin_str(dt=None) -> str: return (dt or benin_now()).strftime("%d/%m/%Y %H:%M")
def benin_time() -> str:       return benin_now().strftime("%H:%M")

AI_META = {
    "groq":      {"name": "🟢 Groq — Llama 3.3 70B",       "model": "llama-3.3-70b-versatile"},
    "openai":    {"name": "🔵 OpenAI — GPT-4o Mini",        "model": "gpt-4o-mini"},
    "anthropic": {"name": "🟠 Anthropic — Claude 3 Haiku",  "model": "claude-3-haiku-20240307"},
    "gemini":    {"name": "🔴 Google — Gemini 2.0 Flash",   "model": "gemini-2.0-flash"},
    "mistral":   {"name": "🟣 Mistral AI — Small",          "model": "mistral-small-latest"},
}
AI_LIST = list(AI_META.keys())

CONFIG_FILE  = "config.json"
SESSION_FILE = "session.txt"
SECRETARY_FILE = "secretary.json"

DEFAULT_CONFIG = {
    "credentials": {
        "telegram_api_id":   "",
        "telegram_api_hash":  "",
        "bot_token":          "",
        "telegram_session":   "",
        "admin_id":           "1190237801"
    },
    # Quotas & délais
    "daily_quota":        200,
    "quota_used_today":   0,
    "quota_date":         str(date.today()),
    "delay_seconds":      30,       # Délai avant réponse nouveau contact
    "reply_delay_seconds":10,       # Délai réponse contact connu
    # Modes
    "auto_reply_enabled": True,
    "stealth_mode":        True,    # True = répond comme Sossou lui-même
    # IA (aucune clé pré-configurée — l'admin les ajoute via /menu → 🤖 Fournisseurs IA)
    "active_ai":   "gemini",
    "ai_providers": {
        k: {"keys": [], "model": v["model"]}
        for k, v in AI_META.items()
    },
    # Données
    "daily_program":      [],
    "reminders":          [],
    "requests":           [],
    "baccara_strategies": [],
    "knowledge_base": [
        "Je m'appelle Sossou Kouamé Apollinaire, je suis développeur professionnel basé au Bénin.",
        "Je propose des formations sur le jeu Baccara 1xbet : 90 dollars — Formation complète avec stratégies et techniques gagnantes.",
        "Je crée des bots Telegram personnalisés avec hébergement inclus : 30 dollars — Bot clé en main.",
        "Je propose des stratégies professionnelles pour Baccara 1xbet : 50 dollars — Testée et efficace.",
        "Mon numéro WhatsApp : +22995501564"
    ]
}


def load_config() -> dict:
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("quota_date") != str(date.today()):
            cfg["quota_used_today"] = 0
            cfg["quota_date"] = str(date.today())
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        cfg.setdefault("credentials", DEFAULT_CONFIG["credentials"].copy())
        cfg.setdefault("ai_providers", DEFAULT_CONFIG["ai_providers"].copy())
        cfg.setdefault("reminders", [])
        cfg.setdefault("requests", [])
        cfg.setdefault("baccara_strategies", [])
        cfg.setdefault("stealth_mode", True)
        cfg.setdefault("active_ai", "gemini")
        cfg.setdefault("reply_delay_seconds", 10)
        cfg.setdefault("daily_quota", 200)
        # Nettoyer champs obsolètes
        cfg.pop("groq_api_key", None)
        cfg.pop("ai_model", None)
        cfg.pop("secretary_notes", None)
        if not isinstance(cfg.get("daily_program"), list):
            old = cfg.get("daily_program", "")
            cfg["daily_program"] = [old] if old else []
        for k in AI_LIST:
            cfg["ai_providers"].setdefault(k, DEFAULT_CONFIG["ai_providers"][k].copy())
            pdata = cfg["ai_providers"][k]
            # Migration ancien format "key" → "keys" (liste)
            if "key" in pdata and "keys" not in pdata:
                old_key = pdata.pop("key", "")
                pdata["keys"] = [old_key] if old_key else []
            pdata.setdefault("keys", [])
            pdata.pop("key", None)           # supprimer l'ancien champ s'il reste
            pdata.pop("quota_used", None)    # nettoyage champs obsolètes
            pdata.pop("quota_date", None)
        # Migration clé groq legacy
        legacy = cfg.get("groq_api_key") or cfg.get("credentials", {}).get("groq_api_key", "")
        if legacy:
            groq_keys = cfg["ai_providers"].setdefault("groq", {}).setdefault("keys", [])
            if legacy not in groq_keys:
                groq_keys.append(legacy)
        save_config(cfg)
        return cfg
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def save_sec_log(sec_log: dict):
    """Sauvegarde sec_log sur disque (clés en str pour JSON)."""
    try:
        data = {str(k): v for k, v in sec_log.items()}
        with open(SECRETARY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"save_sec_log: {e}")


def load_sec_log() -> dict:
    """Charge sec_log depuis le disque (clés reconverties en int)."""
    try:
        if Path(SECRETARY_FILE).exists():
            with open(SECRETARY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.warning(f"load_sec_log: {e}")
    return {}


def _get(cfg, env_key, cfg_path, default=""):
    return os.environ.get(env_key) or cfg.get("credentials", {}).get(cfg_path) or default


# ═══════════════════════════════════════════════════════════════════════════════
#  MULTI-IA : VÉRIFICATION & APPELS
# ═══════════════════════════════════════════════════════════════════════════════

def _http(url, payload, headers):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


# ── Quota tracking multi-clés (en mémoire) ─────────────────────────────────────
_quota_exhausted: dict = {}   # {(provider, idx): timestamp}
# Délais de retry selon le type d'erreur :
# rate limit (429) = court (90s), quota/crédits épuisés = long (1h)
RATE_LIMIT_RESET_SECS = 90      # Gemini/Groq rate limit → retry après 90s
QUOTA_RESET_SECS      = 3600    # Crédits épuisés → retry après 1h

def _is_quota_ok(provider: str, idx: int) -> bool:
    ts, reset = _quota_exhausted.get((provider, idx), (None, QUOTA_RESET_SECS))
    return ts is None or (time.time() - ts) > reset

def _mark_quota_exhausted(provider: str, idx: int, is_rate_limit: bool = False):
    reset = RATE_LIMIT_RESET_SECS if is_rate_limit else QUOTA_RESET_SECS
    _quota_exhausted[(provider, idx)] = (time.time(), reset)
    label = "limite de fréquence" if is_rate_limit else "quota/crédits épuisés"
    logger.warning(f"⚠️ {label} {provider}[{idx}] — retry dans {reset}s")

def _is_quota_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in (
        "429", "quota", "rate limit", "rate_limit",
        "resource exhausted", "too many requests", "exceeded"
    ))

def _is_rate_limit_error(e: Exception) -> bool:
    """Distingue les rate limits temporaires (429 RPM) des quotas épuisés (crédits)."""
    msg = str(e).lower()
    is_429 = "429" in msg or "too many requests" in msg or "rate limit" in msg or "rate_limit" in msg
    is_quota = "quota" in msg or "resource exhausted" in msg or "exceeded your" in msg or "billing" in msg
    return is_429 and not is_quota


def verify_key(provider, api_key, model) -> tuple[bool, str]:
    # Vérification du format de la clé avant d'appeler l'API
    fmt_ok = {
        "groq":      api_key.startswith("gsk_"),
        "openai":    api_key.startswith(("sk-", "sk-proj-")),
        "anthropic": api_key.startswith("sk-ant-"),
        "gemini":    len(api_key) > 20,
        "mistral":   len(api_key) > 20,
    }
    if not fmt_ok.get(provider, True):
        return False, f"❌ Format de clé incorrect pour {provider}"

    # Gemini : ne pas faire d'appel test — la limite de fréquence (15 req/min) déclenche
    # systématiquement un 429 même sur une clé neuve. On valide seulement le format.
    if provider == "gemini":
        return True, (
            f"✅ Clé Gemini enregistrée — format valide.\n"
            f"Modèle : `{model}`\n"
            f"_La clé sera testée automatiquement au premier message reçu._"
        )

    try:
        if provider == "groq":
            c = Groq(api_key=api_key)
            c.chat.completions.create(model=model,
                messages=[{"role":"user","content":"Hi"}], max_tokens=5)
            return True, f"✅ Clé valide — Modèle : `{model}`"
        elif provider == "openai":
            r = _http("https://api.openai.com/v1/chat/completions",
                {"model": model, "messages": [{"role":"user","content":"Hi"}], "max_tokens": 5},
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
            return True, f"✅ Clé valide — Modèle : `{model}`\nTokens test : {r.get('usage',{}).get('total_tokens','?')}"
        elif provider == "anthropic":
            r = _http("https://api.anthropic.com/v1/messages",
                {"model": model, "max_tokens": 5, "messages": [{"role":"user","content":"Hi"}]},
                {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
            return True, f"✅ Clé valide — Modèle : `{model}`"
        elif provider == "mistral":
            r = _http("https://api.mistral.ai/v1/chat/completions",
                {"model": model, "messages": [{"role":"user","content":"Hi"}], "max_tokens": 5},
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
            return True, f"✅ Clé valide — Modèle : `{model}`"
    except Exception as e:
        err = str(e)
        # 429 : deux cas différents
        is_rate_lim = "429" in err or "too many" in err.lower() or "rate limit" in err.lower()
        is_quota    = "quota" in err.lower() or "resource exhausted" in err.lower() or "billing" in err.lower()
        if is_rate_lim and not is_quota:
            return True, (
                f"✅ Clé acceptée — limite de fréquence temporaire (normal).\n"
                f"La clé fonctionnera dans quelques secondes automatiquement.\n"
                f"_Aucune action requise._"
            )
        if is_rate_lim or is_quota:
            return True, (
                f"⚠️ Clé acceptée — quota/crédits épuisés sur votre compte.\n"
                f"Rechargez votre compte {provider.capitalize()} ou créez une nouvelle clé.\n"
                f"`{err[:120]}`"
            )
        if "404" in err or "not found" in err.lower():
            return False, (
                f"❌ Modèle introuvable (404).\n"
                f"Le modèle `{model}` n'existe pas ou n'est pas disponible dans votre région.\n"
                f"Essayez de changer le modèle via ⚙️ Paramètres IA."
            )
        if any(k in err.lower() for k in ("401","403","unauthorized","invalid_api_key","authentication","expired","invalid_key","api_key_invalid")):
            return False, f"❌ Clé invalide ou expirée — vérifiez sur le tableau de bord {provider.capitalize()}\n`{err[:150]}`"
        return False, f"❌ Erreur inattendue\n`{err[:150]}`"
    return False, "Fournisseur inconnu"


async def ai_call(provider, api_key, model, system_prompt, messages,
                  max_tokens=400, temperature=0.80) -> str:
    loop = asyncio.get_event_loop()
    def _do():
        all_msgs = [{"role":"system","content":system_prompt}] + messages
        if provider == "groq":
            c = Groq(api_key=api_key)
            r = c.chat.completions.create(model=model, messages=all_msgs,
                max_tokens=max_tokens, temperature=temperature)
            return r.choices[0].message.content.strip()
        elif provider == "openai":
            r = _http("https://api.openai.com/v1/chat/completions",
                {"model":model,"messages":all_msgs,"max_tokens":max_tokens,"temperature":temperature},
                {"Authorization":f"Bearer {api_key}","Content-Type":"application/json"})
            return r["choices"][0]["message"]["content"].strip()
        elif provider == "anthropic":
            user_msgs = [m for m in messages if m["role"] in ("user","assistant")]
            r = _http("https://api.anthropic.com/v1/messages",
                {"model":model,"system":system_prompt,"messages":user_msgs,"max_tokens":max_tokens},
                {"x-api-key":api_key,"anthropic-version":"2023-06-01","Content-Type":"application/json"})
            return r["content"][0]["text"].strip()
        elif provider == "gemini":
            parts = [{"role":"user" if m["role"]=="user" else "model",
                      "parts":[{"text":m["content"]}]} for m in messages]
            r = _http(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                {"system_instruction":{"parts":[{"text":system_prompt}]},"contents":parts,
                 "generationConfig":{"maxOutputTokens":max_tokens,"temperature":temperature}},
                {"Content-Type":"application/json"})
            return r["candidates"][0]["content"]["parts"][0]["text"].strip()
        elif provider == "mistral":
            r = _http("https://api.mistral.ai/v1/chat/completions",
                {"model":model,"messages":all_msgs,"max_tokens":max_tokens,"temperature":temperature},
                {"Authorization":f"Bearer {api_key}","Content-Type":"application/json"})
            return r["choices"][0]["message"]["content"].strip()
        raise ValueError(f"Fournisseur inconnu: {provider}")
    return await loop.run_in_executor(None, _do)


# ═══════════════════════════════════════════════════════════════════════════════
#  PROMPTS IA
# ═══════════════════════════════════════════════════════════════════════════════

SESSION_TIMEOUT = 3600

def _moment():
    h = benin_now().hour
    if 5 <= h < 12: return "matin"
    if 12 <= h < 14: return "midi"
    if 14 <= h < 18: return "après-midi"
    if 18 <= h < 22: return "soirée"
    return "nuit"

def _greeting():
    return {"matin":"Bonjour","midi":"Bonne journée","après-midi":"Bon après-midi",
            "soirée":"Bonsoir","nuit":"Bonsoir"}.get(_moment(),"Bonjour")

STEALTH_RULE = """
RÈGLES ABSOLUES (à ne jamais enfreindre) :
• Tu ES Sossou Kouamé Apollinaire — parle en 1ère personne (JE, MON, MA, MES…)
• JAMAIS de mention d'"assistante", "bot", "IA" ou "je suis absent"
• Si on demande si tu es un bot → "Non, mon téléphone répond automatiquement 😄"
• Si la question est TROP PERSONNELLE → réponds UNIQUEMENT : "Un instant stp 😊"
• Réponds dans la langue de l'interlocuteur, 1-3 phrases MAX, ton naturel et humain
• INTERDICTION ABSOLUE de parler de tes services ou activités si la personne n'en parle pas — attends qu'elle pose une question ou montre un intérêt explicite
• Si la personne dit "salut", tu réponds "Salut ! Comment tu vas ?" rien de plus
• Si elle dit "bien et toi ?", tu réponds "Bien merci !" rien de plus
• Tu suis le rythme et le sujet de la conversation — tu ne dévies jamais vers un pitch commercial sans y être invité"""

NORMAL_RULE = """
RÈGLES :
• Tu es l'assistante de Sossou Kouamé Apollinaire
• 1ère personne assistante, chaleureuse et naturelle
• Ne parle des services de M. Sossou QUE si la personne le demande explicitement
• Si question trop personnelle → "Un instant stp 😊 M. Sossou vous répond bientôt."
• Langue de l'interlocuteur, 1-3 phrases max, suit le rythme de la conversation"""


def build_prompt(contact_type: str, config: dict, style: dict = None,
                  projects_ctx: str = "", away_mode: bool = False,
                  away_history: str = "") -> str:
    kb = "\n".join(f"• {x}" for x in config["knowledge_base"])
    progs = config.get("daily_program", [])
    prog_blk = ("Programme du jour de Sossou :\n" + "\n".join(f"  - {p}" for p in progs)) if progs else ""
    moment = _moment()
    time_tips = {
        "matin": "Demande comment s'est passée sa nuit.",
        "midi": "Demande s'il a déjà mangé.",
        "après-midi": "Demande comment se passe sa journée.",
        "soirée": "Demande comment s'est passée sa journée.",
        "nuit": "Souhaite une bonne nuit.",
    }
    stealth = config.get("stealth_mode", True)
    rules = STEALTH_RULE if stealth else NORMAL_RULE

    # Bloc style d'écriture avec ce contact
    style_block = ""
    if style:
        formality  = style.get("formality", "")
        tone       = style.get("tone", "")
        emojis     = style.get("uses_emojis", False)
        phrases    = style.get("typical_phrases", [])
        style_block = (
            f"\nSTYLE D'ÉCRITURE avec cette personne (reproduis-le exactement) :\n"
            f"• Ton : {formality} / {tone}\n"
            f"• Emojis : {'oui' if style.get('uses_emojis') else 'non'}\n"
            + (f"• Expressions typiques : {', '.join(phrases[:4])}\n" if phrases else "")
        )

    # Bloc contexte projets en cours
    proj_block = f"\nCONTEXTE PROJETS EN COURS avec cette personne :\n{projects_ctx}\n" \
                 if projects_ctx else ""

    # La knowledge base : disponible en référence, ne jamais pousser proactivement
    kb_ref = (
        f"\nSERVICES QUE TU PROPOSES (à mentionner SEULEMENT si la personne en parle ou le demande) :\n{kb}\n"
    )

    # Stratégies Baccara : à partager UNIQUEMENT si demande explicite, et UNE seule à la fois
    strats = config.get("baccara_strategies", [])
    baccara_block = ""
    if strats:
        strat_lines = "\n".join(
            f"  Stratégie {i} — {s['name']} : {s['description']}"
            for i, s in enumerate(strats, 1)
        )
        baccara_block = (
            f"\nSTRATÉGIES BACCARA DISPONIBLES :\n{strat_lines}\n\n"
            f"RÈGLE : Ne partage ces stratégies QUE si la personne demande explicitement "
            f"une stratégie Baccara. Dans ce cas, donne-lui UNE SEULE stratégie "
            f"(la plus adaptée ou en commençant par la Stratégie 1). "
            f"Ne donne JAMAIS toutes les stratégies à la fois. "
            f"Si elle veut en savoir plus, elle demandera.\n"
        )

    # ── MODE ABSENT : le bot prend le contrôle total ──────────────────────────
    if away_mode:
        hist_block = (
            f"\nHISTORIQUE RÉCENT DE CETTE CONVERSATION (tes messages = SOSSOU) :\n{away_history}\n"
            if away_history else ""
        )
        return (
            f"Tu ES Sossou Kouamé Apollinaire. Tu réponds à sa place pendant son ABSENCE.\n"
            f"Il ne sait pas encore que tu as répondu — il verra ça à son retour.\n\n"
            f"MISSION : Répondre exactement comme Sossou le ferait :\n"
            f"• Reproduis parfaitement son style, son ton, ses expressions habituelles\n"
            f"• Réponds naturellement et humainement — jamais de réponses robotiques\n"
            f"• Si quelqu'un parle d'argent ou de budget limité pour un bot/service :\n"
            f"  → Note mentalement et réponds 'Ok, on voit ça ensemble bientôt 😊'\n"
            f"• Si quelqu'un dit 'n'oublie pas' ou 'rappelle-toi' → 'C'est noté ✍️'\n"
            f"• Si question trop technique ou sensible → 'Ok je reviens vers toi bientôt 😊'\n"
            f"• Réponds en {moment}\n"
            f"{hist_block}{style_block}{proj_block}{kb_ref}{baccara_block}\n{rules}"
        )

    if contact_type == "first":
        return (
            f"C'est le TOUT PREMIER message de cette personne. "
            f"Commence par '{_greeting()} !' puis réponds naturellement à ce qu'elle dit. "
            f"Ne parle PAS de tes services ni de Baccara dans ce premier message — "
            f"laisse d'abord la personne s'exprimer.\n"
            f"{prog_blk}{style_block}{proj_block}{kb_ref}{baccara_block}\n{rules}"
        )
    if contact_type == "returning":
        return (
            f"Cette personne revient après une pause. Re-salue-la naturellement en {moment}.\n"
            f"{time_tips.get(moment,'')}\n"
            f"Ne parle de tes services ou stratégies QUE si elle en parle en premier.\n"
            f"{prog_blk}{style_block}{proj_block}{kb_ref}{baccara_block}\n{rules}"
        )
    # ongoing : suit le fil exact de la discussion
    return (
        f"Continue la conversation naturellement. Réponds UNIQUEMENT à ce que la personne "
        f"vient de dire. Ne dévie jamais vers tes services, Baccara ou activités sauf si "
        f"elle en parle explicitement.\n"
        f"{style_block}{proj_block}{kb_ref}{baccara_block}\n{rules}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  HEALTH SERVER
# ═══════════════════════════════════════════════════════════════════════════════

def start_health_server():
    import json as _json
    _start_time = time.time()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            uptime_s = int(time.time() - _start_time)
            h, m, s  = uptime_s // 3600, (uptime_s % 3600) // 60, uptime_s % 60
            body = _json.dumps({
                "status":  "ok",
                "service": "assistance-sossou",
                "uptime":  f"{h:02d}h{m:02d}m{s:02d}s",
                "time_benin": datetime.now(timezone(timedelta(hours=1))).strftime("%d/%m/%Y %H:%M"),
            }, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass

    port = int(os.environ.get("PORT", 5000))
    threading.Thread(
        target=HTTPServer(("0.0.0.0", port), H).serve_forever,
        daemon=True
    ).start()
    logger.info(f"Health-check HTTP sur le port {port}")


# ═══════════════════════════════════════════════════════════════════════════════
#  MODE SETUP
# ═══════════════════════════════════════════════════════════════════════════════

def run_setup_bot(BOT_TOKEN, API_ID, API_HASH, OWNER_ID, PHONE_NUMBER):
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import SessionPasswordNeededError

    auth = {}

    async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("❌ Accès refusé."); return
        phone = PHONE_NUMBER
        if context.args:
            raw = context.args[0].strip()
            phone = raw if raw.startswith("+") else "+"+raw
        await update.message.reply_text(f"📤 Envoi du code au *{phone}*...", parse_mode="Markdown")
        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            auth[update.effective_user.id] = {"client":client,"phone":phone,
                "phone_code_hash":result.phone_code_hash,"awaiting_2fa":False}
            await update.message.reply_text("✅ Code envoyé !\n\nTapez `aa<code>` ex: `aa12345`",
                parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

    async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid not in auth: return
        txt = (update.message.text or "").strip()
        if not txt.lower().startswith("aa"): return
        code = txt[2:].strip()
        if not code:
            await update.message.reply_text("❌ Code vide. Ex: `aa12345`", parse_mode="Markdown"); return
        s = auth[uid]
        try:
            await s["client"].sign_in(s["phone"], code=code, phone_code_hash=s["phone_code_hash"])
        except SessionPasswordNeededError:
            s["awaiting_2fa"] = True
            await update.message.reply_text("🔐 2FA requis. Tapez `pass <motdepasse>`", parse_mode="Markdown"); return
        except Exception as e:
            await update.message.reply_text(f"❌ {e}"); return
        await _finish(s["client"], update, uid)

    async def handle_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        s = auth.get(uid, {})
        if not s.get("awaiting_2fa"): return
        txt = (update.message.text or "").strip()
        if not txt.lower().startswith("pass "): return
        try:
            await s["client"].sign_in(password=txt[5:].strip())
            await _finish(s["client"], update, uid)
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

    async def _finish(client, update, uid):
        import sys
        ss = client.session.save()
        await client.disconnect()
        auth.pop(uid, None)
        Path(SESSION_FILE).write_text(ss)
        cfg = load_config()
        cfg.setdefault("credentials", {})["telegram_session"] = ss
        save_config(cfg)
        await update.message.reply_text(
            "✅ *CONNEXION RÉUSSIE !*\n\n🔄 Redémarrage en mode USERBOT dans 5s...\n\n"
            "Tapez /menu dans vos Messages Sauvegardés Telegram.",
            parse_mode="Markdown")
        # ── Envoyer la session en morceaux (utile pour Render) ──────────────
        try:
            header = (
                "🔑 *VOTRE SESSION TELEGRAM*\n\n"
                "⚠️ *Copiez cette chaîne et ajoutez-la dans Render*\n"
                "Variable : `TELEGRAM_SESSION`\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            await update.message.reply_text(header, parse_mode="Markdown")
            # Envoyer la session par morceaux de 3000 caractères max
            chunk_size = 3000
            for i in range(0, len(ss), chunk_size):
                part = ss[i:i+chunk_size]
                num  = (i // chunk_size) + 1
                total = (len(ss) + chunk_size - 1) // chunk_size
                label = f"*Partie {num}/{total}* :\n`{part}`" if total > 1 else f"`{part}`"
                await update.message.reply_text(label, parse_mode="Markdown")
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "✅ Copiez la chaîne ci-dessus → Render → Environment → `TELEGRAM_SESSION`\n\n"
                "_Ainsi votre session survivra à chaque redéploiement._",
                parse_mode="Markdown")
        except Exception as _e:
            logger.warning(f"Impossible d'envoyer la session dans le chat : {_e}")
        # ── Redémarrage ──────────────────────────────────────────────────────
        def _restart():
            time.sleep(5)
            os.execv(sys.executable, [sys.executable]+sys.argv)
        threading.Thread(target=_restart, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("connect", cmd_connect))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^pass "), handle_pass))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^aa"), handle_code))
    app.run_polling(drop_pending_updates=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  MODE USERBOT
# ═══════════════════════════════════════════════════════════════════════════════

def run_userbot(API_ID, API_HASH, BOT_TOKEN, GROQ_API_KEY, SESSION_STRING, OWNER_ID):
    from telethon import TelegramClient, events, Button
    from telethon.sessions import StringSession

    # ── État global ─────────────────────────────────────────────────────────────
    config          = load_config()
    sec_log: dict   = load_sec_log()   # Chargé depuis le disque, persistant entre redémarrages
    conv_history    = {}               # {user_id: [messages]}
    pending_tasks   = {}               # {chat_id: asyncio.Task}
    known_users     = set(sec_log.keys())   # Contacts déjà connus (restaurés depuis le disque)
    last_msg_time   = {}
    stopped_chats   = set()
    # ── Mode Absent ─────────────────────────────────────────────────────────────
    away_mode       = [False]          # [0] = bool — le bot prend le contrôle total
    away_mode_start = [0.0]            # [0] = timestamp du début du mode absent
    away_log: dict  = {}               # {uid: {"name":str,"msgs":[],"bot_replies":[]}}
    logger.info(f"📂 Secrétariat chargé : {len(sec_log)} contacts, "
                f"{sum(len(v.get('msgs',[])) for v in sec_log.values())} messages")

    state = {
        "program_waiting":  False,
        "ai_waiting":       None,   # provider name or None
        "param_waiting":    None,   # "delay"|"replydelay"|"quota"|"addinfo"|"remind"|"addprog" or None
        "remind_text":      None,
    }

    # ── Migration clé Groq ───────────────────────────────────────────────────────
    if GROQ_API_KEY:
        groq_keys = config["ai_providers"]["groq"].setdefault("keys", [])
        if GROQ_API_KEY not in groq_keys:
            groq_keys.append(GROQ_API_KEY)
            save_config(config)

    # ── Helpers ──────────────────────────────────────────────────────────────────

    _ctrl_active  = [True]   # [False] si conflit 409 — désactive les envois locaux
    _client_ref   = [None]   # Référence partagée vers le client Telethon

    def _send_bot(text: str, parse_mode="Markdown"):
        if not _ctrl_active[0]:
            return
        try:
            payload = json.dumps({"chat_id": OWNER_ID, "text": text,
                                  "parse_mode": parse_mode}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data=payload, headers={"Content-Type":"application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10): pass
        except Exception as e:
            logger.warning(f"send_bot: {e}")

    _ai_key_alerted = [False]   # Eviter de spammer la notif "clés manquantes"

    async def notify(text: str):
        if not _ctrl_active[0]:
            return
        if BOT_TOKEN:
            await asyncio.get_event_loop().run_in_executor(None, _send_bot, text)
        else:
            # Fallback : envoyer via le userbot lui-même (Saved Messages)
            tg = _client_ref[0]
            if tg:
                try:
                    await tg.send_message("me", text, parse_mode="md")
                except Exception as e:
                    logger.warning(f"notify fallback: {e}")
            else:
                logger.debug(f"notify (client non prêt) : {text[:80]}")

    def _get_ai():
        """Retourne (provider, première_clé_valide, model) pour affichage/stats."""
        ordered = [config.get("active_ai","groq")] + [k for k in AI_LIST if k != config.get("active_ai","groq")]
        for provider in ordered:
            pdata = config["ai_providers"].get(provider, {})
            model = pdata.get("model", AI_META[provider]["model"])
            for idx, key in enumerate(pdata.get("keys", [])):
                if key and _is_quota_ok(provider, idx):
                    return provider, key, model
        return "groq", GROQ_API_KEY, "llama-3.3-70b-versatile"

    async def smart_ai_call(system_prompt: str, messages: list,
                             max_tokens: int = 400, temperature: float = 0.80) -> str:
        """Appel IA avec bascule automatique entre clés et fournisseurs si quota épuisé."""
        ordered = [config.get("active_ai","groq")] + [k for k in AI_LIST if k != config.get("active_ai","groq")]
        last_err = None
        for provider in ordered:
            pdata = config["ai_providers"].get(provider, {})
            model = pdata.get("model", AI_META[provider]["model"])
            keys  = pdata.get("keys", [])
            for idx, key in enumerate(keys):
                if not key or not _is_quota_ok(provider, idx):
                    continue
                try:
                    return await ai_call(provider, key, model, system_prompt, messages,
                                         max_tokens, temperature)
                except Exception as e:
                    if _is_quota_error(e):
                        _mark_quota_exhausted(provider, idx, is_rate_limit=_is_rate_limit_error(e))
                        last_err = e
                        continue
                    raise
        # Fallback : clé Groq intégrée si définie
        if GROQ_API_KEY:
            return await ai_call("groq", GROQ_API_KEY, "llama-3.3-70b-versatile",
                                  system_prompt, messages, max_tokens, temperature)
        raise Exception("Toutes les clés IA sont épuisées ou non configurées") from last_err

    def _check_quota() -> bool:
        today = str(date.today())
        if config.get("quota_date") != today:
            config["quota_used_today"] = 0
            config["quota_date"] = today
        if config["quota_used_today"] >= config["daily_quota"]:
            return False
        config["quota_used_today"] += 1
        save_config(config)
        return True

    def _sec_log(user_id: int, name: str, role: str, text: str):
        if not text or not text.strip():
            return
        if user_id not in sec_log:
            sec_log[user_id] = {"name": name, "msgs": []}
        # Mettre à jour le nom si plus récent
        sec_log[user_id]["name"] = name
        sec_log[user_id]["msgs"].append({
            "r": role, "t": text.strip()[:500],
            "d": benin_str()
        })
        if len(sec_log[user_id]["msgs"]) > 200:
            sec_log[user_id]["msgs"] = sec_log[user_id]["msgs"][-200:]
        # Sauvegarde persistante sur disque
        save_sec_log(sec_log)

    # ── IA réponse ────────────────────────────────────────────────────────────────

    async def get_reply(user_id: int, text: str, contact_type: str,
                        is_away: bool = False) -> str:
        if not _check_quota():
            return "Un instant stp 😊" if config.get("stealth_mode", True) else \
                   "Mon assistant a atteint son quota journalier. Je vous réponds bientôt 🙏"

        # ── Pré-charger l'historique depuis le secrétariat si conv_history est vide ──
        # Cela donne au bot le contexte des échanges précédents même après redémarrage
        if user_id not in conv_history or not conv_history[user_id]:
            stored_msgs = sec_log.get(user_id, {}).get("msgs", [])
            if stored_msgs:
                uname = sec_log[user_id].get("name", f"ID:{user_id}")
                preloaded = []
                for m in stored_msgs[-18:]:   # 18 derniers messages max
                    role    = "assistant" if m["r"] == "out" else "user"
                    prefix  = "" if role == "assistant" else f"[{uname}] "
                    content = f"{prefix}{m['t']}"
                    preloaded.append({"role": role, "content": content})
                conv_history[user_id] = preloaded
                logger.debug(f"💬 Historique pré-chargé pour {uname}: {len(preloaded)} msgs")

        hist = conv_history.setdefault(user_id, [])
        hist.append({"role":"user","content":text})
        if len(hist) > 20:
            conv_history[user_id] = hist[-20:]

        # Récupérer le style appris pour ce contact
        contact_data  = sec_log.get(user_id, {})
        style         = contact_data.get("style")
        # Construire le contexte des projets en cours avec ce contact
        projects_ctx  = ""
        last_analysis = contact_data.get("last_analysis", {})
        if last_analysis.get("has_project") and last_analysis.get("projects"):
            proj_lines = [
                f"• {p['title']} ({p.get('status','?')})"
                for p in last_analysis["projects"]
                if p.get("status") in ("en_cours", "à_démarrer")
            ]
            if proj_lines:
                projects_ctx = "\n".join(proj_lines)

        # Historique de la conversation pour le mode absent
        away_history = ""
        if is_away:
            msgs = contact_data.get("msgs", [])[-15:]
            name = contact_data.get("name", f"ID:{user_id}")
            away_history = "\n".join(
                f"[{'SOSSOU' if m['r']=='out' else name.upper()}] {m['t'][:150]}"
                for m in msgs
            )

        sys_p = build_prompt(contact_type, config, style=style, projects_ctx=projects_ctx,
                             away_mode=is_away, away_history=away_history)
        try:
            reply = await smart_ai_call(sys_p, conv_history[user_id])
            conv_history[user_id].append({"role":"assistant","content":reply})
            return reply
        except Exception as e:
            err = str(e)
            needs_alert = any(k in err.lower() for k in (
                "401","unauthorized","expired","invalid","non configurées","épuisées"
            ))
            if needs_alert and not _ai_key_alerted[0]:
                _ai_key_alerted[0] = True
                await notify(
                    "⚠️ *Aucune clé IA fonctionnelle !*\n\n"
                    "L'assistante répond 'Un instant stp' à tous les messages car aucune clé API n'est configurée.\n\n"
                    "👉 *Solution :* envoie /menu → 🤖 Fournisseurs IA → ajoute au moins une clé (Groq, Gemini, etc.)\n\n"
                    f"_Erreur : {err[:150]}_"
                )
            return "Un instant stp 😊" if config.get("stealth_mode", True) else \
                   "Je suis momentanément indisponible. Je vous réponds dès que possible 🙏"

    # ── Extracteur organisation ───────────────────────────────────────────────────

    async def extract_request(user_id: int, name: str, text: str):
        prompt = (
            f"Message reçu de : {name}\nMessage : {text}\n\n"
            "Est-ce une DEMANDE DE SERVICE ou une QUESTION nécessitant un suivi (commande, formation, bot, stratégie, prix, RDV, etc.) ?\n"
            "Réponds en JSON strict UNIQUEMENT :\n"
            '{"is_request": true, "summary": "résumé court", "category": "formation|bot|stratégie|info|autre"}\n'
            'OU {"is_request": false}'
        )
        try:
            r = await smart_ai_call(
                "Analyse de message. Réponds en JSON strict.",
                [{"role":"user","content":prompt}], max_tokens=150, temperature=0.1)
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if not m: return
            data = json.loads(m.group())
            if not data.get("is_request"): return
            req = {
                "id": int(time.time()),
                "contact": name, "contact_id": user_id,
                "text": text[:300],
                "summary": data.get("summary", text[:100]),
                "category": data.get("category", "autre"),
                "date": benin_str(),
                "status": "pending",
                "ai_suggestion": ""
            }
            config["requests"].append(req)
            save_config(config)
            logger.info(f"📋 Demande enregistrée : {req['summary']}")
        except Exception as e:
            logger.debug(f"extract_request: {e}")

    # ── Extracteur rappels (secrétariat) ──────────────────────────────────────────

    async def extract_reminder(contact_name: str, text: str):
        if len(text) < 8: return
        prompt = (
            f"Heure Bénin actuelle : {benin_str()}\n"
            f"Contact : {contact_name}\nMessage envoyé : {text}\n\n"
            "Y a-t-il une PROMESSE, ENGAGEMENT ou DEADLINE dans ce message ?\n"
            "JSON strict :\n"
            '{"has_reminder": true, "text": "...", "deadline": "YYYY-MM-DDTHH:MM ou null"}\n'
            'OU {"has_reminder": false}'
        )
        try:
            r = await smart_ai_call(
                "Analyse de promesses. Réponds en JSON strict.",
                [{"role":"user","content":prompt}], max_tokens=150, temperature=0.1)
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if not m: return
            data = json.loads(m.group())
            if not data.get("has_reminder"): return
            rem = {
                "id": int(time.time()),
                "text": data.get("text", text[:100]),
                "contact": contact_name,
                "deadline": data.get("deadline"),
                "created": benin_str(),
                "notified": False
            }
            config["reminders"].append(rem)
            save_config(config)
            logger.info(f"📝 Rappel : {rem['text']}")
        except Exception as e:
            logger.debug(f"extract_reminder: {e}")

    # ── Analyse intelligente des conversations ─────────────────────────────────────

    # Cache anti-doublon : {user_id: timestamp_dernière_analyse}
    _analysis_cache: dict = {}
    ANALYSIS_COOLDOWN = 300   # 5 min minimum entre deux analyses du même contact

    async def smart_contact_analysis(user_id: int, name: str, new_msg: str):
        """
        Analyse approfondie d'une conversation :
        • Détecte le style d'écriture de Sossou avec ce contact
        • Identifie les projets / engagements en cours
        • Envoie automatiquement au Secrétariat + Organisation si projet trouvé
        • Notifie Sossou avec un résumé actionnable
        """
        now_ts = time.time()
        if now_ts - _analysis_cache.get(user_id, 0) < ANALYSIS_COOLDOWN:
            return                          # trop tôt, on attend
        _analysis_cache[user_id] = now_ts

        history = sec_log.get(user_id, {}).get("msgs", [])
        if len(history) < 3:
            return                          # pas assez d'historique

        # Construire l'historique pour l'analyse
        conv_lines = []
        for m in history[-30:]:
            role_label = "SOSSOU" if m["r"] == "out" else name.upper()
            conv_lines.append(f"[{role_label}] {m['t']}")
        conv_text = "\n".join(conv_lines)

        prompt = f"""Analyse cette conversation entre Sossou et {name}.

HISTORIQUE :
{conv_text}

NOUVEAU MESSAGE DE {name.upper()} : {new_msg}

Réponds en JSON strict UNIQUEMENT :
{{
  "has_project": true/false,
  "projects": [
    {{
      "title": "titre court du projet",
      "status": "en_cours|à_démarrer|terminé",
      "actions_for_sossou": ["action concrète 1", "action 2"],
      "deadline": "YYYY-MM-DD ou null"
    }}
  ],
  "writing_style": {{
    "formality": "formel|semi-formel|informel|amical",
    "uses_emojis": true/false,
    "language": "français|anglais|autre",
    "typical_phrases": ["ex phrase 1", "ex phrase 2"],
    "tone": "professionnel|décontracté|enthousiaste|neutre"
  }},
  "urgent_actions": ["action urgente si applicable, sinon liste vide"],
  "notification": "1-2 phrases de résumé pour Sossou, ou null si rien d'important"
}}"""

        try:
            r = await smart_ai_call(
                "Tu es l'assistant intelligent de Sossou Kouamé Apollinaire. Analyse précise.",
                [{"role": "user", "content": prompt}],
                max_tokens=600, temperature=0.1)
            m_json = re.search(r'\{.*\}', r, re.DOTALL)
            if not m_json:
                return
            data = json.loads(m_json.group())

            # ── Sauvegarder le style + l'analyse dans sec_log ─────────────────
            if user_id not in sec_log:
                sec_log[user_id] = {"name": name, "msgs": []}
            sec_log[user_id]["style"]         = data.get("writing_style", {})
            sec_log[user_id]["last_analysis"] = data
            sec_log[user_id]["analysis_date"] = benin_str()
            logger.info(f"🔍 Analyse contact {name} : projet={data.get('has_project')}")

            # ── Si projet(s) détecté(s) → Organisation + Secrétariat ──────────
            notif_parts = []
            if data.get("has_project") and data.get("projects"):
                existing_summaries = {r["summary"] for r in config["requests"]}
                for proj in data["projects"]:
                    if proj.get("status") in ("en_cours", "à_démarrer"):
                        title = proj.get("title", "")
                        if title and title not in existing_summaries:
                            existing_summaries.add(title)
                            actions_txt = "\n".join(
                                f"• {a}" for a in proj.get("actions_for_sossou", []))
                            req = {
                                "id": int(time.time()),
                                "contact": name,
                                "contact_id": user_id,
                                "text": new_msg[:300],
                                "summary": title,
                                "category": "projet",
                                "date": benin_str(),
                                "status": "pending",
                                "ai_suggestion": actions_txt,
                                "deadline": proj.get("deadline")
                            }
                            config["requests"].append(req)
                            notif_parts.append(
                                f"📌 Projet : *{title}*\n"
                                + (f"   Actions : {actions_txt}" if actions_txt else "")
                                + (f"\n   Deadline : {proj['deadline']}" if proj.get("deadline") else "")
                            )
                            # ── Rappel si deadline ────────────────────────────
                            if proj.get("deadline"):
                                dl_str = proj["deadline"]
                                if "T" not in dl_str:
                                    dl_str += "T09:00"
                                config["reminders"].append({
                                    "id": int(time.time()) + 1,
                                    "text": f"Projet '{title}' avec {name}",
                                    "contact": name,
                                    "deadline": dl_str,
                                    "created": benin_str(),
                                    "notified": False
                                })
                if notif_parts:
                    save_config(config)

            # ── Notification à Sossou ──────────────────────────────────────────
            notification = data.get("notification")
            urgent       = data.get("urgent_actions", [])
            if notification or notif_parts or urgent:
                lines = [f"🔔 *Analyse — {name}*\n"]
                if notification:
                    lines.append(notification)
                if notif_parts:
                    lines.append("\n📂 *Nouveaux projets ajoutés à l'Organisation :*")
                    lines.extend(notif_parts)
                if urgent:
                    lines.append("\n🎯 *Actions urgentes pour vous :*")
                    lines.extend(f"  ✅ {a}" for a in urgent)
                if notif_parts:
                    lines.append("\n_Consultez /menu → 📋 Organisation_")
                await notify("\n".join(lines))

        except Exception as e:
            logger.debug(f"smart_contact_analysis({name}): {e}")

    # ── Vérificateur de rappels ────────────────────────────────────────────────────

    async def reminder_checker():
        while True:
            try:
                await asyncio.sleep(60)
                now = benin_now()
                changed = False
                for r in config.get("reminders", []):
                    if r.get("notified") or not r.get("deadline"): continue
                    try:
                        dl = datetime.fromisoformat(r["deadline"]).replace(tzinfo=BENIN_TZ)
                    except Exception: continue
                    diff = (dl - now).total_seconds() / 60
                    if diff <= 30:
                        dl_str = dl.strftime("%d/%m à %H:%M")
                        prefix = "⏰ *RAPPEL DÉPASSÉ !*" if diff <= 0 else f"⏰ *Rappel dans {int(diff)} min !*"
                        await notify(f"{prefix}\n\n👤 {r.get('contact','?')}\n📌 {r.get('text','?')}\n"
                                     f"🕐 Échéance : {dl_str} (heure Bénin)\n\n_/menu → 📝 Rappels_")
                        if diff <= 0:
                            r["notified"] = True
                        changed = True
                if changed: save_config(config)
            except Exception as e:
                logger.debug(f"reminder_checker: {e}")

    # ── Génération du rapport "Quoi de neuf" ─────────────────────────────────────

    NOUBLIE_KEYWORDS = [
        "n'oublie pas", "noublie pas", "oublie pas", "rappelle-toi", "rappelle toi",
        "souviens-toi", "souviens toi", "comme on s'est dit", "comme convenu",
        "tu te souviens", "n'oublie surtout pas", "n oublie pas"
    ]

    async def handle_noublie_pas(uid: int, name: str, text_in: str):
        """Quand quelqu'un dit 'n'oublie pas', cherche le contexte et crée une note."""
        try:
            msgs = sec_log.get(uid, {}).get("msgs", [])[-30:]
            hist_lines = "\n".join(
                f"[{'SOSSOU' if m['r']=='out' else name.upper()}] {m['t'][:200]}"
                for m in msgs
            )
            prompt = (
                f"Conversation avec {name}:\n{hist_lines}\n\n"
                f"Message actuel : '{text_in}'\n\n"
                f"La personne dit de ne pas oublier quelque chose. "
                f"Résume EN UNE PHRASE ce dont il faut se souvenir (promesse, demande, accord). "
                f"Si rien de précis n'est mentionné dans l'historique, dis 'Vérifier avec {name}'."
            )
            note = await smart_ai_call(
                "Extraction de note importante.", [{"role":"user","content":prompt}],
                max_tokens=120, temperature=0.1)

            # Ajouter dans l'organisation
            req = {
                "id": int(time.time()),
                "contact": name, "contact_id": uid,
                "text": text_in[:300],
                "summary": f"⚠️ À ne pas oublier avec {name}: {note.strip()[:150]}",
                "category": "rappel",
                "date": benin_str(),
                "status": "pending",
                "ai_suggestion": ""
            }
            config["requests"].append(req)
            save_config(config)
            # Ajouter dans away_log si mode absent
            if away_mode[0]:
                slot = away_log.setdefault(uid, {"name": name, "msgs": [], "bot_replies": [], "notes": []})
                slot.setdefault("notes", []).append(note.strip()[:200])
            await notify(
                f"📌 *Note importante créée !*\n\n"
                f"👤 {name}\n"
                f"💬 Message : _{text_in[:100]}_\n\n"
                f"📝 Note : {note.strip()[:200]}\n\n"
                f"_Ajouté dans Organisation → Demandes_"
            )
        except Exception as e:
            logger.debug(f"handle_noublie_pas: {e}")

    async def generate_briefing() -> str:
        """Génère le rapport 'Quoi de neuf' pour Sossou à son retour."""
        if not away_log:
            return "📭 Aucune conversation pendant ton absence."

        since = benin_str(datetime.fromtimestamp(away_mode_start[0], tz=BENIN_TZ)) \
                if away_mode_start[0] > 0 else "une période récente"

        sections = []
        for uid, d in away_log.items():
            name     = d.get("name", f"ID:{uid}")
            msgs     = d.get("msgs", [])
            replies  = d.get("bot_replies", [])
            notes    = d.get("notes", [])
            # Reconstruire la conversation pendant l'absence
            conv = []
            for m in msgs:
                conv.append(f"[{name.upper()}] {m['t'][:200]}")
            for r in replies:
                conv.append(f"[SOSSOU (bot)] {r['t'][:200]}")
            sections.append({
                "name": name, "uid": uid,
                "conv": "\n".join(conv[-12:]),
                "nb_msgs": len(msgs),
                "nb_replies": len(replies),
                "notes": notes
            })

        # Demander à l'IA de faire un résumé intelligent
        convs_text = ""
        for s in sections:
            convs_text += (
                f"\n=== {s['name']} ({s['nb_msgs']} msg(s) reçus, "
                f"{s['nb_replies']} réponse(s) bot) ===\n"
                f"{s['conv']}\n"
            )
            if s["notes"]:
                convs_text += f"[NOTES IMPORTANTES] {'; '.join(s['notes'])}\n"

        prompt = (
            f"Sossou vient de revenir après une absence. "
            f"Voici ce qui s'est passé depuis {since} :\n\n{convs_text}\n\n"
            f"Fais-lui un RAPPORT DE RETOUR complet et structuré :\n"
            f"1. Pour chaque personne : résume ce qu'elle voulait, l'humeur, les points importants\n"
            f"2. Ce que le bot a répondu en son nom (résumé)\n"
            f"3. Les ACTIONS URGENTES que Sossou doit faire à son retour (rappels, réponses, bots à créer, etc.)\n"
            f"4. Les opportunités détectées (budget limité, demande de service, etc.)\n\n"
            f"Ton : direct, professionnel, actionnable. Commence par les plus urgents."
        )
        ai_summary = await smart_ai_call(
            "Tu es la secrétaire personnelle de Sossou. Tu lui fais un rapport de retour.",
            [{"role":"user","content":prompt}], max_tokens=900, temperature=0.3)

        nb_total = sum(len(d.get("msgs",[])) for d in away_log.values())
        names    = ", ".join(d.get("name","?") for d in away_log.values())
        return (
            f"📬 *QUOI DE NEUF — Rapport de retour*\n"
            f"_Période : depuis {since}_\n"
            f"_Contacts : {len(away_log)} personne(s) — {names}_\n"
            f"_Messages reçus : {nb_total}_\n\n"
            f"{ai_summary[:3000]}"
        )

    # ── Coaching automatique (analyse quand Sossou est inactif) ───────────────────

    _last_sossou_activity = [time.time()]   # [0] = timestamp dernier msg sortant
    _coached_convs: dict  = {}              # {uid: timestamp dernière analyse coaching}
    COACH_IDLE_SECS  = 300     # Attendre 5 min d'inactivité avant d'analyser
    COACH_COOLDOWN   = 3600    # Ne pas re-analyser une même conv dans l'heure
    COACH_CHECK_SECS = 120     # Vérifier toutes les 2 minutes

    async def generate_coaching_report(convs_to_analyze: list) -> str:
        """Demande à l'IA d'analyser les messages sortants de Sossou et de suggérer des améliorations."""
        sections = []
        for uid, d in convs_to_analyze:
            name = d.get("name", f"ID:{uid}")
            msgs = d.get("msgs", [])
            if not msgs:
                continue
            # Construire la conversation complète
            conv_lines = []
            for m in msgs[-20:]:
                label = "SOSSOU" if m["r"] == "out" else name.upper()
                conv_lines.append(f"[{label}] {m['t'][:200]}")
            sections.append(f"=== Conversation avec {name} ===\n" + "\n".join(conv_lines))

        if not sections:
            return ""

        full_conv = "\n\n".join(sections)
        prompt = (
            f"Tu es le conseiller personnel de Sossou Kouamé Apollinaire.\n"
            f"Analyse les messages que SOSSOU a écrits dans ces conversations récentes.\n\n"
            f"{full_conv}\n\n"
            f"Pour chaque conversation, dis-lui :\n"
            f"1. Les fautes d'orthographe ou de grammaire qu'il a faites (avec la correction)\n"
            f"2. Les formulations qu'il aurait pu améliorer (montre l'original et la version améliorée)\n"
            f"3. Les opportunités commerciales qu'il a manquées (formation, bot, stratégie) — si applicable\n"
            f"4. Ce qu'il aurait dû dire différemment pour mieux conclure ou fidéliser\n\n"
            f"Sois direct, bref et actionnable. Si aucune faute ni amélioration notable, dis-le.\n"
            f"Réponds en français, format structuré avec les noms des contacts en titre."
        )
        return await smart_ai_call(
            "Tu es le conseiller personnel et coach de communication de Sossou.",
            [{"role": "user", "content": prompt}],
            max_tokens=800, temperature=0.3)

    async def coaching_checker():
        """Analyse les conversations récentes quand Sossou est inactif et envoie un rapport."""
        await asyncio.sleep(30)   # Attendre le démarrage complet
        while True:
            try:
                await asyncio.sleep(COACH_CHECK_SECS)
                idle_time = time.time() - _last_sossou_activity[0]
                if idle_time < COACH_IDLE_SECS:
                    continue   # Sossou est encore actif, on attend

                # Trouver les conversations non encore analysées ou analysées il y a longtemps
                now_ts = time.time()
                to_analyze = []
                for uid, d in list(sec_log.items()):
                    # Vérifier si Sossou a écrit dans cette conv
                    has_outgoing = any(m["r"] == "out" for m in d.get("msgs", []))
                    if not has_outgoing:
                        continue
                    last_coached = _coached_convs.get(uid, 0)
                    if now_ts - last_coached < COACH_COOLDOWN:
                        continue   # Déjà analysé récemment
                    # Prendre uniquement les convs avec activité récente (48h)
                    last_msg_ts = None
                    for m in reversed(d.get("msgs", [])):
                        try:
                            from datetime import datetime as _dt
                            last_msg_ts = _dt.strptime(m["d"], "%d/%m/%Y %H:%M")
                            break
                        except: pass
                    if last_msg_ts:
                        age_hours = (benin_now().replace(tzinfo=None) - last_msg_ts).total_seconds() / 3600
                        if age_hours > 48:
                            continue   # Trop vieux
                    to_analyze.append((uid, d))

                if not to_analyze:
                    continue

                # Limiter à 5 conversations max par rapport
                to_analyze = to_analyze[:5]

                logger.info(f"🎓 Coaching : analyse de {len(to_analyze)} conversations...")
                report = await generate_coaching_report(to_analyze)
                if not report or len(report.strip()) < 30:
                    continue

                # Marquer comme analysé
                for uid, _ in to_analyze:
                    _coached_convs[uid] = now_ts

                names = ", ".join(d.get("name","?") for _, d in to_analyze)
                await notify(
                    f"🎓 *Rapport Coaching — {len(to_analyze)} conversation(s)*\n"
                    f"_Contacts : {names}_\n\n"
                    f"{report[:3000]}\n\n"
                    f"_/menu → 📋 Secrétariat pour voir les conversations_"
                )
            except Exception as e:
                logger.debug(f"coaching_checker: {e}")

    # ── Auto-réponse ───────────────────────────────────────────────────────────────

    async def auto_reply(client, chat_id, user_id, text, contact_type,
                         force_away: bool = False):
        try:
            is_away = force_away or away_mode[0]
            # En mode absent : délai fixe 10s ; sinon délai config
            if is_away:
                await asyncio.sleep(10)
            else:
                wait = config["delay_seconds"] if contact_type in ("first","returning") \
                       else config.get("reply_delay_seconds", 5)
                await asyncio.sleep(wait)
                if not config.get("auto_reply_enabled", True): return
                if chat_id in stopped_chats: return

            reply = await get_reply(user_id, text, contact_type, is_away=is_away)
            await client.send_message(chat_id, reply)

            # Enregistrer la réponse du bot dans away_log
            if is_away:
                name = sec_log.get(user_id, {}).get("name", f"ID:{user_id}")
                slot = away_log.setdefault(user_id, {"name": name, "msgs": [], "bot_replies": []})
                slot["bot_replies"].append({
                    "t": reply[:300], "d": benin_str(), "in_msg": text[:200]
                })
                _sec_log(user_id, name, "out", reply)   # aussi dans secrétariat

        except asyncio.CancelledError: pass
        except Exception as e: logger.error(f"auto_reply: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    #  MENUS TELETHON (boutons inline)
    # ═══════════════════════════════════════════════════════════════════════════

    def mk_main_menu():
        nb_strats  = len(config.get("baccara_strategies", []))
        nb_convs   = len(sec_log)
        coach_lbl  = f"🎓 Rapport coaching ({nb_convs} convs)"
        # Bouton Mode Absent
        if away_mode[0]:
            nb_away  = len(away_log)
            away_lbl = f"✅ Bot répond à ta place — {nb_away} conv(s) | ARRÊTER"
        else:
            away_lbl = "📵 Je suis occupé — Bot répond à ma place"
        return [
            [Button.inline("📋 Organisation",  b"org"),   Button.inline("📝 Secrétariat", b"sec")],
            [Button.inline("📅 Programme",      b"prog"),  Button.inline("🤖 Fournisseurs IA", b"ai")],
            [Button.inline(f"🎲 Stratégies Baccara ({nb_strats})", b"strat")],
            [Button.inline(away_lbl,           b"away_toggle")],
            [Button.inline("📬 Quoi de neuf ?", b"quoi_de_neuf"),
             Button.inline(coach_lbl,           b"coach")],
            [Button.inline("📊 Stats & Statut", b"stats"), Button.inline("⚙️ Paramètres", b"prm")],
        ]

    def mk_org_menu():
        pending = sum(1 for r in config["requests"] if r["status"]=="pending")
        done    = sum(1 for r in config["requests"] if r["status"]=="done")
        return [
            [Button.inline(f"⏳ En attente ({pending})",     b"org_p"),
             Button.inline(f"✅ Traitées ({done})",          b"org_d")],
            [Button.inline("💡 Analyser & Proposer",        b"org_a"),
             Button.inline("🗑 Vider traitées",              b"org_c")],
            [Button.inline("🔙 Menu principal",             b"mm")],
        ]

    def mk_sec_menu():
        total    = sum(len(v["msgs"]) for v in sec_log.values())
        contacts = len(sec_log)
        with_proj = sum(1 for d in sec_log.values() if d.get("last_analysis",{}).get("has_project"))
        return [
            [Button.inline(f"📱 Contacts ({contacts}) — dont {with_proj} projets", b"sec_contacts")],
            [Button.inline(f"📚 Conversations ({total} messages)",  b"sec_c")],
            [Button.inline("💡 Analyser & Proposer solutions",      b"sec_a")],
            [Button.inline("📋 Résumé du jour (IA)",                b"sec_r")],
            [Button.inline("📝 Rappels enregistrés",                b"rem")],
            [Button.inline("🗑 Tout effacer (RAZ)",                 b"sec_wipe")],
            [Button.inline("🔙 Menu principal",                     b"mm")],
        ]

    def mk_prog_menu():
        progs = config.get("daily_program", [])
        count = len(progs)
        return [
            [Button.inline(f"📅 Voir programme ({count} tâches)", b"prog_v")],
            [Button.inline("➕ Ajouter une tâche",  b"prog_a"),
             Button.inline("🗑 Vider programme",    b"prog_c")],
            [Button.inline("🔙 Menu principal",     b"mm")],
        ]

    def mk_ai_menu():
        providers = config["ai_providers"]
        active    = config.get("active_ai","groq")
        stealth   = "🕵️ Furtif : ON" if config.get("stealth_mode",True) else "👁 Furtif : OFF"
        auto      = "✅ Auto-réponse : ON" if config.get("auto_reply_enabled",True) else "🛑 Auto-réponse : OFF"
        rows = []
        for i, k in enumerate(AI_LIST, 1):
            pdata     = providers.get(k, {})
            keys_list = [x for x in pdata.get("keys", []) if x]
            n_keys    = len(keys_list)
            has_key   = n_keys > 0
            is_act    = k == active
            icon      = "🔵" if is_act else ("✅" if has_key else "❌")
            name_short = AI_META[k]['name'].split('—')[0].strip()
            key_badge  = f" ({n_keys}🔑)" if n_keys > 1 else ""
            label      = f"{icon} {i}. {name_short}{key_badge}"
            rows.append([Button.inline(label, f"ai_{k}".encode())])
        rows.append([Button.inline(stealth, b"ai_st"), Button.inline(auto, b"ai_auto")])
        rows.append([Button.inline("🔙 Menu principal", b"mm")])
        return rows

    def mk_strat_menu():
        strats = config.get("baccara_strategies", [])
        return [
            [Button.inline(f"📋 Voir les {len(strats)} stratégie(s)", b"strat_v")],
            [Button.inline("➕ Ajouter une stratégie",                 b"strat_a")],
            [Button.inline("🔙 Menu principal",                        b"mm")],
        ]

    def text_strat_list() -> str:
        strats = config.get("baccara_strategies", [])
        if not strats:
            return (
                "🎲 *Stratégies Baccara*\n\n"
                "_Aucune stratégie enregistrée pour l'instant._\n\n"
                "Appuyez sur ➕ Ajouter pour en saisir une."
            )
        lines = [f"🎲 *Stratégies Baccara ({len(strats)})*\n"]
        for i, s in enumerate(strats, 1):
            name = s.get("name", f"Stratégie {i}")
            desc = s.get("description", "")
            lines.append(f"*{i}. {name}*\n   _{desc}_\n")
        lines.append("_Quand un contact demande une stratégie, le bot en donne une seule._")
        return "\n".join(lines)

    def mk_prm_menu():
        d  = config['delay_seconds']
        rd = config.get('reply_delay_seconds', 5)
        q  = config['daily_quota']
        qu = config['quota_used_today']
        return [
            [Button.inline(f"⏱ Délai absence : {d}s",          b"prm_d"),
             Button.inline(f"⚡ Délai réponse : {rd}s",          b"prm_r")],
            [Button.inline(f"🔢 Quota : {qu}/{q}/jour",          b"prm_q")],
            [Button.inline("📚 Base de connaissances",           b"prm_k")],
            [Button.inline("➕ Ajouter info",   b"prm_ka"),
             Button.inline("➖ Voir & supprimer", b"prm_kv")],
            [Button.inline("🔙 Menu principal", b"mm")],
        ]

    # ═══════════════════════════════════════════════════════════════════════════
    #  CONTENUS DES MENUS
    # ═══════════════════════════════════════════════════════════════════════════

    def text_org_pending() -> str:
        reqs = [r for r in config["requests"] if r["status"]=="pending"]
        if not reqs:
            return "📋 *Organisation — Demandes en attente*\n\n_Aucune demande en attente._"
        lines = [f"📋 *Organisation — {len(reqs)} demande(s) en attente*\n"]
        for i, r in enumerate(reqs, 1):
            cat = r.get("category","?")
            lines.append(
                f"*{i}.* [{r['date']}] {r['contact']}\n"
                f"   📌 {r['summary']}\n"
                f"   🏷 {cat}")
        lines.append(f"\n_Commandes : `/orgdone <n>` pour marquer comme traité_")
        return "\n".join(lines)

    def text_org_done() -> str:
        reqs = [r for r in config["requests"] if r["status"]=="done"]
        if not reqs:
            return "✅ *Organisation — Demandes traitées*\n\n_Aucune demande traitée._"
        lines = [f"✅ *Organisation — {len(reqs)} traitée(s)*\n"]
        for i, r in enumerate(reqs[-20:], 1):
            lines.append(f"*{i}.* {r['contact']} — {r['summary']} [{r['date']}]")
        return "\n".join(lines)

    def text_prog() -> str:
        progs = config.get("daily_program", [])
        if not progs:
            return "📅 *Programme du jour*\n\n_Aucune tâche enregistrée._\n\nAppuyez ➕ pour ajouter."
        lines = [f"📅 *Programme du jour — {benin_str(benin_now())[:10]}*\n"]
        for i, p in enumerate(progs, 1):
            lines.append(f"  {i}. {p}")
        return "\n".join(lines)

    def text_stats() -> str:
        used  = config["quota_used_today"]
        total = config["daily_quota"]
        pct   = int((used/total)*100) if total else 0
        st    = "✅ Active" if config.get("auto_reply_enabled",True) else "🛑 Arrêtée"
        stealth = "🕵️ ON" if config.get("stealth_mode",True) else "🔵 OFF"
        active = config.get("active_ai","groq")
        reqs_p = sum(1 for r in config["requests"] if r["status"]=="pending")
        rems   = len(config.get("reminders",[]))
        nb_conv = len(sec_log)
        nb_msgs = sum(len(v["msgs"]) for v in sec_log.values())
        ai_lines = []
        for k in AI_LIST:
            d         = config["ai_providers"].get(k, {})
            keys_list = [x for x in d.get("keys", []) if x]
            n_keys    = len(keys_list)
            s  = "✅" if n_keys > 0 else "❌"
            nb = f" ({n_keys}🔑)" if n_keys > 1 else ""
            a  = " ← ACTIF" if k==active else ""
            ai_lines.append(f"  {s} {AI_META[k]['name']}{nb}{a}")
        return (
            f"📊 *Stats — Bot Sossou*\n\n"
            f"🕐 Heure Bénin : {benin_time()}\n"
            f"🔄 Auto-réponse : {st} | Furtif : {stealth}\n"
            f"📈 Quota : {used}/{total} ({pct}%)\n"
            f"⏱ Délai : {config['delay_seconds']}s | Réponse : {config.get('reply_delay_seconds',5)}s\n"
            f"👥 Contacts : {len(known_users)}\n\n"
            f"📋 Demandes en attente : {reqs_p}\n"
            f"📝 Rappels actifs : {rems}\n"
            f"📚 Conversations : {nb_conv} contacts, {nb_msgs} messages\n\n"
            f"🤖 *IA :*\n" + "\n".join(ai_lines)
        )

    def text_contacts_list() -> str:
        """Vue de tous les contacts enregistrés avec statut d'analyse."""
        if not sec_log:
            return "📱 *Contacts enregistrés*\n\n_Aucun contact pour l'instant._"
        lines = [f"📱 *Contacts enregistrés — {len(sec_log)} contact(s)*\n"]
        for uid, d in list(sec_log.items()):
            nb_msgs = len(d.get("msgs", []))
            name    = d.get("name", f"ID:{uid}")
            last    = d["msgs"][-1]["t"][:50] if d.get("msgs") else "—"
            has_analysis = "last_analysis" in d
            has_project  = d.get("last_analysis", {}).get("has_project", False)
            style        = d.get("style", {})
            formality    = style.get("formality", "")
            ana_icon     = ("📌" if has_project else "✅") if has_analysis else "⏳"
            lines.append(
                f"{ana_icon} *{name}* — {nb_msgs} msg(s)\n"
                + (f"   Style : {formality}\n" if formality else "")
                + f"   Dernier : _{last[:50]}_\n"
            )
        lines.append("\n_Cliquez sur un contact dans le menu pour voir le détail._")
        return "\n".join(lines)

    def text_contact_detail(uid: int) -> str:
        """Détail d'un contact : historique + analyse."""
        d = sec_log.get(uid)
        if not d:
            return "❌ Contact introuvable."
        name   = d.get("name", f"ID:{uid}")
        msgs   = d.get("msgs", [])
        style  = d.get("style", {})
        ana    = d.get("last_analysis", {})
        ana_dt = d.get("analysis_date", "")

        lines = [f"👤 *{name}* — {len(msgs)} message(s)\n"]

        # Historique récent
        lines.append("📜 *Historique récent :*")
        for m in msgs[-15:]:
            r   = "➡️ Vous" if m["r"] == "out" else f"⬅️ {name}"
            lines.append(f"  [{m.get('d','')}] {r}: _{m['t'][:80]}_")

        # Style détecté
        if style:
            lines.append(f"\n🎨 *Style détecté :*")
            lines.append(f"  Ton : {style.get('formality','')} / {style.get('tone','')}")
            lines.append(f"  Emojis : {'oui' if style.get('uses_emojis') else 'non'}")
            phrases = style.get("typical_phrases", [])
            if phrases:
                lines.append(f"  Expressions : {', '.join(phrases[:3])}")

        # Projets détectés
        if ana.get("has_project") and ana.get("projects"):
            lines.append(f"\n📂 *Projets détectés* (analyse du {ana_dt}) :")
            for p in ana["projects"]:
                lines.append(f"  📌 *{p.get('title','?')}* [{p.get('status','?')}]")
                for a in p.get("actions_for_sossou", []):
                    lines.append(f"      ✅ {a}")
                if p.get("deadline"):
                    lines.append(f"      📅 Deadline : {p['deadline']}")
        elif ana:
            lines.append(f"\n_Aucun projet détecté (analysé le {ana_dt})_")

        # Actions urgentes
        urgent = ana.get("urgent_actions", [])
        if urgent:
            lines.append(f"\n🎯 *Actions urgentes :*")
            for a in urgent:
                lines.append(f"  ✅ {a}")

        return "\n".join(lines)

    def mk_sec_contacts_menu():
        """Menu avec bouton par contact pour voir le détail."""
        rows = []
        for uid, d in list(sec_log.items()):
            name = d.get("name", f"ID:{uid}")
            has_proj = d.get("last_analysis", {}).get("has_project", False)
            icon = "📌" if has_proj else "👤"
            rows.append([Button.inline(f"{icon} {name}", f"sec_ct_{uid}".encode())])
        rows.append([Button.inline("🔙 Secrétariat", b"sec")])
        return rows

    async def text_sec_analyze(client) -> str:
        if not sec_log:
            return "📝 *Secrétariat*\n\n_Aucune conversation enregistrée pour l'instant._"
        summary_parts = []
        for uid, data in list(sec_log.items())[-5:]:
            name = data["name"]
            msgs = data["msgs"][-10:]
            conv = "\n".join(f"[{m['r'].upper()}] {m['t']}" for m in msgs)
            summary_parts.append(f"Contact : {name}\n{conv}")
        all_text = "\n\n---\n\n".join(summary_parts)
        prompt = (
            f"Voici des conversations récentes de Sossou Kouamé Apollinaire :\n\n{all_text}\n\n"
            "En tant que secrétaire intelligent, analyse ces conversations et propose :\n"
            "1. Un résumé des points importants\n"
            "2. Des actions recommandées\n"
            "3. Des opportunités commerciales détectées\n"
            "4. Des réponses suggérées si nécessaire\n\n"
            "Sois concis et actionnable. Réponds en français."
        )
        try:
            return await smart_ai_call(
                "Tu es le secrétaire intelligent de Sossou Kouamé Apollinaire.",
                [{"role":"user","content":prompt}], max_tokens=600, temperature=0.5)
        except Exception as e:
            return f"❌ Erreur analyse : {e}"

    async def text_sec_resume() -> str:
        if not sec_log:
            return "📤 *Résumé du jour*\n\n_Aucune conversation aujourd'hui._"
        all_contacts = []
        for uid, data in sec_log.items():
            name = data["name"]
            nb   = len(data["msgs"])
            inc  = sum(1 for m in data["msgs"] if m["r"]=="in")
            out  = sum(1 for m in data["msgs"] if m["r"]=="out")
            last = data["msgs"][-1]["t"][:80] if data["msgs"] else ""
            all_contacts.append(f"- {name} : {nb} messages ({inc} reçus, {out} envoyés)\n  Dernier : {last}")
        contacts_text = "\n".join(all_contacts)
        prompt = (
            f"Conversations du jour de Sossou Kouamé Apollinaire :\n{contacts_text}\n\n"
            "Fais un résumé exécutif en 5-8 lignes max avec :\n"
            "• Ce qui s'est passé\n• Ce qui est urgent\n• Actions à faire"
        )
        try:
            result = await smart_ai_call(
                "Tu es le secrétaire de Sossou. Résumé exécutif.",
                [{"role":"user","content":prompt}], max_tokens=400, temperature=0.4)
            return f"📤 *Résumé du jour — {benin_str(benin_now())[:10]}*\n\n{result}"
        except Exception as e:
            return f"❌ Erreur résumé : {e}"

    async def text_org_analyze() -> str:
        reqs = [r for r in config["requests"] if r["status"]=="pending"]
        if not reqs:
            return "📋 *Analyse Organisation*\n\n_Aucune demande en attente à analyser._"
        req_text = "\n".join(
            f"- [{r['category']}] {r['contact']} : {r['summary']}" for r in reqs)
        prompt = (
            f"Sossou a {len(reqs)} demandes en attente :\n{req_text}\n\n"
            "En tant que conseiller, propose :\n"
            "1. La priorité de traitement\n"
            "2. Les actions concrètes à faire pour chaque demande\n"
            "3. Des réponses types suggérées\n"
            "4. Des opportunités commerciales\n\n"
            "Sois concis et pratique."
        )
        try:
            result = await smart_ai_call(
                "Tu es le conseiller commercial de Sossou Kouamé Apollinaire.",
                [{"role":"user","content":prompt}], max_tokens=600, temperature=0.5)
            return f"💡 *Analyse Organisation*\n\n{result}"
        except Exception as e:
            return f"❌ Erreur : {e}"

    def text_reminders() -> str:
        rems = config.get("reminders", [])
        if not rems:
            return "📝 *Rappels*\n\n_Aucun rappel enregistré._\n\n_Le secrétaire extrait automatiquement vos promesses._"
        lines = [f"📝 *Rappels ({len(rems)})*\n"]
        for i, r in enumerate(rems, 1):
            done = "✅" if r.get("notified") else "⏳"
            dl   = r.get("deadline","—")
            if dl and dl != "—":
                try:
                    dt = datetime.fromisoformat(dl).replace(tzinfo=BENIN_TZ)
                    dl = dt.strftime("%d/%m à %H:%M (Bénin)")
                except: pass
            lines.append(f"{done} *{i}.* {r.get('contact','?')}\n   📌 {r.get('text','?')}\n   🕐 {dl}")
        lines.append("\n_`/donenote <n>` | `/deletenote <n>`_")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════════════
    #  CLIENT TELETHON
    # ═══════════════════════════════════════════════════════════════════════════

    async def _main():
        try:
            client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                raise ValueError("Session non autorisée")
            _client_ref[0] = client   # rendre le client accessible à notify()
        except Exception as e:
            err = str(e)
            logger.error(f"❌ Session invalide : {e}")
            # Effacer la session invalide pour basculer en mode SETUP
            try:
                cfg2 = load_config()
                cfg2.setdefault("credentials", {})["telegram_session"] = ""
                save_config(cfg2)
                Path(SESSION_FILE).write_text("")
                logger.warning("🗑 Session effacée — passage en mode SETUP")
            except Exception: pass
            return

        # ── Chargement de l'historique Telegram au démarrage ─────────────────
        async def load_telegram_history():
            """Importe les derniers messages des conversations privées dans sec_log.
            Prudent : max 25 dialogs, 30 messages chacun, pause entre chaque."""
            await asyncio.sleep(3)   # Laisser le bot s'initialiser d'abord
            try:
                nb_dialogs = 0
                nb_msgs    = 0
                dialogs_done = 0
                async for dialog in client.iter_dialogs(limit=50):
                    if dialogs_done >= 25:
                        break          # Max 25 conversations privées
                    if not dialog.is_user:
                        continue       # ignorer groupes et canaux
                    entity = dialog.entity
                    if getattr(entity, "bot", False):
                        continue       # ignorer les bots
                    uid  = entity.id
                    name = (f"{getattr(entity,'first_name','') or ''} "
                            f"{getattr(entity,'last_name','') or ''}").strip() or f"ID:{uid}"

                    # Ne pas re-charger si déjà bien rempli (> 20 msgs)
                    existing_count = len(sec_log.get(uid, {}).get("msgs", []))
                    if existing_count >= 20:
                        known_users.add(uid)
                        dialogs_done += 1
                        continue

                    existing_texts = {m["t"] for m in sec_log.get(uid, {}).get("msgs", [])}
                    new_msgs = []
                    try:
                        async for msg in client.iter_messages(entity, limit=30):
                            if not msg.text or not msg.text.strip():
                                continue
                            role = "out" if msg.out else "in"
                            ts   = benin_str(msg.date.astimezone(BENIN_TZ) if msg.date else benin_now())
                            t    = msg.text.strip()[:500]
                            if t not in existing_texts:
                                new_msgs.append({"r": role, "t": t, "d": ts})
                                existing_texts.add(t)
                    except Exception:
                        pass   # Flood wait géré par Telethon automatiquement

                    if new_msgs:
                        new_msgs.reverse()   # Ordre chronologique
                        if uid not in sec_log:
                            sec_log[uid] = {"name": name, "msgs": []}
                        sec_log[uid]["name"] = name
                        sec_log[uid]["msgs"] = new_msgs + sec_log[uid]["msgs"]
                        sec_log[uid]["msgs"] = sec_log[uid]["msgs"][-200:]
                        nb_msgs += len(new_msgs)
                        nb_dialogs += 1

                    known_users.add(uid)
                    dialogs_done += 1
                    await asyncio.sleep(0.5)   # Pause pour éviter le flood

                if nb_dialogs > 0:
                    save_sec_log(sec_log)
                total_contacts = len(sec_log)
                total_msgs = sum(len(v.get("msgs",[])) for v in sec_log.values())
                logger.info(f"📥 Historique chargé : {nb_dialogs} nouvelles convs, "
                            f"{nb_msgs} msgs. Total : {total_contacts} contacts, {total_msgs} msgs")
            except Exception as e:
                logger.warning(f"load_telegram_history: {e}")

        asyncio.get_event_loop().create_task(load_telegram_history())
        logger.info("🔄 Chargement historique Telegram en arrière-plan...")

        # ── Messages entrants ─────────────────────────────────────────────────

        @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def on_in(event):
            sender = await event.get_sender()
            if not sender or getattr(sender,"bot",False): return
            chat_id = event.chat_id
            uid     = sender.id
            now     = time.time()
            name    = (f"{getattr(sender,'first_name','') or ''} "
                       f"{getattr(sender,'last_name','') or ''}").strip() or f"ID:{uid}"

            # Secrétariat : enregistrer le message
            text_in = event.text or ""
            _sec_log(uid, name, "in", text_in)

            first_contact = uid not in known_users
            last_time     = last_msg_time.get(uid, 0)
            is_returning  = (not first_contact) and ((now - last_time) > SESSION_TIMEOUT)
            last_msg_time[uid] = now

            if first_contact:
                contact_type = "first"
                known_users.add(uid)
                conv_history.pop(uid, None)
                # Notifier l'admin
                try:
                    await notify(
                        f"🔔 *Nouveau contact !*\n\n"
                        f"👤 {name}\n🆔 ID: {uid}\n\n"
                        f"Message : _{text_in[:100]}_\n\n"
                        f"Auto-réponse dans {config['delay_seconds']}s.")
                except: pass
            elif is_returning:
                contact_type = "returning"
                conv_history.pop(uid, None)
            else:
                contact_type = "ongoing"

            # Enregistrer dans away_log si mode absent
            if away_mode[0]:
                slot = away_log.setdefault(uid, {"name": name, "msgs": [], "bot_replies": [], "notes": []})
                slot["msgs"].append({"t": text_in[:300], "d": benin_str()})

            # Extraction de demandes (organisation) + analyse intelligente
            if text_in:
                asyncio.create_task(extract_request(uid, name, text_in))
                asyncio.create_task(smart_contact_analysis(uid, name, text_in))

            # Détection "n'oublie pas / rappelle-toi"
            text_low = text_in.lower()
            if any(kw in text_low for kw in NOUBLIE_KEYWORDS):
                asyncio.create_task(handle_noublie_pas(uid, name, text_in))

            # Annuler tâche précédente
            t = pending_tasks.get(chat_id)
            if t and not t.done(): t.cancel()

            # Mode absent → toujours répondre ; sinon vérifier auto_reply_enabled
            if away_mode[0]:
                pending_tasks[chat_id] = asyncio.create_task(
                    auto_reply(client, chat_id, uid, text_in, contact_type, force_away=True))
            elif config.get("auto_reply_enabled", True) and chat_id not in stopped_chats:
                pending_tasks[chat_id] = asyncio.create_task(
                    auto_reply(client, chat_id, uid, text_in, contact_type))

        # ── Messages sortants ──────────────────────────────────────────────────

        @client.on(events.NewMessage(outgoing=True, func=lambda e: e.is_private))
        async def on_out(event):
            text = event.text or ""
            if text.startswith("/"): return

            # Capture états en attente
            if state["param_waiting"] == "addprog" and text:
                state["param_waiting"] = None
                progs = config.setdefault("daily_program", [])
                progs.append(text.strip())
                save_config(config)
                await event.respond(f"✅ Tâche ajoutée !\n\n{text_prog()}", buttons=mk_prog_menu())
                return

            if state["param_waiting"] == "delay" and text.strip().isdigit():
                config["delay_seconds"] = int(text.strip())
                save_config(config)
                state["param_waiting"] = None
                await event.respond(f"✅ Délai absence : *{config['delay_seconds']}s*",
                                    buttons=mk_prm_menu())
                return

            if state["param_waiting"] == "replydelay" and text.strip().isdigit():
                config["reply_delay_seconds"] = int(text.strip())
                save_config(config)
                state["param_waiting"] = None
                await event.respond(f"✅ Délai réponse : *{config['reply_delay_seconds']}s*",
                                    buttons=mk_prm_menu())
                return

            if state["param_waiting"] == "quota" and text.strip().isdigit():
                config["daily_quota"] = int(text.strip())
                save_config(config)
                state["param_waiting"] = None
                await event.respond(f"✅ Quota : *{config['daily_quota']}/jour*",
                                    buttons=mk_prm_menu())
                return

            if state["param_waiting"] == "addinfo" and text:
                config["knowledge_base"].append(text.strip())
                save_config(config)
                state["param_waiting"] = None
                await event.respond(f"✅ Info ajoutée !\n_{text.strip()}_", buttons=mk_prm_menu())
                return

            if state["param_waiting"] == "addstrat" and text:
                raw = text.strip()
                # Format attendu : "Nom | Description" ou juste "Description"
                if "|" in raw:
                    nom, desc = raw.split("|", 1)
                    nom  = nom.strip()
                    desc = desc.strip()
                else:
                    # Numéro automatique si pas de nom donné
                    n = len(config.get("baccara_strategies", [])) + 1
                    nom  = f"Stratégie {n}"
                    desc = raw
                strat_obj = {"name": nom, "description": desc}
                config.setdefault("baccara_strategies", []).append(strat_obj)
                save_config(config)
                state["param_waiting"] = None
                await event.respond(
                    f"✅ Stratégie enregistrée !\n\n"
                    f"*{nom}*\n_{desc}_",
                    buttons=mk_strat_menu()
                )
                return

            if state["param_waiting"] == "remind" and text:
                if "|" in text:
                    nt, dl_t = text.split("|", 1)
                    try:
                        dl_dt = datetime.fromisoformat(dl_t.strip()).replace(tzinfo=BENIN_TZ)
                        dl_iso = dl_dt.strftime("%Y-%m-%dT%H:%M")
                    except:
                        dl_iso = dl_t.strip()
                else:
                    nt, dl_iso = text, None
                config["reminders"].append({
                    "id": int(time.time()), "text": nt.strip(), "contact": "Manuel",
                    "deadline": dl_iso, "created": benin_str(), "notified": False
                })
                save_config(config)
                state["param_waiting"] = None
                await event.respond(f"✅ Rappel ajouté !", buttons=mk_sec_menu())
                return

            if state["ai_waiting"] and text:
                provider = state["ai_waiting"]
                state["ai_waiting"] = None
                await event.delete()
                await event.respond("🔍 Vérification...")
                loop = asyncio.get_event_loop()
                model = config["ai_providers"][provider].get("model", AI_META[provider]["model"])
                ok, info = await loop.run_in_executor(None, verify_key, provider, text.strip(), model)
                if not ok:
                    await event.respond(f"❌ Clé invalide\n\n{info}", buttons=mk_ai_menu())
                else:
                    new_key = text.strip()
                    keys_list = config["ai_providers"][provider].setdefault("keys", [])
                    if new_key not in keys_list:
                        keys_list.append(new_key)
                    config["active_ai"] = provider
                    save_config(config)
                    masked   = new_key[:8]+"..."+new_key[-4:]
                    n_keys   = len(keys_list)
                    await event.respond(
                        f"✅ *{AI_META[provider]['name']}* — clé ajoutée !\n\n"
                        f"Clé : `{masked}`\n{info}\n\n"
                        f"Total clés pour ce fournisseur : *{n_keys}*\n"
                        f"_(bascule automatique si quota épuisé)_", buttons=mk_ai_menu())
                return

            # Mettre à jour l'horodatage d'activité de Sossou
            _last_sossou_activity[0] = time.time()

            # Annuler auto-réponse si admin répond manuellement
            chat_id = event.chat_id
            t = pending_tasks.get(chat_id)
            if t and not t.done(): t.cancel()

            # Secrétariat + rappels
            if text and len(text) > 5:
                try:
                    ent  = await event.get_chat()
                    cname = (f"{getattr(ent,'first_name','') or ''} "
                             f"{getattr(ent,'last_name','') or ''}").strip() or f"Chat:{chat_id}"
                    _sec_log(chat_id, cname, "out", text)
                    asyncio.create_task(extract_reminder(cname, text))
                except: pass

        # ── Callbacks Telethon (boutons) ──────────────────────────────────────

        @client.on(events.CallbackQuery)
        async def on_cb(event):
            data = event.data.decode("utf-8")
            await event.answer()

            if data == "mm":
                await event.edit("🏠 *Menu Principal — Bot Sossou*\n\nChoisissez une section :",
                                 buttons=mk_main_menu())

            elif data == "org":
                await event.edit("📋 *Organisation*\nGestion des demandes clients :",
                                 buttons=mk_org_menu())
            elif data == "org_p":
                await event.edit(text_org_pending(), buttons=mk_org_menu())
            elif data == "org_d":
                await event.edit(text_org_done(), buttons=mk_org_menu())
            elif data == "org_a":
                await event.edit("💡 Analyse en cours...", buttons=None)
                result = await text_org_analyze()
                await event.edit(result, buttons=mk_org_menu())
            elif data == "org_c":
                config["requests"] = [r for r in config["requests"] if r["status"]!="done"]
                save_config(config)
                await event.edit("✅ Demandes traitées supprimées.", buttons=mk_org_menu())

            elif data == "sec":
                total = sum(len(v["msgs"]) for v in sec_log.values())
                await event.edit(
                    f"📝 *Secrétariat*\n\n"
                    f"📚 {len(sec_log)} contacts | {total} messages enregistrés\n"
                    f"🕐 Heure Bénin : {benin_time()}\n\n"
                    f"Choisissez une action :", buttons=mk_sec_menu())
            elif data == "sec_contacts":
                await event.edit(text_contacts_list(), buttons=mk_sec_contacts_menu())

            elif data.startswith("sec_ct_"):
                try:
                    ct_uid = int(data.split("sec_ct_")[1])
                except:
                    await event.answer("❌ Contact invalide", alert=True); return
                detail = text_contact_detail(ct_uid)
                cname  = sec_log.get(ct_uid, {}).get("name", f"ID:{ct_uid}")
                await event.edit(detail[:3800], buttons=[
                    [Button.inline("🔍 Forcer analyse IA maintenant", f"sec_ana_{ct_uid}".encode())],
                    [Button.inline("🔙 Contacts",   b"sec_contacts")],
                    [Button.inline("🔙 Secrétariat", b"sec")],
                ])

            elif data.startswith("sec_ana_"):
                try:
                    ct_uid = int(data.split("sec_ana_")[1])
                except:
                    await event.answer("❌ Contact invalide", alert=True); return
                ct_data = sec_log.get(ct_uid, {})
                cname   = ct_data.get("name", f"ID:{ct_uid}")
                if len(ct_data.get("msgs", [])) < 3:
                    await event.answer("⚠️ Pas assez de messages (min 3)", alert=True); return
                # Réinitialiser le cooldown pour forcer l'analyse
                _analysis_cache.pop(ct_uid, None)
                await event.edit(f"🔍 Analyse en cours pour *{cname}*...", buttons=None)
                last_msg = ct_data["msgs"][-1]["t"] if ct_data.get("msgs") else "—"
                await smart_contact_analysis(ct_uid, cname, last_msg)
                detail = text_contact_detail(ct_uid)
                await event.edit(detail[:3800], buttons=[
                    [Button.inline("🔍 Re-analyser", f"sec_ana_{ct_uid}".encode())],
                    [Button.inline("🔙 Contacts",    b"sec_contacts")],
                    [Button.inline("🔙 Secrétariat", b"sec")],
                ])

            elif data == "sec_c":
                if not sec_log:
                    await event.edit("📚 *Conversations*\n\n_Aucune conversation enregistrée._",
                                     buttons=mk_sec_menu())
                    return
                lines = [f"📚 *Conversations du jour*\n"]
                for uid, d in list(sec_log.items())[-10:]:
                    nb = len(d["msgs"])
                    last = d["msgs"][-1]["t"][:60] if d["msgs"] else "—"
                    lines.append(f"👤 *{d['name']}* ({nb} msgs)\n   _{last}_\n")
                await event.edit("\n".join(lines), buttons=mk_sec_menu())
            elif data == "sec_a":
                await event.edit("💡 Analyse en cours...", buttons=None)
                result = await text_sec_analyze(client)
                await event.edit(result[:3000], buttons=mk_sec_menu())
            elif data == "sec_r":
                await event.edit("📤 Génération du résumé...", buttons=None)
                result = await text_sec_resume()
                await event.edit(result[:3000], buttons=mk_sec_menu())

            elif data == "sec_wipe":
                nb = len(sec_log)
                nb_msgs = sum(len(v.get("msgs",[])) for v in sec_log.values())
                await event.edit(
                    f"⚠️ *Effacer toutes les données ?*\n\n"
                    f"Cela supprimera définitivement :\n"
                    f"• {nb} contact(s) enregistré(s)\n"
                    f"• {nb_msgs} message(s) archivé(s)\n"
                    f"• Toutes les analyses IA\n\n"
                    f"_Cette action est irréversible._",
                    buttons=[
                        [Button.inline("✅ Oui, tout effacer", b"sec_wipe_ok")],
                        [Button.inline("❌ Annuler",            b"sec")],
                    ])

            elif data == "sec_wipe_ok":
                sec_log.clear()
                conv_history.clear()
                known_users.clear()
                _coached_convs.clear()
                _analysis_cache.clear()
                save_sec_log(sec_log)
                _ai_key_alerted[0] = False  # Réactiver les alertes clé IA
                await event.edit(
                    "✅ *Données effacées avec succès !*\n\n"
                    "Toutes les conversations et contacts ont été supprimés.\n"
                    "L'assistante repart de zéro.",
                    buttons=[[Button.inline("🔙 Menu principal", b"mm")]])

            elif data == "rem":
                await event.edit(text_reminders(), buttons=[
                    [Button.inline("➕ Ajouter un rappel", b"rem_a")],
                    [Button.inline("🔙 Secrétariat", b"sec")],
                ])
            elif data == "rem_a":
                state["param_waiting"] = "remind"
                await event.edit(
                    "📝 *Ajouter un rappel*\n\n"
                    "Envoyez : `texte | YYYY-MM-DD HH:MM`\n"
                    "Ex : `Finir bot de Jean | 2026-03-22 23:59`\n\n"
                    "_(date/heure Bénin)_")

            # ── Mode Absent ────────────────────────────────────────────────────
            elif data == "away_toggle":
                if away_mode[0]:
                    # Désactiver
                    away_mode[0] = False
                    nb = len(away_log)
                    await event.edit(
                        f"🔴 *Mode Absent désactivé*\n\n"
                        f"📊 Pendant ton absence : {nb} personne(s) ont écrit.\n\n"
                        f"Tape *📬 Quoi de neuf ?* pour voir le rapport complet.",
                        buttons=[
                            [Button.inline("📬 Quoi de neuf ?", b"quoi_de_neuf")],
                            [Button.inline("🔙 Menu", b"mm")],
                        ])
                else:
                    # Activer
                    away_mode[0]       = True
                    away_mode_start[0] = time.time()
                    away_log.clear()
                    await event.edit(
                        f"📵 *Je suis occupé — Bot activé !*\n\n"
                        f"✅ Le bot répond à ta place dès maintenant.\n\n"
                        f"⏱ Délai naturel : 10 secondes avant chaque réponse\n"
                        f"🧠 Connaît ton style d'écriture et tes projets\n"
                        f"📝 Note tout ce qui se dit dans le secrétariat\n"
                        f"📌 Détecte les *\"n'oublie pas\"* → crée des notes auto\n"
                        f"💰 Détecte les demandes de budget limité → alerte\n\n"
                        f"_Quand tu reviens → *📬 Quoi de neuf ?* pour le rapport complet._",
                        buttons=[
                            [Button.inline("📬 Quoi de neuf ? (rapport)", b"quoi_de_neuf")],
                            [Button.inline("🔙 Menu", b"mm")],
                        ])

            # ── Quoi de neuf ────────────────────────────────────────────────────
            elif data == "quoi_de_neuf":
                if not away_log:
                    await event.edit(
                        "📭 *Aucune conversation enregistrée pendant ton absence.*\n\n"
                        "Active d'abord le Mode Absent, puis reviens ici pour voir le rapport.",
                        buttons=[[Button.inline("🔙 Menu", b"mm")]])
                    return
                await event.edit("📬 *Génération du rapport en cours...*", buttons=None)
                briefing = await generate_briefing()
                # Reset après lecture
                away_log.clear()
                await event.edit(
                    briefing[:4000],
                    buttons=[
                        [Button.inline("🔄 Réactiver Mode Absent", b"away_toggle")],
                        [Button.inline("📋 Organisation", b"org")],
                        [Button.inline("🔙 Menu", b"mm")],
                    ])

            # ── Rapport Coaching ───────────────────────────────────────────────
            elif data == "coach":
                nb = len(sec_log)
                if nb == 0:
                    await event.edit("📭 Aucune conversation enregistrée pour l'instant.",
                                     buttons=[[Button.inline("🔙 Menu", b"mm")]]); return
                await event.edit(
                    f"🎓 *Rapport Coaching*\n\n"
                    f"📚 {nb} conversation(s) dans le secrétariat.\n\n"
                    f"*Analyse en cours...* Cette opération peut prendre 30s.",
                    buttons=None)
                # Analyser toutes les conversations (max 5)
                to_analyze = [
                    (uid, d) for uid, d in sec_log.items()
                    if any(m["r"] == "out" for m in d.get("msgs", []))
                ][:5]
                if not to_analyze:
                    await event.edit(
                        "📭 Aucun de vos messages sortants trouvé pour l'analyse.\n"
                        "_(Envoyez des messages à vos contacts d'abord)_",
                        buttons=[[Button.inline("🔙 Menu", b"mm")]]); return
                report = await generate_coaching_report(to_analyze)
                # Marquer comme analysé
                now_ts = time.time()
                for uid, _ in to_analyze:
                    _coached_convs[uid] = now_ts
                if not report or len(report.strip()) < 20:
                    await event.edit("✅ Aucune erreur notable détectée dans vos messages récents.",
                                     buttons=[[Button.inline("🔙 Menu", b"mm")]]); return
                names = ", ".join(d.get("name","?") for _, d in to_analyze)
                await event.edit(
                    f"🎓 *Rapport Coaching — {len(to_analyze)} conv(s)*\n"
                    f"_Contacts : {names}_\n\n"
                    f"{report[:3500]}",
                    buttons=[
                        [Button.inline("🔄 Réanalyser", b"coach_force")],
                        [Button.inline("🗑 Supprimer ce rapport", b"coach_del")],
                        [Button.inline("🔙 Menu", b"mm")],
                    ])

            elif data == "coach_force":
                # Force une nouvelle analyse (ignore le cooldown)
                await event.edit("🔄 *Réanalyse en cours...*", buttons=None)
                for uid in sec_log:
                    _coached_convs[uid] = 0   # Reset cooldown
                to_analyze = [
                    (uid, d) for uid, d in sec_log.items()
                    if any(m["r"] == "out" for m in d.get("msgs", []))
                ][:5]
                if not to_analyze:
                    await event.edit("📭 Aucun message sortant trouvé.",
                                     buttons=[[Button.inline("🔙 Menu", b"mm")]]); return
                report = await generate_coaching_report(to_analyze)
                now_ts = time.time()
                for uid, _ in to_analyze:
                    _coached_convs[uid] = now_ts
                if not report or len(report.strip()) < 20:
                    await event.edit("✅ Aucune erreur notable.",
                                     buttons=[[Button.inline("🔙 Menu", b"mm")]]); return
                names = ", ".join(d.get("name","?") for _, d in to_analyze)
                await event.edit(
                    f"🎓 *Rapport Coaching (actualisé)*\n"
                    f"_Contacts : {names}_\n\n"
                    f"{report[:3500]}",
                    buttons=[
                        [Button.inline("🔄 Réanalyser", b"coach_force")],
                        [Button.inline("🗑 Supprimer ce rapport", b"coach_del")],
                        [Button.inline("🔙 Menu", b"mm")],
                    ])

            elif data == "coach_del":
                try:
                    await event.delete()
                except Exception:
                    await event.edit("🗑 Rapport supprimé.",
                                     buttons=[[Button.inline("🔙 Menu", b"mm")]])

            # ── Stratégies Baccara ─────────────────────────────────────────────
            elif data == "strat":
                await event.edit(text_strat_list(), buttons=mk_strat_menu())

            elif data == "strat_v":
                strats = config.get("baccara_strategies", [])
                if not strats:
                    await event.edit(
                        "🎲 *Stratégies Baccara*\n\n_Aucune stratégie enregistrée._",
                        buttons=mk_strat_menu())
                    return
                # Afficher avec bouton supprimer pour chacune
                lines = [f"🎲 *Stratégies enregistrées ({len(strats)})*\n"]
                for i, s in enumerate(strats, 1):
                    lines.append(f"*{i}. {s.get('name','')}*\n   _{s.get('description','')}_\n")
                del_buttons = [
                    [Button.inline(f"🗑 Supprimer #{i} — {s.get('name','')[:25]}",
                                   f"strat_del_{i-1}".encode())]
                    for i, s in enumerate(strats, 1)
                ]
                del_buttons.append([Button.inline("🔙 Stratégies", b"strat")])
                await event.edit("\n".join(lines), buttons=del_buttons)

            elif data == "strat_a":
                state["param_waiting"] = "addstrat"
                await event.edit(
                    "🎲 *Ajouter une stratégie Baccara*\n\n"
                    "Deux formats possibles :\n\n"
                    "**Format complet** (avec nom) :\n"
                    "`Nom de la stratégie | Description détaillée`\n\n"
                    "**Format simple** (nom automatique) :\n"
                    "`Description de la stratégie directement`\n\n"
                    "_Exemple : `Même carte | Quand le joueur reçoit la même carte deux fois, "
                    "miser sur cette carte au jeu suivant.`_"
                )

            elif data.startswith("strat_del_"):
                try:
                    idx = int(data.split("strat_del_")[1])
                except:
                    await event.answer("❌ Index invalide", alert=True); return
                strats = config.get("baccara_strategies", [])
                if 0 <= idx < len(strats):
                    removed = strats.pop(idx)
                    save_config(config)
                    await event.edit(
                        f"🗑 Stratégie supprimée : *{removed.get('name','')}*",
                        buttons=mk_strat_menu()
                    )
                else:
                    await event.answer("❌ Stratégie introuvable", alert=True)

            elif data == "prog":
                await event.edit(text_prog(), buttons=mk_prog_menu())
            elif data == "prog_v":
                await event.edit(text_prog(), buttons=mk_prog_menu())
            elif data == "prog_a":
                state["param_waiting"] = "addprog"
                await event.edit("📅 *Ajouter une tâche*\n\nTapez votre tâche dans le prochain message :")
            elif data == "prog_c":
                config["daily_program"] = []
                save_config(config)
                await event.edit("✅ Programme vidé.", buttons=mk_prog_menu())

            elif data == "ai":
                await event.edit("🤖 *Fournisseurs IA*\n\nCliquez pour configurer une clé :",
                                 buttons=mk_ai_menu())
            elif data == "ai_st":
                config["stealth_mode"] = not config.get("stealth_mode", True)
                save_config(config)
                status = "🕵️ ON — Je réponds comme Sossou lui-même" if config["stealth_mode"] \
                         else "🔵 OFF — Je me présente comme l'assistante"
                await event.edit(f"Mode furtif : *{status}*", buttons=mk_ai_menu())
            elif data == "ai_auto":
                config["auto_reply_enabled"] = not config.get("auto_reply_enabled", True)
                save_config(config)
                if config["auto_reply_enabled"]:
                    stopped_chats.clear()
                status = "✅ Activée" if config["auto_reply_enabled"] else "🛑 Désactivée"
                await event.edit(f"Auto-réponse : *{status}*", buttons=mk_ai_menu())
            elif data.startswith("ai_"):
                provider = data[3:]
                if provider in AI_META:
                    state["ai_waiting"] = provider
                    pdata     = config["ai_providers"].get(provider, {})
                    keys_list = [x for x in pdata.get("keys", []) if x]
                    n_keys    = len(keys_list)
                    keys_info = "\n".join(
                        f"  🔑 Clé {i+1}: `{k[:8]}...{k[-4:]}`"
                        for i, k in enumerate(keys_list)
                    ) if keys_list else "  _Aucune clé configurée_"
                    urls = {"groq":"console.groq.com/keys","openai":"platform.openai.com/api-keys",
                            "anthropic":"console.anthropic.com","gemini":"aistudio.google.com/app/apikey",
                            "mistral":"console.mistral.ai/api-keys"}
                    await event.edit(
                        f"🔑 *{AI_META[provider]['name']}*\n\n"
                        f"Clés configurées ({n_keys}) :\n{keys_info}\n\n"
                        f"Envoyez une *nouvelle clé* pour l'ajouter à la liste.\n"
                        f"_(bascule automatique si une clé est épuisée)_\n\n"
                        f"🔗 {urls.get(provider,'')}")

            elif data == "stats":
                await event.edit(text_stats(), buttons=[
                    [Button.inline("🔄 Actualiser", b"stats")],
                    [Button.inline("🔙 Menu", b"mm")],
                ])

            elif data == "prm":
                await event.edit("⚙️ *Paramètres*", buttons=mk_prm_menu())
            elif data == "prm_d":
                state["param_waiting"] = "delay"
                await event.edit(
                    f"⏱ *Délai absence actuel : {config['delay_seconds']}s*\n\n"
                    f"Envoyez le nouveau délai en secondes (ex: `30`) :")
            elif data == "prm_r":
                state["param_waiting"] = "replydelay"
                await event.edit(
                    f"⚡ *Délai réponse actuel : {config.get('reply_delay_seconds',5)}s*\n\n"
                    f"Envoyez le nouveau délai en secondes (ex: `5`) :")
            elif data == "prm_q":
                state["param_waiting"] = "quota"
                await event.edit(
                    f"🔢 *Quota actuel : {config['daily_quota']}/jour*\n"
                    f"Utilisé aujourd'hui : {config['quota_used_today']}\n\n"
                    f"Envoyez le nouveau quota (ex: `200`) :")
            elif data == "prm_k":
                kb = config["knowledge_base"]
                lines = [f"📚 *Base de connaissances ({len(kb)} entrées)*\n"]
                for i, x in enumerate(kb, 1):
                    lines.append(f"{i}. {x}")
                await event.edit("\n".join(lines), buttons=[
                    [Button.inline("➕ Ajouter", b"prm_ka"),
                     Button.inline("⚙️ Paramètres", b"prm")],
                    [Button.inline("🔙 Menu", b"mm")],
                ])
            elif data == "prm_ka":
                state["param_waiting"] = "addinfo"
                await event.edit("➕ *Ajouter une information*\n\nTapez l'info à ajouter :")
            elif data == "prm_kv":
                kb = config["knowledge_base"]
                lines = [f"📚 *Base de connaissances*\n"]
                for i, x in enumerate(kb, 1):
                    lines.append(f"`/removeinfo {i}` — {x[:80]}")
                await event.edit("\n".join(lines), buttons=[[Button.inline("🔙 Paramètres", b"prm")]])

        # ── Commandes textuelles ───────────────────────────────────────────────

        @client.on(events.NewMessage(outgoing=True, pattern=r"^/menu(\s|$)"))
        async def cmd_menu(event):
            await event.respond(
                f"🏠 *Menu Principal — Bot Sossou*\n\n"
                f"🕐 {benin_time()} (heure Bénin)\n"
                f"Auto-réponse : {'✅' if config.get('auto_reply_enabled',True) else '🛑'} | "
                f"Furtif : {'🕵️' if config.get('stealth_mode',True) else '🔵'}\n\n"
                f"Choisissez une section :", buttons=mk_main_menu())

        @client.on(events.NewMessage(outgoing=True, pattern=r"^/orgdone\s+(\d+)$"))
        async def cmd_orgdone(event):
            idx = int(event.pattern_match.group(1)) - 1
            pending = [r for r in config["requests"] if r["status"]=="pending"]
            if not (0 <= idx < len(pending)):
                await event.respond(f"❌ Numéro invalide (1 à {len(pending)})"); return
            pending[idx]["status"] = "done"
            save_config(config)
            await event.respond(f"✅ Marqué comme traité :\n_{pending[idx]['summary']}_")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^/stop(\s|$)"))
        async def cmd_stop(event):
            args = (event.text or "").strip().split()[1:]
            if args and args[0].lstrip("-").isdigit():
                stopped_chats.add(int(args[0]))
                await event.respond(f"🛑 Auto-réponse arrêtée pour `{args[0]}`")
            else:
                config["auto_reply_enabled"] = False; save_config(config)
                await event.respond("🛑 Auto-réponse *désactivée*.\n`/resume` pour réactiver.")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^/resume(\s|$)"))
        async def cmd_resume(event):
            args = (event.text or "").strip().split()[1:]
            if args and args[0].lstrip("-").isdigit():
                stopped_chats.discard(int(args[0]))
                await event.respond(f"✅ Auto-réponse réactivée pour `{args[0]}`")
            else:
                config["auto_reply_enabled"] = True; save_config(config)
                stopped_chats.clear()
                await event.respond("✅ Auto-réponse *réactivée*.")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^/donenote\s+(\d+)$"))
        async def cmd_donenote(event):
            idx = int(event.pattern_match.group(1)) - 1
            rems = config.get("reminders", [])
            if not (0 <= idx < len(rems)):
                await event.respond(f"❌ Invalide (1 à {len(rems)})"); return
            rems[idx]["notified"] = True; save_config(config)
            await event.respond(f"✅ Fait : _{rems[idx].get('text','?')}_")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^/deletenote\s+(\d+)$"))
        async def cmd_deletenote(event):
            idx = int(event.pattern_match.group(1)) - 1
            rems = config.get("reminders", [])
            if not (0 <= idx < len(rems)):
                await event.respond(f"❌ Invalide (1 à {len(rems)})"); return
            removed = rems.pop(idx); save_config(config)
            await event.respond(f"✅ Supprimé : _{removed.get('text','?')}_")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^/removeinfo\s+(\d+)$"))
        async def cmd_removeinfo(event):
            idx = int(event.pattern_match.group(1)) - 1
            kb  = config["knowledge_base"]
            if not (0 <= idx < len(kb)):
                await event.respond(f"❌ Invalide (1 à {len(kb)})"); return
            removed = kb.pop(idx); save_config(config)
            await event.respond(f"✅ Supprimé : _{removed}_")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^/help(\s|$)"))
        async def cmd_help(event):
            await event.respond(
                "🛠 *Commandes — Tapez /menu pour les boutons*\n\n"
                "📋 *Organisation :*\n"
                "• `/orgdone <n>` — Marquer demande comme traitée\n\n"
                "📝 *Secrétariat & Rappels :*\n"
                "• `/donenote <n>` — Marquer rappel fait\n"
                "• `/deletenote <n>` — Supprimer rappel\n\n"
                "🔄 *Auto-réponse :*\n"
                "• `/stop` / `/resume` — Global\n"
                "• `/stop <chat_id>` / `/resume <chat_id>` — Par chat\n\n"
                "📚 *Base de connaissances :*\n"
                "• `/removeinfo <n>` — Supprimer une info\n\n"
                "🏠 `/menu` — Menu principal avec boutons")

        # ═══════════════════════════════════════════════════════════════════════
        #  BOT DE CONTRÔLE (chat privé du bot Telegram)
        # ═══════════════════════════════════════════════════════════════════════

        # Vérifie si une autre instance (déploiement) monopolise déjà le token
        def _bot_token_free(token: str) -> bool:
            """Retourne True si le token est disponible (aucun autre polling actif)."""
            try:
                import urllib.request as _ur, json as _js
                req = _ur.Request(
                    f"https://api.telegram.org/bot{token}/getUpdates?timeout=0&limit=1",
                    headers={"Content-Type": "application/json"}, method="GET")
                with _ur.urlopen(req, timeout=8) as r:
                    return True   # 200 OK → token libre
            except Exception as e:
                if "409" in str(e) or "Conflict" in str(e):
                    return False  # token déjà utilisé par le déploiement
                return True       # autre erreur → on tente quand même

        # Si une instance déployée occupe déjà le token, on désactive le bot de contrôle
        # local pour éviter les conflits 409 permanents. Le userbot Telethon reste actif.
        _effective_bot_token = BOT_TOKEN
        if BOT_TOKEN and not _bot_token_free(BOT_TOKEN):
            logger.warning(
                "⚠️ Bot de contrôle ignoré : une instance déployée est déjà active "
                "(token occupé). Le userbot Telethon reste pleinement fonctionnel."
            )
            _ctrl_active[0] = False
            _effective_bot_token = ""

        if _effective_bot_token:
            from telegram import (Update as _U, InlineKeyboardButton as _IKB,
                                  InlineKeyboardMarkup as _IKM)
            from telegram.ext import (Application as _App, CommandHandler as _CH,
                                      MessageHandler as _MH, filters as _F,
                                      ContextTypes as _CT, CallbackQueryHandler as _CQH)

            ctrl = _App.builder().token(BOT_TOKEN).build()
            ctrl_state: dict = {}  # {user_id: {step, data}}

            def _owner(fn):
                async def w(update: _U, context: _CT.DEFAULT_TYPE):
                    if update.effective_user and update.effective_user.id == OWNER_ID:
                        await fn(update, context)
                return w

            # ── Générateurs de claviers pour le control bot ───────────────────

            def bk_main():
                if away_mode[0]:
                    nb_away  = len(away_log)
                    away_btn = _IKB(f"✅ Bot répond à ta place — {nb_away} conv(s) | ARRÊTER",
                                    callback_data="away_toggle")
                else:
                    away_btn = _IKB("📵 Je suis occupé — Bot répond à ma place",
                                    callback_data="away_toggle")
                return _IKM([
                    [away_btn],
                    [_IKB("📬 Quoi de neuf ?",   callback_data="quoi_de_neuf"),
                     _IKB("🎓 Coaching",          callback_data="coach")],
                    [_IKB("📋 Organisation",      callback_data="org"),
                     _IKB("📝 Secrétariat",        callback_data="sec")],
                    [_IKB("📅 Programme",          callback_data="prog"),
                     _IKB("🤖 Fournisseurs IA",    callback_data="ai")],
                    [_IKB("📊 Stats & Statut",     callback_data="stats"),
                     _IKB("⚙️ Paramètres",         callback_data="prm")],
                ])

            def bk_org():
                p = sum(1 for r in config["requests"] if r["status"]=="pending")
                d = sum(1 for r in config["requests"] if r["status"]=="done")
                return _IKM([
                    [_IKB(f"⏳ En attente ({p})", callback_data="org_p"),
                     _IKB(f"✅ Traitées ({d})",   callback_data="org_d")],
                    [_IKB("💡 Analyser & Proposer", callback_data="org_a"),
                     _IKB("🗑 Vider traitées",       callback_data="org_c")],
                    [_IKB("🔙 Menu",                callback_data="mm")],
                ])

            def bk_sec():
                total    = sum(len(v["msgs"]) for v in sec_log.values())
                contacts = len(sec_log)
                return _IKM([
                    [_IKB(f"📚 Conversations ({contacts} contacts)", callback_data="sec_c")],
                    [_IKB("💡 Analyser & Proposer solutions",        callback_data="sec_a")],
                    [_IKB("📋 Résumé du jour (IA)",                  callback_data="sec_r")],
                    [_IKB("📝 Rappels",                              callback_data="rem")],
                    [_IKB("🗑 Tout effacer (RAZ)",                   callback_data="sec_wipe")],
                    [_IKB("➕ Ajouter rappel manuel",                callback_data="rem_a"),
                     _IKB("🔙 Menu",                                 callback_data="mm")],
                ])

            def bk_prog():
                progs = config.get("daily_program", [])
                return _IKM([
                    [_IKB(f"📅 Voir programme ({len(progs)} tâches)", callback_data="prog_v")],
                    [_IKB("➕ Ajouter une tâche", callback_data="prog_a"),
                     _IKB("🗑 Vider",              callback_data="prog_c")],
                    [_IKB("🔙 Menu",               callback_data="mm")],
                ])

            def bk_ai():
                providers = config["ai_providers"]
                active    = config.get("active_ai","groq")
                stealth   = "🕵️ Furtif : ON" if config.get("stealth_mode",True) else "👁 Furtif : OFF"
                auto      = "✅ Auto : ON" if config.get("auto_reply_enabled",True) else "🛑 Auto : OFF"
                rows = []
                for i, k in enumerate(AI_LIST, 1):
                    d         = providers.get(k, {})
                    keys_list = [x for x in d.get("keys", []) if x]
                    n_keys    = len(keys_list)
                    has_key   = n_keys > 0
                    is_act    = k == active
                    icon      = "🔵" if is_act else ("✅" if has_key else "❌")
                    name_short = AI_META[k]["name"].split("—")[0].strip()
                    badge      = f" ({n_keys}🔑)" if n_keys > 1 else ""
                    rows.append([_IKB(f"{icon} {i}. {name_short}{badge}", callback_data=f"ai_{k}")])
                rows.append([_IKB(stealth, callback_data="ai_st"),
                             _IKB(auto,    callback_data="ai_auto")])
                rows.append([_IKB("🔙 Menu", callback_data="mm")])
                return _IKM(rows)

            def bk_prm():
                d  = config["delay_seconds"]
                rd = config.get("reply_delay_seconds",5)
                q  = config["daily_quota"]
                qu = config["quota_used_today"]
                return _IKM([
                    [_IKB(f"⏱ Délai absence : {d}s", callback_data="prm_d"),
                     _IKB(f"⚡ Délai réponse : {rd}s", callback_data="prm_r")],
                    [_IKB(f"🔢 Quota : {qu}/{q}/j",    callback_data="prm_q")],
                    [_IKB("📚 Base de connaissances",   callback_data="prm_k")],
                    [_IKB("➕ Ajouter info",  callback_data="prm_ka"),
                     _IKB("📝 Voir & suppr.", callback_data="prm_kv")],
                    [_IKB("🔙 Menu",          callback_data="mm")],
                ])

            # ── /start & /menu ────────────────────────────────────────────────

            @_owner
            async def bc_start(update: _U, context: _CT.DEFAULT_TYPE):
                await update.message.reply_text(
                    f"🏠 *Menu Principal — Bot Sossou*\n\n"
                    f"🕐 {benin_time()} (heure Bénin)\n"
                    f"Auto-réponse : {'✅' if config.get('auto_reply_enabled',True) else '🛑'}\n"
                    f"Mode furtif : {'🕵️ ON' if config.get('stealth_mode',True) else '🔵 OFF'}\n\n"
                    f"Choisissez une section :",
                    reply_markup=bk_main(), parse_mode="Markdown")

            # ── Callbacks control bot ─────────────────────────────────────────

            async def bc_cb(update: _U, context: _CT.DEFAULT_TYPE):
                q = update.callback_query
                await q.answer()
                if q.from_user.id != OWNER_ID: return
                d = q.data
                uid = q.from_user.id

                async def edit(text, kb=None):
                    try:
                        await q.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
                    except Exception: pass

                if d == "mm":
                    await edit(f"🏠 *Menu Principal*\n\n🕐 {benin_time()} (heure Bénin)", bk_main())
                elif d == "org":
                    await edit("📋 *Organisation* — Gestion des demandes clients", bk_org())
                elif d == "org_p":
                    await edit(text_org_pending(), bk_org())
                elif d == "org_d":
                    await edit(text_org_done(), bk_org())
                elif d == "org_a":
                    await edit("💡 Analyse en cours...", None)
                    result = await text_org_analyze()
                    await edit(result[:4000], bk_org())
                elif d == "org_c":
                    config["requests"] = [r for r in config["requests"] if r["status"]!="done"]
                    save_config(config)
                    await edit("✅ Demandes traitées supprimées.", bk_org())
                elif d == "sec":
                    t = sum(len(v["msgs"]) for v in sec_log.values())
                    await edit(f"📝 *Secrétariat*\n\n{len(sec_log)} contacts | {t} messages", bk_sec())
                elif d == "sec_c":
                    if not sec_log:
                        await edit("📚 Aucune conversation enregistrée.", bk_sec()); return
                    lines = ["📚 *Conversations du jour*\n"]
                    for uid2, dat in list(sec_log.items())[-10:]:
                        nb = len(dat["msgs"])
                        last = dat["msgs"][-1]["t"][:60] if dat["msgs"] else "—"
                        lines.append(f"👤 *{dat['name']}* ({nb} msgs)\n_{last}_\n")
                    await edit("\n".join(lines)[:4000], bk_sec())
                elif d == "sec_a":
                    await edit("💡 Analyse IA en cours...", None)
                    result = await text_sec_analyze(client)
                    await edit(result[:4000], bk_sec())
                elif d == "sec_r":
                    await edit("📤 Génération du résumé...", None)
                    result = await text_sec_resume()
                    await edit(result[:4000], bk_sec())
                elif d == "sec_wipe":
                    nb = len(sec_log)
                    nb_msgs = sum(len(v.get("msgs",[])) for v in sec_log.values())
                    kb = _IKM([
                        [_IKB("✅ Oui, tout effacer", callback_data="sec_wipe_ok")],
                        [_IKB("❌ Annuler",            callback_data="sec")],
                    ])
                    await edit(
                        f"⚠️ *Effacer toutes les données ?*\n\n"
                        f"Cela supprimera définitivement :\n"
                        f"• {nb} contact(s) enregistré(s)\n"
                        f"• {nb_msgs} message(s) archivé(s)\n"
                        f"• Toutes les analyses IA\n\n"
                        f"_Cette action est irréversible._", kb)
                elif d == "sec_wipe_ok":
                    sec_log.clear()
                    conv_history.clear()
                    known_users.clear()
                    _coached_convs.clear()
                    _analysis_cache.clear()
                    save_sec_log(sec_log)
                    _ai_key_alerted[0] = False
                    kb = _IKM([[_IKB("🔙 Menu", callback_data="mm")]])
                    await edit(
                        "✅ *Données effacées avec succès !*\n\n"
                        "Toutes les conversations et contacts ont été supprimés.\n"
                        "L'assistante repart de zéro.", kb)
                elif d == "rem":
                    kb = _IKM([[_IKB("🔙 Secrétariat", callback_data="sec")]])
                    await edit(text_reminders(), kb)
                elif d == "rem_a":
                    ctrl_state[uid] = {"step":"remind"}
                    await edit("📝 *Ajouter un rappel*\n\nEnvoyez : `texte | YYYY-MM-DD HH:MM`\n"
                               "Ex : `Finir bot Jean | 2026-03-22 23:59`")
                elif d == "prog":
                    await edit(text_prog(), bk_prog())
                elif d == "prog_v":
                    await edit(text_prog(), bk_prog())
                elif d == "prog_a":
                    ctrl_state[uid] = {"step":"addprog"}
                    await edit("📅 *Ajouter une tâche*\n\nEnvoyez la tâche :")
                elif d == "prog_c":
                    config["daily_program"] = []; save_config(config)
                    await edit("✅ Programme vidé.", bk_prog())
                elif d == "ai":
                    await edit("🤖 *Fournisseurs IA*\n\nCliquez pour configurer :", bk_ai())
                elif d == "ai_st":
                    config["stealth_mode"] = not config.get("stealth_mode", True)
                    save_config(config)
                    s = "🕵️ ON — Je réponds comme Sossou" if config["stealth_mode"] else "🔵 OFF — Assistante"
                    await edit(f"Mode furtif : *{s}*", bk_ai())
                elif d == "ai_auto":
                    config["auto_reply_enabled"] = not config.get("auto_reply_enabled", True)
                    save_config(config)
                    if config["auto_reply_enabled"]: stopped_chats.clear()
                    s = "✅ Activée" if config["auto_reply_enabled"] else "🛑 Désactivée"
                    await edit(f"Auto-réponse : *{s}*", bk_ai())
                elif d.startswith("ai_"):
                    provider = d[3:]
                    if provider in AI_META:
                        ctrl_state[uid] = {"step":"ai_key","provider":provider}
                        pdata     = config["ai_providers"].get(provider, {})
                        keys_list = [x for x in pdata.get("keys", []) if x]
                        n_keys    = len(keys_list)
                        keys_info = "\n".join(
                            f"  🔑 Clé {i+1}: `{k[:8]}...{k[-4:]}`"
                            for i, k in enumerate(keys_list)
                        ) if keys_list else "  _Aucune clé configurée_"
                        urls = {"groq":"console.groq.com/keys","openai":"platform.openai.com/api-keys",
                                "anthropic":"console.anthropic.com","gemini":"aistudio.google.com/app/apikey",
                                "mistral":"console.mistral.ai/api-keys"}
                        await edit(
                            f"🔑 *{AI_META[provider]['name']}*\n\n"
                            f"Clés configurées ({n_keys}) :\n{keys_info}\n\n"
                            f"Envoyez une *nouvelle clé* pour l'ajouter.\n"
                            f"_(bascule automatique si quota épuisé)_\n"
                            f"🔗 {urls.get(provider,'')}")
                elif d == "stats":
                    await edit(text_stats(), _IKM([
                        [_IKB("🔄 Actualiser", callback_data="stats")],
                        [_IKB("🔙 Menu",        callback_data="mm")],
                    ]))
                elif d == "prm":
                    await edit("⚙️ *Paramètres*", bk_prm())
                elif d == "prm_d":
                    ctrl_state[uid] = {"step":"delay"}
                    await edit(f"⏱ Délai absence actuel : *{config['delay_seconds']}s*\n\nEnvoyez le nouveau délai (ex: `30`) :")
                elif d == "prm_r":
                    ctrl_state[uid] = {"step":"replydelay"}
                    await edit(f"⚡ Délai réponse actuel : *{config.get('reply_delay_seconds',5)}s*\n\nEnvoyez (ex: `5`) :")
                elif d == "prm_q":
                    ctrl_state[uid] = {"step":"quota"}
                    await edit(f"🔢 Quota actuel : *{config['daily_quota']}/jour*\n\nEnvoyez le nouveau quota :")
                elif d == "prm_k":
                    kb2 = config["knowledge_base"]
                    lines = [f"📚 *Base ({len(kb2)} entrées)*\n"]
                    for i, x in enumerate(kb2, 1):
                        lines.append(f"{i}. {x[:80]}")
                    mk = _IKM([[_IKB("➕ Ajouter", callback_data="prm_ka"),
                                _IKB("⚙️ Paramètres", callback_data="prm")]])
                    await edit("\n".join(lines)[:4000], mk)
                elif d == "prm_ka":
                    ctrl_state[uid] = {"step":"addinfo"}
                    await edit("➕ *Ajouter une information*\n\nTapez l'info :")
                elif d == "prm_kv":
                    kb2 = config["knowledge_base"]
                    lines = [f"📚 *Base ({len(kb2)} entrées)*\n"]
                    for i, x in enumerate(kb2, 1):
                        lines.append(f"`/removeinfo {i}` — {x[:70]}")
                    mk = _IKM([[_IKB("🔙 Paramètres", callback_data="prm")]])
                    await edit("\n".join(lines)[:4000], mk)

                elif d == "away_toggle":
                    if away_mode[0]:
                        # Désactiver
                        away_mode[0] = False
                        duree = int(time.time() - away_mode_start[0])
                        h, m  = duree // 3600, (duree % 3600) // 60
                        nb    = len(away_log)
                        await edit(
                            f"🟢 *Mode Occupé désactivé*\n\n"
                            f"⏱ Durée : {h}h{m:02d}m\n"
                            f"💬 Conversations gérées : {nb}\n\n"
                            f"Tape *Quoi de neuf ?* pour le rapport complet.",
                            _IKM([
                                [_IKB("📬 Quoi de neuf ? (rapport complet)", callback_data="quoi_de_neuf")],
                                [_IKB("🔙 Menu", callback_data="mm")],
                            ])
                        )
                    else:
                        # Activer
                        away_mode[0]       = True
                        away_mode_start[0] = time.time()
                        away_log.clear()
                        await edit(
                            f"📵 *Je suis occupé — Bot activé !*\n\n"
                            f"✅ Le bot répond à ta place dès maintenant.\n\n"
                            f"⏱ Délai naturel : 10 secondes avant chaque réponse\n"
                            f"🧠 Connaît ton style d'écriture et tes projets\n"
                            f"📝 Note tout ce qui se dit dans le secrétariat\n"
                            f"📌 Détecte les *\"n'oublie pas\"* → crée des notes auto\n\n"
                            f"_Quand tu reviens → appuie sur le bouton pour l'arrêter._",
                            _IKM([
                                [_IKB("🛑 Arrêter (je suis de retour)", callback_data="away_toggle")],
                                [_IKB("🔙 Menu", callback_data="mm")],
                            ])
                        )

                elif d == "quoi_de_neuf":
                    if not away_log:
                        await edit(
                            "📬 *Quoi de neuf ?*\n\n"
                            "Aucune conversation en mode absent pour l'instant.\n"
                            "Active d'abord *📵 Je suis occupé* pour que le bot gère tes messages.",
                            _IKM([[_IKB("🔙 Menu", callback_data="mm")]])
                        )
                    else:
                        await edit("⏳ *Génération du rapport en cours...*\n\nAnalyse de toutes les conversations...", None)
                        nb = len(away_log)
                        conv_lines = []
                        for uid2, msgs in list(away_log.items())[-8:]:
                            name = sec_log.get(str(uid2), {}).get("name", f"Contact {uid2}")
                            conv_lines.append(f"👤 *{name}* — {len(msgs)} msg(s)")
                            for m2 in msgs[-2:]:
                                conv_lines.append(f"  › _{m2[:80]}_")
                        conv_txt = "\n".join(conv_lines)
                        prompt = (
                            f"Voici les conversations gérées pendant l'absence de Sossou "
                            f"({nb} contacts) :\n\n{conv_txt}\n\n"
                            f"Fais un BREF rapport : points importants, promesses détectées, "
                            f"actions requises. Max 200 mots."
                        )
                        try:
                            rapport = await smart_ai_call(
                                "Tu es le secrétaire intelligent de Sossou.",
                                [{"role":"user","content":prompt}],
                                max_tokens=400, temperature=0.5)
                        except Exception:
                            rapport = conv_txt
                        away_log.clear()
                        await edit(
                            f"📬 *Rapport — Quoi de neuf ?*\n\n{rapport[:3800]}",
                            _IKM([[_IKB("🔙 Menu", callback_data="mm")]])
                        )

                elif d == "coach":
                    nb_convs = len(sec_log)
                    await edit(
                        f"🎓 *Rapport Coaching*\n\n{nb_convs} conversation(s) analysées.\n\n"
                        f"_Le rapport est généré automatiquement quand tu es inactif 5+ min._",
                        _IKM([
                            [_IKB("🔄 Forcer l'analyse maintenant", callback_data="coach_force")],
                            [_IKB("🔙 Menu", callback_data="mm")],
                        ])
                    )

                elif d == "coach_force":
                    await edit("🎓 *Analyse coaching en cours...*", None)
                    try:
                        msgs_out = []
                        for dat in list(sec_log.values())[-5:]:
                            for m2 in dat["msgs"]:
                                if m2.get("r") == "out":
                                    msgs_out.append(m2["t"])
                        if not msgs_out:
                            await edit("Pas encore de messages sortants à analyser.", _IKM([[_IKB("🔙 Menu", callback_data="mm")]]))
                        else:
                            sample = "\n".join(msgs_out[-15:])
                            prompt = (
                                f"Analyse ces messages envoyés par Sossou à ses contacts :\n\n{sample}\n\n"
                                f"Donne un coaching bref : fautes d'orthographe, meilleures formulations, "
                                f"opportunités manquées. Max 200 mots."
                            )
                            rapport = await smart_ai_call(
                                "Tu es le coach personnel de Sossou Kouamé.",
                                [{"role":"user","content":prompt}],
                                max_tokens=400, temperature=0.5)
                            await edit(
                                f"🎓 *Coaching IA*\n\n{rapport[:3800]}",
                                _IKM([
                                    [_IKB("🗑 Supprimer ce rapport", callback_data="coach_del")],
                                    [_IKB("🔙 Menu", callback_data="mm")],
                                ]))
                    except Exception as e:
                        await edit(f"❌ Erreur : {e}", _IKM([[_IKB("🔙 Menu", callback_data="mm")]]))

                elif d == "coach_del":
                    try:
                        await query.message.delete()
                    except Exception:
                        await edit("🗑 Rapport supprimé.", _IKM([[_IKB("🔙 Menu", callback_data="mm")]]))

            # ── Messages texte control bot ─────────────────────────────────────

            @_owner
            async def bc_msg(update: _U, context: _CT.DEFAULT_TYPE):
                uid  = update.effective_user.id
                text = update.message.text or ""
                st   = ctrl_state.get(uid, {})
                step = st.get("step")

                if step == "ai_key":
                    provider = st["provider"]
                    ctrl_state.pop(uid, None)
                    await update.message.reply_text(f"🔍 Vérification *{AI_META[provider]['name']}*...",
                        parse_mode="Markdown")
                    loop = asyncio.get_event_loop()
                    model = config["ai_providers"][provider].get("model", AI_META[provider]["model"])
                    ok, info = await loop.run_in_executor(None, verify_key, provider, text.strip(), model)
                    if not ok:
                        await update.message.reply_text(f"❌ Clé invalide\n\n{info}",
                            reply_markup=bk_ai(), parse_mode="Markdown")
                    else:
                        new_key = text.strip()
                        keys_list = config["ai_providers"][provider].setdefault("keys", [])
                        if new_key not in keys_list:
                            keys_list.append(new_key)
                        config["active_ai"] = provider
                        save_config(config)
                        masked = new_key[:8]+"..."+new_key[-4:]
                        n_keys = len(keys_list)
                        await update.message.reply_text(
                            f"✅ *{AI_META[provider]['name']}* — clé ajoutée !\n\n"
                            f"Clé : `{masked}`\n{info}\n\n"
                            f"Total clés : *{n_keys}* _(bascule auto si quota épuisé)_",
                            reply_markup=bk_ai(), parse_mode="Markdown")

                elif step == "addprog":
                    ctrl_state.pop(uid, None)
                    progs = config.setdefault("daily_program", [])
                    progs.append(text.strip()); save_config(config)
                    await update.message.reply_text(f"✅ Tâche ajoutée !\n\n{text_prog()}",
                        reply_markup=bk_prog(), parse_mode="Markdown")

                elif step == "delay":
                    if text.strip().isdigit():
                        ctrl_state.pop(uid, None)
                        config["delay_seconds"] = int(text.strip()); save_config(config)
                        await update.message.reply_text(f"✅ Délai absence : *{config['delay_seconds']}s*",
                            reply_markup=bk_prm(), parse_mode="Markdown")
                    else:
                        await update.message.reply_text("❌ Veuillez envoyer un nombre (ex: `30`)",
                            parse_mode="Markdown")

                elif step == "replydelay":
                    if text.strip().isdigit():
                        ctrl_state.pop(uid, None)
                        config["reply_delay_seconds"] = int(text.strip()); save_config(config)
                        await update.message.reply_text(f"✅ Délai réponse : *{config['reply_delay_seconds']}s*",
                            reply_markup=bk_prm(), parse_mode="Markdown")

                elif step == "quota":
                    if text.strip().isdigit():
                        ctrl_state.pop(uid, None)
                        config["daily_quota"] = int(text.strip()); save_config(config)
                        await update.message.reply_text(f"✅ Quota : *{config['daily_quota']}/jour*",
                            reply_markup=bk_prm(), parse_mode="Markdown")

                elif step == "addinfo":
                    ctrl_state.pop(uid, None)
                    config["knowledge_base"].append(text.strip()); save_config(config)
                    await update.message.reply_text(f"✅ Info ajoutée !\n_{text.strip()}_",
                        reply_markup=bk_prm(), parse_mode="Markdown")

                elif step == "remind":
                    ctrl_state.pop(uid, None)
                    if "|" in text:
                        nt, dl_t = text.split("|",1)
                        try:
                            dl_dt = datetime.fromisoformat(dl_t.strip()).replace(tzinfo=BENIN_TZ)
                            dl_iso = dl_dt.strftime("%Y-%m-%dT%H:%M")
                        except:
                            dl_iso = dl_t.strip()
                    else:
                        nt, dl_iso = text, None
                    config["reminders"].append({
                        "id": int(time.time()), "text": nt.strip(), "contact": "Manuel (bot)",
                        "deadline": dl_iso, "created": benin_str(), "notified": False
                    })
                    save_config(config)
                    await update.message.reply_text(f"✅ Rappel ajouté !\n📌 {nt.strip()}",
                        reply_markup=bk_sec(), parse_mode="Markdown")

            ctrl.add_handler(_CH("start",   bc_start))
            ctrl.add_handler(_CH("menu",    bc_start))
            ctrl.add_handler(_CQH(bc_cb))
            ctrl.add_handler(_MH(_F.TEXT & ~_F.COMMAND, bc_msg))

            # Gestionnaire d'erreur : si 409 Conflict (instance déployée active),
            # on stoppe proprement le polling local et on cède la main au déploiement.
            from telegram.error import Conflict as _TGConflict

            async def _ctrl_error_handler(update, context):
                if isinstance(context.error, _TGConflict):
                    if _ctrl_active[0]:
                        _ctrl_active[0] = False
                        logger.warning(
                            "⚠️ 409 Conflict — instance déployée déjà active. "
                            "Polling local arrêté. Le userbot Telethon reste fonctionnel."
                        )
                        try:
                            await ctrl.updater.stop()
                        except Exception:
                            pass
                else:
                    logger.error(f"Erreur bot de contrôle : {context.error}")

            ctrl.add_error_handler(_ctrl_error_handler)

            await ctrl.initialize()
            await ctrl.start()
            await ctrl.updater.start_polling(drop_pending_updates=True)
            logger.info("✅ Bot de contrôle actif")

        # ── Notification de démarrage ──────────────────────────────────────────
        try:
            active  = config.get("active_ai", "gemini")
            ai_name = AI_META.get(active, {}).get("name", active)
            has_keys = any(
                len(config["ai_providers"].get(p, {}).get("keys", [])) > 0
                for p in AI_META
            )
            ai_status = f"🤖 IA : {ai_name}" if has_keys else "⚠️ Aucune clé IA — configure via /menu → 🤖 Fournisseurs IA"
            await notify(
                f"✅ *Assista Kouamé — ACTIF !*\n\n"
                f"{ai_status}\n"
                f"🕵️ Furtif : {'ON' if config.get('stealth_mode',True) else 'OFF'}\n"
                f"🕐 Heure Bénin : {benin_time()}\n\n"
                f"👉 Tapez /menu pour les commandes"
            )
        except Exception as _e:
            logger.debug(f"Notification démarrage : {_e}")

        asyncio.create_task(reminder_checker())
        asyncio.create_task(coaching_checker())

        try:
            await client.run_until_disconnected()
        finally:
            if _effective_bot_token:
                try:
                    await ctrl.updater.stop()
                    await ctrl.stop()
                    await ctrl.shutdown()
                except: pass

    asyncio.run(_main())


# ═══════════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # ── Lecture config.py en priorité basse (valeurs par défaut codées) ──────
    _cp = {}
    try:
        import config as _cfg_mod
        _cp = {k: getattr(_cfg_mod, k, "") for k in (
            "TELEGRAM_API_ID","TELEGRAM_API_HASH","TELEGRAM_BOT_TOKEN",
            "ADMIN_ID","PHONE_NUMBER","GROQ_API_KEY","TELEGRAM_SESSION")}
    except Exception:
        pass

    cfg            = load_config()
    PHONE_NUMBER   = _get(cfg,"PHONE_NUMBER","phone_number",
                          str(_cp.get("PHONE_NUMBER","")  or "+22995501564"))
    OWNER_ID       = int(_get(cfg,"ADMIN_ID","admin_id",
                          str(_cp.get("ADMIN_ID","")      or "1190237801")))
    API_ID         = int(_get(cfg,"TELEGRAM_API_ID","telegram_api_id",
                          str(_cp.get("TELEGRAM_API_ID","") or "29177661")))
    API_HASH       = _get(cfg,"TELEGRAM_API_HASH","telegram_api_hash",
                          str(_cp.get("TELEGRAM_API_HASH","") or "a8639172fa8d35dbfd8ea46286d349ab"))
    BOT_TOKEN      = _get(cfg,"TELEGRAM_BOT_TOKEN","bot_token",
                          str(_cp.get("TELEGRAM_BOT_TOKEN","") or "7653246287:AAH7-HVGo9EqUo8DWfhnleZSN3Y8Gp5_Nfg"))
    GROQ_API_KEY   = _get(cfg,"GROQ_API_KEY","groq_api_key",
                          str(_cp.get("GROQ_API_KEY","") or ""))
    SESSION_STRING = _get(cfg,"TELEGRAM_SESSION","telegram_session",
                          str(_cp.get("TELEGRAM_SESSION","") or "")).strip()

    # Fallback 2 : session.txt
    if not SESSION_STRING:
        if os.path.exists(SESSION_FILE):
            SESSION_STRING = Path(SESSION_FILE).read_text().strip()
            if SESSION_STRING: logger.info("📄 Session chargée depuis session.txt")

    # Validation de la session obtenue
    if SESSION_STRING:
        try:
            from telethon.sessions import StringSession as _SS
            _SS(SESSION_STRING)
        except Exception:
            logger.warning("⚠️ Session invalide, abandon.")
            SESSION_STRING = ""

    if not API_ID or not API_HASH:
        raise ValueError("TELEGRAM_API_ID et TELEGRAM_API_HASH requis.")

    start_health_server()

    if SESSION_STRING:
        logger.info("✅ Session → Mode USERBOT")
        run_userbot(API_ID, API_HASH, BOT_TOKEN, GROQ_API_KEY, SESSION_STRING, OWNER_ID)
        logger.warning("⚠️ Session invalide → bascule SETUP")

    if BOT_TOKEN:
        logger.info("ℹ️ Mode SETUP → /connect dans le bot")
        run_setup_bot(BOT_TOKEN, API_ID, API_HASH, OWNER_ID, PHONE_NUMBER)
    else:
        raise ValueError("TELEGRAM_SESSION ou TELEGRAM_BOT_TOKEN requis.")
