"""
Sheets Bridge - Google Sheets integration with offline fallback
Reads/writes Google Sheets if credentials exist, otherwise saves to local JSON/CSV
"""
import os
import json
import csv
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime

# Try to import gspread for Google Sheets
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False


class SheetsBridge:
    """
    Bridge between LangGraph and Google Sheets.
    Works online (Google Sheets API) if configured, or offline (local JSON/CSV) otherwise.
    """

    def __init__(self):
        self.output_dir = "/opt/projetos/hermes-unified/output/sheets/"
        self.creds_dir = "/opt/projetos/hermes-unified/config/"
        os.makedirs(self.output_dir, exist_ok=True)
        self.client = self._init_client()

    def _init_client(self):
        """Try to initialize Google Sheets client with service account credentials."""
        if not GSPREAD_AVAILABLE:
            return None

        creds_path = os.path.join(self.creds_dir, "google-service-account.json")
        if os.path.exists(creds_path):
            try:
                scope = [
                    "https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"
                ]
                creds = Credentials.from_service_account_file(creds_path, scopes=scope)
                client = gspread.authorize(creds)
                print("   [SHEETS] Google Sheets client initialized")
                return client
            except Exception as e:
                print(f"   [SHEETS] Failed to init Google client: {e}")
                return None

        # Also try service account from env var
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if sa_json:
            try:
                import json as _json
                sa_info = _json.loads(sa_json)
                scope = [
                    "https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"
                ]
                creds = Credentials.from_service_account_info(sa_info, scopes=scope)
                client = gspread.authorize(creds)
                print("   [SHEETS] Google Sheets client initialized from env")
                return client
            except Exception as e:
                print(f"   [SHEETS] Failed to init Google client from env: {e}")
                return None

        print("   [SHEETS] No Google credentials found - using offline mode (local JSON/CSV)")
        return None

    def _is_online(self) -> bool:
        """Check if Google Sheets API is available."""
        return self.client is not None

    def _save_local_json(self, data: dict, filename: str) -> str:
        """Save data to local JSON file."""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath

    def _save_local_csv(self, headers: list, rows: list, filename: str) -> str:
        """Save data to local CSV file."""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        return filepath

    def _load_local_json(self, filename: str) -> Optional[dict]:
        """Load data from local JSON file."""
        filepath = os.path.join(self.output_dir, filename)
        if os.path.exists(filepath):
            with open(filepath) as f:
                return json.load(f)
        return None

    def create_sheet(self, title: str, headers: list, rows: Optional[list] = None) -> Tuple[str, bool, str]:
        """
        Create a new sheet (Google Sheet if online, local JSON/CSV if offline).

        Args:
            title: Sheet title/name
            headers: Column headers (list of strings)
            rows: Optional initial data rows (list of lists)

        Returns:
            Tuple[identifier, success, message]
        """
        rows = rows or []

        if self._is_online():
            try:
                sh = self.client.create(title)
                worksheet = sh.get_worksheet(0)

                # Write headers
                cell_list = worksheet.range(1, 1, 1, len(headers))
                for i, cell in enumerate(cell_list):
                    cell.value = headers[i]
                worksheet.update_cells(cell_list)

                # Write rows
                if rows:
                    for r_idx, row in enumerate(rows, start=2):
                        cell_list = worksheet.range(r_idx, 1, r_idx, len(row))
                        for i, cell in enumerate(cell_list):
                            cell.value = row[i] if i < len(row) else ""
                        worksheet.update_cells(cell_list)

                return sh.url, True, f"Google Sheet created: {title}"
            except Exception as e:
                # Fallback to offline
                print(f"   [SHEETS] Google API error, falling back to local: {e}")

        # Offline mode: save as JSON + CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:30]

        data = {
            "title": title,
            "headers": headers,
            "rows": rows,
            "created_at": datetime.now().isoformat(),
            "source": "local"
        }

        json_filename = f"{safe_title}_{timestamp}.json"
        csv_filename = f"{safe_title}_{timestamp}.csv"

        json_path = self._save_local_json(data, json_filename)
        csv_path = self._save_local_csv(headers, rows, csv_filename)

        return json_path, True, f"Sheet saved locally: {json_filename} (+ CSV)"

    def read_sheet(self, sheet_id_or_path: str) -> Tuple[list, bool, str]:
        """
        Read data from a sheet.

        Args:
            sheet_id_or_path: Google Sheet ID/URL, or local file path

        Returns:
            Tuple[list of dicts, success, message]
        """
        # Local file mode
        if os.path.exists(sheet_id_or_path):
            ext = os.path.splitext(sheet_id_or_path)[1].lower()
            if ext == ".json":
                data = self._load_local_json(os.path.basename(sheet_id_or_path))
                if data:
                    return data, True, f"Read from local JSON: {os.path.basename(sheet_id_or_path)}"
            elif ext == ".csv":
                with open(sheet_id_or_path, newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                return rows, True, f"Read from local CSV: {os.path.basename(sheet_id_or_path)}"

            # Try parent path
            alt_path = os.path.join(self.output_dir, os.path.basename(sheet_id_or_path))
            if os.path.exists(alt_path):
                return self.read_sheet(alt_path)

            return [], False, f"File not found: {sheet_id_or_path}"

        # Google Sheets mode
        if self._is_online():
            try:
                # Try as ID or URL
                if sheet_id_or_path.startswith("http"):
                    sh = self.client.open_by_url(sheet_id_or_path)
                else:
                    sh = self.client.open_by_key(sheet_id_or_path)

                worksheet = sh.get_worksheet(0)
                all_data = worksheet.get_all_records()
                return all_data, True, f"Read Google Sheet: {sh.title} ({len(all_data)} rows)"
            except Exception as e:
                return [], False, f"Error reading Google Sheet: {e}"

        return [], False, "No sheet found and no Google credentials configured"

    def append_row(self, sheet_id_or_path: str, row: list) -> Tuple[bool, str]:
        """
        Append a row to an existing sheet.

        Args:
            sheet_id_or_path: Google Sheet ID/URL, or local file path
            row: List of values to append

        Returns:
            Tuple[success, message]
        """
        if self._is_online():
            try:
                if sheet_id_or_path.startswith("http"):
                    sh = self.client.open_by_url(sheet_id_or_path)
                else:
                    sh = self.client.open_by_key(sheet_id_or_path)

                worksheet = sh.get_worksheet(0)
                worksheet.append_row(row)
                return True, f"Row appended to Google Sheet: {sh.title}"
            except Exception as e:
                print(f"   [SHEETS] Google API error, falling back to local: {e}")

        # Offline: try to update local JSON
        # Look for the sheet in output dir
        basename = os.path.basename(sheet_id_or_path)
        json_path = os.path.join(self.output_dir, basename)

        if not os.path.exists(json_path) and not basename.endswith(".json"):
            # Try finding any JSON for this sheet
            for f in os.listdir(self.output_dir):
                if f.endswith(".json") and (basename in f or sheet_id_or_path in f):
                    json_path = os.path.join(self.output_dir, f)
                    break

        if os.path.exists(json_path):
            with open(json_path) as f:
                data = json.load(f)
            data["rows"].append(row)
            data["updated_at"] = datetime.now().isoformat()
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True, f"Row appended to local sheet: {basename}"

        # Create a new local sheet with just this row
        return self.create_sheet(f"appended_{datetime.now().strftime('%H%M%S')}", [f"col{i+1}" for i in range(len(row))], [row])[1:]

    def list_sheets(self) -> Tuple[list, bool, str]:
        """
        List all available sheets.

        Returns:
            Tuple[list of sheet info, success, message]
        """
        sheets = []

        # List local files
        for f in sorted(os.listdir(self.output_dir)):
            if f.endswith((".json", ".csv")):
                fpath = os.path.join(self.output_dir, f)
                sheets.append({
                    "filename": f,
                    "path": fpath,
                    "size": os.path.getsize(fpath),
                    "modified": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat(),
                    "source": "local"
                })

        # List Google Sheets if online
        if self._is_online():
            try:
                for sh in self.client.openall():
                    sheets.append({
                        "title": sh.title,
                        "url": sh.url,
                        "id": sh.id,
                        "source": "google"
                    })
            except Exception as e:
                print(f"   [SHEETS] Error listing Google Sheets: {e}")

        if sheets:
            return sheets, True, f"Found {len(sheets)} sheets"
        return sheets, True, "No sheets found"

    def export_to_csv(self, sheet_id_or_path: str) -> Tuple[str, bool, str]:
        """
        Export a sheet to CSV file.

        Args:
            sheet_id_or_path: Google Sheet ID/URL, or local file path

        Returns:
            Tuple[filepath, success, message]
        """
        data, success, msg = self.read_sheet(sheet_id_or_path)
        if not success:
            return "", False, msg

        if not data:
            return "", False, "No data to export"

        if isinstance(data, dict) and "rows" in data:
            rows = data["rows"]
            headers = data["headers"]
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [[row.get(h, "") for h in headers] for row in data]
        else:
            return "", False, "Unknown data format"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"export_{timestamp}.csv"
        csv_path = self._save_local_csv(headers, rows, filename)

        return csv_path, True, f"CSV exported: {filename}"


# Singleton
_sheets_bridge = None

def get_sheets_bridge() -> SheetsBridge:
    global _sheets_bridge
    if _sheets_bridge is None:
        _sheets_bridge = SheetsBridge()
    return _sheets_bridge
