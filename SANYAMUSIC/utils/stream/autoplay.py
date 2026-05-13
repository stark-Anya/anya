# -----------------------------------------------
# SanyaMusic — AI-Powered Autoplay
# Groq AI + Strong duplicate detection
# -----------------------------------------------
import asyncio
import random
import json
import re
import aiohttp

from SANYAMUSIC import LOGGER, YouTube, app
from SANYAMUSIC.utils.database import get_cmode, get_lang
from SANYAMUSIC.utils.formatters import time_to_seconds
from strings import get_string
import config

# Per-chat history — title fingerprints
_played_history: dict = {}
_MAX_HISTORY = 80

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.1-8b-instant"

_FALLBACKS = [
    "top hindi songs", "bollywood hits",
    "best hindi songs", "popular songs 2024",
]

_SYSTEM_PROMPT = """You are a music analysis AI. Given a song title and artist, return YouTube search queries to find similar songs.
Return ONLY valid JSON:
{
  "mood": "romantic",
  "language": "hindi",
  "genre": "pop",
  "vibe": "love",
  "queries": ["query1", "query2", "query3"]
}
Rules: exactly 3 queries, include artist in first query if known, match language and mood. No markdown, no explanation."""


# ── Duplicate Detection ──────────────────────────────────────────────

_STOP_WORDS = {
    'the','a','an','and','or','but','in','on','at','to','for','of','with',
    'by','is','it','this','that','ka','ki','ke','hai','ho','na','aur','se',
    'me','mein','official','audio','video','lyrical','lyrics','full','song',
    'hd','ft','feat','version','remix','cover','new','latest','slow','reverb',
}

def _fingerprint(title: str) -> frozenset:
    """Title ke significant words — duplicate check ke liye."""
    title = title.lower()
    title = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', title)
    title = re.sub(r'[^\w\s]', ' ', title)
    words = frozenset(
        w for w in title.split()
        if w and w not in _STOP_WORDS and len(w) > 2
    )
    return words

def _is_duplicate(title: str, history: list) -> bool:
    """Ek bhi significant word match = duplicate."""
    new_fp = _fingerprint(title)
    if not new_fp:
        return False
    return any(new_fp & old_fp for old_fp in history)

def _mark_played(chat_id: int, title: str):
    if chat_id not in _played_history:
        _played_history[chat_id] = []
    _played_history[chat_id].append(_fingerprint(title))
    if len(_played_history[chat_id]) > _MAX_HISTORY:
        _played_history[chat_id] = _played_history[chat_id][-_MAX_HISTORY:]


# ── Artist Extract ───────────────────────────────────────────────────

def _extract_artist(title: str) -> str:
    if not title:
        return ""
    if " - " in title:
        parts = title.split(" - ")
        return parts[0].strip() if len(parts[0].split()) <= 3 else parts[-1].strip()
    if " | " in title:
        parts = [p.strip() for p in title.split(" | ")]
        for p in reversed(parts):
            if len(p.split()) <= 4:
                return p
    for sep in [" ft.", " feat."]:
        if sep in title.lower():
            idx = title.lower().index(sep)
            return title[idx + len(sep):].split("(")[0].strip()
    return " ".join(title.split()[:2])


# ── Groq AI ─────────────────────────────────────────────────────────

async def _ask_groq(title: str, artist: str) -> dict | None:
    groq_key = getattr(config, "GROQ_API_KEY", None)
    if not groq_key:
        return None
    try:
        payload = {
            "model": _GROQ_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f'Song: "{title}"\nArtist: "{artist or "Unknown"}"'},
            ],
            "temperature": 0.5,
            "max_tokens": 250,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _GROQ_URL, json=payload,
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                raw = data["choices"][0]["message"]["content"].strip()
                raw = raw.replace("```json", "").replace("```", "").strip()
                return json.loads(raw)
    except Exception as e:
        LOGGER(__name__).warning(f"Autoplay AI: {e}")
        return None


# ── Search ───────────────────────────────────────────────────────────

async def _search(queries: list, limit: int = 15) -> list:
    top2, rest = queries[:2], queries[2:]
    random.shuffle(rest)
    for q in top2 + rest:
        try:
            results = await YouTube.suggestions(q, limit=limit)
            if results:
                return results
        except Exception:
            continue
    return []


