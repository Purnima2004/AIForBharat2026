#  AI Video Generation Studio

Transform any idea into a stunning AI video — powered by **Google Gemini**.

## How It Works

```
Your Prompt
    ↓  Gemini Flash enhances it (cinematic details, mood, camera moves)
    ↓  Imagen 4 generates 4 unique visual scenes
    ↓  Veo 2 creates image-to-video (or FFmpeg/GIF fallback)
    ↓  Download your video!
```

---

## Prerequisites

| Tool | Download |
|------|----------|
| Python 3.10+ | [python.org](https://python.org) |
| Node.js 18+ | [nodejs.org](https://nodejs.org) — for n8n |
| FFmpeg (optional) | [ffmpeg.org](https://ffmpeg.org) — better video quality |
| Gemini API Key | [aistudio.google.com](https://aistudio.google.com) |

---

## Quick Start

### 1. Set Your API Key

Edit `.env` and put your Gemini API key:

```
GEMINI_API_KEY=AIza...your-key-here...
```

### 2. Run the App

```bat
start.bat
```

That's it! Your browser will open at `http://localhost:5000`.

---

## Manual Setup (if start.bat fails)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Start n8n (optional — the app works without it)
npx n8n

# Start Flask backend
python app.py
```

Open `http://localhost:5000` in your browser.

---

## n8n Workflow Setup (Optional)

The app runs a **built-in Python pipeline** by default (no n8n needed).
If you want to use the n8n visual workflow instead:

1. Start n8n: `npx n8n`
2. Open `http://localhost:5678`
3. Import `n8n_workflow.json` (Settings → Import from file)
4. Add your **Gemini API key** to n8n Variables (`GEMINI_API_KEY`)
5. Activate the workflow
6. Update `.env`: set `N8N_WEBHOOK_URL=http://localhost:5678/webhook/ai-video`

---

## API Used

| API | Purpose | Free? |
|-----|---------|-------|
| `gemini-2.0-flash` | Prompt enhancement | Free tier |
| `imagen-4.0-generate-001` | 4 image generation | Free tier |
| `veo-2.0-generate-001` | Image → Video | Paid (free GIF fallback included) |

---

## Output Files

All generated images and videos are saved in the `outputs/` folder.

---

## Project Structure

```
f:\bharat for ai\
├── app.py              ← Flask backend + full AI pipeline
├── .env                ← Your API keys (DO NOT commit this)
├── requirements.txt
├── n8n_workflow.json   ← Import into n8n (optional)
├── start.bat           ← One-click startup
├── static/
│   ├── index.html      ← Frontend UI
│   ├── style.css       ← Glassmorphism design
│   └── app.js          ← Prompt → poll → result logic
└── outputs/            ← Generated images & videos
```
