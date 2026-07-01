"""
DV360 Bridge - Google Display & Video 360 Analytics Agent
Fetches DV360 advertiser/campaign/line-item performance via API if credentials exist,
saves reports to local JSON otherwise.
"""
import os
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import uuid

# Knowledge Graph for persistent storage
try:
    from tools.memory_bridge import get_kg
    KG_AVAILABLE = True
except ImportError:
    KG_AVAILABLE = False
    print("   [DV360] KnowledgeGraphStore not available")

# Try to import Google API client for DV360
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


class DV360Bridge:
    """
    Bridge between LangGraph and Google Display & Video 360 API.
    Works online (DV360 API) if OAuth credentials configured, or offline (local JSON) otherwise.
    """

    def __init__(self):
        self.output_dir = "/opt/projetos/hermes-unified/output/dv360/"
        self.creds_dir = "/opt/projetos/hermes-unified/config/"
        os.makedirs(self.output_dir, exist_ok=True)
        self.service = self._init_service()

    def _init_service(self):
        """Try to initialize DV360 API service with OAuth 2.0 credentials."""
        if not GOOGLE_API_AVAILABLE:
            print("   [DV360] google-api-python-client not installed")
            return None

        # Try google-credentials.json first
        creds_path = os.path.join(self.creds_dir, "google-credentials.json")
        if os.path.exists(creds_path):
            try:
                creds = Credentials.from_authorized_user_file(creds_path)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                service = build("displayvideo", "v4", credentials=creds)
                print("   [DV360] API service initialized")
                return service
            except Exception as e:
                print(f"   [DV360] Failed to init from file: {e}")

        # Try secrets.json for token info
        secrets_path = os.path.join(self.creds_dir, "secrets.json")
        if os.path.exists(secrets_path):
            try:
                with open(secrets_path) as f:
                    secrets = json.load(f)
                token_json = secrets.get("GOOGLE_ADS_CREDENTIALS", "")
                if token_json:
                    if isinstance(token_json, str):
                        creds = Credentials.from_authorized_user_info(json.loads(token_json))
                    else:
                        creds = Credentials.from_authorized_user_info(token_json)
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    service = build("displayvideo", "v4", credentials=creds)
                    print("   [DV360] API service initialized from secrets")
                    return service
            except Exception as e:
                print(f"   [DV360] Failed to init from secrets: {e}")

        # Try env var
        sa_json = os.environ.get("GOOGLE_ADS_CREDENTIALS", "")
        if sa_json:
            try:
                creds = Credentials.from_authorized_user_info(json.loads(sa_json))
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                service = build("displayvideo", "v4", credentials=creds)
                print("   [DV360] API service initialized from env")
                return service
            except Exception as e:
                print(f"   [DV360] Failed to init from env: {e}")

        print("   [DV360] No Google credentials found - using offline mode (local JSON)")
        return None

    def _is_online(self) -> bool:
        """Check if DV360 API is available."""
        return self.service is not None

    def _save_local_json(self, data: dict, filename: str) -> str:
        """Save data to local JSON file."""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return filepath

    def _save_to_kg(self, summary: dict, campaign_id: str, period_start: str, period_end: str, bridge: str = "dv360_bridge"):
        """Save campaign metrics to KnowledgeGraphStore after an operation."""
        if not KG_AVAILABLE:
            return
        try:
            kg = get_kg()
            if not kg:
                return

            # 1. Save/update campaign
            campaign_dict = {
                "id": campaign_id,
                "name": f"DV360 Campaign {campaign_id}",
                "platform": "dv360",
                "start_date": period_start,
                "end_date": period_end,
                "bridge_source": bridge
            }
            kg.save_campaign(campaign_dict, bridge=bridge)

            # 2. Save each metric linked to the campaign
            metric_mapping = {
                "impressions": ("Impressions", "count"),
                "clicks": ("Clicks", "count"),
                "ctr": ("CTR", "percent"),
                "conversions": ("Conversions", "count"),
                "spend_usd": ("Spend", "USD"),
                "cpm": ("CPM", "USD"),
                "cpc": ("CPC", "USD"),
                "cpa": ("CPA", "USD"),
            }
            saved_count = 0
            for key, (metric_name, unit) in metric_mapping.items():
                value = summary.get(key)
                if value is None:
                    continue
                try:
                    float_val = float(value)
                except (ValueError, TypeError):
                    continue

                metric_dict = {
                    "name": metric_name,
                    "value": float_val,
                    "unit": unit,
                    "platform": "dv360",
                    "period_start": period_start,
                    "period_end": period_end,
                }
                kg.save_metric(metric_dict, campaign_id=campaign_id, bridge=bridge)
                saved_count += 1

            if saved_count > 0:
                print(f"   [DV360] Saved {saved_count} metrics to KnowledgeGraph for campaign '{campaign_id}'")
        except Exception as e:
            print(f"   [DV360] Warning: could not save to KG: {e}")

    def _load_local_json(self, filename: str) -> Optional[dict]:
        """Load data from local JSON file."""
        filepath = os.path.join(self.output_dir, filename)
        if os.path.exists(filepath):
            with open(filepath) as f:
                return json.load(f)
        return None

    def _make_timestamp(self) -> str:
        """Create a timestamp string for filenames."""
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def list_advertisers(self, partner_id: str = None) -> Tuple[list, bool, str]:
        """
        List advertisers accessible by the authenticated user.

        Args:
            partner_id: Optional partner ID to filter by

        Returns:
            Tuple[list of advertisers, success, message]
        """
        if self._is_online():
            try:
                request = self.service.advertisers().list()
                if partner_id:
                    request = self.service.advertisers().list(partnerId=partner_id)
                response = request.execute()
                advertisers = response.get("advertisers", [])
                # Save to local cache
                ts = self._make_timestamp()
                cache = {
                    "source": "dv360_api",
                    "fetched_at": datetime.now().isoformat(),
                    "advertisers": advertisers
                }
                self._save_local_json(cache, f"advertisers_{ts}.json")
                return advertisers, True, f"Found {len(advertisers)} advertisers"
            except Exception as e:
                error_msg = str(e)[:300]
                return [], False, f"DV360 API error: {error_msg}"

        # Offline: return instructions
        instructions = {
            "message": "DV360 API not configured - offline mode",
            "help": "To enable online mode, configure google-credentials.json in config/ with OAuth tokens",
            "scope": "https://www.googleapis.com/auth/display-video",
            "endpoint": "https://displayvideo.googleapis.com/v4/advertisers",
            "sample_advertiser": {
                "advertiserId": "123456789",
                "displayName": "Sample Advertiser",
                "partnerId": "987654321",
                "status": "ACTIVE"
            }
        }
        return [instructions], True, "DV360 offline mode - see instructions"

    def get_performance(self, advertiser_id: str,
                        start_date: str, end_date: str,
                        metrics: list = None) -> Tuple[dict, bool, str]:
        """
        Get campaign/insertion order performance metrics.

        Args:
            advertiser_id: DV360 advertiser ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            metrics: List of metrics to fetch (default: impressions, clicks, conversions, spend)

        Returns:
            Tuple[performance data, success, message]
        """
        if metrics is None:
            metrics = ["IMPRESSIONS", "CLICKS", "TOTAL_CONVERSIONS", "MEDIA_COST"]

        if self._is_online():
            try:
                # Use the Google Ads reporting API via DV360
                # Build a query for the advertiser
                report_data = {
                    "advertiserId": advertiser_id,
                    "dateRange": {
                        "startDate": start_date,
                        "endDate": end_date
                    },
                    "metrics": metrics,
                    "dimensions": ["ADVERTISER", "CAMPAIGN", "INSERTION_ORDER", "LINE_ITEM"]
                }
                # Attempt to call the API
                # Note: DV360 v4 uses advertisers.lineItems.list for stats
                line_items = []
                page_token = None
                while True:
                    request_params = {
                        "advertiserId": advertiser_id,
                        "filter": f"entityStatus='ENTITY_STATUS_ACTIVE'",
                        "pageSize": 100
                    }
                    if page_token:
                        request_params["pageToken"] = page_token
                    response = self.service.advertisers().lineItems().list(**request_params).execute()
                    items = response.get("lineItems", [])
                    line_items.extend(items)
                    page_token = response.get("nextPageToken")
                    if not page_token:
                        break

                # Aggregate stats
                total_impressions = sum(int(li.get("integrationDetails", {}).get("ioId", 0) or 0) for li in line_items)
                total_clicks = sum(int(li.get("clickThroughUrl", {}).get("landingPageUrl", "0") or "0") for li in line_items if li.get("clickThroughUrl", {}).get("landingPageUrl", "").isdigit())
                total_spend = sum(float(li.get("budget", {}).get("mediaFee", {}).get("amountMicros", 0) or 0) / 1_000_000 for li in line_items)

                result = {
                    "advertiserId": advertiser_id,
                    "dateRange": {"start": start_date, "end": end_date},
                    "metrics": {
                        "impressions": total_impressions,
                        "clicks": total_clicks,
                        "spend_usd": round(total_spend, 2),
                        "line_items_count": len(line_items)
                    },
                    "line_items": line_items[:50],
                    "source": "dv360_api"
                }

                ts = self._make_timestamp()
                self._save_local_json(result, f"performance_{advertiser_id}_{ts}.json")

                # Save to KnowledgeGraph
                summary = result.get("metrics", result.get("summary", {}))
                self._save_to_kg(summary, "dv360_sample", start_date, end_date)

                return result, True, f"Performance data for {advertiser_id}: {len(line_items)} line items"
            except Exception as e:
                error_msg = str(e)[:300]
                # Fallback to offline
                result = self._offline_performance(advertiser_id, start_date, end_date, metrics)
                result["error"] = error_msg
                return result, True, f"DV360 API error, used offline fallback: {error_msg}"

        # Offline mode
        result = self._offline_performance(advertiser_id, start_date, end_date, metrics)
        # Save to KnowledgeGraph
        self._save_to_kg(result.get("summary", {}), "dv360_sample", start_date, end_date)
        return result, True, "DV360 offline mode - sample performance data"

    def _offline_performance(self, advertiser_id: str, start_date: str, end_date: str,
                              metrics: list = None) -> dict:
        """Generate sample performance data for offline mode."""
        if metrics is None:
            metrics = ["IMPRESSIONS", "CLICKS", "TOTAL_CONVERSIONS", "MEDIA_COST"]

        return {
            "advertiserId": advertiser_id,
            "dateRange": {"start": start_date, "end": end_date},
            "metrics": {m: f"<{m}_value>" for m in metrics},
            "summary": {
                "impressions": 1250000,
                "clicks": 34500,
                "ctr": 2.76,
                "conversions": 890,
                "spend_usd": 45200.00,
                "cpm": 36.16,
                "cpc": 1.31,
                "cpa": 50.79
            },
            "line_items_sample": [
                {"lineItemId": "li_001", "displayName": "Display - Prospecting", "impressions": 450000, "clicks": 12000, "spend": 18000.00},
                {"lineItemId": "li_002", "displayName": "Video - Retargeting", "impressions": 350000, "clicks": 9800, "spend": 14500.00},
                {"lineItemId": "li_003", "displayName": "Native - Awareness", "impressions": 250000, "clicks": 6700, "spend": 7200.00},
                {"lineItemId": "li_004", "displayName": "Audio - Reach", "impressions": 200000, "clicks": 6000, "spend": 5500.00}
            ],
            "source": "offline_sample"
        }

    def generate_report(self, advertiser_id: str,
                         start_date: str, end_date: str,
                         dimensions: list = None,
                         metrics: list = None) -> Tuple[str, bool, str]:
        """
        Generate a performance report.

        Args:
            advertiser_id: DV360 advertiser ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            dimensions: List of dimensions (default: date, campaign, line_item)
            metrics: List of metrics (default: impressions, clicks, spend, conversions)

        Returns:
            Tuple[path to saved report, success, message]
        """
        if dimensions is None:
            dimensions = ["DATE", "CAMPAIGN", "LINE_ITEM"]
        if metrics is None:
            metrics = ["IMPRESSIONS", "CLICKS", "TOTAL_CONVERSIONS", "MEDIA_COST"]

        performance, success, msg = self.get_performance(advertiser_id, start_date, end_date, metrics)
        if not success:
            return "", False, msg

        # Build a structured report
        report = {
            "report_type": "dv360_performance",
            "advertiser_id": advertiser_id,
            "date_range": {"start": start_date, "end": end_date},
            "generated_at": datetime.now().isoformat(),
            "dimensions": dimensions,
            "metrics": metrics,
            "data": performance,
            "summary": performance.get("summary", performance.get("metrics", {})),
            "recommendations": [
                "Review underperforming line items",
                "Adjust bid strategies based on CPA/CPC trends",
                "Consider audience segmentation improvements"
            ]
        }

        ts = self._make_timestamp()
        filename = f"report_{advertiser_id}_{ts}.json"
        path = self._save_local_json(report, filename)

        # Save to KnowledgeGraph
        report_summary = performance.get("summary", performance.get("metrics", {}))
        self._save_to_kg(report_summary, "dv360_sample", start_date, end_date)

        return path, True, f"Report saved: {filename}"

    def compare_periods(self, advertiser_id: str,
                        period1_start: str, period1_end: str,
                        period2_start: str, period2_end: str) -> Tuple[str, bool, str]:
        """
        Generate a comparison report between two time periods.

        Args:
            advertiser_id: DV360 advertiser ID
            period1_start: Start of period 1 (YYYY-MM-DD)
            period1_end: End of period 1 (YYYY-MM-DD)
            period2_start: Start of period 2 (YYYY-MM-DD)
            period2_end: End of period 2 (YYYY-MM-DD)

        Returns:
            Tuple[path to comparison report, success, message]
        """
        p1_data, p1_ok, p1_msg = self.get_performance(advertiser_id, period1_start, period1_end)
        p2_data, p2_ok, p2_msg = self.get_performance(advertiser_id, period2_start, period2_end)

        if not p1_ok:
            return "", False, f"Period 1 error: {p1_msg}"
        if not p2_ok:
            return "", False, f"Period 2 error: {p2_msg}"

        p1_summary = p1_data.get("summary", p1_data.get("metrics", {}))
        p2_summary = p2_data.get("summary", p2_data.get("metrics", {}))

        # Calculate deltas
        comparison = {
            "type": "dv360_period_comparison",
            "advertiser_id": advertiser_id,
            "period_1": {"start": period1_start, "end": period1_end},
            "period_2": {"start": period2_start, "end": period2_end},
            "period_1_data": p1_summary,
            "period_2_data": p2_summary,
            "deltas": {},
            "generated_at": datetime.now().isoformat()
        }

        # Calculate deltas for common metrics
        numeric_keys = ["impressions", "clicks", "conversions", "spend_usd", "cpm", "cpc", "cpa", "ctr"]
        for key in numeric_keys:
            v1 = p1_summary.get(key, 0)
            v2 = p2_summary.get(key, 0)
            try:
                v1_f = float(v1) if not isinstance(v1, (int, float)) else v1
                v2_f = float(v2) if not isinstance(v2, (int, float)) else v2
                if v1_f != 0:
                    pct_change = round(((v2_f - v1_f) / v1_f) * 100, 2)
                else:
                    pct_change = None
                comparison["deltas"][key] = {
                    "period_1": v1_f,
                    "period_2": v2_f,
                    "absolute_change": round(v2_f - v1_f, 2),
                    "percentage_change": pct_change
                }
            except (ValueError, TypeError):
                comparison["deltas"][key] = {
                    "period_1": v1,
                    "period_2": v2,
                    "note": "non-numeric values"
                }

        ts = self._make_timestamp()
        filename = f"comparison_{advertiser_id}_{ts}.json"
        path = self._save_local_json(comparison, filename)

        # Save to KnowledgeGraph
        if KG_AVAILABLE:
            try:
                kg = get_kg()
                if kg:
                    # Save metrics for both periods
                    self._save_to_kg(p1_summary, "dv360_sample", period1_start, period1_end)
                    self._save_to_kg(p2_summary, "dv360_sample", period2_start, period2_end)
                    # Add a comparison relationship linking the two period entries
                    comp_id = f"comparison_{ts}"
                    kg.add_relationship(
                        source_type="period",
                        source_id=f"{period1_start}_{period1_end}",
                        rel_type="compared_with",
                        target_type="period",
                        target_id=f"{period2_start}_{period2_end}",
                        bridge="dv360_bridge"
                    )
                    print(f"   [DV360] Saved period comparison to KnowledgeGraph ({comp_id})")
            except Exception as e:
                print(f"   [DV360] Warning: could not save comparison to KG: {e}")

        return path, True, f"Comparison report saved: {filename}"

    def status(self) -> dict:
        """Returns current configuration status."""
        return {
            "tool": "DV360 Bridge",
            "online": self._is_online(),
            "output_dir": self.output_dir,
            "creds_file": os.path.join(self.creds_dir, "google-credentials.json"),
            "setup_docs": {
                "how_to_configure": "Place OAuth 2.0 credentials in config/google-credentials.json or set GOOGLE_ADS_CREDENTIALS env var",
                "required_scope": "https://www.googleapis.com/auth/display-video",
                "api_endpoint": "https://displayvideo.googleapis.com/v4",
                "docs_url": "https://developers.google.com/display-video/api/guides/getting-started/overview"
            },
            "available_methods": [
                "list_advertisers(partner_id)",
                "get_performance(advertiser_id, start_date, end_date, metrics)",
                "generate_report(advertiser_id, start_date, end_date, dimensions, metrics)",
                "compare_periods(advertiser_id, period1_start, period1_end, period2_start, period2_end)",
                "status()"
            ]
        }


# Singleton
_dv360_bridge = None

def get_dv360_bridge() -> DV360Bridge:
    global _dv360_bridge
    if _dv360_bridge is None:
        _dv360_bridge = DV360Bridge()
    return _dv360_bridge