# ── Pick Song ────────────────────────────────────────────────────────

def _pick(suggestions: list, current_title: str, history: list) -> dict | None:
    current_fp = _fingerprint(current_title)
    candidates = []
    for song in suggestions:
        t = song.get("title", "")
        fp = _fingerprint(t)
        # Current song skip
        if current_fp & fp:
            continue
        # History duplicate skip
        if _is_duplicate(t, history):
            continue
        # Duration check
        dur = time_to_seconds(song.get("duration", "0:00"))
        if dur == 0 or dur > config.DURATION_LIMIT:
            continue
        candidates.append(song)

    if candidates:
        return random.choice(candidates)

    # History full — reset
    return None


# ── Main ─────────────────────────────────────────────────────────────

async def _autoplay_next(client, chat_id: int, last_played: dict):
    try:
        title = last_played.get("title", "") if last_played else ""
        original_chat_id = last_played.get("chat_id", chat_id) if last_played else chat_id
        artist = _extract_artist(title)
        history = _played_history.get(chat_id, [])

        LOGGER(__name__).info(f"Autoplay: chat={chat_id} | '{title}'")

        # AI queries
        ai_result = await _ask_groq(title, artist)
        if ai_result and ai_result.get("queries"):
            queries = ai_result["queries"]
            if artist and not any(artist.lower() in q.lower() for q in queries):
                queries.insert(0, f"{artist} songs")
            queries.extend(_FALLBACKS)
        else:
            queries = ([f"{artist} songs", f"{artist} hits"] if artist else []) + _FALLBACKS

        # Search
        suggestions = await _search(queries, limit=15)
        if not suggestions:
            LOGGER(__name__).error(f"Autoplay: No results for chat {chat_id}")
            return

        # Pick
        next_song = _pick(suggestions, title, history)
        if not next_song:
            # Reset history aur dobara try
            LOGGER(__name__).info(f"Autoplay: Resetting history for chat {chat_id}")
            _played_history[chat_id] = []
            next_song = _pick(suggestions, title, [])

        if not next_song:
            LOGGER(__name__).error(f"Autoplay: No suitable song for chat {chat_id}")
            return

        LOGGER(__name__).info(f"Autoplay: Selected '{next_song['title']}'")

        # Track fetch
        details = None
        for song in [next_song] + [s for s in suggestions if s != next_song]:
            if _is_duplicate(song.get("title", ""), _played_history.get(chat_id, [])):
                continue
            try:
                details, _ = await YouTube.track(song["id"], True)
                next_song = song
                break
            except Exception:
                continue

        if not details:
            LOGGER(__name__).error("Autoplay: Track fetch failed")
            return

        _mark_played(chat_id, next_song["title"])

        # Channel mode
        chat_id_for_stream = chat_id
        channel = await get_cmode(chat_id)
        if channel:
            chat_id_for_stream = channel

        language = await get_lang(chat_id)
        _ = get_string(language)

        # Mood text
        mood_text = ""
        if ai_result:
            mood = ai_result.get("mood", "")
            vibe = ai_result.get("vibe", "")
            if mood:
                mood_text = f"\n🎭 <i>{mood.capitalize()}{' • ' + vibe.capitalize() if vibe else ''}</i>"

        # Notification — 20 sec baad delete
        msg = None
        try:
            msg = await app.send_message(
                original_chat_id,
                f"🔄 <b>Autoplay</b>\n\n"
                f"🎵 <b>{next_song['title']}</b>\n"
                f"🎤 <i>{artist or 'Auto Selected'}</i>"
                f"{mood_text}",
            )
            async def _del():
                await asyncio.sleep(20)
                try:
                    await msg.delete()
                except Exception:
                    pass
            asyncio.create_task(_del())
        except Exception:
            pass

        # Play
        try:
            from SANYAMUSIC.utils.stream.stream import stream
            await stream(
                app, _, msg, app.id, details,
                chat_id_for_stream, "Autoplay", original_chat_id,
                video=None, streamtype="youtube", forceplay=True,
            )
        except Exception as e:
            LOGGER(__name__).error(f"Autoplay: Stream error: {e}")
            if msg:
                try:
                    await msg.delete()
                except Exception:
                    pass

    except Exception as e:
        LOGGER(__name__).error(f"Autoplay: Fatal: {e}")
