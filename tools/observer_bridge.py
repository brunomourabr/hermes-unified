"""
Observer Bridge - System for continuous monitoring with cron-based watchers
Creates scripts that can be invoked by cron for periodic checks
"""

import os
import json
import subprocess
import stat
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

# Import KnowledgeGraphStore for saving observations as Sources
try:
    from tools.memory_bridge import get_kg
    _KG_AVAILABLE = True
except ImportError:
    _KG_AVAILABLE = False
except Exception:
    _KG_AVAILABLE = False


class ObserverBridge:
    """
    Bridge between LangGraph and cron-based monitoring.
    Creates watcher scripts for periodic checks on web prices,
    content changes, file modifications, and API health.
    """

    def __init__(self):
        self.watch_dir = "/opt/projetos/hermes-unified/output/observations"
        self.scripts_dir = os.path.join(self.watch_dir, "scripts")
        self.data_dir = os.path.join(self.watch_dir, "data")
        os.makedirs(self.watch_dir, exist_ok=True)
        self._load_registry()

    def _registry_path(self) -> str:
        return os.path.join(self.watch_dir, "watchers_registry.json")

    def _load_registry(self) -> list:
        """Load the watchers registry from disk."""
        reg_path = self._registry_path()
        if os.path.exists(reg_path):
            with open(reg_path, "r") as f:
                try:
                    self._registry = json.load(f)
                    return self._registry
                except (json.JSONDecodeError, TypeError):
                    pass
        self._registry = []
        return self._registry

    def _save_registry(self):
        """Save the watchers registry to disk."""
        with open(self._registry_path(), "w") as f:
            json.dump(self._registry, f, indent=2)

    def _resolve_interval_minutes(self, interval: str) -> int:
        """Convert interval string to minutes."""
        interval = interval.strip().lower()
        if interval == "daily":
            return 1440
        elif interval == "hourly" or interval == "1h":
            return 60
        elif interval == "30m":
            return 30
        elif interval == "15m":
            return 15
        elif interval == "5m":
            return 5
        elif interval.endswith("m"):
            try:
                return int(interval[:-1])
            except ValueError:
                return 60
        elif interval.endswith("h"):
            try:
                return int(interval[:-1]) * 60
            except ValueError:
                return 60
        # Assume it's a cron expression - default to hourly
        return 60

    def _cron_expression(self, interval: str) -> str:
        """Convert interval string to cron expression."""
        minutes = self._resolve_interval_minutes(interval)
        if minutes >= 1440:
            return "0 6 * * *"  # Daily at 6 AM
        elif minutes >= 60:
            hours = minutes // 60
            return f"0 */{hours} * * *"
        else:
            return f"*/{minutes} * * * *"

    def _generate_watcher_script(
        self,
        name: str,
        target: str,
        check_type: str,
        notification: str
    ) -> str:
        """Generate a Python watcher script for cron execution."""
        os.makedirs(self.scripts_dir, exist_ok=True)
        script_path = os.path.join(self.scripts_dir, f"watcher_{name}.py")

        data_file = os.path.join(self.data_dir, f"{name}.json")

        # Template variables for substitution
        t = {
            "name": name,
            "target": target,
            "check_type": check_type,
            "data_dir": self.data_dir,
            "data_file": data_file,
            "notification": notification,
        }

        script_template = '''#!/usr/bin/env python3
"""
Watcher: {name}
Type: {check_type}
Target: {target}
Created: {created}
"""
import os
import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

WATCH_DIR = "{data_dir}"
DATA_FILE = "{data_file}"
NOTIFICATION = "{notification}"


def load_history():
    """Load previous observation data."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except (json.JSONDecodeError, TypeError):
                return {{}}
    return {{"observations": [], "latest": None}}


def save_observation(observation: dict):
    """Save a new observation to history."""
    history = load_history()
    history["observations"].append(observation)
    history["latest"] = observation
    # Keep only last 100 observations
    if len(history["observations"]) > 100:
        history["observations"] = history["observations"][-100:]
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(history, f, indent=2)
    return history


def check_web_price() -> dict:
    """Check price on a web page."""
    url = "{target}"
    try:
        req = urllib.request.Request(url, headers={{
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Simple price extraction patterns
        import re
        price_patterns = [
            r'\\$\\d+[,\\.]\\d{{2}}',
            r'R\\$\\s*\\d+[,\\.]\\d{{2}}',
            r'price[":=]+\\s*["\\']?([\\d.,]+)',
            r'currency[":=]+\\s*["\\']?([\\d.,]+)',
        ]
        prices = []
        for pattern in price_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            prices.extend(matches[:3])

        return {{
            "timestamp": datetime.now().isoformat(),
            "type": "web_price",
            "url": url,
            "prices_found": prices[:5],
            "page_size": len(html),
            "status": "ok" if prices else "no_prices_found"
        }}
    except Exception as e:
        return {{
            "timestamp": datetime.now().isoformat(),
            "type": "web_price",
            "url": url,
            "error": str(e),
            "status": "error"
        }}


def check_web_content() -> dict:
    """Check web page content for changes."""
    url = "{target}"
    try:
        req = urllib.request.Request(url, headers={{
            "User-Agent": "Mozilla/5.0"
        }})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Content fingerprint for change detection
        import hashlib
        content_hash = hashlib.md5(html.encode()).hexdigest()
        title_match = __import__("re").search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        title = title_match.group(1) if title_match else "N/A"

        return {{
            "timestamp": datetime.now().isoformat(),
            "type": "web_content",
            "url": url,
            "title": title,
            "content_hash": content_hash,
            "page_size": len(html),
            "status": "ok"
        }}
    except Exception as e:
        return {{
            "timestamp": datetime.now().isoformat(),
            "type": "web_content",
            "url": url,
            "error": str(e),
            "status": "error"
        }}


def check_file_change() -> dict:
    """Check file for modifications."""
    filepath = "{target}"
    if not os.path.exists(filepath):
        return {{
            "timestamp": datetime.now().isoformat(),
            "type": "file_change",
            "filepath": filepath,
            "exists": False,
            "status": "not_found"
        }}

    stat_info = os.stat(filepath)
    return {{
        "timestamp": datetime.now().isoformat(),
        "type": "file_change",
        "filepath": filepath,
        "exists": True,
        "size": stat_info.st_size,
        "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
        "status": "ok"
    }}


def check_api_health() -> dict:
    """Check API endpoint health."""
    url = "{target}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")[:500]
        return {{
            "timestamp": datetime.now().isoformat(),
            "type": "api_health",
            "url": url,
            "status_code": status,
            "response_preview": body,
            "status": "ok" if status < 400 else "degraded"
        }}
    except Exception as e:
        return {{
            "timestamp": datetime.now().isoformat(),
            "type": "api_health",
            "url": url,
            "error": str(e),
            "status": "down"
        }}


def send_notification(observation: dict):
    """Send notification about the observation."""
    if NOTIFICATION and NOTIFICATION != "none":
        msg = "[Watcher:{name}] " + str(observation.get("status","?")) + " - " + str(observation.get("type","?"))
        log_path = os.path.join(WATCH_DIR, "notifications.log")
        with open(log_path, "a") as f:
            f.write(datetime.now().isoformat() + " | " + msg + " | " + json.dumps(observation) + "\\n")


# Main execution
if __name__ == "__main__":
    checkers = {{
        "web_price": check_web_price,
        "web_content": check_web_content,
        "file_change": check_file_change,
        "api_health": check_api_health,
    }}

    checker = checkers.get("{check_type}")
    if checker:
        observation = checker()
        save_observation(observation)
        send_notification(observation)
        print(json.dumps(observation, indent=2))
    else:
        print("Unknown check type: {check_type}")
'''

        # Perform substitutions
        script_content = script_template.format(
            name=t["name"],
            target=t["target"],
            check_type=t["check_type"],
            data_dir=t["data_dir"],
            data_file=t["data_file"],
            notification=t["notification"],
            created=datetime.now().isoformat()
        )

        with open(script_path, "w") as f:
            f.write(script_content)

        # Make executable
        st = os.stat(script_path)
        os.chmod(script_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        return script_path

    def create_watcher(
        self,
        name: str,
        target: str,
        check_type: str,
        interval: str = "1h",
        notification: str = "none"
    ) -> dict:
        """
        Create a watcher script for periodic monitoring.

        Creates a standalone Python script that can be invoked by cron.
        The script performs the specified check and saves observations.

        Args:
            name: Unique watcher name
            target: URL (for web_price/web_content/api_health) or file path (for file_change)
            check_type: "web_price", "web_content", "file_change", "api_health"
            interval: "30m", "1h", "2h", "daily", or cron expression
            notification: "none" (log only, extensible)

        Returns:
            dict with watcher info including script path and cron suggestion
        """
        # Validate check_type
        valid_types = ["web_price", "web_content", "file_change", "api_health"]
        if check_type not in valid_types:
            return {
                "error": f"Invalid check_type. Must be one of: {', '.join(valid_types)}",
                "success": False
            }

        # Generate the watcher script
        script_path = self._generate_watcher_script(name, target, check_type, notification)

        cron_expr = self._cron_expression(interval)
        cron_line = f"{cron_expr} python3 {script_path}"

        watcher_info = {
            "name": name,
            "target": target,
            "check_type": check_type,
            "interval": interval,
            "cron_expression": cron_expr,
            "script_path": script_path,
            "data_file": os.path.join(self.data_dir, f"{name}.json"),
            "cron_command": cron_line,
            "created": datetime.now().isoformat(),
            "enabled": False,  # User must add to crontab
            "success": True,
            "setup_instructions": (
                f"To activate, add this line to crontab (crontab -e):\n"
                f"{cron_line}\n\n"
                f"Or run manually: python3 {script_path}"
            )
        }

        # Add to registry
        self._load_registry()
        # Remove existing watcher with same name
        self._registry = [w for w in self._registry if w.get("name") != name]
        self._registry.append(watcher_info)
        self._save_registry()

        return watcher_info

    def list_watchers(self) -> List[dict]:
        """List all registered watchers."""
        self._load_registry()
        return list(self._registry)

    def remove_watcher(self, name: str) -> bool:
        """Remove a watcher by name."""
        self._load_registry()
        initial_count = len(self._registry)
        self._registry = [w for w in self._registry if w.get("name") != name]

        if len(self._registry) < initial_count:
            self._save_registry()
            # Remove script file
            script_path = os.path.join(self.scripts_dir, f"watcher_{name}.py")
            if os.path.exists(script_path):
                os.remove(script_path)
            return True
        return False

    def get_last_observation(self, name: str) -> dict:
        """Get the most recent observation for a watcher."""
        data_file = os.path.join(self.data_dir, f"{name}.json")
        if not os.path.exists(data_file):
            return {"error": f"No observations for watcher '{name}'", "exists": False}

        with open(data_file, "r") as f:
            try:
                history = json.load(f)
                latest = history.get("latest", {})
                return {
                    **latest,
                    "exists": True,
                    "total_observations": len(history.get("observations", []))
                }
            except (json.JSONDecodeError, TypeError):
                return {"error": "Corrupted observation data", "exists": False}

    def get_observation_history(self, name: str, limit: int = 10) -> List[dict]:
        """Get observation history for a watcher."""
        data_file = os.path.join(self.data_dir, f"{name}.json")
        if not os.path.exists(data_file):
            return []

        with open(data_file, "r") as f:
            try:
                history = json.load(f)
                obs = history.get("observations", [])
                return obs[-limit:]
            except (json.JSONDecodeError, TypeError):
                return []

    def install_to_crontab(self, name: str) -> Tuple[bool, str]:
        """
        Install a watcher's cron job using the system crontab.

        Requires the 'crontab' command to be available.
        """
        self._load_registry()
        watcher = next((w for w in self._registry if w.get("name") == name), None)
        if not watcher:
            return False, f"Watcher '{name}' not found"

        cron_line = watcher.get("cron_command", "")
        if not cron_line:
            return False, "No cron command configured"

        try:
            # Get existing crontab
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                existing = result.stdout
            else:
                existing = ""

            # Check if already installed
            if cron_line in existing:
                return True, f"Watcher '{name}' already in crontab"

            # Append the cron job
            new_crontab = existing.strip() + "\n" + cron_line + "\n"

            # Write back
            proc = subprocess.run(
                ["crontab", "-"],
                input=new_crontab,
                text=True,
                capture_output=True,
                timeout=10
            )

            if proc.returncode == 0:
                # Update registry
                for w in self._registry:
                    if w.get("name") == name:
                        w["enabled"] = True
                self._save_registry()
                return True, f"Watcher '{name}' installed to crontab"
            else:
                return False, f"Failed to install crontab: {proc.stderr}"

        except FileNotFoundError:
            return False, "crontab command not available. Install cron package."
        except Exception as e:
            return False, f"Error: {str(e)}"

    def remove_from_crontab(self, name: str) -> Tuple[bool, str]:
        """Remove a watcher's cron job from the system crontab."""
        self._load_registry()
        watcher = next((w for w in self._registry if w.get("name") == name), None)
        if not watcher:
            return False, f"Watcher '{name}' not found"

        cron_line = watcher.get("cron_command", "")

        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return False, "No crontab found"

            lines = result.stdout.split("\n")
            filtered = [l for l in lines if cron_line not in l]
            new_crontab = "\n".join(filtered).strip() + "\n"

            proc = subprocess.run(
                ["crontab", "-"],
                input=new_crontab,
                text=True,
                capture_output=True,
                timeout=10
            )

            if proc.returncode == 0:
                for w in self._registry:
                    if w.get("name") == name:
                        w["enabled"] = False
                self._save_registry()
                return True, f"Watcher '{name}' removed from crontab"
            else:
                return False, f"Failed: {proc.stderr}"

        except FileNotFoundError:
            return False, "crontab command not available"
        except Exception as e:
            return False, f"Error: {str(e)}"

    # =====================================================================
    # KNOWLEDGE GRAPH INTEGRATION
    # =====================================================================

    def _save_observation_to_kg(self, observation: dict, watcher_name: str = None) -> Optional[str]:
        """
        Save an observation as a Source in the KnowledgeGraphStore.

        Creates a source entry with domain 'observation' containing the
        observation data as context. Returns the source ID or None on failure.
        """
        if not _KG_AVAILABLE:
            return None

        try:
            kg = get_kg()
            source_data = {
                "id": observation.get("id", ""),
                "url": observation.get("url", observation.get("source", "")),
                "title": f"Observation: {observation.get('type', 'unknown')} - {watcher_name or 'anonymous'}",
                "domain": "observation",
                "relevance_score": observation.get("confidence", 0.5),
            }

            # Add the full observation payload as extra fields for provenance
            source_data["observation_type"] = observation.get("type", "")
            source_data["observation_status"] = observation.get("status", "")
            source_data["observation_timestamp"] = observation.get("timestamp", datetime.now().isoformat())
            source_data["watcher_name"] = watcher_name or ""
            source_data["observation_payload"] = json.dumps(observation, ensure_ascii=False)

            sid = kg.save_source(source_data, bridge="observer_bridge")

            # Also create a relationship from this observation source to its watcher
            if watcher_name:
                kg.add_relationship(
                    "source", sid,
                    "generated_by", "watcher", watcher_name,
                    bridge="observer_bridge"
                )

            return sid
        except Exception as e:
            print(f"   ⚠ [ObserverBridge] Failed to save observation to KG: {e}")
            return None

    def check_and_notify(self, name: str) -> dict:
        """
        Run a watcher check immediately, save observation, and notify.

        Executes the watcher script for the given name, captures the result,
        saves the observation to both local storage and the Knowledge Graph,
        and returns the observation data.

        Args:
            name: Name of the watcher to check

        Returns:
            dict with observation data and KG save status
        """
        self._load_registry()
        watcher = next((w for w in self._registry if w.get("name") == name), None)
        if not watcher:
            return {"error": f"Watcher '{name}' not found", "success": False}

        script_path = watcher.get("script_path")
        if not script_path or not os.path.exists(script_path):
            return {"error": f"Watcher script not found for '{name}'", "success": False}

        try:
            # Run the watcher script
            result = subprocess.run(
                ["python3", script_path],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return {
                    "error": f"Watcher script failed: {result.stderr}",
                    "success": False,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }

            # Parse observation from script output
            try:
                observation = json.loads(result.stdout.strip())
            except (json.JSONDecodeError, TypeError):
                observation = {
                    "timestamp": datetime.now().isoformat(),
                    "type": watcher.get("check_type", "unknown"),
                    "status": "completed",
                    "raw_output": result.stdout.strip()
                }

            # Save to KG as a Source
            kg_id = self._save_observation_to_kg(observation, watcher_name=name)

            return {
                "success": True,
                "observation": observation,
                "watcher": name,
                "kg_source_id": kg_id,
                "kg_saved": kg_id is not None
            }

        except subprocess.TimeoutExpired:
            return {"error": f"Watcher '{name}' timed out after 60s", "success": False}
        except Exception as e:
            return {"error": f"Error running watcher: {str(e)}", "success": False}

    def check_dashboard(self, names: List[str] = None) -> List[dict]:
        """
        Run checks for multiple watchers and save all observations to KG.

        Args:
            names: List of watcher names to check. If None, checks all enabled watchers.

        Returns:
            List of dicts with results per watcher
        """
        self._load_registry()

        if names is None:
            # Check all enabled watchers
            watchers = [w for w in self._registry if w.get("enabled", False)]
        else:
            watchers = [w for w in self._registry if w.get("name") in names]

        if not watchers:
            return [{"error": "No watchers found to check", "success": False}]

        results = []
        for watcher in watchers:
            result = self.check_and_notify(watcher["name"])
            results.append(result)

        return results


# Singleton
_observer_bridge = None

def get_observer_bridge() -> ObserverBridge:
    global _observer_bridge
    if _observer_bridge is None:
        _observer_bridge = ObserverBridge()
    return _observer_bridge
