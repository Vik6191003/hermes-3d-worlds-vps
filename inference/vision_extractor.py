"""
Phase 2 — Inference: Vision AI Game State Extraction
Uses Gemini to extract structured game data from screenshots.
Asks clarifying questions via Telegram when confidence is low.
"""

import os
import json
import re
import base64
import requests
from datetime import datetime, timezone

BASE = "/root/hermes-3d-worlds"
EXTRACTED_DIR = f"{BASE}/data/extracted"

# Game-specific extraction prompts
GAME_PROMPTS = {
    "nba_2k": """You are analyzing an NBA 2K (basketball video game) screenshot.
Extract ALL of the following with HIGH PRECISION:
- game_quarter: "Q1", "Q2", "Q3", "Q4", "OT" or null
- time_remaining: MM:SS format in the quarter
- home_team: text team name (e.g., "Lakers", "Celtics")
- away_team: text team name
- home_score: integer
- away_score: integer  
- game_mode: "MyCareer", "MyTeam", "Blacktop", "Park", "PlayNow", "League", or null
- myplayer_position: e.g., "PG", "SG", "SF", "PF", "C", or null
- myplayer_grade: letter grade like "A+", "B-", or null
- arena_name: text arena name or null
- difficulty: "Rookie", "Pro", "All-Star", "Superstar", "Legend", or null
- console_generation: "Series X", "Series S", or "One"
- extraction_confidence: 0.0-1.0 for overall quality

Format your response as valid JSON only. Use null for unknown fields.
Example: {"game_quarter": "Q3", "time_remaining": "05:32", "home_team": "Lakers", "away_team": "Celtics", "home_score": 87, "away_score": 82, "game_mode": "Park", "myplayer_position": "PG", "myplayer_grade": "A-", "arena_name": null, "difficulty": "Pro", "console_generation": "Series X", "extraction_confidence": 0.82}""",

    "madden": """You are analyzing a Madden NFL (football video game) screenshot.
Extract ALL of the following with HIGH PRECISION:
- game_quarter: "Q1", "Q2", "Q3", "Q4", "OT" or null
- time_remaining: MM:SS format in the quarter
- home_team: text team name (e.g., "Chiefs", "Eagles")
- away_team: text team name
- home_score: integer
- away_score: integer
- down_and_distance: e.g., "3rd and 7", "1st and 10", or null
- field_position: e.g., "OPP 35", "OWN 20", or null
- game_mode: "Franchise", "Ultimate Team", "Face of the Franchise", "Play Now", or null
- season_year: e.g., "2025", "2024" or null
- season_week: integer 1-53 or null
- console_generation: "Series X", "Series S", or "One"
- extraction_confidence: 0.0-1.0 for overall quality

Format response as valid JSON only. Use null for unknown fields.""",

    "ncaa": """You are analyzing an NCAA Football video game screenshot.
Extract ALL of the following with HIGH PRECISION:
- game_quarter: "Q1", "Q2", "Q3", "Q4", "OT" or null
- time_remaining: MM:SS format in the quarter
- home_team: text team name (e.g., "Georgia", "Alabama")
- away_team: text team named
- home_score: integer
- away_score: integer
- down_and_distance: e.g., "3rd and 5", or null
- field_position: e.g., "OPP 40", or null
- game_mode: "Campus Dakota", "Dynasty", "Road to Glory", "Play Now", or null
- console_generation: "Series X", "Series S", or "One"
- conference: text conference name or null
- ap_rankings: integer ranking or null
- extraction_confidence: 0.0-1.0 for overall quality

Format response as valid JSON only. Use null for unknown fields."""
}

GAME_CONFIDENCE_THRESHOLDS = {
    "nba_2k": 0.7,
    "madden": 0.7,
    "ncaa": 0.7
}


