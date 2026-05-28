# Hermes 3D Game World Builder

Transform Xbox screenshots into walkable 3D game environments.

## What It Does

```
Your Xbox screenshot (OneDrive)
  → Vision AI extracts game state (Gemini Flash)
  → Live ESPN data enriches it
  → Three.js renders interactive 3D world
  → Walk through it, click stats, toggle between NBA 2K / Madden / NCAA
```

## Architecture (5 Phases)

| Phase | Component | Output |
|---|---|---|
| **Detection** | `detection/onedrive_monitor.py` | Xbox screenshots queued |
| **Inference** | `inference/vision_extractor.py` | Structured game state (JSON) |
| **Enrichment** | `enrichment/enrichment_engine.py` | Live ESPN/Sports Reference data |
| **Generation** | `generation/world_generator.py` + React app | 3D world spec + rendered world |
| **Interaction** | `server/telegramBridge.py` + React hooks | Walkable UI + clarification bridge |

## Quick Start

```bash
# Run full pipeline
python3 run_pipeline.py full

# Stage-by-stage
python3 run_pipeline.py detect    # OneDrive → screenshots
python3 run_pipeline.py extract  # Vision AI → game state
python3 run_pipeline.py enrich   # ESPN/schedules/news
python3 run_pipeline.py generate # 3D world
```

## 3D App (React-Three-Fiber)

```bash
cd generation/react-worlds
npm install
npm run dev      # development
npm run build    # production
```

Deployed at: **https://hermes-3d-worlds.vercel.app**

## Environment Variables

```bash
MICROSOFT_CLIENT_ID=      # Azure AD — OneDrive Graph API
MICROSOFT_CLIENT_SECRET=
MICROSOFT_ACCESS_TOKEN=
MICROSOFT_REFRESH_TOKEN=
GEMINI_API_KEY=          # Google AI Studio
TELEGRAM_BOT_TOKEN=      # Bot for clarification questions
TELEGRAM_CHAT_ID=        # Your Telegram chat ID
```

## World Toggle

Three separate worlds in one app:
- **NBA 2K World** — basketball court, player grades, MyPark stats
- **Madden World** — football field, down/distance, franchise standings
- **NCAA World** — college football field, AP rankings, recruiting news

## Clarification Questions

When confidence < 70%, the system asks via Telegram:
> *"I'm 60% sure this is Q3 Park game. Is this MyCareer or Play Now? Which console — Series X or One?"*

Answer via Telegram → world regenerates with your correction.

## IP/Legal Constraints (Personal Use Only)

- ✅ Extract YOUR stats via AI → transformation, not copying
- ✅ Generic procedural geometry → original art
- ✅ AI-generated avatars → not official face scans
- ✅ Public ESPN/Schedule data → no scraped content
- ❌ Official team logos or trademarks in 3D
- ❌ Player face scans reproduced
- ❌ Public distribution without IP attorney review

## Cron (Optional Automation)

```bash
# Every 10 min: check screenshots
*/10 * * * * python3 /root/hermes-3d-worlds/run_pipeline.py detect

# Every 30 min: enrich + generate
*/30 * * * * python3 /root/hermes-3d-worlds/run_pipeline.py enrich
```

## Tech Stack

- **VPS:** Hermes Agent on Hostinger VPS
- **Vision:** Google Gemini 2.0 Flash (Azure AI)
- **Data:** ESPN API, Sports Reference (free, personal use)
- **3D:** Three.js + React-Three-Fiber + Zustand
- **Hosting:** Vercel (React app)
- **Messaging:** Telegram bot bridge

## Cost Estimate

- Gemini Flash vision: ~$0.001/screenshot
- Vercel: Free tier
- ESPN/Sports Reference: Free
- **Total: ~$0.50-2.00/month**

## Repository

https://github.com/Vik6191003/hermes-3d-worlds