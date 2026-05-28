---
name: 3d-game-world-builder
description: Build real-time 3D game worlds from Xbox screenshots. Reads OneDrive Xbox Captures → Vision AI extracts game state → live ESPN data enriches worlds → Three.js renders interactive environments per sport (NBA 2K, Madden, NCAA). Asks clarifying questions via Telegram when confused. Toggle between game worlds. Personal use only — no official logos/team assets/IP infringement.
version: 1.0.0
author: Hermes Agent for Alexander Barnes
license: Personal use only
triggers:
  - "build worlds"
  - "3D game worlds"
  - "3D world builder"
  - "generate game world"
---

# 3D Game World Builder — Hermes Agent

## What This Is

A 5-phase pipeline that transforms your Xbox screenshots into walkable 3D environments:

```
Xbox screenshot
  → Stage 1: OneDrive monitor detects new screenshot
  → Stage 2: Vision AI extracts game state (Gemini Flash)
  → Stage 3: Live ESPN/Sports Reference data enriches it
  → Stage 4: Procedural 3D world generated (Three.js)
  → Stage 5: You walk through it, click on stats, ask questions
```

## Architecture

| Layer | Component | Output |
|---|---|---|
| **Detection** | `onedrive_monitor.py` | Screenshots in `data/screenshots/` |
| **Inference** | `vision_extractor.py` | Extracted game state in `data/extracted/` |
| **Enrichment** | `enrichment_engine.py` | Enriched data in `data/enriched/` |
| **Generation** | `world_generator.py` + React app | World specs in `data/worlds/` |
| **Interaction** | React-Three-Fiber app + Telegram bridge | Walkable 3D worlds |

## Quick Start

```bash
# Run the full pipeline
python3 /root/hermes-3d-worlds/run_pipeline.py full

# Run specific phase
python3 /root/hermes-3d-worlds/run_pipeline.py detect
python3 /root/hermes-3d-worlds/run_pipeline.py extract
python3 /root/hermes-3d-worlds/run_pipeline.py enrich
python3 /root/hermes-3d-worlds/run_pipeline.py generate

# Dry run — check screenshot queue
python3 /root/hermes-3d-worlds/run_pipeline.py check
```

## When It Asks Questions

The system asks clarifying questions via Telegram when:
- Confidence < 70% on game type or game mode
- 3+ key fields missing (quarter, teams, game mode, etc.)
- Season/week context unclear

Example: *"I'm 60% sure this is Q3 of a Park game. Is this MyCareer or Play Now mode? And which console — Series X or One?"*

Answer via Telegram → world regenerates with your answer.

## World Toggle

Three separate worlds, one app:
- **NBA 2K World** — basketball court, player grades, MyPark stats
- **Madden World** — football field, down/distance, franchise standings
- **NCAA World** — college football field, AP rankings, recruiting news

## IP/Legal Constraints

**CAN DO (definitely legal for personal use):**
- Extract numerical data from YOUR screenshots via AI → transformation, not copying
- Build 3D worlds with GENERIC PROCEDURAL GEOMETRY (original art)
- Use AI-generated avatars (generic player figures, not official face scans)
- Display PUBLIC ESPN/schedule data (no scraped game content)
- Pull your own stats, news feeds, schedules

**CANNOT DO (legally risky):**
- Official team logos, stadium photos, or copyrighted marks in 3D
- Player face scans reproduced in 3D (likeness rights)
- Distribute publicly without IP attorney review
- Claim official partnerships or App Store release without licensing

**Rule:** If you're not sure → ask before shipping. Personal use = zero enforcement risk.

## Cron Jobs (optional automation)

```bash
# Every 10 minutes: check for new screenshots → extract → enrich → generate
*/10 * * * * python3 /root/hermes-3d-worlds/run_pipeline.py detect && python3 /root/hermes-3d-worlds/run_pipeline.py extract

# Every 30 minutes: enrich existing → generate worlds
*/30 * * * * python3 /root/hermes-3d-worlds/run_pipeline.py enrich && python3 /root/hermes-3d-worlds/run_pipeline.py generate
```

## Files

| Path | Purpose |
|---|---|
| `/root/hermes-3d-worlds/config.json` | Game IDs, API thresholds |
| `/root/hermes-3d-worlds/run_pipeline.py` | End-to-end orchestration |
| `/root/hermes-3d-worlds/detection/onedrive_monitor.py` | OneDrive screenshot monitor |
| `/root/hermes-3d-worlds/inference/vision_extractor.py` | Gemini vision AI extraction |
| `/root/hermes-3d-worlds/enrichment/enrichment_engine.py` | ESPN/Sports Reference connector |
| `/root/hermes-3d-worlds/enrichment/run_enrichment.py` | Enrichment CLI |
| `/root/hermes-3d-worlds/generation/world_generator.py` | World spec JSON generator |
| `/root/hermes-3d-worlds/generation/react-worlds/` | React-Three-Fiber 3D app |
| `/root/hermes-3d-worlds/generation/react-worlds/server/telegramBridge.py` | Telegram clarification bridge |
| `/root/hermes-3d-worlds/data/screenshots/` | Downloaded Xbox screenshots |
| `/root/hermes-3d-worlds/data/extracted/` | Vision AI extraction results |
| `/root/hermes-3d-worlds/data/enriched/` | Live-data-enriched game state |
| `/root/hermes-3d-worlds/data/worlds/` | 3D world spec JSONs |

## Environment Variables Needed

```bash
MICROSOFT_CLIENT_ID=     # Azure AD app registration for OneDrive
MICROSOFT_CLIENT_SECRET= # Same Azure app
MICROSOFT_ACCESS_TOKEN=  # OAuth token (auto-refreshed)
MICROSOFT_REFRESH_TOKEN= # Refresh token for OneDrive Graph API
GEMINI_API_KEY=          # Google AI Studio key for Gemini Flash
TELEGRAM_BOT_TOKEN=      # Bot token for clarification bridge
TELEGRAM_CHAT_ID=        # Alexander's Telegram chat ID
VPS_BRIDGE_URL=          # VPS WebSocket bridge URL
```

## Cost

- Gemini Flash vision: ~$0.001/screenshot (first 60 min free)
- ESPN/Sports Reference APIs: Free (personal use)
- Vercel hosting: Free tier
- OneDrive API: Free (personal Microsoft account)
- **Est. monthly: ~$0.50-2.00** depending on screenshot volume

## Trigger

Say **"build worlds"** → dispatch all subagents in parallel, wait for results, report completion.

## Skills Required

- `subagent-driven-development` — for parallel subagent execution
- `screenshot-ocr` — for optional lower-cost OCR fallback
- `xbox-smartglass-automation` — Xbox context and setup
- `telegram-bot` — for clarification bridge

[END SKILL: 3d-game-world-builder]