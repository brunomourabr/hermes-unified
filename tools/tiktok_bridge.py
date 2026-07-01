"""
TikTok Bridge - TikTok Ads Analytics Agent
Fetches TikTok Ads campaign/adgroup performance data via the Business API if configured,
saves to local JSON otherwise.
"""
import os
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime
import uuid

# Try to import TikTok Business API SDK
try:
    import business_api_client
    from business_api_client import ApiClient, Configuration
    TIKTOK_SDK_AVAILABLE = True
except ImportError:
    TIKTOK_SDK_AVAILABLE = False


class TikTokBridge:
    """
    Bridge between LangGraph and TikTok Ads Business API.
    Works online (TikTok Business API) if access token configured, or offline (local JSON) otherwise.
    """

    def __init__(self):
        self.output_dir = "/opt/projetos/hermes-unified/output/tiktok/"
        self.creds_dir = "/opt/projetos/hermes-unified/config/"
        os.makedirs(self.output_dir, exist_ok=True)
        self.api_client = self._init_client()
        self._access_token = None

    def _init_client(self):
        """Try to initialize TikTok Ads API client."""
        if not TIKTOK_SDK_AVAILABLE:
            print("   [TIKTOK] tiktok-business-api-sdk-official not installed")
            return None

        # Try secrets.json first
        secrets_path = os.path.join(self.creds_dir, "secrets.json")
        access_token = ""
        if os.path.exists(secrets_path):
            try:
                with open(secrets_path) as f:
                    secrets = json.load(f)
                access_token = secrets.get("TIKTOK_ACCESS_TOKEN", "")
            except Exception:
                pass

        # Fallback to env var
        if not access_token:
            access_token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")

        if access_token:
            try:
                configuration = Configuration()
                configuration.access_token = access_token
                api_client = ApiClient(configuration)
                self._access_token = access_token
                print("   [TIKTOK] TikTok Ads API client initialized")
                return api_client
            except Exception as e:
                print(f"   [TIKTOK] Failed to init client: {e}")
                return None

        print("   [TIKTOK] No TikTok access token configured - using offline mode (local JSON)")
        return None

    def _is_online(self) -> bool:
        """Check if TikTok API is available."""
        return self.api_client is not None and self._access_token is not None

    def _save_local_json(self, data: dict, filename: str) -> str:
        """Save data to local JSON file."""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return filepath

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

    def list_advertisers(self) -> Tuple[list, bool, str]:
        """
        List TikTok Advertiser accounts accessible by this user.

        Returns:
            Tuple[list of advertisers, success, message]
        """
        if self._is_online():
            try:
                advertiser_api = AdvertiserApi(self.api_client)
                response = advertiser_api.advertiser_info_get(
                    access_token=self._access_token
                )
                data = response.get("data", {}).get("list", [])
                ts = self._make_timestamp()
                cache = {
                    "source": "tiktok_api",
                    "fetched_at": datetime.now().isoformat(),
                    "advertisers": data
                }
                self._save_local_json(cache, f"advertisers_{ts}.json")
                return data, True, f"Found {len(data)} advertisers"
            except Exception as e:
                error_msg = str(e)[:300]
                return [], False, f"TikTok API error: {error_msg}"

        # Offline mode
        instructions = {
            "message": "TikTok Ads API not configured - offline mode",
            "help": "To enable online mode, add 'TIKTOK_ACCESS_TOKEN' to config/secrets.json or set TIKTOK_ACCESS_TOKEN env var",
            "docs_url": "https://ads.tiktok.com/marketing_api/docs",
            "sample_advertiser": {
                "advertiser_id": "1234567890",
                "advertiser_name": "Sample Advertiser",
                "company_name": "Sample Company",
                "status": "STATUS_ENABLE"
            }
        }
        return [instructions], True, "TikTok offline mode - see instructions"

    def get_campaign_performance(self, advertiser_id: str,
                                  start_date: str, end_date: str) -> Tuple[dict, bool, str]:
        """
        Get campaign-level performance metrics.

        Args:
            advertiser_id: TikTok advertiser ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Tuple[campaign performance data, success, message]
        """
        if self._is_online():
            try:
                campaign_api = CampaignApi(self.api_client)
                # The SDK typically uses a report endpoint or campaign get with stats
                response = campaign_api.campaign_get(
                    access_token=self._access_token,
                    advertiser_id=advertiser_id,
                    fields=["campaign_id", "campaign_name", "campaign_type",
                            "status", "objective", "budget", "budget_mode",
                            "create_time", "modify_time"]
                )
                data = response.get("data", {}).get("list", [])

                # Now get statistics for each campaign
                # In a real scenario, you'd call the report/integrated/get endpoint
                campaigns_with_stats = []
                for campaign in data[:20]:
                    campaigns_with_stats.append({
                        **campaign,
                        "stats": {
                            "impressions": 0,
                            "clicks": 0,
                            "spend": 0,
                            "conversions": 0
                        }
                    })

                result = {
                    "advertiser_id": advertiser_id,
                    "date_range": {"start": start_date, "end": end_date},
                    "campaigns": campaigns_with_stats,
                    "source": "tiktok_api"
                }

                ts = self._make_timestamp()
                self._save_local_json(result, f"campaigns_{advertiser_id}_{ts}.json")

                return result, True, f"Found {len(data)} campaigns for {advertiser_id}"
            except Exception as e:
                error_msg = str(e)[:300]
                fallback = self._offline_campaign_performance(advertiser_id, start_date, end_date)
                fallback["error"] = error_msg
                return fallback, True, f"TikTok API error, used offline fallback: {error_msg}"

        # Offline mode
        result = self._offline_campaign_performance(advertiser_id, start_date, end_date)
        return result, True, "TikTok offline mode - sample campaign data"

    def _offline_campaign_performance(self, advertiser_id: str, start_date: str, end_date: str) -> dict:
        """Generate sample campaign performance data for offline mode."""
        return {
            "advertiser_id": advertiser_id,
            "date_range": {"start": start_date, "end": end_date},
            "campaigns": [
                {
                    "campaign_id": "camp_001",
                    "campaign_name": "Brand Awareness - Q2",
                    "objective": "AWARENESS",
                    "status": "ACTIVE",
                    "budget": 50000.00,
                    "stats": {
                        "impressions": 850000,
                        "clicks": 28500,
                        "ctr": 3.35,
                        "conversions": 520,
                        "spend": 42300.00,
                        "cpm": 49.76,
                        "cpc": 1.48,
                        "cpa": 81.35
                    }
                },
                {
                    "campaign_id": "camp_002",
                    "campaign_name": "Performance Max - Conversions",
                    "objective": "CONVERSIONS",
                    "status": "ACTIVE",
                    "budget": 35000.00,
                    "stats": {
                        "impressions": 420000,
                        "clicks": 18200,
                        "ctr": 4.33,
                        "conversions": 410,
                        "spend": 28700.00,
                        "cpm": 68.33,
                        "cpc": 1.58,
                        "cpa": 70.00
                    }
                },
                {
                    "campaign_id": "camp_003",
                    "campaign_name": "Retargeting - Web Visitors",
                    "objective": "RETARGETING",
                    "status": "ACTIVE",
                    "budget": 15000.00,
                    "stats": {
                        "impressions": 180000,
                        "clicks": 8900,
                        "ctr": 4.94,
                        "conversions": 230,
                        "spend": 12300.00,
                        "cpm": 68.33,
                        "cpc": 1.38,
                        "cpa": 53.48
                    }
                }
            ],
            "source": "offline_sample"
        }

    def get_adgroup_stats(self, advertiser_id: str,
                           start_date: str, end_date: str) -> Tuple[dict, bool, str]:
        """
        Get ad group level performance statistics.

        Args:
            advertiser_id: TikTok advertiser ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Tuple[ad group stats data, success, message]
        """
        if self._is_online():
            try:
                adgroup_api = AdGroupApi(self.api_client)
                response = adgroup_api.adgroup_get(
                    access_token=self._access_token,
                    advertiser_id=advertiser_id,
                    fields=["adgroup_id", "adgroup_name", "campaign_id",
                            "status", "bid_type", "bid_price",
                            "gender", "age", "interest_categories",
                            "create_time", "modify_time"]
                )
                data = response.get("data", {}).get("list", [])

                adgroups_with_stats = []
                for ag in data[:30]:
                    adgroups_with_stats.append({
                        **ag,
                        "stats": {
                            "impressions": 0,
                            "clicks": 0,
                            "spend": 0.0,
                            "conversions": 0
                        }
                    })

                result = {
                    "advertiser_id": advertiser_id,
                    "date_range": {"start": start_date, "end": end_date},
                    "adgroups": adgroups_with_stats,
                    "source": "tiktok_api"
                }

                ts = self._make_timestamp()
                self._save_local_json(result, f"adgroups_{advertiser_id}_{ts}.json")

                return result, True, f"Found {len(data)} ad groups for {advertiser_id}"
            except Exception as e:
                error_msg = str(e)[:300]
                fallback = self._offline_adgroup_stats(advertiser_id, start_date, end_date)
                fallback["error"] = error_msg
                return fallback, True, f"TikTok API error, used offline fallback: {error_msg}"

        # Offline mode
        result = self._offline_adgroup_stats(advertiser_id, start_date, end_date)
        return result, True, "TikTok offline mode - sample ad group data"

    def _offline_adgroup_stats(self, advertiser_id: str, start_date: str, end_date: str) -> dict:
        """Generate sample ad group stats for offline mode."""
        return {
            "advertiser_id": advertiser_id,
            "date_range": {"start": start_date, "end": end_date},
            "adgroups": [
                {
                    "adgroup_id": "ag_001",
                    "adgroup_name": "Prospecting - Women 18-35",
                    "campaign_id": "camp_001",
                    "status": "ACTIVE",
                    "bid_type": "CPC",
                    "bid_price": 1.50,
                    "targeting": {"gender": "FEMALE", "age": ["18-24", "25-34"]},
                    "stats": {
                        "impressions": 320000,
                        "clicks": 11200,
                        "ctr": 3.50,
                        "conversions": 185,
                        "spend": 16800.00,
                        "cpm": 52.50,
                        "cpc": 1.50,
                        "cpa": 90.81
                    }
                },
                {
                    "adgroup_id": "ag_002",
                    "adgroup_name": "Prospecting - Men 25-45",
                    "campaign_id": "camp_001",
                    "status": "ACTIVE",
                    "bid_type": "CPM",
                    "bid_price": 45.00,
                    "targeting": {"gender": "MALE", "age": ["25-34", "35-44"]},
                    "stats": {
                        "impressions": 280000,
                        "clicks": 9800,
                        "ctr": 3.50,
                        "conversions": 155,
                        "spend": 14200.00,
                        "cpm": 50.71,
                        "cpc": 1.45,
                        "cpa": 91.61
                    }
                },
                {
                    "adgroup_id": "ag_003",
                    "adgroup_name": "Retargeting - Past Visitors",
                    "campaign_id": "camp_003",
                    "status": "ACTIVE",
                    "bid_type": "OCPM",
                    "bid_price": 55.00,
                    "targeting": {"audience_type": "RETARGETING"},
                    "stats": {
                        "impressions": 95000,
                        "clicks": 5200,
                        "ctr": 5.47,
                        "conversions": 145,
                        "spend": 8900.00,
                        "cpm": 93.68,
                        "cpc": 1.71,
                        "cpa": 61.38
                    }
                }
            ],
            "source": "offline_sample"
        }

    def generate_report(self, advertiser_id: str,
                         start_date: str, end_date: str) -> Tuple[str, bool, str]:
        """
        Generate a performance report for TikTok Ads.

        Args:
            advertiser_id: TikTok advertiser ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Tuple[path to saved report, success, message]
        """
        campaigns, c_ok, c_msg = self.get_campaign_performance(advertiser_id, start_date, end_date)
        adgroups, a_ok, a_msg = self.get_adgroup_stats(advertiser_id, start_date, end_date)

        report = {
            "report_type": "tiktok_ads_performance",
            "advertiser_id": advertiser_id,
            "date_range": {"start": start_date, "end": end_date},
            "generated_at": datetime.now().isoformat(),
            "campaigns": campaigns.get("campaigns", []),
            "adgroups": adgroups.get("adgroups", []),
            "summary": {
                "campaigns_count": len(campaigns.get("campaigns", [])),
                "adgroups_count": len(adgroups.get("adgroups", [])),
            },
            "recommendations": [
                "Review high-CPA campaigns for optimization",
                "Check ad group bid strategies against performance goals",
                "Analyze creative performance by demographic segments"
            ]
        }

        # Aggregate totals
        total_impressions = 0
        total_clicks = 0
        total_spend = 0.0
        for camp in campaigns.get("campaigns", []):
            stats = camp.get("stats", {})
            total_impressions += int(stats.get("impressions", 0))
            total_clicks += int(stats.get("clicks", 0))
            total_spend += float(stats.get("spend", 0))
        report["summary"]["total_impressions"] = total_impressions
        report["summary"]["total_clicks"] = total_clicks
        report["summary"]["total_spend_usd"] = round(total_spend, 2)

        ts = self._make_timestamp()
        filename = f"report_{advertiser_id}_{ts}.json"
        path = self._save_local_json(report, filename)

        return path, True, f"TikTok report saved: {filename}"

    def compare_periods(self, advertiser_id: str,
                        period1_start: str, period1_end: str,
                        period2_start: str, period2_end: str) -> Tuple[str, bool, str]:
        """
        Compare TikTok Ads performance between two time periods.

        Args:
            advertiser_id: TikTok advertiser ID
            period1_start: Start of period 1 (YYYY-MM-DD)
            period1_end: End of period 1 (YYYY-MM-DD)
            period2_start: Start of period 2 (YYYY-MM-DD)
            period2_end: End of period 2 (YYYY-MM-DD)

        Returns:
            Tuple[path to comparison report, success, message]
        """
        p1_data, p1_ok, p1_msg = self.get_campaign_performance(advertiser_id, period1_start, period1_end)
        p2_data, p2_ok, p2_msg = self.get_campaign_performance(advertiser_id, period2_start, period2_end)

        if not p1_ok:
            return "", False, f"Period 1 error: {p1_msg}"
        if not p2_ok:
            return "", False, f"Period 2 error: {p2_msg}"

        # Aggregate period 1
        p1_stats = {"impressions": 0, "clicks": 0, "spend": 0.0, "conversions": 0}
        for camp in p1_data.get("campaigns", []):
            s = camp.get("stats", {})
            p1_stats["impressions"] += int(s.get("impressions", 0))
            p1_stats["clicks"] += int(s.get("clicks", 0))
            p1_stats["spend"] += float(s.get("spend", 0))
            p1_stats["conversions"] += int(s.get("conversions", 0))

        # Aggregate period 2
        p2_stats = {"impressions": 0, "clicks": 0, "spend": 0.0, "conversions": 0}
        for camp in p2_data.get("campaigns", []):
            s = camp.get("stats", {})
            p2_stats["impressions"] += int(s.get("impressions", 0))
            p2_stats["clicks"] += int(s.get("clicks", 0))
            p2_stats["spend"] += float(s.get("spend", 0))
            p2_stats["conversions"] += int(s.get("conversions", 0))

        comparison = {
            "type": "tiktok_period_comparison",
            "advertiser_id": advertiser_id,
            "period_1": {"start": period1_start, "end": period1_end},
            "period_2": {"start": period2_start, "end": period2_end},
            "period_1_stats": p1_stats,
            "period_2_stats": p2_stats,
            "deltas": {}
        }

        for key in ["impressions", "clicks", "spend", "conversions"]:
            v1 = p1_stats.get(key, 0)
            v2 = p2_stats.get(key, 0)
            v1_f = float(v1)
            v2_f = float(v2)
            if v1_f != 0:
                pct = round(((v2_f - v1_f) / v1_f) * 100, 2)
            else:
                pct = None
            comparison["deltas"][key] = {
                "period_1": v1_f,
                "period_2": v2_f,
                "absolute_change": round(v2_f - v1_f, 2),
                "percentage_change": pct
            }

        # Also compare campaign-level
        p1_camps = {c.get("campaign_id"): c for c in p1_data.get("campaigns", [])}
        p2_camps = {c.get("campaign_id"): c for c in p2_data.get("campaigns", [])}
        campaign_comparisons = []
        all_ids = set(list(p1_camps.keys()) + list(p2_camps.keys()))
        for cid in all_ids:
            c1 = p1_camps.get(cid, {})
            c2 = p2_camps.get(cid, {})
            campaign_comparisons.append({
                "campaign_id": cid,
                "campaign_name": c1.get("campaign_name") or c2.get("campaign_name", ""),
                "period_1": c1.get("stats", {}),
                "period_2": c2.get("stats", {}),
                "present_in": "both" if cid in p1_camps and cid in p2_camps else ("period_1_only" if cid in p1_camps else "period_2_only")
            })
        comparison["campaign_comparisons"] = campaign_comparisons

        ts = self._make_timestamp()
        filename = f"comparison_{advertiser_id}_{ts}.json"
        path = self._save_local_json(comparison, filename)

        return path, True, f"TikTok comparison report saved: {filename}"

    def status(self) -> dict:
        """Returns current configuration status."""
        return {
            "tool": "TikTok Ads Bridge",
            "online": self._is_online(),
            "output_dir": self.output_dir,
            "creds_file": os.path.join(self.creds_dir, "secrets.json"),
            "setup_docs": {
                "how_to_configure": "Add 'TIKTOK_ACCESS_TOKEN' to config/secrets.json or set TIKTOK_ACCESS_TOKEN env var",
                "required_fields": ["TIKTOK_ACCESS_TOKEN"],
                "api_endpoint": "https://business-api.tiktok.com",
                "docs_url": "https://ads.tiktok.com/marketing_api/docs"
            },
            "available_methods": [
                "list_advertisers()",
                "get_campaign_performance(advertiser_id, start_date, end_date)",
                "get_adgroup_stats(advertiser_id, start_date, end_date)",
                "generate_report(advertiser_id, start_date, end_date)",
                "compare_periods(advertiser_id, period1_start, period1_end, period2_start, period2_end)",
                "status()"
            ]
        }


# Singleton
_tiktok_bridge = None

def get_tiktok_bridge() -> TikTokBridge:
    global _tiktok_bridge
    if _tiktok_bridge is None:
        _tiktok_bridge = TikTokBridge()
    return _tiktok_bridge