class VisionExtractor:
    def __init__(self):
        self.config = json.load(open(f"{BASE}/config.json"))
        self.vision_config = self.config["vision"]
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self.clarification_history = f"{BASE}/inference/clarification_history.json"
        self._init_clarification_store()

    def _init_clarification_store(self):
        if not os.path.exists(self.clarification_history):
            with open(self.clarification_history, "w") as f:
                json.dump([], f)

    def _detect_game_type(self, image_path):
        """Fast pre-check to route to correct prompt."""
        if not self.gemini_api_key:
            return "nba_2k"
        try:
            with open(image_path, "rb") as f:
                img_data = f.read()
            b64 = base64.b64encode(img_data).decode()
            mime = "image/png" if image_path.endswith(".png") else "image/jpeg"
            quick_prompt = "Is this NBA 2K (basketball), Madden (football), or NCAA (college football)? Reply with one word only."
            data = {
                "contents": [{"parts": [
                    {"text": quick_prompt},
                    {"inline_data": {"mimeType": mime, "data": b64}}
                ]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 20}
            }
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}",
                json=data, timeout=20
            )
            if r.ok:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"].lower()
                if "basketball" in text or "nba" in text:
                    return "nba_2k"
                elif "ncaa" in text or "college" in text:
                    return "ncaa"
                elif "madden" in text or "football" in text:
                    return "madden"
        except Exception as e:
            print(f"Game type detection failed: {e}")
        return "nba_2k"

    def _extract_with_gemini(self, image_path, game_type):
        """Call Gemini with game-specific prompt, return extracted JSON."""
        if not self.gemini_api_key:
            return {"error": "GEMINI_API_KEY not set", "game_type": game_type,
                    "extraction_confidence": 0.0}
        try:
            with open(image_path, "rb") as f:
                img_data = f.read()
            b64 = base64.b64encode(img_data).decode()
            mime = "image/png" if image_path.endswith(".png") else "image/jpeg"
            prompt = GAME_PROMPTS.get(game_type, GAME_PROMPTS["nba_2k"])
            data = {
                "contents": [{"parts": [
                    {"text": prompt},
                    {"inline_data": {"mimeType": mime, "data": b64}}
                ]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 512}
            }
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}",
                json=data, timeout=30
            )
            if r.ok:
                resp = r.json()
                raw_text = resp["candidates"][0]["content"]["parts"][0]["text"]
                # Parse JSON from markdown code block or bare
                match = re.search(r'\{[\s\S]+\}', raw_text)
                if match:
                    return json.loads(match.group())
                return {"raw_response": raw_text, "game_type": game_type,
                        "extraction_confidence": 0.0}
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse failed: {e}", "game_type": game_type,
                    "extraction_confidence": 0.0}
        except Exception as ex:
            return {"error": str(ex), "game_type": game_type,
                    "extraction_confidence": 0.0}
        return {"error": "unknown", "game_type": game_type}

    def _build_clarification_question(self, result, game_type):
        """Build a human-readable question for missing/uncertain fields."""
        questions = []
        if not result.get("game_quarter") or not result.get("time_remaining"):
            questions.append("quarter and time remaining")
        if not result.get("home_team") or not result.get("away_team"):
            questions.append("both team names")
        if not result.get("game_mode"):
            questions.append("game mode (MyCareer, Park, Franchise, etc.)")
        if not result.get("extraction_confidence"):
            questions.append("overall game situation")
        return "I need help identifying: " + ", ".join(questions[:3])

    def extract(self, image_path, screenshot_hash):
        """Main extraction pipeline."""
        print(f"[{datetime.now().isoformat()}] Extracting from {image_path}")
        game_type = self._detect_game_type(image_path)
        print(f"  Game type: {game_type}")
        result = self._extract_with_gemini(image_path, game_type)
        result["processed_at"] = datetime.now(timezone.utc).isoformat()
        result["screenshot_hash"] = screenshot_hash
        result["game_type"] = game_type

        os.makedirs(EXTRACTED_DIR, exist_ok=True)
        out_path = f"{EXTRACTED_DIR}/{screenshot_hash}.json"
        conf = result.get("extraction_confidence", 0.0)
        print(f"  Confidence: {conf:.0%}")

        threshold = GAME_CONFIDENCE_THRESHOLDS.get(game_type, 0.7)
        uncertain_fields = [k for k, v in result.items()
                            if v is None and k not in ("arena_name", "ap_rankings", "difficulty", "season_year")]

        if conf < threshold or len(uncertain_fields) >= 3:
            result["needs_clarification"] = True
            result["clarification_reason"] = self._build_clarification_question(result, game_type)
            result["status"] = "pending_clarification"
            print(f"  Clarification needed: {result['clarification_reason']}")
        else:
            result["needs_clarification"] = False
            result["status"] = "ready_for_enrichment"
            print(f"  Ready for enrichment")

        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    def apply_answer(self, screenshot_hash, answer_text):
        """User answered a clarification question — update extraction."""
        history = json.load(open(self.clarification_history))
        updated = False
        for item in reversed(history):
            if item["screenshot_hash"] == screenshot_hash and item["answer"] is None:
                item["answer"] = answer_text
                item["answered_at"] = datetime.now(timezone.utc).isoformat()
                updated = True
                break
        if updated:
            with open(self.clarification_history, "w") as f:
                json.dump(history, f, indent=2)

        extracted = json.load(open(f"{EXTRACTED_DIR}/{screenshot_hash}.json"))
        extracted["clarification_answer"] = answer_text
        extracted["status"] = "ready_for_enrichment"
        extracted["needs_clarification"] = False
        with open(f"{EXTRACTED_DIR}/{screenshot_hash}.json", "w") as f:
            json.dump(extracted, f, indent=2)
        return extracted

    def get_pending_clarifications(self):
        """Return all extractions awaiting user input."""
        pending = []
        for fname in os.listdir(EXTRACTED_DIR):
            if fname.endswith(".json"):
                d = json.load(open(f"{EXTRACTED_DIR}/{fname}"))
                if d.get("needs_clarification"):
                    pending.append(d)
        return pending


if __name__ == "__main__":
    import sys
    extractor = VisionExtractor()
    if len(sys.argv) > 1:
        import hashlib
        with open(sys.argv[1], "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()[:16]
        result = extractor.extract(sys.argv[1], h)
        print(json.dumps(result, indent=2))
    else:
        pending = extractor.get_pending_clarifications()
        print(f"Pending clarifications: {len(pending)}")
        for p in pending:
            print(f"  {p['screenshot_hash']}: {p.get('clarification_reason', '')}")