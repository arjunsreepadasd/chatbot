"""
AI Chatbot - Flask Backend
Powered by Google Gemini API with streaming and Redis caching
"""

from flask import Flask, request, jsonify, render_template, session, Response, stream_with_context
from google import genai
from google.genai import types
import os
import json
import hashlib
import redis
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production-abc123")

# ─────────────────────────────────────────────
# 🤖 CUSTOMIZE YOUR BOT HERE
# ─────────────────────────────────────────────
BOT_NAME    = "Aria"
BOT_PERSONA = """You are Aria, a friendly, helpful, and witty AI assistant.
Your personality:
- Warm and approachable — you make users feel comfortable
- Concise but thorough — you give clear answers without rambling
- Occasionally light-hearted, but always professional

Rules:
- If you don't know something, say so honestly
- Keep responses conversational and easy to read
- Use bullet points or numbered lists when it helps clarity
"""
GEMINI_MODEL = "gemini-flash-latest"
# ─────────────────────────────────────────────

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB   = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

# TTL settings
CACHE_TTL   = int(os.environ.get("CACHE_TTL", 86400))    # 24 hours for API response cache
HISTORY_TTL = int(os.environ.get("HISTORY_TTL", 604800)) # 7 days for conversation history

# Maximum number of messages kept in history (user + model turns combined)
MAX_HISTORY_MESSAGES = 40

# In-memory stats counters (reset on restart)
_cache_hits   = 0
_cache_misses = 0

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# ─────────────────────────────────────────────
# Redis helpers
# ─────────────────────────────────────────────

def _build_cache_key(message: str, history_key: str) -> str:
    """Build the Redis key for an API response cache entry."""
    return "cache:" + hashlib.sha256(f"{history_key}:{message}".encode()).hexdigest()


def get_redis():
    """Return a Redis client, or None if Redis is unavailable."""
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        r.ping()
        return r
    except Exception:
        return None


def get_user_history(session_id: str) -> list:
    """Load conversation history from Redis; fall back to session."""
    r = get_redis()
    if r:
        raw = r.get(f"chat_history:{session_id}")
        if raw:
            return json.loads(raw)
    return session.get("history", [])


def save_user_history(session_id: str, history: list) -> None:
    """Persist conversation history to Redis and session (fallback)."""
    # Keep only the last MAX_HISTORY_MESSAGES messages
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    session["history"] = trimmed
    r = get_redis()
    if r:
        r.setex(f"chat_history:{session_id}", HISTORY_TTL, json.dumps(trimmed))


def get_cached_response(message: str, history_key: str) -> str | None:
    """Return a cached API response for identical (message, history) pairs."""
    global _cache_hits, _cache_misses
    r = get_redis()
    if not r:
        _cache_misses += 1
        return None
    value = r.get(_build_cache_key(message, history_key))
    if value:
        _cache_hits += 1
        return value
    _cache_misses += 1
    return None


def set_cached_response(message: str, history_key: str, response: str) -> None:
    """Store an API response in the cache."""
    r = get_redis()
    if not r:
        return
    r.setex(_build_cache_key(message, history_key), CACHE_TTL, response)


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    session.setdefault("session_id", os.urandom(16).hex())
    session["history"] = []
    return render_template("index.html", bot_name=BOT_NAME)


@app.route("/chat", methods=["POST"])
def chat():
    global _cache_hits

    data = request.get_json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY is missing. Add it to your .env file."}), 401

    session_id = session.setdefault("session_id", os.urandom(16).hex())
    history = get_user_history(session_id)

    # Build a short key for the cache lookup (hash of existing history messages)
    history_key = hashlib.sha256(json.dumps(history).encode()).hexdigest()

    # Check cache for an identical (context + message) pair
    cached = get_cached_response(user_message, history_key)
    if cached:
        history.append({"role": "user",  "parts": [user_message]})
        history.append({"role": "model", "parts": [cached]})
        save_user_history(session_id, history)

        def stream_cached():
            yield f"data: {json.dumps({'token': cached})}\n\n"
            yield f"data: {json.dumps({'done': True, 'cached': True})}\n\n"

        return Response(stream_with_context(stream_cached()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Build contents for Gemini
    contents = []
    for msg in history:
        contents.append(types.Content(role=msg["role"], parts=[types.Part(text=msg["parts"][0])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    # Save user message immediately
    history.append({"role": "user", "parts": [user_message]})
    save_user_history(session_id, history)

    def generate():
        full_reply = ""
        try:
            stream = client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=BOT_PERSONA,
                    max_output_tokens=1024,
                ),
            )
            for chunk in stream:
                if chunk.text:
                    full_reply += chunk.text
                    yield f"data: {json.dumps({'token': chunk.text})}\n\n"

            # Save assistant reply and cache the response
            hist = get_user_history(session_id)
            hist.append({"role": "model", "parts": [full_reply]})
            save_user_history(session_id, hist)
            set_cached_response(user_message, history_key, full_reply)

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            error_msg = str(e)
            print(f"[Gemini ERROR]: {error_msg}")
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/clear", methods=["POST"])
def clear_history():
    session_id = session.get("session_id")
    session["history"] = []
    if session_id:
        r = get_redis()
        if r:
            r.delete(f"chat_history:{session_id}")
    return jsonify({"status": "ok"})


@app.route("/health")
def health():
    """Health check — reports Redis connectivity."""
    r = get_redis()
    redis_ok = r is not None
    return jsonify({
        "status": "ok",
        "redis": "connected" if redis_ok else "unavailable (running without cache)",
    })


@app.route("/cache-stats")
def cache_stats():
    """Return cache hit/miss statistics."""
    r = get_redis()
    info = {}
    if r:
        try:
            redis_info = r.info("memory")
            info["used_memory_human"] = redis_info.get("used_memory_human", "N/A")
        except Exception:
            pass
    total = _cache_hits + _cache_misses
    hit_rate = round((_cache_hits / total) * 100, 1) if total else 0
    return jsonify({
        "cache_hits":   _cache_hits,
        "cache_misses": _cache_misses,
        "hit_rate_pct": hit_rate,
        "redis_memory": info.get("used_memory_human", "N/A"),
        "redis_status": "connected" if r else "unavailable",
    })


if __name__ == "__main__":
    if not os.environ.get("GEMINI_API_KEY"):
        print("\n⚠️  GEMINI_API_KEY not set! Add it to your .env file.\n")
    else:
        r = get_redis()
        if r:
            print(f"\n✅ {BOT_NAME} is ready with Redis! Visit: http://127.0.0.1:5000\n")
        else:
            print(f"\n✅ {BOT_NAME} is ready (no Redis — running without cache). Visit: http://127.0.0.1:5000\n")
    app.run(debug=True)
