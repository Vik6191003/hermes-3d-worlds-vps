"""
Phase 3 — Enrichment: Live Sports Data Enrichment Engine
Fetches real-world data to enrich extracted game screenshots.
Works with: NBA 2K, Madden NFL, NCAA Football screenshots.
"""

import os
import json
import re
import hashlib
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

import requests
import feedparser

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE = "/root/hermes-3d-worlds"
CONFIG_PATH = f"{BASE}/config.json"
EXTRACTED_DIR = f"{BASE}/data/extracted"
ENRICHED_DIR = f"{BASE}/data/enriched"
os.makedirs(ENRICHED_DIR, exist_ok=True)

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(f"{BASE}/logs/enrichment.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("enrichment")


# ═══════════════════════════════════════════════════════════════════════════════
# ESPN API Connector
# ═══════════════════════════════════════════════════════════════════════════════

class ESPNConnector:
    """Fetches live scores, schedules, standings from ESPN public API."""

    SPORT_MAP = {
        "nba_2k":     {"espn": "basketball/nba",     "name": "NBA"},
        "madden":     {"espn": "football/nfl",        "name": "NFL"},
        "ncaa":       {"espn": "football/college-football", "name": "College Football"},
        "basketball": {"espn": "basketball/nba",      "name": "NBA"},
        "football":   {"espn": "football/nfl",        "name": "NFL"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.espn_base = self.config.get("espn_api_base", "https://site.api.espn.com/apis/site/v2")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Hermes-3D-Worlds/1.0"})
        self.cache = {}   # simple time-cached results

    def _cache_get(self, key: str, ttl_seconds: int = 120) -> Optional[Any]:
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry["ts"] < ttl_seconds:
                return entry["data"]
        return None

    def _cache_set(self, key: str, data: Any):
        self.cache[key] = {"ts": time.time(), "data": data}

    def fetch_scoreboard(self, sport: str) -> dict:
        """Fetch current scoreboard for a sport."""
        sport_key = self.SPORT_MAP.get(sport, {"espn": "basketball/nba"})["espn"]
        cache_key = f"scoreboard:{sport_key}"
        
        cached = self._cache_get(cache_key, ttl_seconds=60)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached

        url = f"{self.espn_base}/sports/{sport_key}/scoreboard"
        try:
            resp = self.session.get(url, timeout=15)
            if resp.ok:
                data = resp.json()
                self._cache_set(cache_key, data)
                logger.info(f"Fetched {sport_key} scoreboard: {len(data.get('events', []))} events")
                return data
            else:
                logger.warning(f"ESPN scoreboard failed ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            logger.error(f"ESPN scoreboard error: {e}")
        return {"events": []}

    def fetch_schedule(self, sport: str, limit: int = 25) -> dict:
        """Fetch upcoming schedule for a sport."""
        sport_key = self.SPORT_MAP.get(sport, {"espn": "basketball/nba"})["espn"]
        cache_key = f"schedule:{sport_key}"
        
        cached = self._cache_get(cache_key, ttl_seconds=300)
        if cached is not None:
            return cached

        url = f"{self.espn_base}/sports/{sport_key}/scoreboard?dates={datetime.now().strftime('%Y%m%d')}"
        try:
            resp = self.session.get(url, timeout=15)
            if resp.ok:
                data = resp.json()
                self._cache_set(cache_key, data)
                return data
        except Exception as e:
            logger.error(f"ESPN schedule error: {e}")
        return {"events": []}

    def fetch_standings(self, sport: str) -> dict:
        """Fetch current standings."""
        sport_key = self.SPORT_MAP.get(sport, {"espn": "basketball/nba"})["espn"]
        url = f"{self.espn_base}/sports/{sport_key}/standings"
        try:
            resp = self.session.get(url, timeout=15)
            if resp.ok:
                return resp.json()
        except Exception as e:
            logger.error(f"ESPN standings error: {e}")
        return {}

    def get_team_info(self, sport: str, team_name: str) -> Optional[dict]:
        """Look up a specific team's info from today's scoreboard."""
        scoreboard = self.fetch_scoreboard(sport)
        for event in scoreboard.get("events", []):
            for competitor in event.get("competitions", [{}])[0].get("competitors", []):
                team = competitor.get("team", {})
                if team_name.lower() in team.get("displayName", "").lower() or \
                   team_name.lower() in team.get("shortDisplayName", "").lower():
                    return team
        return None

    def extract_live_data_for_teams(self, sport: str, team_names: List[str]) -> dict:
        """Extract live scores and stats for specific teams."""
        scoreboard = self.fetch_scoreboard(sport)
        results = {"teams": {}, "games": []}
        
        team_lower = [t.lower() for t in team_names]
        
        for event in scoreboard.get("events", []):
            competition = event.get("competitions", [{}])[0]
            for competitor in competition.get("competitors", []):
                team = competitor.get("team", {})
                team_short = team.get("shortDisplayName", "").lower()
                
                if any(t in team_short for t in team_lower):
                    results["teams"][team.get("displayName", "")] = {
                        "score": competitor.get("score", "0"),
                        "home_away": competitor.get("homeAway", "unknown"),
                        "winner": competitor.get("winner", False),
                        "record": competitor.get("records", [{}])[0].get("summary", ""),
                        "logo": team.get("logo", ""),
                    }
            
            # Check if any tracked team is in this game
            comp_teams = [c.get("team", {}).get("shortDisplayName", "").lower() 
                          for c in competition.get("competitors", [])]
            if any(any(t in ct for t in team_lower) for ct in comp_teams):
                results["games"].append({
                    "id": event.get("id", ""),
                    "name": event.get("name", ""),
                    "status": event.get("status", {}).get("type", {}).get("description", ""),
                    "date": event.get("date", ""),
                    "competitors": [
                        {"name": c.get("team", {}).get("displayName", ""),
                         "score": c.get("score", ""),
                         "home_away": c.get("homeAway", "")}
                        for c in competition.get("competitors", [])
                    ]
                })
        
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# Sports Reference Connector
# ═══════════════════════════════════════════════════════════════════════════════

class SportsReferenceConnector:
    """Fetches player stats from Sports Reference (requires scraping)."""

    BASE_URL = "https://www.sports-reference.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; Hermes-3D-Worlds/1.0)"
        })

    def fetch_nba_player_stats(self, player_name: str) -> dict:
        """Search for and fetch NBA player stats."""
        try:
            # Search for player
            search_url = f"{self.BASE_URL}/cbb/search/search.fcgi?search={player_name.replace(' ', '+')}"
            resp = self.session.get(search_url, timeout=10)
            if not resp.ok:
                return {"error": f"Search failed: {resp.status_code}"}
            
            # Look for player page link
            match = re.search(r'/cbb/players/(\w+-\w+\.html)', resp.text)
            if not match:
                # Try NBA
                search_url = f"{self.BASE_URL}/basketball/search/search.fcgi?search={player_name.replace(' ', '+')}"
                resp = self.session.get(search_url, timeout=10)
                match = re.search(r'/basketball/players/(\w+-\w+\.html)', resp.text)
            
            if match:
                player_url = f"{self.BASE_URL}/basketball/players/{match.group(1)}"
                player_resp = self.session.get(player_url, timeout=10)
                if player_resp.ok:
                    return self._parse_nba_player(player_resp.text, player_name)
            
            return {"error": "Player not found", "query": player_name}
        except Exception as e:
            logger.error(f"Sports Reference error: {e}")
            return {"error": str(e)}

    def _parse_nba_player(self, html: str, player_name: str) -> dict:
        """Parse NBA player stats from HTML."""
        result = {"name": player_name, "stats": {}}
        
        # Try to extract per-game stats table
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            
            # Find per-game table
            table = soup.find("table", {"id": "per_game"})
            if table:
                headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
                rows = table.find("tbody").find_all("tr")
                
                if rows:
                    # Get most recent season
                    last_row = rows[0]
                    cells = last_row.find_all(["th", "td"])
                    season_data = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            season_data[headers[i]] = cell.get_text(strip=True)
                    
                    result["stats"] = {
                        "season": season_data.get("Season", "Unknown"),
                        "games": season_data.get("G", "0"),
                        "points_per_game": season_data.get("PPG", season_data.get("pts/g", "")),
                        "rebounds_per_game": season_data.get("TRB", season_data.get("reb/g", "")),
                        "assists_per_game": season_data.get("AST", season_data.get("ast/g", "")),
                        "minutes_per_game": season_data.get("MP", ""),
                        "field_goal_pct": season_data.get("FG%", ""),
                        "three_point_pct": season_data.get("3P%", ""),
                    }
                    result["source"] = "sports-reference-nba"
        except ImportError:
            result["error"] = "BeautifulSoup not available for parsing"
        except Exception as e:
            result["error"] = f"Parse error: {e}"
        
        return result

    def fetch_cfb_player_stats(self, player_name: str) -> dict:
        """Fetch college football player stats."""
        try:
            search_url = f"{self.BASE_URL}/cfb/search/search.fcgi?search={player_name.replace(' ', '+')}"
            resp = self.session.get(search_url, timeout=10)
            if not resp.ok:
                return {"error": f"Search failed: {resp.status_code}"}
            
            match = re.search(r'/cfb/players/(\w+-\w+\.html)', resp.text)
            if match:
                player_url = f"{self.BASE_URL}/cfb/players/{match.group(1)}"
                player_resp = self.session.get(player_url, timeout=10)
                if player_resp.ok:
                    return self._parse_cfb_player(player_resp.text, player_name)
            
            return {"error": "Player not found", "query": player_name}
        except Exception as e:
            logger.error(f"Sports Reference CFB error: {e}")
            return {"error": str(e)}

    def _parse_cfb_player(self, html: str, player_name: str) -> dict:
        """Parse college football player stats."""
        result = {"name": player_name, "stats": {}}
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table", {"id": "passing"})
            if table:
                headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
                rows = table.find("tbody").find_all("tr")
                if rows:
                    last_row = rows[0]
                    cells = last_row.find_all(["th", "td"])
                    season_data = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            season_data[headers[i]] = cell.get_text(strip=True)
                    
                    result["stats"] = {
                        "season": season_data.get("Year", "Unknown"),
                        "passing_yards": season_data.get("Yds", ""),
                        "touchdowns": season_data.get("TD", ""),
                        "interceptions": season_data.get("Int", ""),
                        "completion_pct": season_data.get("Cmp%", ""),
                    }
                    result["source"] = "sports-reference-cfb"
        except ImportError:
            result["error"] = "BeautifulSoup not available"
        except Exception as e:
            result["error"] = f"Parse error: {e}"
        
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# News Feed Aggregator
# ═══════════════════════════════════════════════════════════════════════════════

class NewsAggregator:
    """Aggregates sports news from RSS feeds."""

    RSS_FEEDS = {
        "espn": "https://www.espn.com/espn/rss/news",
        "fox_sports": "https://api.foxsports.com/v1/rss",
        "nba": "https://www.espn.com/nba/rss",
        "nfl": "https://www.espn.com/nfl/rss",
        "college_football": "https://www.espn.com/college-football/rss",
        "bbc_sport": "https://feeds.bbci.co.uk/sport/rss.xml",
        "yahoo_sports": "https://sports.yahoo.com/rss/",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Hermes-3D-Worlds/1.0"})
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes

    def fetch_feed(self, feed_name: str, url: str) -> List[dict]:
        """Fetch and parse a single RSS feed."""
        cache_key = f"rss:{feed_name}"
        
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if time.time() - entry["ts"] < self.cache_ttl:
                return entry["data"]
        
        try:
            resp = self.session.get(url, timeout=10)
            if not resp.ok:
                return []
            
            feed = feedparser.parse(resp.text)
            articles = []
            for entry in feed.entries[:15]:  # limit per feed
                articles.append({
                    "title": entry.get("title", ""),
                    "description": entry.get("summary", entry.get("description", ""))[:300],
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": feed_name,
                })
            
            self.cache[cache_key] = {"ts": time.time(), "data": articles}
            return articles
        except Exception as e:
            logger.error(f"RSS fetch error ({feed_name}): {e}")
            return []

    def fetch_all(self, topics: List[str] = None) -> dict:
        """Fetch all feeds and filter by topics."""
        all_news = []
        topics = [t.lower() for t in (topics or [])]
        
        for feed_name, url in self.RSS_FEEDS.items():
            articles = self.fetch_feed(feed_name, url)
            all_news.extend(articles)
        
        # Sort by published date
        all_news.sort(key=lambda x: x.get("published", ""), reverse=True)
        
        # Filter by topics if specified
        if topics:
            filtered = []
            for article in all_news:
                text = f"{article['title']} {article['description']}".lower()
                if any(t in text for t in topics):
                    filtered.append(article)
            all_news = filtered
        
        return {
            "articles": all_news[:50],  # limit total
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "sources": list(self.RSS_FEEDS.keys()),
        }

    def fetch_team_news(self, team_names: List[str]) -> List[dict]:
        """Fetch news specifically about given teams."""
        topics = team_names + [n.split()[-1] for n in team_names]  # team name + city
        results = self.fetch_all(topics=topics)
        return results.get("articles", [])


# ═══════════════════════════════════════════════════════════════════════════════
# Weather Fetcher (for outdoor stadiums)
# ═══════════════════════════════════════════════════════════════════════════════

class WeatherFetcher:
    """Fetches weather data for stadium locations."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Hermes-3D-Worlds/1.0"})

    def fetch_for_location(self, lat: float = None, lon: float = None, city: str = None) -> dict:
        """Fetch weather for coordinates or city name."""
        # Use wttr.in which is free and doesn't require API key
        try:
            if city:
                url = f"https://wttr.in/{city.replace(' ', '+')}?format=j1"
            else:
                url = f"https://wttr.in/{lat},{lon}?format=j1"
            
            resp = self.session.get(url, timeout=10)
            if resp.ok:
                data = resp.json()
                current = data.get("current_condition", [{}])[0]
                return {
                    "temperature_f": current.get("temp_F", "?"),
                    "condition": current.get("weatherDesc", [{}])[0].get("value", ""),
                    "wind_mph": current.get("windspeedMiles", "?"),
                    "humidity": current.get("humidity", "?"),
                    "source": "wttr.in",
                }
        except Exception as e:
            logger.error(f"Weather fetch error: {e}")
        return {"error": "Weather unavailable"}


# ═══════════════════════════════════════════════════════════════════════════════
# Telegram Notifier
# ═══════════════════════════════════════════════════════════════════════════════

class TelegramNotifier:
    """Sends alerts via Telegram bot."""

    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a text message via Telegram."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram not configured (missing BOT_TOKEN or CHAT_ID)")
            return False
        
        try:
            resp = requests.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10
            )
            if resp.ok:
                logger.info(f"Telegram message sent: {text[:50]}...")
                return True
            else:
                logger.error(f"Telegram error: {resp.text}")
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
        return False

    def alert_game_update(self, game_info: dict) -> bool:
        """Send a game-day alert."""
        teams = game_info.get("teams", {})
        if len(teams) >= 2:
            team_list = list(teams.keys())
            msg = f"🏈 *Game Update*\n\n{team_list[0]} vs {team_list[1]}\n"
            for t, data in teams.items():
                msg += f"• {t}: {data.get('score', '?')}\n"
            return self.send_message(msg)
        return False

    def alert_enrichment_complete(self, enriched_count: int, game_type: str = None) -> bool:
        """Notify that enrichment is complete."""
        msg = f"✅ *Enrichment Complete*\n\nProcessed {enriched_count} screenshot(s)"
        if game_type:
            msg += f" for {game_type}"
        msg += f"\nTime: {datetime.now().strftime('%H:%M:%S')}"
        return self.send_message(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Enrichment Engine
# ═══════════════════════════════════════════════════════════════════════════════

class EnrichmentEngine:
    """
    Orchestrates enrichment of extracted game screenshots.
    
    Takes extracted JSON from Phase 2, fetches live data, produces enriched output.
    """

    def __init__(self, config_path: str = CONFIG_PATH):
        self.config = json.load(open(config_path)) if os.path.exists(config_path) else {}
        self.espn = ESPNConnector(self.config.get("enrichment", {}))
        self.sports_ref = SportsReferenceConnector()
        self.news = NewsAggregator()
        self.weather = WeatherFetcher()
        self.telegram = TelegramNotifier()

    def enrich_extracted(self, extracted_json_path: str) -> dict:
        """
        Main entry point: enrich a single extracted JSON file.
        
        Returns enriched dict with live_scores, schedule, player_stats, news, etc.
        """
        logger.info(f"Processing: {extracted_json_path}")
        
        # Load extracted data
        with open(extracted_json_path, "r") as f:
            extracted = json.load(f)
        
        screenshot_hash = extracted.get("screenshot_hash", "")
        game_type = extracted.get("game_type", "nba_2k")
        home_team = extracted.get("home_team", "")
        away_team = extracted.get("away_team", "")
        
        # Map game_type to sport for ESPN
        sport = game_type
        
        enriched = {
            "live_scores": {},
            "schedule": {},
            "player_stats": {},
            "news": {},
            "weather": {},
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # 1. Fetch live scores
        if home_team or away_team:
            teams = [t for t in [home_team, away_team] if t]
            live_data = self.espn.extract_live_data_for_teams(sport, teams)
            enriched["live_scores"] = live_data
            logger.info(f"Live scores for {teams}: {len(live_data.get('games', []))} games found")
        
        # 2. Fetch schedule
        schedule_data = self.espn.fetch_schedule(sport)
        enriched["schedule"] = {"events": schedule_data.get("events", [])[:10]}
        
        # 3. Fetch player stats (if MyPlayer name available)
        myplayer = extracted.get("myplayer_name") or extracted.get("player_name")
        if myplayer and game_type == "nba_2k":
            enriched["player_stats"] = self.sports_ref.fetch_nba_player_stats(myplayer)
        elif myplayer and game_type == "ncaa":
            enriched["player_stats"] = self.sports_ref.fetch_cfb_player_stats(myplayer)
        
        # 4. Fetch news
        team_names = [t for t in [home_team, away_team] if t]
        if team_names:
            news_articles = self.news.fetch_team_news(team_names)
            enriched["news"] = {
                "articles": news_articles[:10],
                "count": len(news_articles),
            }
        else:
            # General sports news
            enriched["news"] = self.news.fetch_all()
        
        # 5. Fetch weather (for outdoor stadiums - NCAA, some NFL)
        if game_type in ("ncaa", "madden"):
            # Try to get weather for the game location
            # For now, use a general location fetch
            enriched["weather"] = self.weather.fetch_for_location(city="College Station")
        
        # Build world_seed_data structure
        world_seed = {
            "teams_playing": [t for t in [home_team, away_team] if t],
            "game_time": datetime.now(timezone.utc).isoformat(),
            "game_type": game_type,
            "stadium_conditions": {
                "weather": enriched.get("weather", {}),
                "home_team": home_team,
                "away_team": away_team,
            },
            "news_items": enriched.get("news", {}).get("articles", [])[:5],
            "live_scores": enriched.get("live_scores", {}),
        }
        
        # Construct final output
        output = {
            "screenshot_hash": screenshot_hash,
            "game_type": game_type,
            "extracted": extracted,
            "enriched": enriched,
            "world_seed_data": world_seed,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        
        return output

    def process_all(self, input_dir: str = EXTRACTED_DIR, output_dir: str = ENRICHED_DIR) -> List[dict]:
        """Process all extracted JSON files in a directory."""
        os.makedirs(output_dir, exist_ok=True)
        results = []
        
        extracted_files = [f for f in os.listdir(input_dir) if f.endswith(".json")]
        logger.info(f"Found {len(extracted_files)} files to enrich")
        
        for fname in extracted_files:
            input_path = os.path.join(input_dir, fname)
            try:
                enriched = self.enrich_extracted(input_path)
                
                # Save enriched output
                out_path = os.path.join(output_dir, fname)
                with open(out_path, "w") as f:
                    json.dump(enriched, f, indent=2)
                
                results.append({
                    "file": fname,
                    "status": "success",
                    "screenshot_hash": enriched.get("screenshot_hash", ""),
                })
                logger.info(f"Saved: {out_path}")
                
            except Exception as e:
                logger.error(f"Failed to enrich {fname}: {e}")
                results.append({"file": fname, "status": "error", "error": str(e)})
        
        return results

    def run_watch_mode(self, poll_interval_seconds: int = 300):
        """Watch for new files and enrich as they appear."""
        logger.info(f"Starting enrichment watch mode (poll every {poll_interval_seconds}s)")
        seen = set(os.listdir(EXTRACTED_DIR))
        
        while True:
            current = set(os.listdir(EXTRACTED_DIR))
            new_files = current - seen
            
            for fname in new_files:
                if fname.endswith(".json"):
                    input_path = os.path.join(EXTRACTED_DIR, fname)
                    try:
                        enriched = self.enrich_extracted(input_path)
                        out_path = os.path.join(ENRICHED_DIR, fname)
                        with open(out_path, "w") as f:
                            json.dump(enriched, f, indent=2)
                        logger.info(f"Enriched new file: {fname}")
                        
                        # Send Telegram alert
                        self.telegram.alert_enrichment_complete(1, enriched.get("game_type"))
                    except Exception as e:
                        logger.error(f"Error enriching {fname}: {e}")
            
            seen = current
            time.sleep(poll_interval_seconds)


# ═══════════════════════════════════════════════════════════════════════════════
# Standalone functions for CLI use
# ═══════════════════════════════════════════════════════════════════════════════

def enrich_file(extracted_json_path: str, output_dir: str = ENRICHED_DIR) -> dict:
    """Enrich a single extracted file."""
    engine = EnrichmentEngine()
    result = engine.enrich_extracted(extracted_json_path)
    
    os.makedirs(output_dir, exist_ok=True)
    basename = os.path.basename(extracted_json_path)
    out_path = os.path.join(output_dir, basename)
    
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    
    return result


def fetch_live_scores(sport: str) -> dict:
    """Fetch live scores for a sport (utility function)."""
    engine = EnrichmentEngine()
    return engine.espn.fetch_scoreboard(sport)


def fetch_news_for_team(team_name: str) -> List[dict]:
    """Fetch news for a team (utility function)."""
    engine = EnrichmentEngine()
    return engine.news.fetch_team_news([team_name])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hermes 3D World Builder - Enrichment Engine")
    parser.add_argument("action", choices=["enrich", "watch", "scores", "news"],
                        help="Action to perform")
    parser.add_argument("--file", "-f", help="Path to extracted JSON file")
    parser.add_argument("--sport", "-s", default="nba_2k",
                        choices=["nba_2k", "madden", "ncaa", "basketball", "football"],
                        help="Sport type")
    parser.add_argument("--team", "-t", help="Team name for news lookup")
    parser.add_argument("--output", "-o", default=ENRICHED_DIR, help="Output directory")
    parser.add_argument("--interval", "-i", type=int, default=300,
                        help="Poll interval in seconds (watch mode)")
    
    args = parser.parse_args()
    
    engine = EnrichmentEngine()
    
    if args.action == "enrich":
        if not args.file:
            print("Error: --file required for enrich action")
            exit(1)
        result = enrich_file(args.file, args.output)
        print(json.dumps(result, indent=2))
        
    elif args.action == "watch":
        engine.run_watch_mode(poll_interval_seconds=args.interval)
        
    elif args.action == "scores":
        data = engine.espn.fetch_scoreboard(args.sport)
        print(json.dumps(data, indent=2))
        
    elif args.action == "news":
        if not args.team:
            print("Error: --team required for news action")
            exit(1)
        articles = engine.news.fetch_team_news([args.team])
        for a in articles:
            print(f"[{a['source']}] {a['title']}")
            print(f"  {a['description'][:100]}...")
            print()