"""
Phase 1 — Detection: OneDrive Screenshot Monitor
Monitors Xbox Captures folder for new screenshots, queues for analysis.
"""

import os
import json
import time
import hashlib
import requests
from datetime import datetime, timezone
from pathlib import Path

BASE = "/root/hermes-3d-worlds"
CONFIG_PATH = f"{BASE}/config.json"
SCREENSHOTS_DIR = f"{BASE}/data/screenshots"
EXTRACTED_DIR = f"{BASE}/data/extracted"
STATE_FILE = f"{BASE}/detection/state.json"

class OneDriveMonitor:
    def __init__(self):
        self.config = json.load(open(CONFIG_PATH))
        self.od_config = self.config["onedrive"]
        self.access_token = os.environ.get("MICROSOFT_ACCESS_TOKEN", "")
        self.refresh_token = os.environ.get("MICROSOFT_REFRESH_TOKEN", "")
        self.seen_file = f"{BASE}/detection/seen_screenshots.json"
        self.seen = self._load_seen()

    def _load_seen(self):
        if os.path.exists(self.seen_file):
            return json.load(open(self.seen_file))
        return {"hashes": [], "files": []}

    def _save_seen(self):
        with open(self.seen_file, "w") as f:
            json.dump(self.seen, f, indent=2)

    def _get_access_token(self):
        """Refresh access token from refresh token."""
        if not self.refresh_token:
            return None
        try:
            data = {
                "client_id": self.od_config["client_id"],
                "client_secret": self.od_config["client_secret"],
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(self.od_config["scopes"])
            }
            r = requests.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data=data, timeout=10
            )
            if r.ok:
                tokens = r.json()
                self.access_token = tokens["access_token"]
                os.environ["MICROSOFT_ACCESS_TOKEN"] = self.access_token
                if "refresh_token" in tokens:
                    self.refresh_token = tokens["refresh_token"]
                    os.environ["MICROSOFT_REFRESH_TOKEN"] = self.refresh_token
                return self.access_token
        except Exception as e:
            print(f"Token refresh failed: {e}")
        return None

    def _file_hash(self, content):
        return hashlib.sha256(content).hexdigest()[:16]

    def list_xbox_captures(self):
        """List all files in Xbox Captures folder."""
        if not self.access_token:
            if not self._get_access_token():
                return []
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            path = self.od_config["xbox_captures_path"].replace("/", ":/") + ":/children"
            url = f"https://graph.microsoft.com/v1.0/{path}?$filter=file/mimeType eq 'image/png' or file/mimeType eq 'image/jpeg'&$top=50"
            r = requests.get(url, headers=headers, timeout=15)
            if r.ok:
                items = r.json().get("value", [])
                return [f for f in items if f.get("name", "").lower().endswith((".png", ".jpg", ".jpeg"))]
            elif r.status_code == 401:
                self.access_token = ""
                if self._get_access_token():
                    return self.list_xbox_captures()
        except Exception as e:
            print(f"List failed: {e}")
        return []

    def download_screenshot(self, file_info):
        """Download a screenshot and return local path + metadata."""
        if not self.access_token:
            return None
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            file_id = file_info["id"]
            url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"
            r = requests.get(url, headers=headers, timeout=30)
            if r.ok:
                content = r.content
                h = self._file_hash(content)
                # Skip if already seen
                if h in self.seen["hashes"]:
                    return None
                ext = file_info["name"].split(".")[-1].lower()
                local_path = f"{SCREENSHOTS_DIR}/{h}.{ext}"
                with open(local_path, "wb") as f:
                    f.write(content)
                self.seen["hashes"].append(h)
                self.seen["files"].append({
                    "hash": h,
                    "name": file_info["name"],
                    "onedrive_id": file_id,
                    "size": file_info["size"],
                    "captured_at": file_info.get("fileSystemInfo", {}).get("createdDateTime", ""),
                    "local_path": local_path,
                    "queued_at": datetime.now(timezone.utc).isoformat(),
                    "status": "queued"
                })
                self._save_seen()
                return local_path
        except Exception as e:
            print(f"Download failed for {file_info.get('name')}: {e}")
        return None

    def check_new_screenshots(self):
        """Main check: list → download new → return list of new local paths."""
        print(f"[{datetime.now().isoformat()}] Checking OneDrive for new screenshots...")
        files = self.list_xbox_captures()
        print(f"  Found {len(files)} files in Xbox Captures")
        new_paths = []
        for f in files:
            path = self.download_screenshot(f)
            if path:
                new_paths.append(path)
                print(f"  New: {f['name']} → {path}")
        if new_paths:
            print(f"  Queued {len(new_paths)} new screenshots for analysis")
        return new_paths

    def get_queued(self):
        """Return all screenshots still in 'queued' status."""
        return [f for f in self.seen["files"] if f["status"] == "queued"]

    def mark_processing(self, file_hash):
        for f in self.seen["files"]:
            if f["hash"] == file_hash:
                f["status"] = "processing"
                f["processing_started"] = datetime.now(timezone.utc).isoformat()
        self._save_seen()

    def mark_done(self, file_hash):
        for f in self.seen["files"]:
            if f["hash"] == file_hash:
                f["status"] = "done"
                f["processed_at"] = datetime.now(timezone.utc).isoformat()
        self._save_seen()


def run_monitor():
    """CLI entry point — check for new screenshots."""
    monitor = OneDriveMonitor()
    new = monitor.check_new_screenshots()
    queued = monitor.get_queued()
    print(f"Done. {len(new)} new, {len(queued)} total queued")
    return new


if __name__ == "__main__":
    run_monitor()