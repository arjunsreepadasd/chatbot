# 🤖 AI Chatbot with Redis Caching

A conversational AI chatbot powered by **Google Gemini**, built with **Python Flask**, persistent conversation history via **Redis**, and a clean dark-themed UI.

---

## ✨ Why Redis?

| Feature | Without Redis ❌ | With Redis ✅ |
|---|---|---|
| Chat history | Lost on server restart | Survives restarts & crashes |
| Bot memory | Forgets context after reboot | Remembers everything |
| Response speed | Slower (live API call every time) | Instant for repeated questions (cache) |
| API costs | Higher (duplicate calls) | Lower (cached responses reused) |
| Multi-user | All history lost together | Clean per-user separation |

Redis stores two things:
1. **Conversation history** (`chat_history:<session_id>`, 7-day TTL) — so the bot picks up where you left off, even after a restart.
2. **API response cache** (`cache:<hash>`, 24-hour TTL) — identical questions return instantly without calling Gemini again.

---

## 🚀 3 Ways to Run

### Option 1 — Docker Compose (recommended, includes Redis automatically)

```bash
# 1. Copy and fill in your API key
cp .env.example .env
# Edit .env → set GEMINI_API_KEY

# 2. Start everything (Redis + Flask app)
docker-compose up --build

# 3. Open in browser
open http://localhost:5000
```

### Option 2 — Local (Python + local Redis)

```bash
# 1. Install Redis
#    macOS:  brew install redis && brew services start redis
#    Ubuntu: sudo apt install redis-server && sudo systemctl start redis

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy and fill in your API key
cp .env.example .env
# Edit .env → set GEMINI_API_KEY

# 4. Run the app
python app.py

# 5. Open in browser
open http://127.0.0.1:5000
```

### Option 3 — Local (no Redis)

Redis is **optional**. If it is not running, the app falls back gracefully to Flask sessions (history is not persisted across restarts, caching is disabled).

```bash
pip install -r requirements.txt
cp .env.example .env   # set GEMINI_API_KEY
python app.py
```

---

## 📁 Project Structure

```
chatbot/
├── app.py                  # Flask backend + Gemini API + Redis integration
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container image for the app
├── docker-compose.yml      # Orchestrates app + Redis
├── .env.example            # Environment variable template
├── .env                    # Your secrets (DO NOT commit this)
├── Makefile                # Helper commands
└── templates/
    └── index.html          # Chat UI (HTML + CSS + JS)
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and set at minimum `GEMINI_API_KEY`.

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Google Gemini API key |
| `SECRET_KEY` | `change-this-...` | Flask session secret |
| `REDIS_HOST` | `localhost` | Redis hostname (`redis` inside Docker) |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database index |
| `REDIS_PASSWORD` | *(empty)* | Redis password (if any) |
| `CACHE_TTL` | `86400` | API response cache lifetime (seconds) |
| `HISTORY_TTL` | `604800` | Conversation history lifetime (seconds) |

---

## 🔌 API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Chat UI |
| `POST` | `/chat` | Send a message, get a streaming response |
| `POST` | `/clear` | Clear the current session's history |
| `GET` | `/health` | Check app and Redis status |
| `GET` | `/cache-stats` | View cache hit/miss statistics |

### `/health` example response
```json
{
  "status": "ok",
  "redis": "connected"
}
```

### `/cache-stats` example response
```json
{
  "cache_hits": 42,
  "cache_misses": 10,
  "hit_rate_pct": 80.8,
  "redis_memory": "1.23M",
  "redis_status": "connected"
}
```

- **cache_hits** — how many times a response was served from Redis (no API call needed)
- **cache_misses** — how many times a fresh Gemini API call was made
- **hit_rate_pct** — percentage of requests served from cache

---

## ✅ How to Verify It Works

```bash
# 1. Check the app is running
curl http://localhost:5000/health

# 2. Check Redis is connected
# Expected: { "status": "ok", "redis": "connected" }

# 3. Send two identical messages and watch cache_hits increase
curl http://localhost:5000/cache-stats
```

---

## 🎨 Customize Your Bot

Open `app.py` and edit the constants near the top:

```python
BOT_NAME    = "Aria"          # Change the bot's name
BOT_PERSONA = """..."""       # Change its personality and rules
GEMINI_MODEL = "gemini-flash-latest"  # Swap the Gemini model
```

---

## 🔧 Troubleshooting

**Redis connection refused**
- Check Redis is running: `redis-cli ping` → should return `PONG`
- If using Docker Compose, make sure you ran `docker-compose up` (not just `python app.py`)
- The app works without Redis — you'll see `"redis": "unavailable"` in `/health`

**GEMINI_API_KEY missing**
- Make sure `.env` exists and contains `GEMINI_API_KEY=<your key>`
- Get a free key at [https://aistudio.google.com/](https://aistudio.google.com/)

**Port 5000 already in use**
- Change the host port in `docker-compose.yml`: `"5001:5000"`
- Or kill the existing process: `lsof -ti:5000 | xargs kill`

**History not persisting between sessions**
- Redis must be running and reachable
- Check `/health` — if `redis` shows `"unavailable"`, history falls back to Flask sessions (in-memory only)

