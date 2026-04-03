"""
AI Chatbot - Flask Backend
Powered by Google Gemini API with streaming
Redis-backed caching and conversation history
"""

from flask import Flask, request, jsonify, render_template, session, Response, stream_with_context
from google import genai
from google.genai import types
import os
import json
import uuid
from dotenv import load_dotenv

import cache as cache_module

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

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def _get_session_id() -> str:
    """Return a stable session ID, creating one if needed."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


@app.route("/")
def index():
    sid = _get_session_id()
    cache_module.clear_history(sid)
    return render_template("index.html", bot_name=BOT_NAME)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY is missing. Add it to your .env file."}), 401

    sid     = _get_session_id()
    history = cache_module.get_history(sid)

    # ── Cache lookup ──────────────────────────────────────────────────────────
    cached = cache_module.get_cached_response(sid, user_message, history)
    if cached:
        # Stream the cached reply in word-sized chunks to give the same
        # progressive feel as a live streamed response.
        def _replay():
            words = cached.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                yield f"data: {json.dumps({'token': token, 'cached': True})}\n\n"
            new_history = history + [
                {"role": "user",  "parts": [user_message]},
                {"role": "model", "parts": [cached]},
            ]
            cache_module.set_history(sid, new_history)
            yield f"data: {json.dumps({'done': True})}\n\n"

        return Response(
            stream_with_context(_replay()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Build Gemini content list ─────────────────────────────────────────────
    contents = []
    for msg in history:
        role = msg["role"]
        text = msg["parts"][0]
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    # Snapshot history before the user turn for cache keying, then persist
    history_before_user = list(history)
    history.append({"role": "user", "parts": [user_message]})
    cache_module.set_history(sid, history)

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

            # Save assistant reply using the local history snapshot to avoid
            # a redundant Redis round-trip.
            history.append({"role": "model", "parts": [full_reply]})
            cache_module.set_history(sid, history)
            cache_module.set_cached_response(sid, user_message, history_before_user, full_reply)
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            error_msg = str(e)
            print(f"[Gemini ERROR]: {error_msg}")
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/clear", methods=["POST"])
def clear_history():
    sid = _get_session_id()
    cache_module.clear_history(sid)
    return jsonify({"status": "ok"})


@app.route("/cache-stats")
def cache_stats():
    """Return cache hit/miss statistics and Redis availability."""
    return jsonify(cache_module.get_stats())


@app.route("/health")
def health():
    """Lightweight health-check endpoint."""
    return jsonify({
        "status":          "ok",
        "redis_available": cache_module.is_available(),
        "bot_name":        BOT_NAME,
    })


if __name__ == "__main__":
    if not os.environ.get("GEMINI_API_KEY"):
        print("\n⚠️  GEMINI_API_KEY not set! Add it to your .env file.\n")
    else:
        redis_status = "✅ connected" if cache_module.is_available() else "⚠️  unavailable (using in-memory fallback)"
        print(f"\n✅ {BOT_NAME} is ready! Visit: http://127.0.0.1:5000")
        print(f"   Redis: {redis_status}\n")
    app.run(debug=True)

