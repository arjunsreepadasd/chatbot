# 🤖 AI Chatbot – Quick Start Guide

A conversational AI chatbot powered by **Claude** (Anthropic), built with **Python Flask** and a clean dark-themed UI.

---

## ✅ Setup (5 minutes)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Add your API key
```bash
# Copy the example env file
cp .env.example .env

# Open .env and paste your Anthropic API key
# Get a free key at: https://console.anthropic.com/
```

### 3. Run the app
```bash
python app.py
```

### 4. Open in browser
Visit: **http://127.0.0.1:5000**

---

## 🎨 Customize Your Bot

Open `app.py` and edit these lines near the top:

```python
BOT_NAME    = "Aria"          # Change the bot's name
BOT_PERSONA = """..."""       # Change its personality and rules
```

---

## 📁 Project Structure

```
chatbot/
├── app.py                  # Flask backend + Claude API
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── .env                    # Your secrets (DO NOT commit this)
└── templates/
    └── index.html          # Chat UI (HTML + CSS + JS)
```

---

## 💡 Features

- ✅ AI-powered responses via Claude
- ✅ Remembers conversation history (last 20 turns)
- ✅ Custom bot name and persona
- ✅ Beautiful dark-themed chat UI
- ✅ Typing indicator
- ✅ Clear chat button
- ✅ Mobile responsive
