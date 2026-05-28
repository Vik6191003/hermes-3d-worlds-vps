#!/usr/bin/env python3
"""
Phase 3 — Enrichment: CLI Runner
Usage:
    python run_enrichment.py enrich --file /path/to/extracted.json
    python run_enrichment.py batch --input /root/hermes-3d-worlds/data/extracted
    python run_enrichment.py watch --interval 300
    python run_enrichment.py scores --sport nba_2k
    python run_enrichment.py news --team "Lakers"
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enrichment_engine import (
    EnrichmentEngine,
    enrich_file,
    fetch_live_scores,
    fetch_news_for_team,
    EXTRACTED_DIR,
    ENRICHED_DIR,
    BASE,
)

def cmd_enrich(engine, args):
    """Enrich a single extracted file."""
    if not args.file:
        # Try to find any extracted file
        files = [f for f in os.listdir(EXTRACTED_DIR) if f.endswith(".json")]
        if not files:
            print("No extracted JSON files found.")
            return
        args.file = os.path.join(EXTRACTED_DIR, files[0])
        print(f"Auto-selected: {args.file}")
    
    result = engine.enrich_extracted(args.file)
    
    if args.output:
        out_path = os.path.join(args.output, os.path.basename(args.file))
    else:
        out_path = os.path.join(ENRICHED_DIR, os.path.basename(args.file))
    
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"✅ Enriched: {out_path}")
    print(f"   Game type: {result.get('game_type', 'unknown')}")
    print(f"   Teams: {result.get('world_seed_data', {}).get('teams_playing', [])}")
    print(f"   Live games found: {len(result.get('enriched', {}).get('live_scores', {}).get('games', []))}")
    print(f"   News articles: {result.get('enriched', {}).get('news', {}).get('count', 0)}")
    
    return result

def cmd_batch(engine, args):
    """Batch process all extracted files."""
    input_dir = args.input or EXTRACTED_DIR
    output_dir = args.output or ENRICHED_DIR
    
    if not os.path.exists(input_dir):
        print(f"Input directory not found: {input_dir}")
        return
    
    files = [f for f in os.listdir(input_dir) if f.endswith(".json")]
    if not files:
        print("No JSON files to process.")
        return
    
    print(f"Processing {len(files)} file(s) from {input_dir}...")
    
    results = engine.process_all(input_dir=input_dir, output_dir=output_dir)
    
    success = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - success
    
    print(f"\n✅ Completed: {success} successful, {failed} failed")
    
    if args.telegram and success > 0:
        engine.telegram.alert_enrichment_complete(success)
    
    return results

def cmd_watch(engine, args):
    """Run in watch mode for continuous enrichment."""
    interval = args.interval or 300
    print(f"🔄 Starting enrichment watch mode (poll every {interval}s)")
    print(f"   Watching: {EXTRACTED_DIR}")
    print(f"   Output:   {ENRICHED_DIR}")
    print(f"   Press Ctrl+C to stop")
    
    try:
        engine.run_watch_mode(poll_interval_seconds=interval)
    except KeyboardInterrupt:
        print("\n⏹️ Watch mode stopped.")

def cmd_scores(args):
    """Fetch and display live scores."""
    sport = args.sport or "nba_2k"
    print(f"📊 Fetching {sport} scores...")
    
    data = fetch_live_scores(sport)
    events = data.get("events", [])
    
    if not events:
        print("No games found.")
        return
    
    print(f"Found {len(events)} game(s):\n")
    for event in events:
        name = event.get("name", "Unknown Game")
        status = event.get("status", {}).get("type", {}).get("description", "")
        date = event.get("date", "")[:16]
        
        print(f"🏀 {name}")
        print(f"   Status: {status}")
        print(f"   Date: {date}")
        
        for comp in event.get("competitions", [{}])[0].get("competitors", []):
            team = comp.get("team", {})
            score = comp.get("score", "?")
            ha = comp.get("homeAway", "")
            print(f"   {'(H)' if ha == 'home' else '(A)'} {team.get('displayName', '?')}: {score}")
        print()

def cmd_news(args):
    """Fetch news for a team."""
    if not args.team:
        print("Error: --team required")
        return
    
    print(f"📰 Fetching news for: {args.team}")
    articles = fetch_news_for_team(args.team)
    
    if not articles:
        print("No news found.")
        return
    
    print(f"Found {len(articles)} article(s):\n")
    for a in articles:
        print(f"[{a.get('source', '?')}] {a.get('title', '?')}")
        desc = a.get('description', '')
        if desc:
            print(f"   {desc[:150]}...")
        print()

def cmd_test(engine, args):
    """Run tests with sample data or synthetic data."""
    print("🧪 Running enrichment tests...")
    
    # Create a synthetic test file
    test_data = {
        "screenshot_hash": "test_abc123",
        "game_type": "nba_2k",
        "home_team": "Lakers",
        "away_team": "Celtics",
        "home_score": 87,
        "away_score": 82,
        "game_quarter": "Q3",
        "time_remaining": "05:32",
        "game_mode": "PlayNow",
        "myplayer_name": "LeBron James",
        "extraction_confidence": 0.92,
        "processed_at": "2025-01-15T20:00:00Z",
        "status": "ready_for_enrichment"
    }
    
    # Save test file
    test_path = f"{EXTRACTED_DIR}/test_abc123.json"
    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    with open(test_path, "w") as f:
        json.dump(test_data, f)
    
    print(f"  Created test file: {test_path}")
    
    # Run enrichment
    result = engine.enrich_extracted(test_path)
    
    print(f"  Game type: {result.get('game_type')}")
    print(f"  Teams: {result.get('world_seed_data', {}).get('teams_playing', [])}")
    print(f"  Live scores found: {len(result.get('enriched', {}).get('live_scores', {}).get('games', []))}")
    print(f"  News count: {result.get('enriched', {}).get('news', {}).get('count', 0)}")
    
    # Verify output structure
    assert "screenshot_hash" in result
    assert "extracted" in result
    assert "enriched" in result
    assert "world_seed_data" in result
    assert "live_scores" in result["enriched"]
    assert "news" in result["enriched"]
    
    print("  ✅ All structure checks passed")
    
    # Save result
    out_path = f"{ENRICHED_DIR}/test_abc123.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Saved: {out_path}")
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Hermes 3D World Builder — Enrichment CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # enrich command
    p_enrich = subparsers.add_parser("enrich", help="Enrich a single extracted JSON file")
    p_enrich.add_argument("--file", "-f", help="Path to extracted JSON file")
    p_enrich.add_argument("--output", "-o", help="Output directory")
    
    # batch command  
    p_batch = subparsers.add_parser("batch", help="Batch process all extracted files")
    p_batch.add_argument("--input", "-i", help="Input directory (default: extracted/)")
    p_batch.add_argument("--output", "-o", help="Output directory (default: enriched/)")
    p_batch.add_argument("--telegram", "-t", action="store_true", help="Send Telegram notification on completion")
    
    # watch command
    p_watch = subparsers.add_parser("watch", help="Watch mode for continuous enrichment")
    p_watch.add_argument("--interval", type=int, default=300, help="Poll interval in seconds")
    
    # scores command
    p_scores = subparsers.add_parser("scores", help="Fetch live scores for a sport")
    p_scores.add_argument("--sport", "-s", default="nba_2k",
                         choices=["nba_2k", "madden", "ncaa", "basketball", "football"],
                         help="Sport type")
    
    # news command
    p_news = subparsers.add_parser("news", help="Fetch news for a team")
    p_news.add_argument("--team", "-t", required=True, help="Team name")
    
    # test command
    p_test = subparsers.add_parser("test", help="Run enrichment tests with sample data")
    
    args = parser.parse_args()
    
    # Handle command aliases
    if args.command == "scores" and not hasattr(args, 'sport'):
        args.sport = "nba_2k"
    
    engine = EnrichmentEngine()
    
    commands = {
        "enrich": lambda: cmd_enrich(engine, args),
        "batch": lambda: cmd_batch(engine, args),
        "watch": lambda: cmd_watch(engine, args),
        "scores": lambda: cmd_scores(args),
        "news": lambda: cmd_news(args),
        "test": lambda: cmd_test(engine, args),
    }
    
    result = commands.get(args.command, lambda: parser.print_help())()
    
    if result and args.command == "enrich":
        sys.exit(0)
    
    return result


if __name__ == "__main__":
    main()