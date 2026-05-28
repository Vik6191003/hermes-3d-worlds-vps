"""
Hermes 3D Game World Builder — Orchestration Script
Ties all 5 phases into one end-to-end pipeline.

Usage:
  python3 run_pipeline.py [--check-only] [--phase N]
  python3 run_pipeline.py full     # Run all phases end-to-end
  python3 run_pipeline.py monitor  # Run detection + inference only
  python3 run_pipeline.py generate  # Run generation + interaction
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

BASE = "/root/hermes-3d-worlds"
SCREENSHOTS_DIR = f"{BASE}/data/screenshots"
EXTRACTED_DIR = f"{BASE}/data/extracted"
ENRICHED_DIR = f"{BASE}/data/enriched"
WORLDS_DIR = f"{BASE}/data/worlds"


def phase1_detection():
    """Phase 1: Monitor OneDrive for new screenshots."""
    print(f"\n{'='*60}")
    print("PHASE 1: Detection — OneDrive Monitor")
    print(f"{'='*60}")
    sys.path.insert(0, f"{BASE}/detection")
    from onedrive_monitor import OneDriveMonitor
    monitor = OneDriveMonitor()
    new = monitor.check_new_screenshots()
    queued = monitor.get_queued()
    print(f"Result: {len(new)} new screenshots downloaded, {len(queued)} total queued")
    return new


def phase2_inference():
    """Phase 2: Extract game state from queued screenshots."""
    print(f"\n{'='*60}")
    print("PHASE 2: Inference — Vision AI Extraction")
    print(f"{'='*60}")
    sys.path.insert(0, f"{BASE}/inference")
    from vision_extractor import VisionExtractor
    extractor = VisionExtractor()
    
    from onedrive_monitor import OneDriveMonitor
    monitor = OneDriveMonitor()
    queued = monitor.get_queued()
    
    results = []
    for item in queued:
        h = item["hash"]
        path = item["local_path"]
        if not os.path.exists(path):
            continue
        try:
            r = extractor.extract(path, h)
            results.append(r)
            status = "⚠️" if r.get("needs_clarification") else "✅"
            print(f"  {status} [{r.get('game_type')}] {h}: conf={r.get('extraction_confidence', 0):.0%}")
        except Exception as e:
            print(f"  ❌ {h}: {e}")
    
    pending = [r for r in results if r.get("needs_clarification")]
    print(f"Result: {len(results)} processed, {len(pending)} need clarification")
    
    # Ask clarification via Telegram bridge if needed
    if pending:
        try:
            sys.path.insert(0, f"{BASE}/interaction")
            from telegramBridge import push_update, config as tb_config, load_config
            cfg = load_config()
            for p in pending:
                questions = p.get("clarification_questions", [])
                if questions:
                    push_update(
                        cfg.get("TELEGRAM_BOT_TOKEN", ""),
                        cfg.get("TELEGRAM_CHAT_ID", ""),
                        f"🎮 Need clarification for screenshot {p.get('hash', '?')}:\n" +
                        "\n".join(f"Q{i+1}: {q}" for i, q in enumerate(questions))
                    )
        except Exception as e:
            print(f"  ⚠️ Telegram bridge not available: {e}")
    
    return results


def phase3_enrichment():
    """Phase 3: Enrich extracted screenshots with live data."""
    print(f"\n{'='*60}")
    print("PHASE 3: Enrichment — Live Data Integration")
    print(f"{'='*60}")
    sys.path.insert(0, f"{BASE}/enrichment")
    
    files = [f for f in os.listdir(EXTRACTED_DIR) if f.endswith(".json")]
    results = []
    for fname in files:
        try:
            from run_enrichment import enrich_single
            enriched = enrich_single(f"{EXTRACTED_DIR}/{fname}")
            results.append(enriched)
            print(f"  ✅ {fname}")
        except Exception as e:
            print(f"  ❌ {fname}: {e}")
    
    print(f"Result: {len(results)} files enriched")
    return results


def phase4_generation():
    """Phase 4: Generate world specs from enriched data."""
    print(f"\n{'='*60}")
    print("PHASE 4: Generation — 3D World Specs")
    print(f"{'='*60}")
    sys.path.insert(0, f"{BASE}/generation")
    from world_generator import WorldGenerator
    gen = WorldGenerator()
    results = gen.generate_all_worlds()
    
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['file']}: {r['error']}")
        else:
            print(f"  ✅ {r['type']} world: {r['world']}")
    
    print(f"Result: {len([r for r in results if 'error' not in r])} worlds generated")
    return results


def check_screenshots():
    """Dry-run: check if screenshots can be processed."""
    files = os.listdir(SCREENSHOTS_DIR)
    print(f"Screenshots in queue: {len(files)}")
    for f in files:
        print(f"  {f}")


def run_full_pipeline():
    """Run all phases in sequence."""
    print(f"\nHermes 3D Game World Builder — Full Pipeline")
    print(f"Started: {datetime.now().isoformat()}")
    
    new = phase1_detection()
    r2 = phase2_inference()
    
    # Only continue enrichment if extraction is ready
    ready = [r for r in r2 if not r.get("needs_clarification")]
    if not ready:
        print("\n⚠️ All extractions need clarification — skipping enrichment/generation")
        print("Answer clarification questions to continue")
        return
    
    r3 = phase3_enrichment()
    r4 = phase4_generation()
    
    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    worlds = [r for r in r4 if "error" not in r]
    print(f"Worlds ready: {len(worlds)}")


CLI_COMMANDS = {
    "full": run_full_pipeline,
    "detect": phase1_detection,
    "extract": phase2_inference,
    "enrich": phase3_enrichment,
    "generate": phase4_generation,
    "check": check_screenshots,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes 3D Game World Builder Pipeline")
    parser.add_argument("command", nargs="?", default="check",
                        choices=list(CLI_COMMANDS.keys()))
    parser.add_argument("--phase", type=int, help="Run specific phase")
    args = parser.parse_args()
    
    if args.phase:
        phases = {1: phase1_detection, 2: phase2_inference,
                  3: phase3_enrichment, 4: phase4_generation}
        phases[args.phase]()
    else:
        CLI_COMMANDS.get(args.command, check_screenshots)()