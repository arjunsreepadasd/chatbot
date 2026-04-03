"""
AI Chatbot - Flask Backend
Powered by Google Gemini API with streaming
"""

from flask import Flask, request, jsonify, render_template, session, Response, stream_with_context
from google import genai
from google.genai import types
import os
import json
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

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


@app.route("/")
def index():
    session["history"] = []
    return render_template("index.html", bot_name=BOT_NAME)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY is missing. Add it to your .env file."}), 401

    # Build conversation history
    history = session.get("history", [])
    contents = []
    for msg in history:
        role = msg["role"]
        text = msg["parts"][0]
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    # Save user message to session now
    history.append({"role": "user", "parts": [user_message]})
    session["history"] = history

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

            # Save assistant reply to session
            hist = session.get("history", [])
            hist.append({"role": "model", "parts": [full_reply]})
            session["history"] = hist[-40:]
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            error_msg = str(e)
            print(f"[Gemini ERROR]: {error_msg}")
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/clear", methods=["POST"])
def clear_history():
    session["history"] = []
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    if not os.environ.get("GEMINI_API_KEY"):
        print("\n⚠️  GEMINI_API_KEY not set! Add it to your .env file.\n")
    else:
        print(f"\n✅ {BOT_NAME} is ready! Visit: http://127.0.0.1:5000\n")
    app.run(debug=True)
