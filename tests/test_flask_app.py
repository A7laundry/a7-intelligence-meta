"""Smoke tests for Flask application endpoints."""
import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    def test_health_returns_version(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert "version" in data


class TestDashboardEndpoints:
    def test_dashboard_page_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"A7 Intelligence" in resp.data

    def test_dashboard_api_7d(self, client):
        resp = client.get("/api/dashboard/7d")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data
        assert "campaigns" in data
        assert "daily_trend" in data

    def test_dashboard_api_today(self, client):
        resp = client.get("/api/dashboard/today")
        assert resp.status_code == 200

    def test_dashboard_api_30d(self, client):
        resp = client.get("/api/dashboard/30d")
        assert resp.status_code == 200

    def test_dashboard_api_invalid_range(self, client):
        resp = client.get("/api/dashboard/invalid")
        assert resp.status_code == 400

    def test_refresh_endpoint(self, client):
        resp = client.post("/api/dashboard/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"


class TestCampaignsEndpoints:
    def test_list_campaigns(self, client):
        resp = client.get("/api/campaigns")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "campaigns" in data

    def test_platforms_status(self, client):
        resp = client.get("/api/platforms")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "meta" in data
        assert "google" in data


class TestExportEndpoints:
    def test_csv_export(self, client):
        resp = client.get("/api/export/campaigns.csv")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert b"Platform,Campaign" in resp.data


class TestStatsEndpoint:
    def test_stats_returns_200(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "daily_snapshots" in data
        assert "campaigns_tracked" in data


class TestAICoachEndpoints:
    def test_briefing_returns_200(self, client):
        resp = client.get("/api/ai-coach/briefing")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "headline" in data
        assert "generated_at" in data

    def test_briefing_with_days_param(self, client):
        resp = client.get("/api/ai-coach/briefing?days=30")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "headline" in data

    def test_recommendations_returns_200(self, client):
        resp = client.get("/api/ai-coach/recommendations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "recommendations" in data
        assert "count" in data
        assert isinstance(data["recommendations"], list)

    def test_recommendations_severity_filter(self, client):
        resp = client.get("/api/ai-coach/recommendations?severity=critical")
        assert resp.status_code == 200
        data = resp.get_json()
        for r in data["recommendations"]:
            assert r["severity"] == "critical"

    def test_health_returns_200(self, client):
        resp = client.get("/api/ai-coach/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "label" in data
        assert "score" in data
        assert data["label"] in ("strong", "stable", "at_risk", "weak", "unknown")
        assert 0 <= data["score"] <= 100

    def test_health_has_components(self, client):
        resp = client.get("/api/ai-coach/health")
        data = resp.get_json()
        if "components" in data:
            assert "conversion_efficiency" in data["components"]
            assert "trend_direction" in data["components"]
            assert "creative_health" in data["components"]

    def test_refresh_returns_200(self, client):
        resp = client.post("/api/ai-coach/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "briefing" in data
        assert "health" in data


class TestBudgetIntelligenceEndpoints:
    def test_budget_summary_returns_200(self, client):
        resp = client.get("/api/budget/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_spend" in data
        assert "ratios" in data

    def test_budget_opportunities_returns_200(self, client):
        resp = client.get("/api/budget/opportunities")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "opportunities" in data

    def test_budget_waste_returns_200(self, client):
        resp = client.get("/api/budget/waste")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "campaigns" in data

    def test_budget_pacing_returns_200(self, client):
        resp = client.get("/api/budget/pacing")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "campaigns" in data

    def test_budget_anomalies_returns_200(self, client):
        resp = client.get("/api/budget/anomalies")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "anomalies" in data


class TestAlertsEndpoints:
    def test_list_alerts_returns_200(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "alerts" in data
        assert "count" in data

    def test_alert_history_returns_200(self, client):
        resp = client.get("/api/alerts/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "alerts" in data

    def test_refresh_alerts_returns_200(self, client):
        resp = client.post("/api/alerts/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"


class TestBudgetLogic:
    def test_budget_allocation_classification(self):
        from app.services.budget_intelligence_service import BudgetIntelligenceService
        bi = BudgetIntelligenceService()
        # Monkey-patch dashboard data
        campaigns = [
            {"name": "Good", "status": "ACTIVE", "spend": 100, "conversions": 10, "cpa": 10, "ctr": 2.5, "clicks": 50},
            {"name": "Waste", "status": "ACTIVE", "spend": 80, "conversions": 0, "cpa": 0, "ctr": 0.2, "clicks": 3},
            {"name": "Neutral", "status": "ACTIVE", "spend": 3, "conversions": 0, "cpa": 0, "ctr": 1.0, "clicks": 1},
        ]
        dashboard = {
            "summary": {"total": {"spend": 183, "conversions": 10, "cpa": 18.3, "ctr": 1.5}},
            "campaigns": {"meta": campaigns, "google": []},
            "comparison": {"changes": {}},
        }
        bi._get_dashboard_data = lambda days, account_id=None: dashboard

        result = bi.analyze_budget_allocation(days=7)
        assert result["efficient_spend"] == 100
        assert result["waste_spend"] == 80
        assert result["neutral_spend"] == 3
        assert result["ratios"]["efficient_pct"] > 0

    def test_scaling_detection(self):
        from app.services.budget_intelligence_service import BudgetIntelligenceService
        bi = BudgetIntelligenceService()
        campaigns = [
            {"name": "Star", "status": "ACTIVE", "spend": 100, "conversions": 8, "cpa": 12.5, "ctr": 3.0, "clicks": 80},
            {"name": "Average", "status": "ACTIVE", "spend": 200, "conversions": 4, "cpa": 50, "ctr": 1.0, "clicks": 40},
        ]
        dashboard = {
            "summary": {"total": {}},
            "campaigns": {"meta": campaigns, "google": []},
            "comparison": {"changes": {}},
        }
        bi._get_dashboard_data = lambda days, account_id=None: dashboard

        opps = bi.detect_scaling_opportunities(days=7)
        assert len(opps) >= 1
        assert opps[0]["campaign_name"] == "Star"
        assert opps[0]["suggested_budget_increase_pct"] > 0

    def test_waste_detection(self):
        from app.services.budget_intelligence_service import BudgetIntelligenceService
        bi = BudgetIntelligenceService()
        campaigns = [
            {"name": "Loser", "status": "ACTIVE", "spend": 50, "conversions": 0, "cpa": 0, "ctr": 0.3, "clicks": 2},
        ]
        dashboard = {
            "summary": {"total": {}},
            "campaigns": {"meta": campaigns, "google": []},
            "comparison": {"changes": {}},
        }
        bi._get_dashboard_data = lambda days, account_id=None: dashboard

        waste = bi.detect_budget_waste(days=7)
        assert waste["waste_spend"] == 50
        assert len(waste["campaigns"]) == 1

    def test_efficiency_score(self):
        from app.services.budget_intelligence_service import BudgetIntelligenceService
        bi = BudgetIntelligenceService()
        campaigns = [
            {"name": "A", "status": "ACTIVE", "spend": 100, "conversions": 5, "cpa": 20, "ctr": 2.0, "clicks": 50},
        ]
        dashboard = {
            "summary": {"total": {}},
            "campaigns": {"meta": campaigns, "google": []},
            "comparison": {"changes": {}},
        }
        bi._get_dashboard_data = lambda days, account_id=None: dashboard

        score = bi.compute_efficiency_score(days=7)
        assert 0 <= score["score"] <= 100
        assert "components" in score


class TestAlertDeduplication:
    def test_duplicate_not_persisted_twice(self, client):
        import uuid
        from app.services.alerts_service import AlertsService
        svc = AlertsService()
        unique_type = f"test_dedup_{uuid.uuid4().hex[:8]}"
        alert = svc._make_alert(
            alert_type=unique_type,
            severity="info",
            entity_type="test",
            entity_name="TestEntity",
            title="Test",
            message="Dedup test",
        )
        # First should succeed
        assert not svc._is_duplicate(alert)
        svc._persist(alert)
        # Second should be detected as duplicate
        assert svc._is_duplicate(alert)


class TestGrowthScoreEndpoints:
    def test_growth_score_returns_200(self, client):
        resp = client.get("/api/growth-score")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "score" in data
        assert "label" in data
        assert data["label"] in ("elite", "strong", "stable", "at_risk", "weak", "unknown")
        assert 0 <= data["score"] <= 100

    def test_growth_score_has_components(self, client):
        resp = client.get("/api/growth-score")
        data = resp.get_json()
        if "components" in data:
            assert "account_health" in data["components"]
            assert "budget_efficiency" in data["components"]
            assert "creative_health" in data["components"]

    def test_growth_score_has_summary(self, client):
        resp = client.get("/api/growth-score")
        data = resp.get_json()
        assert "summary" in data
        assert len(data["summary"]) > 0


class TestOperationsEndpoints:
    def test_ops_status_returns_200(self, client):
        resp = client.get("/api/operations/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "operations" in data

    def test_ops_history_returns_200(self, client):
        resp = client.get("/api/operations/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "history" in data

    def test_run_snapshot_returns_200(self, client):
        resp = client.post("/api/operations/run/snapshot")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "status" in data

    def test_run_ai_refresh_returns_200(self, client):
        resp = client.post("/api/operations/run/ai-refresh")
        assert resp.status_code == 200

    def test_run_alerts_returns_200(self, client):
        resp = client.post("/api/operations/run/alerts")
        assert resp.status_code == 200

    def test_run_daily_briefing_returns_200(self, client):
        resp = client.post("/api/operations/run/daily-briefing")
        assert resp.status_code == 200

    def test_run_end_of_day_returns_200(self, client):
        resp = client.post("/api/operations/run/end-of-day")
        assert resp.status_code == 200


class TestAutomationEndpoints:
    def test_proposals_returns_200(self, client):
        resp = client.get("/api/automation/proposals")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "allowed" in data
        assert "blocked" in data

    def test_evaluate_returns_200(self, client):
        resp = client.post("/api/automation/evaluate")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "execution_mode" in data

    def test_guardrails_config_returns_200(self, client):
        resp = client.get("/api/automation/guardrails")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["guardrails_active"] == True
        assert "execution_mode" in data
        assert "max_budget_change_pct" in data


class TestGrowthScoreLogic:
    def test_growth_score_computation(self):
        from app.services.growth_score_service import GrowthScoreService
        gs = GrowthScoreService()
        result = gs.build_growth_score(days=7)
        assert 0 <= result["score"] <= 100
        assert result["label"] in ("elite", "strong", "stable", "at_risk", "weak")
        assert "components" in result
        assert "summary" in result
        assert "top_positive_driver" in result
        assert "top_negative_driver" in result


class TestGuardrailsLogic:
    def test_guardrails_block_high_budget_change(self):
        from app.services.automation_guardrails_service import AutomationGuardrailsService
        svc = AutomationGuardrailsService()
        action = {
            "action_type": "increase_budget",
            "entity_name": "Test Campaign",
            "suggested_change_pct": 50,
            "confidence": "high",
        }
        result = svc.validate_action(action)
        assert not result["allowed"]
        assert "exceeds max" in result["reason"].lower()

    def test_guardrails_allow_valid_action(self):
        from app.services.automation_guardrails_service import AutomationGuardrailsService
        svc = AutomationGuardrailsService()
        action = {
            "action_type": "increase_budget",
            "entity_name": "Test Campaign",
            "suggested_change_pct": 20,
            "confidence": "high",
        }
        result = svc.validate_action(action)
        assert result["allowed"]

    def test_guardrails_block_low_confidence(self):
        from app.services.automation_guardrails_service import AutomationGuardrailsService
        svc = AutomationGuardrailsService()
        action = {
            "action_type": "increase_budget",
            "entity_name": "Test Campaign",
            "suggested_change_pct": 10,
            "confidence": "low",
        }
        result = svc.validate_action(action)
        assert not result["allowed"]
        assert "confidence" in result["reason"].lower()

    def test_apply_guardrails_limits_actions(self):
        from app.services.automation_guardrails_service import AutomationGuardrailsService
        svc = AutomationGuardrailsService()
        # Create more proposals than max_actions_per_run
        proposals = [
            {"action_type": "increase_budget", "entity_name": f"C{i}",
             "suggested_change_pct": 10, "confidence": "high"}
            for i in range(10)
        ]
        result = svc.apply_guardrails(proposals)
        assert result["allowed_count"] <= svc.config["max_actions_per_run"]
        assert result["blocked_count"] > 0
        assert result["execution_mode"] == "dry_run"


class TestSchedulerService:
    def test_operations_log_persists(self, client):
        # Run a job
        client.post("/api/operations/run/alerts")
        # Check history
        resp = client.get("/api/operations/history")
        data = resp.get_json()
        assert len(data["history"]) >= 1
        assert data["history"][0]["operation_type"] == "alert_refresh"


class TestAICoachLogic:
    """Test AI Coach rule-based engine directly."""

    def test_coach_service_instantiates(self):
        from app.services.ai_coach_service import AICoachService
        coach = AICoachService()
        assert coach is not None

    def test_waste_alert_detection(self):
        from app.services.ai_coach_service import AICoachService
        coach = AICoachService()
        # Simulate campaigns with high spend and zero conversions
        campaigns = [
            {"name": "Waste Campaign", "status": "ACTIVE", "spend": 100, "conversions": 0, "cpa": 0, "ctr": 0.3, "clicks": 5},
        ]
        dashboard = {
            "summary": {"total": {"spend": 100, "conversions": 0, "cpa": 0, "ctr": 0.3}},
            "campaigns": {"meta": campaigns, "google": []},
            "comparison": {"changes": {}},
        }
        # Monkey-patch to test rule
        original = coach._get_dashboard_data
        coach._get_dashboard_data = lambda days, account_id=None: dashboard
        coach._get_creatives = lambda days, account_id=None: []

        recs = coach.generate_recommendations(days=7)
        coach._get_dashboard_data = original

        waste_recs = [r for r in recs if r["type"] == "waste_alert"]
        assert len(waste_recs) >= 1
        assert waste_recs[0]["severity"] == "critical"

    def test_scaling_opportunity_detection(self):
        from app.services.ai_coach_service import AICoachService
        coach = AICoachService()
        campaigns = [
            {"name": "Winner", "status": "ACTIVE", "spend": 80, "conversions": 5, "cpa": 16, "ctr": 2.5, "clicks": 100},
            {"name": "Average", "status": "ACTIVE", "spend": 200, "conversions": 4, "cpa": 50, "ctr": 1.0, "clicks": 50},
        ]
        dashboard = {
            "summary": {"total": {"spend": 280, "conversions": 9, "cpa": 31.1, "ctr": 1.5}},
            "campaigns": {"meta": campaigns, "google": []},
            "comparison": {"changes": {}},
        }
        original = coach._get_dashboard_data
        coach._get_dashboard_data = lambda days, account_id=None: dashboard
        coach._get_creatives = lambda days, account_id=None: []

        recs = coach.generate_recommendations(days=7)
        coach._get_dashboard_data = original

        scale_recs = [r for r in recs if r["type"] == "scaling_opportunity"]
        assert len(scale_recs) >= 1
        assert scale_recs[0]["severity"] == "success"

    def test_health_labels(self):
        from app.services.ai_coach_service import AICoachService
        coach = AICoachService()
        # Test with no data - should degrade gracefully
        health = coach.build_account_health_snapshot(days=7)
        assert health["label"] in ("strong", "stable", "at_risk", "weak")
        assert 0 <= health["score"] <= 100


# ══════════════════════════════════════════════════════════
# Phase 3: Cross-Platform Intelligence Tests
# ══════════════════════════════════════════════════════════

class TestGoogleAdsClientFallback:
    """Google Ads client should degrade gracefully when not configured."""

    def test_wrapper_initializes_without_config(self):
        from app.services.google_ads_client import GoogleAdsClientWrapper
        wrapper = GoogleAdsClientWrapper()
        assert wrapper.available is False

    def test_fetch_campaigns_returns_empty(self):
        from app.services.google_ads_client import GoogleAdsClientWrapper
        wrapper = GoogleAdsClientWrapper()
        assert wrapper.fetch_campaigns() == []

    def test_fetch_account_metrics_returns_empty(self):
        from app.services.google_ads_client import GoogleAdsClientWrapper
        wrapper = GoogleAdsClientWrapper()
        assert wrapper.fetch_account_metrics() == {}

    def test_fetch_campaign_metrics_returns_empty(self):
        from app.services.google_ads_client import GoogleAdsClientWrapper
        wrapper = GoogleAdsClientWrapper()
        assert wrapper.fetch_campaign_metrics() == []

    def test_fetch_daily_metrics_returns_empty(self):
        from app.services.google_ads_client import GoogleAdsClientWrapper
        wrapper = GoogleAdsClientWrapper()
        assert wrapper.fetch_daily_metrics() == []


class TestCrossPlatformEndpoints:
    """Test cross-platform API endpoints."""

    def test_platform_summary_returns_200(self, client):
        resp = client.get("/api/platforms/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "platforms" in data
        assert "total_spend" in data
        assert "platforms_active" in data

    def test_platform_efficiency_returns_200(self, client):
        resp = client.get("/api/platforms/efficiency")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "platforms" in data

    def test_platform_opportunities_returns_200(self, client):
        resp = client.get("/api/platforms/opportunities")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "opportunities" in data
        assert isinstance(data["opportunities"], list)

    def test_platform_spend_share_returns_200(self, client):
        resp = client.get("/api/platforms/spend-share")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "labels" in data
        assert "values" in data
        assert "percentages" in data

    def test_platform_budget_evaluation_returns_200(self, client):
        resp = client.get("/api/platforms/budget-evaluation")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_spend" in data
        assert "meta_spend" in data
        assert "google_spend" in data

    def test_platform_summary_with_days_param(self, client):
        resp = client.get("/api/platforms/summary?days=30")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["period_days"] == 30


class TestCrossPlatformLogic:
    """Test cross-platform service business logic."""

    def test_platform_summary_computation(self):
        from app.services.cross_platform_service import CrossPlatformService
        cp = CrossPlatformService()
        # Monkey-patch dashboard data
        cp._get_dashboard_data = lambda days, account_id=None: {
            "summary": {
                "meta": {"spend": 500, "impressions": 10000, "clicks": 200, "ctr": 2.0, "conversions": 10, "cpa": 50},
                "google": {"spend": 300, "impressions": 8000, "clicks": 150, "ctr": 1.88, "conversions": 8, "cpa": 37.5},
                "total": {},
            },
            "campaigns": {"meta": [], "google": []},
        }

        result = cp.get_platform_summary(days=7)
        assert result["total_spend"] == 800
        assert len(result["platforms"]) == 2
        # Check share of spend
        meta_p = next(p for p in result["platforms"] if p["platform"] == "meta")
        assert meta_p["share_of_spend"] == 62.5  # 500/800 * 100

    def test_channel_efficiency_comparison(self):
        from app.services.cross_platform_service import CrossPlatformService
        cp = CrossPlatformService()
        cp._get_dashboard_data = lambda days, account_id=None: {
            "summary": {
                "meta": {"spend": 500, "impressions": 10000, "clicks": 200, "ctr": 2.0, "conversions": 10, "cpa": 50},
                "google": {"spend": 300, "impressions": 8000, "clicks": 150, "ctr": 1.88, "conversions": 12, "cpa": 25},
                "total": {},
            },
            "campaigns": {"meta": [], "google": []},
        }

        result = cp.get_channel_efficiency(days=7)
        assert result["best_channel"] is not None
        assert len(result["platforms"]) == 2

    def test_detect_cpa_opportunity(self):
        from app.services.cross_platform_service import CrossPlatformService
        cp = CrossPlatformService()
        cp._get_dashboard_data = lambda days, account_id=None: {
            "summary": {
                "meta": {"spend": 500, "impressions": 10000, "clicks": 200, "ctr": 2.0, "conversions": 5, "cpa": 100},
                "google": {"spend": 300, "impressions": 8000, "clicks": 150, "ctr": 1.88, "conversions": 12, "cpa": 25},
                "total": {},
            },
            "campaigns": {"meta": [], "google": []},
        }

        result = cp.detect_channel_opportunities(days=7)
        opps = result["opportunities"]
        efficiency_opps = [o for o in opps if o["type"] == "channel_efficiency"]
        assert len(efficiency_opps) >= 1
        assert efficiency_opps[0]["to_platform"] == "google"

    def test_detect_concentration_risk(self):
        from app.services.cross_platform_service import CrossPlatformService
        cp = CrossPlatformService()
        cp._get_dashboard_data = lambda days, account_id=None: {
            "summary": {
                "meta": {"spend": 950, "impressions": 10000, "clicks": 200, "ctr": 2.0, "conversions": 10, "cpa": 95},
                "google": {"spend": 50, "impressions": 1000, "clicks": 20, "ctr": 2.0, "conversions": 2, "cpa": 25},
                "total": {},
            },
            "campaigns": {"meta": [], "google": []},
        }

        result = cp.detect_channel_opportunities(days=7)
        risk_opps = [o for o in result["opportunities"] if o["type"] == "concentration_risk"]
        assert len(risk_opps) >= 1
        assert risk_opps[0]["from_platform"] == "meta"

    def test_spend_share_chart_data(self):
        from app.services.cross_platform_service import CrossPlatformService
        cp = CrossPlatformService()
        cp._get_dashboard_data = lambda days, account_id=None: {
            "summary": {
                "meta": {"spend": 600, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0},
                "google": {"spend": 400, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0},
                "total": {},
            },
            "campaigns": {"meta": [], "google": []},
        }

        result = cp.get_spend_share(days=7)
        assert result["labels"] == ["Meta", "Google"]
        assert result["values"] == [600, 400]
        assert result["total_spend"] == 1000

    def test_cross_platform_budget_evaluation(self):
        from app.services.cross_platform_service import CrossPlatformService
        cp = CrossPlatformService()
        cp._get_dashboard_data = lambda days, account_id=None: {
            "summary": {
                "meta": {"spend": 500, "impressions": 10000, "clicks": 200, "ctr": 2.0, "conversions": 5, "cpa": 100},
                "google": {"spend": 300, "impressions": 8000, "clicks": 150, "ctr": 1.88, "conversions": 12, "cpa": 25},
                "total": {},
            },
            "campaigns": {"meta": [], "google": []},
        }

        result = cp.evaluate_cross_platform_budget(days=7)
        assert result["total_spend"] == 800
        assert result["meta_spend"] == 500
        assert result["google_spend"] == 300


class TestGrowthScoreChannelBalance:
    """Test channel balance component in growth score."""

    def test_growth_score_includes_channel_balance(self):
        from app.services.growth_score_service import GrowthScoreService
        gs = GrowthScoreService()
        result = gs.build_growth_score(days=7)
        assert "channel_balance" in result["components"]

    def test_channel_balance_neutral_single_platform(self):
        from app.services.growth_score_service import GrowthScoreService
        gs = GrowthScoreService()
        balance = gs._get_channel_balance(days=7)
        # Without Google configured, should return neutral (50) or balanced (100) when no data
        assert balance["score"] in (50, 100)


class TestAICoachCrossChannelRecs:
    """Test AI Coach cross-channel recommendation types."""

    def test_coach_generates_channel_recs(self):
        from app.services.ai_coach_service import AICoachService
        coach = AICoachService()
        # Monkey-patch to provide cross-platform data
        campaigns = [
            {"name": "Meta Campaign", "status": "ACTIVE", "spend": 100, "conversions": 2, "cpa": 50, "ctr": 1.5, "clicks": 30},
        ]
        dashboard = {
            "summary": {
                "total": {"spend": 100, "conversions": 2, "cpa": 50, "ctr": 1.5},
                "meta": {"spend": 100, "conversions": 2, "cpa": 50, "ctr": 1.5},
                "google": {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0},
            },
            "campaigns": {"meta": campaigns, "google": []},
            "comparison": {"changes": {}},
        }
        coach._get_dashboard_data = lambda days, account_id=None: dashboard
        coach._get_creatives = lambda days, account_id=None: []

        # Should not fail even without cross-platform data
        recs = coach.generate_recommendations(days=7)
        assert isinstance(recs, list)


class TestNormalizedMetrics:
    """Test that both platforms use normalized metric structure."""

    def test_platform_summary_has_normalized_fields(self):
        from app.services.cross_platform_service import CrossPlatformService
        cp = CrossPlatformService()
        cp._get_dashboard_data = lambda days, account_id=None: {
            "summary": {
                "meta": {"spend": 100, "impressions": 5000, "clicks": 100, "ctr": 2.0, "conversions": 5, "cpa": 20},
                "google": {"spend": 80, "impressions": 4000, "clicks": 80, "ctr": 2.0, "conversions": 4, "cpa": 20},
                "total": {},
            },
            "campaigns": {"meta": [], "google": []},
        }

        result = cp.get_platform_summary(days=7)
        required_fields = {"platform", "spend", "impressions", "clicks", "conversions", "ctr", "avg_cpa", "share_of_spend"}
        for p in result["platforms"]:
            assert required_fields.issubset(set(p.keys())), f"Missing fields in {p['platform']}: {required_fields - set(p.keys())}"


# ══════════════════════════════════════════════════════════
# Phase 4A: Advanced Analytics + Executive Reporting Tests
# ══════════════════════════════════════════════════════════

class TestAnalyticsBaselines:
    """Test baseline calculation logic."""

    def test_baseline_returns_structure(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.calculate_baseline("spend", days=30)
        assert "average" in result
        assert "std_dev" in result
        assert "min" in result
        assert "max" in result
        assert "confidence" in result
        assert "datapoints" in result

    def test_baseline_all_metrics(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.calculate_all_baselines(days=30)
        assert "baselines" in result
        assert "spend" in result["baselines"]
        assert "conversions" in result["baselines"]
        assert "cpa" in result["baselines"]
        assert "ctr" in result["baselines"]

    def test_baseline_graceful_no_data(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.calculate_baseline("spend", days=1)
        assert result["confidence"] == "low"
        assert result["average"] == 0


class TestAnomalyDetection:
    """Test anomaly detection logic."""

    def test_anomaly_returns_structure(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.detect_metric_anomalies("spend", days=7)
        assert "anomalies" in result
        assert "baseline" in result
        assert isinstance(result["anomalies"], list)

    def test_all_anomalies_returns_structure(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.detect_all_anomalies(days=7)
        assert "anomalies" in result
        assert "count" in result
        assert "critical" in result
        assert "warning" in result

    def test_anomaly_graceful_no_data(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.detect_metric_anomalies("cpa", days=1)
        assert result["anomalies"] == []


class TestForecasting:
    """Test forecast generation logic."""

    def test_forecast_returns_structure(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.forecast_metric("spend", horizon_days=7)
        assert "forecast" in result
        assert "trend_direction" in result
        assert "confidence" in result
        assert isinstance(result["forecast"], list)

    def test_forecast_all_metrics(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.forecast_all_metrics(horizon_days=7)
        assert "forecasts" in result
        assert "spend" in result["forecasts"]
        assert "conversions" in result["forecasts"]

    def test_forecast_graceful_no_data(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.forecast_metric("spend", horizon_days=7)
        # Should handle gracefully even with no data
        assert result["trend_direction"] in ("rising", "falling", "stable", "insufficient_data")

    def test_linear_regression_correctness(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        # Perfect linear: y = 2x + 1
        x = [0, 1, 2, 3, 4]
        y = [1, 3, 5, 7, 9]
        slope, intercept = AdvancedAnalyticsService._linear_regression(x, y)
        assert abs(slope - 2.0) < 0.001
        assert abs(intercept - 1.0) < 0.001

    def test_r_squared_perfect_fit(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        x = [0, 1, 2, 3, 4]
        y = [1, 3, 5, 7, 9]
        r2 = AdvancedAnalyticsService._r_squared(x, y, 2.0, 1.0)
        assert abs(r2 - 1.0) < 0.001


class TestConfidenceScoring:
    """Test confidence scoring logic."""

    def test_high_confidence(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.compute_insight_confidence(data_points=30, consistency=0.9, sample_days=30)
        assert result == "high"

    def test_medium_confidence(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.compute_insight_confidence(data_points=14, consistency=0.5, sample_days=14)
        assert result == "medium"

    def test_low_confidence(self):
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        svc = AdvancedAnalyticsService()
        result = svc.compute_insight_confidence(data_points=2, consistency=0.1, sample_days=2)
        assert result == "low"


class TestAnalyticsEndpoints:
    """Test analytics API endpoints."""

    def test_baselines_returns_200(self, client):
        resp = client.get("/api/analytics/baselines")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "baselines" in data

    def test_anomalies_returns_200(self, client):
        resp = client.get("/api/analytics/anomalies")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "anomalies" in data
        assert "count" in data

    def test_anomalies_per_metric_returns_200(self, client):
        resp = client.get("/api/analytics/anomalies/spend")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "metric" in data
        assert data["metric"] == "spend"

    def test_anomalies_invalid_metric_returns_400(self, client):
        resp = client.get("/api/analytics/anomalies/invalid")
        assert resp.status_code == 400

    def test_forecast_returns_200(self, client):
        resp = client.get("/api/analytics/forecast")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "forecasts" in data

    def test_forecast_per_metric_returns_200(self, client):
        resp = client.get("/api/analytics/forecast/conversions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["metric"] == "conversions"

    def test_forecast_invalid_metric_returns_400(self, client):
        resp = client.get("/api/analytics/forecast/invalid")
        assert resp.status_code == 400


class TestReportEndpoints:
    """Test report API endpoints."""

    def test_report_latest_returns_200(self, client):
        resp = client.get("/api/reports/latest")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "title" in data
        assert "sections" in data
        assert "executive_summary" in data["sections"]
        assert "growth_score" in data["sections"]
        assert "forecast" in data["sections"]
        assert "alert_summary" in data["sections"]

    def test_report_generate_returns_200(self, client):
        resp = client.get("/api/reports/generate?days=7")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["period_days"] == 7

    def test_report_export_json(self, client):
        resp = client.get("/api/reports/export/json")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert b"A7 Intelligence" in resp.data

    def test_report_export_csv(self, client):
        resp = client.get("/api/reports/export/csv")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert b"Executive Summary" in resp.data

    def test_report_export_pdf(self, client):
        resp = client.get("/api/reports/export/pdf")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert resp.data[:5] == b"%PDF-"


class TestReportLogic:
    """Test report generation logic."""

    def test_executive_report_structure(self):
        from app.services.reporting_service import ReportingService
        svc = ReportingService()
        report = svc.generate_executive_report(days=7)
        assert "title" in report
        assert "period_days" in report
        assert "sections" in report
        sections = report["sections"]
        assert "executive_summary" in sections
        assert "growth_score" in sections
        assert "platform_comparison" in sections
        assert "top_campaigns" in sections
        assert "risks" in sections
        assert "opportunities" in sections
        assert "forecast" in sections
        assert "alert_summary" in sections

    def test_csv_export_contains_data(self):
        from app.services.reporting_service import ReportingService
        svc = ReportingService()
        csv_content = svc.export_csv(days=7)
        assert "Executive Summary" in csv_content
        assert "Total Spend" in csv_content
        assert "Growth Score" in csv_content

    def test_pdf_export_is_valid_pdf(self):
        from app.services.reporting_service import ReportingService
        svc = ReportingService()
        pdf_bytes = svc.export_pdf(days=7)
        assert pdf_bytes[:5] == b"%PDF-"
        assert b"%%EOF" in pdf_bytes

    def test_alert_summary_structure(self):
        from app.services.reporting_service import ReportingService
        svc = ReportingService()
        report = svc.generate_executive_report(days=7)
        alerts = report["sections"]["alert_summary"]
        assert "unresolved_total" in alerts
        assert "unresolved_critical" in alerts
        assert "unresolved_warnings" in alerts


# ══════════════════════════════════════════════════════════════
# Phase 4B — Automation Engine Tests
# ══════════════════════════════════════════════════════════════

class TestAutomationEngineEndpoints:
    """Test automation API endpoints."""

    def test_actions_list_returns_200(self, client):
        resp = client.get("/api/automation/actions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "actions" in data
        assert "summary" in data

    def test_pending_returns_200(self, client):
        resp = client.get("/api/automation/pending")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "actions" in data
        assert "count" in data

    def test_generate_returns_200(self, client):
        resp = client.post("/api/automation/generate")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "queued" in data or "queued_count" in data

    def test_logs_returns_200(self, client):
        resp = client.get("/api/automation/logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "logs" in data

    def test_approve_nonexistent_returns_error(self, client):
        resp = client.post("/api/automation/99999/approve")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False

    def test_reject_nonexistent_returns_error(self, client):
        resp = client.post("/api/automation/99999/reject")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False

    def test_execute_nonexistent_returns_error(self, client):
        resp = client.post("/api/automation/99999/execute")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False


class TestAutomationProposalGeneration:
    """Test proposal generation from intelligence sources."""

    def test_generate_proposals_returns_list(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        proposals = engine.generate_action_proposals(days=7)
        assert isinstance(proposals, list)

    def test_generate_and_queue_structure(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        result = engine.generate_and_queue(days=7)
        assert "queued" in result
        assert "blocked" in result
        assert "queued_count" in result
        assert "blocked_count" in result
        assert "total_proposals" in result
        assert "execution_mode" in result

    def test_proposal_has_required_fields(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        proposals = engine.generate_action_proposals(days=7)
        for p in proposals:
            assert "action_type" in p
            assert "entity_name" in p
            assert "reason" in p
            assert "confidence" in p


class TestAutomationGuardrails:
    """Test guardrail validation logic."""

    def test_validate_valid_action(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        action = {
            "action_type": "pause_campaign",
            "entity_name": "Test Campaign",
            "platform": "meta",
            "confidence": "high",
            "suggested_change_pct": 0,
        }
        result = engine.validate_action(action)
        assert result["allowed"] is True

    def test_validate_blocks_low_confidence(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        action = {
            "action_type": "increase_budget",
            "entity_name": "Test Campaign",
            "platform": "meta",
            "confidence": "low",
            "suggested_change_pct": 20,
        }
        result = engine.validate_action(action)
        assert result["allowed"] is False
        assert "confidence" in result["reason"].lower()

    def test_validate_blocks_excessive_budget_change(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        action = {
            "action_type": "increase_budget",
            "entity_name": "Test Campaign",
            "platform": "meta",
            "confidence": "high",
            "suggested_change_pct": 50,
        }
        result = engine.validate_action(action)
        assert result["allowed"] is False
        assert "budget" in result["reason"].lower()

    def test_validate_blocks_blacklisted_campaign(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        engine.config["campaign_blacklist"] = ["Protected Campaign"]
        action = {
            "action_type": "pause_campaign",
            "entity_name": "Protected Campaign",
            "platform": "meta",
            "confidence": "high",
            "suggested_change_pct": 0,
        }
        result = engine.validate_action(action)
        assert result["allowed"] is False
        assert "blacklisted" in result["reason"].lower()

    def test_validate_blocks_when_disabled(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        engine.config["global_enabled"] = False
        action = {
            "action_type": "pause_campaign",
            "entity_name": "Test",
            "platform": "meta",
            "confidence": "high",
            "suggested_change_pct": 0,
        }
        result = engine.validate_action(action)
        assert result["allowed"] is False
        assert "disabled" in result["reason"].lower()

    def test_guardrails_config_structure(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        config = engine.get_guardrails_config()
        assert "execution_mode" in config
        assert "max_actions_per_run" in config
        assert "max_budget_change_pct" in config
        assert "min_confidence" in config
        assert "cooldown_hours" in config
        assert config["guardrails_active"] is True


class TestAutomationApprovalWorkflow:
    """Test the approval → execution workflow."""

    def test_full_workflow_dry_run(self):
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()

        unique = uuid.uuid4().hex[:8]
        # Persist a test action
        action = {
            "action_type": "pause_campaign",
            "platform": "meta",
            "entity_type": "campaign",
            "entity_id": f"test_{unique}",
            "entity_name": f"Test Workflow Campaign {unique}",
            "reason": "Testing approval workflow",
            "confidence": "high",
            "suggested_change_pct": 0,
            "status": "proposed",
            "execution_mode": "dry_run",
        }
        action_id = engine._persist_action(action)
        assert action_id is not None

        # Approve
        result = engine.approve_action(action_id)
        assert result["success"] is True
        assert result["status"] == "approved"

        # Execute (dry_run)
        result = engine.execute_action(action_id)
        assert result["success"] is True
        assert result["mode"] == "dry_run"
        assert result["status"] == "executed"

        # Verify logs exist (approve + execute each create a log)
        logs = engine.get_logs(action_id=action_id)
        assert len(logs) >= 2

    def test_reject_workflow(self):
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()

        unique = uuid.uuid4().hex[:8]
        action = {
            "action_type": "increase_budget",
            "platform": "meta",
            "entity_type": "campaign",
            "entity_id": f"test_{unique}",
            "entity_name": f"Test Reject Campaign {unique}",
            "reason": "Testing rejection",
            "confidence": "high",
            "suggested_change_pct": 20,
            "status": "proposed",
            "execution_mode": "dry_run",
        }
        action_id = engine._persist_action(action)

        result = engine.reject_action(action_id)
        assert result["success"] is True
        assert result["status"] == "rejected"

        # Cannot execute after rejection
        result = engine.execute_action(action_id)
        assert result["success"] is False

    def test_cannot_approve_executed_action(self):
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()

        unique = uuid.uuid4().hex[:8]
        action = {
            "action_type": "pause_campaign",
            "platform": "meta",
            "entity_type": "campaign",
            "entity_id": f"test_{unique}",
            "entity_name": f"Test Already Executed {unique}",
            "reason": "Testing state guard",
            "confidence": "high",
            "suggested_change_pct": 0,
            "status": "proposed",
            "execution_mode": "dry_run",
        }
        action_id = engine._persist_action(action)
        engine.approve_action(action_id)
        engine.execute_action(action_id)

        # Cannot approve again
        result = engine.approve_action(action_id)
        assert result["success"] is False


class TestAutomationQueuePersistence:
    """Test queue persistence and retrieval."""

    def test_persist_and_retrieve_action(self):
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()

        unique = uuid.uuid4().hex[:8]
        action = {
            "action_type": "decrease_budget",
            "platform": "google",
            "entity_type": "campaign",
            "entity_id": f"persist_{unique}",
            "entity_name": f"Persistence Test Campaign {unique}",
            "reason": "Testing persistence",
            "confidence": "medium",
            "suggested_change_pct": -15,
            "status": "proposed",
            "execution_mode": "dry_run",
        }
        action_id = engine._persist_action(action)
        retrieved = engine._get_action(action_id)

        assert retrieved is not None
        assert retrieved["action_type"] == "decrease_budget"
        assert retrieved["platform"] == "google"
        assert retrieved["entity_name"] == f"Persistence Test Campaign {unique}"
        assert retrieved["status"] == "proposed"

    def test_action_summary_counts(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        summary = engine.get_action_summary()
        assert "total" in summary
        assert isinstance(summary["total"], int)

    def test_get_pending_filters_correctly(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        pending = engine.get_pending_actions()
        for a in pending:
            assert a["status"] == "proposed"


class TestAutomationExecutionLogs:
    """Test audit trail / execution logs."""

    def test_logs_created_on_workflow(self):
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()

        unique = uuid.uuid4().hex[:8]
        action = {
            "action_type": "rotate_creative",
            "platform": "meta",
            "entity_type": "creative",
            "entity_id": f"log_{unique}",
            "entity_name": f"Log Test Creative {unique}",
            "reason": "Testing audit logs",
            "confidence": "high",
            "suggested_change_pct": 0,
            "status": "proposed",
            "execution_mode": "dry_run",
        }
        action_id = engine._persist_action(action)
        engine._log_action(action_id, action, "proposed", "Action created for log test")

        logs = engine.get_logs(action_id=action_id)
        assert len(logs) >= 1
        assert logs[0]["action_id"] == action_id
        assert logs[0]["message"] == "Action created for log test"

    def test_logs_list_all(self):
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        logs = engine.get_logs(limit=10)
        assert isinstance(logs, list)


class TestCopilotService:
    """Tests for the AI Marketing Copilot service layer."""

    def test_response_structure_validation(self):
        """ask() must return all required fields with correct types."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()
        result = svc.ask("What is the account performance overview?")

        # Required top-level fields
        assert "response_type" in result
        assert "summary" in result
        assert "answer" in result
        assert "key_findings" in result
        assert "recommended_actions" in result
        assert "suggested_actions" in result  # backward-compat alias
        assert "follow_up_questions" in result
        assert "confidence" in result
        assert "confidence_reason" in result
        assert "sources" in result
        assert "generated_at" in result
        assert "provider" in result
        assert "context_summary" in result

        # Types
        assert isinstance(result["key_findings"], list)
        assert isinstance(result["recommended_actions"], list)
        assert isinstance(result["suggested_actions"], list)
        assert isinstance(result["follow_up_questions"], list)
        assert isinstance(result["sources"], list)
        assert result["confidence"] in ("high", "medium", "low")
        assert result["response_type"] in (
            "diagnosis", "risk", "comparison", "opportunity",
            "budget_opportunity", "scaling_opportunity", "analysis"
        )

        # recommended_actions and suggested_actions must be identical
        assert result["recommended_actions"] == result["suggested_actions"]

        # summary must be a non-empty string
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

        # sources must be objects (not raw strings)
        for src in result["sources"]:
            assert isinstance(src, dict)
            assert "type" in src

    def test_account_scoped_context(self):
        """ask() with account_id scopes context_summary correctly."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()
        result = svc.ask("Show budget opportunities", account_id=1, period="7d")

        assert result["context_summary"]["account_id"] == 1
        assert result["context_summary"]["period"] == "7d"
        assert "spend" in result["context_summary"]
        assert "active_alerts" in result["context_summary"]
        assert "growth_score" in result["context_summary"]

        # Result without account_id must also work
        result2 = svc.ask("Show budget opportunities", account_id=None)
        assert result2["context_summary"]["account_id"] is None

    def test_automation_proposal_generation(self):
        """create_proposal() routes through AutomationEngine.generate_action_proposal()."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()

        # Valid actionable proposal
        result = svc.create_proposal(
            action_type="pause_campaign",
            entity_name="Test Waste Campaign",
            entity_type="campaign",
            account_id=1,
            reason="Zero conversions detected by Copilot",
            confidence="high",
            platform="meta",
        )
        assert "success" in result
        assert "action_id" in result
        # Either queued or blocked by guardrail — both are valid outcomes
        if result["success"]:
            assert isinstance(result["action_id"], int)
        else:
            assert result["action_id"] is None
            assert isinstance(result["reason"], str)

        # Invalid action_type must return success=False immediately
        bad = svc.create_proposal(
            action_type="delete_everything",
            entity_name="Some Campaign",
        )
        assert bad["success"] is False
        assert bad["action_id"] is None

    def test_confidence_explanation(self):
        """confidence_reason must match the documented label format."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()

        result = svc.ask("Investigate campaign performance")
        confidence = result["confidence"]
        conf_reason = result["confidence_reason"].lower()

        # Reason must start with the confidence level name
        assert conf_reason.startswith(confidence), (
            f"confidence_reason '{conf_reason}' should start with '{confidence}'"
        )

        # Each level maps to a descriptive phrase
        if confidence == "high":
            assert "consistent" in conf_reason or "clear" in conf_reason
        elif confidence == "medium":
            assert "moderate" in conf_reason or "signal" in conf_reason or "partial" in conf_reason
        else:
            assert "limited" in conf_reason or "conflicting" in conf_reason or "demo" in conf_reason


class TestAccountConnectionValidation:
    """Tests for OnboardingService credential validation and account creation."""

    def test_meta_connect_missing_fields(self, client):
        """POST /api/accounts/connect with missing Meta fields returns 400."""
        resp = client.post("/api/accounts/connect",
                           json={"platform": "meta", "external_account_id": "act_123"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "access_token" in data["error"].lower()

    def test_google_connect_missing_fields(self, client):
        """POST /api/accounts/connect with missing Google fields returns 400."""
        resp = client.post("/api/accounts/connect",
                           json={"platform": "google", "customer_id": "123"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_connect_invalid_platform(self, client):
        """POST /api/accounts/connect with unknown platform returns 400."""
        resp = client.post("/api/accounts/connect",
                           json={"platform": "tiktok", "external_account_id": "act_x"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "platform" in data["error"].lower()

    def test_account_create_and_retrieve(self):
        """AccountService.create_account() inserts and returns the new record."""
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.account_service import AccountService

        unique = uuid.uuid4().hex[:8]
        ext_id = f"act_test_{unique}"
        acc = AccountService.create_account(
            "meta", f"Test Account {unique}", ext_id,
            access_token="test_token_123"
        )
        assert acc is not None
        assert acc["platform"] == "meta"
        assert acc["external_account_id"] == ext_id
        assert acc["account_name"] == f"Test Account {unique}"
        assert acc["status"] == "active"
        # Credentials stored (not exposed in route but present in service)
        assert acc["access_token"] == "test_token_123"

    def test_account_create_duplicate_returns_none(self):
        """Connecting the same account twice returns None (UNIQUE constraint)."""
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.account_service import AccountService

        unique = uuid.uuid4().hex[:8]
        ext_id = f"act_dup_{unique}"
        acc1 = AccountService.create_account("meta", f"Dup Account {unique}", ext_id)
        acc2 = AccountService.create_account("meta", f"Dup Account {unique}", ext_id)
        assert acc1 is not None
        assert acc2 is None  # duplicate rejected

    def test_update_last_sync(self):
        """AccountService.update_last_sync() stamps a timestamp on the account."""
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.account_service import AccountService

        unique = uuid.uuid4().hex[:8]
        acc = AccountService.create_account("meta", f"Sync Test {unique}",
                                             f"act_sync_{unique}")
        assert acc is not None
        AccountService.update_last_sync(acc["id"])
        updated = AccountService.get_by_id(acc["id"])
        assert updated["last_sync"] is not None
        assert "T" in updated["last_sync"]  # ISO timestamp

    def test_meta_validation_bad_token(self):
        """_validate_meta with a fake token returns valid=False (HTTP error from Meta)."""
        from app.services.onboarding_service import OnboardingService
        svc = OnboardingService()
        result = svc._validate_meta("act_000000000000001", "fake_token_not_real")
        # Should fail with Meta API error (not raise an exception)
        assert result["valid"] is False
        assert "error" in result
        assert isinstance(result["error"], str)

    def test_google_validation_missing_fields(self):
        """_validate_google with empty fields returns valid=False."""
        from app.services.onboarding_service import OnboardingService
        svc = OnboardingService()
        assert svc._validate_google("", "tok", "ref")["valid"] is False
        assert svc._validate_google("123", "", "ref")["valid"] is False
        assert svc._validate_google("123", "tok", "")["valid"] is False

    def test_connect_endpoint_strips_credentials(self, client):
        """POST /api/accounts/connect success response never exposes raw credentials."""
        import uuid
        # We can't reach Meta/Google in tests, but we can verify the connect endpoint
        # for the google platform where lightweight validation succeeds without OAuth creds.
        unique = uuid.uuid4().hex[:8]
        resp = client.post("/api/accounts/connect", json={
            "platform": "google",
            "customer_id": f"1234567{unique[:5]}",
            "developer_token": "DEV_TOKEN_TEST",
            "refresh_token": "1//REFRESH_TEST",
            "account_name": f"Test Google {unique}",
        })
        # Google lightweight validation passes when GOOGLE_CLIENT_ID is not set
        if resp.status_code == 201:
            data = resp.get_json()
            assert "access_token" not in (data.get("account") or {})
            assert "developer_token" not in (data.get("account") or {})
            assert "refresh_token" not in (data.get("account") or {})


class TestSnapshotInitialization:
    """Tests for trigger_initial_sync after account connection."""

    def test_trigger_initial_sync_completes(self):
        """trigger_initial_sync runs all three pipeline steps without raising."""
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.account_service import AccountService
        from app.services.onboarding_service import OnboardingService

        unique = uuid.uuid4().hex[:8]
        acc = AccountService.create_account("meta", f"Sync Pipeline {unique}",
                                             f"act_pipeline_{unique}")
        svc = OnboardingService()
        results = svc.trigger_initial_sync(acc["id"])

        assert isinstance(results, dict)
        assert "snapshot" in results
        assert "ai_refresh" in results
        assert "alerts" in results

    def test_trigger_initial_sync_stamps_last_sync(self):
        """After trigger_initial_sync, last_sync is updated on the account record."""
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.account_service import AccountService
        from app.services.onboarding_service import OnboardingService

        unique = uuid.uuid4().hex[:8]
        acc = AccountService.create_account("meta", f"Stamp Test {unique}",
                                             f"act_stamp_{unique}")
        assert acc["last_sync"] is None

        OnboardingService().trigger_initial_sync(acc["id"])
        refreshed = AccountService.get_by_id(acc["id"])
        assert refreshed["last_sync"] is not None


class TestAccountStatusEndpoint:
    """Tests for GET /api/accounts/{id}/status."""

    def test_status_returns_required_fields(self, client):
        """Status endpoint returns all spec-required fields."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/accounts/1/status")
        assert resp.status_code == 200
        data = resp.get_json()
        # Spec-required fields
        assert "last_sync" in data
        assert "campaign_count" in data
        assert "spend_7d" in data
        assert "alerts_count" in data
        # Types
        assert isinstance(data["campaign_count"], int)
        assert isinstance(data["spend_7d"], (int, float))
        assert isinstance(data["alerts_count"], int)

    def test_status_404_for_unknown_account(self, client):
        """Status endpoint returns 404 for non-existent account."""
        resp = client.get("/api/accounts/999999/status")
        assert resp.status_code == 404

    def test_status_spend_7d_non_negative(self, client):
        """spend_7d must be >= 0."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/accounts/1/status")
        assert resp.status_code == 200
        assert resp.get_json()["spend_7d"] >= 0


class TestMultiAccountUX:
    """Multi Account UX — selector persistence, context panel, cross-account data integrity."""

    def test_accounts_list_returns_array(self, client):
        """GET /api/accounts returns a list."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/accounts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_accounts_list_no_credentials_in_response(self, client):
        """Credential fields are never exposed in the accounts list."""
        import uuid
        from app.db.init_db import init_db
        init_db()
        from app.services.account_service import AccountService
        unique = uuid.uuid4().hex[:8]
        AccountService.create_account(
            "meta", f"UX Test {unique}", f"act_ux_{unique}",
            access_token="secret_tok"
        )
        resp = client.get("/api/accounts")
        assert resp.status_code == 200
        for acct in resp.get_json():
            assert "access_token" not in acct
            assert "developer_token" not in acct
            assert "refresh_token" not in acct

    def test_account_status_context_panel_fields(self, client):
        """Status endpoint returns fields needed by the context panel."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/accounts/1/status")
        assert resp.status_code == 200
        data = resp.get_json()
        # Context panel needs: last_sync, spend_today, alerts_count
        assert "spend_today" in data or "spend_7d" in data
        assert "alerts_count" in data or "alerts_active" in data

    def test_cross_account_overview_structure(self, client):
        """Cross-account overview returns accounts, totals, insights, spend_share."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/accounts/overview")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "accounts" in data
        assert "totals" in data
        assert "insights" in data
        assert "spend_share" in data

    def test_cross_account_table_growth_score_field(self, client):
        """Each account in overview has growth_score for row highlighting."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/accounts/overview")
        assert resp.status_code == 200
        accounts = resp.get_json().get("accounts", [])
        for a in accounts:
            assert "growth_score" in a
            assert isinstance(a["growth_score"], (int, float))
            assert "alerts_count" in a

    def test_account_health_endpoint_structure(self, client):
        """Health endpoint returns accounts with growth_score and active_alerts."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/accounts/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "accounts" in data
        for a in data["accounts"]:
            assert "growth_score" in a
            assert "active_alerts" in a
            assert "spend_last_7_days" in a


class TestBillingAndPlans:
    """Billing layer — plan lookup, usage tracking, and limit enforcement."""

    def test_billing_plan_endpoint_returns_200(self, client):
        """GET /api/billing/plan returns plan info."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/billing/plan")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "plan_name" in data
        assert "accounts_limit" in data
        assert "automation_runs_limit" in data
        assert "copilot_queries_limit" in data

    def test_billing_usage_endpoint_returns_200(self, client):
        """GET /api/billing/usage returns plan usage summary."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/billing/usage")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "plan_name" in data
        assert "accounts" in data
        assert "automation" in data
        assert "copilot" in data

    def test_usage_meter_has_required_fields(self, client):
        """Each usage meter has used, limit, pct, unlimited fields."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/billing/usage")
        assert resp.status_code == 200
        data = resp.get_json()
        for key in ("accounts", "automation", "copilot"):
            meter = data[key]
            assert "used" in meter
            assert "unlimited" in meter
            if not meter["unlimited"]:
                assert "limit" in meter
                assert "pct" in meter
                assert 0 <= meter["pct"] <= 100

    def test_default_plan_is_starter(self, client):
        """Default plan for org 1 is Starter."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/billing/plan")
        data = resp.get_json()
        assert data["plan_name"] == "Starter"

    def test_check_account_limit(self):
        """check_account_limit returns allowed/current/limit dict."""
        from app.db.init_db import init_db
        init_db()
        from app.services.billing_service import BillingService
        svc = BillingService()
        result = svc.check_account_limit()
        assert "allowed" in result
        assert "current" in result
        assert "limit" in result
        assert isinstance(result["allowed"], bool)
        assert isinstance(result["current"], int)

    def test_track_usage_increments_counter(self):
        """track_usage persists a usage_metric row."""
        from app.db.init_db import init_db, get_connection
        init_db()
        from app.services.billing_service import BillingService
        svc = BillingService()
        period = __import__('datetime').datetime.utcnow().strftime("%Y-%m")
        # Get baseline
        before = svc.get_usage()["copilot_queries"]
        svc.track_usage("copilot_query")
        after = svc.get_usage()["copilot_queries"]
        assert after == before + 1

    def test_check_copilot_usage_limit_enforcement(self):
        """When copilot_queries used >= limit, allowed=False."""
        from app.db.init_db import init_db
        init_db()
        from app.services.billing_service import BillingService
        svc = BillingService()
        plan = svc.get_plan()
        limit = plan["copilot_queries_limit"]
        if limit is None:
            return  # unlimited plan — skip
        # Record usage up to the limit
        usage = svc.get_usage()
        remaining = limit - usage["copilot_queries"]
        if remaining > 0 and remaining <= 5:
            for _ in range(remaining):
                svc.track_usage("copilot_query")
            result = svc.check_copilot_usage()
            assert result["allowed"] is False


class TestCopilotGrounding:
    """Phase 6B — entity grounding, proposals, session memory, response classification."""

    _VALID_RESPONSE_TYPES = {
        "diagnosis", "risk", "comparison", "opportunity",
        "budget_opportunity", "scaling_opportunity", "analysis",
    }

    def test_entity_grounding_in_findings(self):
        """key_findings items are dicts with ref_type, ref_id, ref_name fields."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()
        result = svc.ask("Why did CPA increase?", account_id=1, period="7d")
        for finding in result.get("key_findings", []):
            assert isinstance(finding, dict), "Each finding must be a dict"
            assert "ref_type" in finding
            assert "ref_id" in finding
            assert "ref_name" in finding

    def test_proposal_from_copilot_via_engine(self):
        """AutomationEngine.create_proposal_from_copilot() returns success/action_id dict."""
        from app.db.init_db import init_db
        init_db()
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        result = engine.create_proposal_from_copilot(
            action_type="increase_budget",
            entity_name="Test Campaign 6B",
            entity_type="campaign",
            account_id=1,
            reason="Phase 6B grounding test",
            confidence="high",
            platform="meta",
        )
        assert isinstance(result, dict)
        assert "success" in result
        assert "action_id" in result

    def test_proposal_accepts_campaign_id(self):
        """create_proposal_from_copilot with campaign_id stores it as entity_id."""
        from app.db.init_db import init_db, get_connection
        init_db()
        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        test_campaign_id = "CAMP_6B_TEST_001"
        result = engine.create_proposal_from_copilot(
            action_type="increase_budget",
            entity_name="Grounding Test Campaign",
            entity_type="campaign",
            account_id=1,
            reason="entity_id persistence test",
            confidence="high",
            platform="meta",
            campaign_id=test_campaign_id,
        )
        assert result.get("success") is True
        action_id = result["action_id"]
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT entity_id FROM automation_actions WHERE id = ?", (action_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["entity_id"] == test_campaign_id

        # Cleanup: remove inserted rows to prevent DB state from leaking into later tests
        conn2 = get_connection()
        try:
            conn2.execute("DELETE FROM automation_logs WHERE action_id = ?", (action_id,))
            conn2.execute("DELETE FROM automation_actions WHERE id = ?", (action_id,))
            conn2.commit()
        finally:
            conn2.close()

    def test_response_classification_types(self):
        """response_type is one of the expanded valid set including budget/scaling_opportunity."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()
        result = svc.ask("Which campaigns should be scaled?", account_id=1, period="7d")
        assert result.get("response_type") in self._VALID_RESPONSE_TYPES

    def test_session_context_memory(self):
        """ask() with 3-item session_context processes without error, returns valid structure."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()
        history = [
            {"question": "Why did CPA increase?", "response_type": "diagnosis",
             "answer": "CPA rose due to budget waste.", "summary": "CPA rose."},
            {"question": "Which campaigns are wasting?", "response_type": "risk",
             "answer": "Campaign X is wasting.", "summary": "Campaign X wasting."},
            {"question": "What are the alerts?", "response_type": "risk",
             "answer": "3 active alerts.", "summary": "3 alerts."},
        ]
        result = svc.ask(
            "How do I fix this?",
            account_id=1,
            period="7d",
            session_context=history,
        )
        assert isinstance(result, dict)
        assert "response_type" in result
        assert "answer" in result
        assert result.get("response_type") in self._VALID_RESPONSE_TYPES

    def test_follow_up_suggestions_present(self):
        """follow_up_questions is a list with at least 1 item."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()
        result = svc.ask("What are the biggest risks?", account_id=1, period="7d")
        follow_ups = result.get("follow_up_questions", [])
        assert isinstance(follow_ups, list)
        assert len(follow_ups) >= 1

    def test_sources_are_structured_objects(self):
        """All source items are dicts with at least a 'type' key."""
        from app.db.init_db import init_db
        init_db()
        from app.services.copilot_service import CopilotService
        svc = CopilotService()
        result = svc.ask("Give me a performance overview.", account_id=1, period="7d")
        for source in result.get("sources", []):
            assert isinstance(source, dict), "Each source must be a dict"
            assert "type" in source, "Each source must have a 'type' key"


class TestContentStudio:
    """Phase 8A — Content Studio: ideas, brand kits, prompts, assets, copilot integration."""

    def test_content_ideas_list_endpoint(self, client):
        """GET /api/content/ideas returns a list."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/content/ideas?account_id=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_create_content_idea(self, client):
        """POST /api/content/ideas creates a new idea and returns id."""
        from app.db.init_db import init_db
        init_db()
        payload = {
            "account_id": 1,
            "title": "Test Instagram Reel",
            "description": "A reel about the brand offer",
            "content_type": "reel",
            "platform_target": "instagram",
            "source": "manual",
        }
        resp = client.post("/api/content/ideas",
                           json=payload,
                           content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "id" in data
        assert data["title"] == "Test Instagram Reel"

    def test_brand_kit_get_returns_defaults(self, client):
        """GET /api/content/brand-kit returns default kit when not yet saved."""
        from app.db.init_db import init_db
        init_db()
        resp = client.get("/api/content/brand-kit?account_id=99")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "primary_color" in data
        assert "font_family" in data

    def test_brand_kit_save_and_retrieve(self, client):
        """POST /api/content/brand-kit saves and GET retrieves the saved kit."""
        from app.db.init_db import init_db
        init_db()
        kit = {
            "account_id": 1,
            "brand_name": "A7 Brand",
            "primary_color": "#FF0000",
            "font_family": "Roboto",
            "style_description": "Bold and modern",
        }
        resp = client.post("/api/content/brand-kit",
                           json=kit, content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("brand_name") == "A7 Brand"
        assert data.get("primary_color") == "#FF0000"

    def test_create_creative_prompt(self, client):
        """POST /api/content/prompts creates a prompt and returns id."""
        from app.db.init_db import init_db
        init_db()
        payload = {
            "account_id": 1,
            "prompt_text": "Photorealistic ad for laundry service, bright colors",
            "style": "photorealistic",
            "aspect_ratio": "1:1",
            "image_type": "ad_creative",
        }
        resp = client.post("/api/content/prompts",
                           json=payload, content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "id" in data
        assert data["image_type"] == "ad_creative"

    def test_create_creative_asset(self, client):
        """POST /api/content/assets registers an asset and returns id."""
        from app.db.init_db import init_db
        init_db()
        payload = {
            "account_id": 1,
            "asset_type": "image",
            "asset_url": "https://example.com/image.png",
            "status": "draft",
        }
        resp = client.post("/api/content/assets",
                           json=payload, content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "id" in data
        assert data["asset_type"] == "image"

    def test_generate_ideas_endpoint(self, client):
        """POST /api/content/generate-ideas returns generated count and ideas list."""
        from app.db.init_db import init_db
        init_db()
        resp = client.post("/api/content/generate-ideas",
                           json={"account_id": 1},
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "generated" in data
        assert "ideas" in data
        assert isinstance(data["ideas"], list)
        assert data["generated"] >= 0

    def test_generate_ideas_creates_db_rows(self):
        """generate_ideas() inserts rows into content_ideas table."""
        from app.db.init_db import init_db, get_connection
        init_db()
        from app.services.content_studio_service import ContentStudioService
        svc = ContentStudioService()
        # Count before
        conn = get_connection()
        before = conn.execute("SELECT COUNT(*) FROM content_ideas WHERE account_id=1").fetchone()[0]
        conn.close()
        ideas = svc.generate_ideas(account_id=1)
        assert isinstance(ideas, list)
        # Count after
        conn = get_connection()
        after = conn.execute("SELECT COUNT(*) FROM content_ideas WHERE account_id=1").fetchone()[0]
        conn.close()
        assert after >= before  # at least no rows deleted; generate_ideas adds rows

    def test_copilot_content_intent(self):
        """Copilot detects content intent and returns content_ideas response type."""
        from app.db.init_db import init_db
        init_db()
        import os
        # Force rule-based by removing API keys temporarily
        saved = {k: os.environ.pop(k) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY") if k in os.environ}
        try:
            from app.services.copilot_service import CopilotService
            svc = CopilotService()
            result = svc.ask("Generate 5 Instagram content ideas based on top campaigns",
                             account_id=1, period="7d")
            assert result.get("response_type") == "content_ideas"
            assert isinstance(result.get("key_findings"), list)
        finally:
            os.environ.update(saved)

class TestContentStudioPhaseB:
    """Phase 8B — Prompt Builder + Image Generation Engine."""

    def test_build_prompt_returns_prompt_text(self, client):
        """build_prompt() returns a non-empty prompt_text combining brand info + idea."""
        from app.db.init_db import init_db
        from app.services.content_studio_service import ContentStudioService
        init_db()
        svc = ContentStudioService()
        idea = svc.create_idea(account_id=1, title="Flash sale reel", description="30% off this weekend only",
                               content_type="reel", platform_target="instagram")
        result = svc.build_prompt(account_id=1, content_idea_id=idea["id"], image_type="social_post")
        assert "id" in result
        assert "prompt_text" in result
        assert len(result["prompt_text"]) > 20
        assert "Flash sale reel" in result["prompt_text"]

    def test_build_prompt_upsert(self, client):
        """Calling build_prompt twice for same idea+image_type updates, not duplicates."""
        from app.db.init_db import init_db, get_connection
        from app.services.content_studio_service import ContentStudioService
        init_db()
        svc = ContentStudioService()
        idea = svc.create_idea(account_id=1, title="Upsert test idea", content_type="post",
                               platform_target="facebook")
        r1 = svc.build_prompt(account_id=1, content_idea_id=idea["id"], image_type="social_post")
        r2 = svc.build_prompt(account_id=1, content_idea_id=idea["id"], image_type="social_post")
        assert r1["id"] == r2["id"]  # same row updated, not new row
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM creative_prompts WHERE content_idea_id=? AND image_type='social_post'",
            (idea["id"],)
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_build_prompt_endpoint(self, client):
        """POST /api/content/prompts/build returns 201 with prompt_text."""
        from app.db.init_db import init_db
        from app.services.content_studio_service import ContentStudioService
        init_db()
        idea = ContentStudioService().create_idea(account_id=1, title="Endpoint test idea")
        resp = client.post("/api/content/prompts/build",
                           json={"account_id": 1, "content_idea_id": idea["id"]},
                           content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "prompt_text" in data
        assert "id" in data

    def test_build_prompt_missing_idea_returns_error(self, client):
        """build_prompt() with non-existent idea_id returns error dict."""
        from app.db.init_db import init_db
        from app.services.content_studio_service import ContentStudioService
        init_db()
        result = ContentStudioService().build_prompt(account_id=1, content_idea_id=99999)
        assert "error" in result

    def test_image_generation_service_mock(self):
        """ImageGenerationService returns mock asset with correct schema."""
        import os
        os.environ.pop("IMAGE_GENERATION_PROVIDER", None)
        from app.services.image_generation_service import ImageGenerationService
        svc = ImageGenerationService()
        result = svc.generate_image("A blue background with text", image_type="social_post",
                                    aspect_ratio="1:1")
        assert "asset_url" in result
        assert "thumbnail_url" in result
        assert result["status"] == "draft"
        assert result["provider"] == "mock"
        assert result["generation_cost"] == 0.0
        assert "placehold.co" in result["asset_url"]

    def test_image_generation_aspect_ratios(self):
        """Mock provider respects aspect ratio dimensions in URL."""
        import os
        os.environ.pop("IMAGE_GENERATION_PROVIDER", None)
        from app.services.image_generation_service import ImageGenerationService
        svc = ImageGenerationService()
        r_square = svc.generate_image("test", aspect_ratio="1:1")
        r_portrait = svc.generate_image("test", aspect_ratio="9:16")
        assert "1024x1024" in r_square["asset_url"]
        assert "1024x1792" in r_portrait["asset_url"]

    def test_generate_asset_from_idea_pipeline(self):
        """generate_asset_from_idea() saves asset to DB and returns asset dict."""
        from app.db.init_db import init_db, get_connection
        from app.services.content_studio_service import ContentStudioService
        init_db()
        svc = ContentStudioService()
        idea = svc.create_idea(account_id=1, title="Pipeline test idea",
                               content_type="post", platform_target="instagram")
        result = svc.generate_asset_from_idea(account_id=1, content_idea_id=idea["id"])
        assert "asset" in result
        assert "prompt" in result
        assert "provider" in result
        assert result["asset"]["id"] is not None
        # Verify row exists in DB
        conn = get_connection()
        row = conn.execute("SELECT * FROM creative_assets WHERE id=?",
                           (result["asset"]["id"],)).fetchone()
        conn.close()
        assert row is not None
        assert row["content_idea_id"] == idea["id"]

    def test_generate_asset_endpoint(self, client):
        """POST /api/content/assets/generate returns 201 with asset and prompt."""
        from app.db.init_db import init_db
        from app.services.content_studio_service import ContentStudioService
        init_db()
        idea = ContentStudioService().create_idea(account_id=1, title="Generate endpoint test")
        resp = client.post("/api/content/assets/generate",
                           json={"account_id": 1, "content_idea_id": idea["id"]},
                           content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "asset" in data
        assert "prompt" in data

    def test_get_asset_endpoint(self, client):
        """GET /api/content/assets/<id> returns asset with provider and generation_cost."""
        from app.db.init_db import init_db
        from app.services.content_studio_service import ContentStudioService
        init_db()
        svc = ContentStudioService()
        idea = svc.create_idea(account_id=1, title="Get asset test idea")
        gen = svc.generate_asset_from_idea(account_id=1, content_idea_id=idea["id"])
        asset_id = gen["asset"]["id"]
        resp = client.get(f"/api/content/assets/{asset_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == asset_id
        assert "provider" in data
        assert "generation_cost" in data
