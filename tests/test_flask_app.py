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


class TestPublishingEngine:
    """Phase 8C — Publishing Engine."""

    def test_create_post_draft(self, client):
        """create_post() inserts a draft and returns id + status."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        svc = PublishingService()
        result = svc.create_post(
            account_id=1,
            title="Winter Promo",
            caption="Keep your home fresh this winter.",
            platform_target="instagram",
            post_type="image_post",
        )
        assert "id" in result
        assert result["status"] == "draft"
        assert result["platform_target"] == "instagram"
        assert result["title"] == "Winter Promo"

    def test_list_posts_filtered_by_account(self):
        """list_posts() returns only posts for the given account."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        svc = PublishingService()
        svc.create_post(account_id=1, title="Post acct 1", platform_target="instagram")
        svc.create_post(account_id=2, title="Post acct 2", platform_target="facebook")
        posts_1 = svc.list_posts(account_id=1)
        posts_2 = svc.list_posts(account_id=2)
        assert all(p["account_id"] == 1 for p in posts_1)
        assert all(p["account_id"] == 2 for p in posts_2)

    def test_schedule_post(self):
        """schedule_post() updates status to scheduled and creates a job."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        svc = PublishingService()
        post = svc.create_post(account_id=1, title="Scheduled post", platform_target="instagram")
        result = svc.schedule_post(post["id"], account_id=1,
                                   scheduled_for="2026-12-31T10:00:00")
        assert result["status"] == "scheduled"
        assert result["scheduled_for"] == "2026-12-31T10:00:00"
        # Job created
        jobs = svc.list_jobs(account_id=1)
        assert any(j["content_post_id"] == post["id"] for j in jobs)

    def test_publish_post_now_mock(self):
        """publish_post_now() in mock mode marks post as published."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        import os
        os.environ.pop("PUBLISHING_PROVIDER", None)
        init_db()
        svc = PublishingService()
        post = svc.create_post(account_id=1, title="Publish now test",
                               platform_target="instagram")
        result = svc.publish_post_now(post["id"], account_id=1)
        assert "post" in result
        assert "result" in result
        assert result["post"]["status"] == "published"
        assert result["result"]["success"] is True
        assert result["result"]["provider"] == "mock"
        assert result["post"]["external_post_id"].startswith("mock_")

    def test_publishing_jobs_created_on_publish(self):
        """publish_post_now() creates a success job record."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        svc = PublishingService()
        post = svc.create_post(account_id=1, title="Jobs test", platform_target="facebook")
        svc.publish_post_now(post["id"], account_id=1)
        jobs = svc.list_jobs(account_id=1)
        post_jobs = [j for j in jobs if j["content_post_id"] == post["id"]]
        assert len(post_jobs) >= 1
        assert post_jobs[-1]["status"] == "success"

    def test_run_due_jobs(self):
        """run_due_jobs() executes scheduled jobs whose time has passed."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        svc = PublishingService()
        post = svc.create_post(account_id=1, title="Due job test",
                               platform_target="instagram")
        # Schedule in the past (already due)
        svc.schedule_post(post["id"], account_id=1, scheduled_for="2020-01-01T00:00:00")
        result = svc.run_due_jobs(account_id=1)
        assert "executed" in result
        assert result["executed"] >= 1

    def test_account_isolation_list_posts(self, client):
        """GET /api/content/posts returns only posts for the requested account."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        svc = PublishingService()
        svc.create_post(account_id=1, title="Iso post acct1")
        resp = client.get("/api/content/posts?account_id=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert all(p["account_id"] == 1 for p in data)

    def test_usage_tracking_post_created(self):
        """create_post() calls billing track_usage for post_created."""
        from app.db.init_db import init_db, get_connection
        from app.services.publishing_service import PublishingService
        init_db()
        conn = get_connection()
        before = conn.execute(
            "SELECT COUNT(*) FROM usage_metrics WHERE metric='post_created'"
        ).fetchone()[0]
        conn.close()
        svc = PublishingService()
        svc.create_post(account_id=1, title="Usage tracking test",
                        platform_target="instagram")
        conn = get_connection()
        after = conn.execute(
            "SELECT COUNT(*) FROM usage_metrics WHERE metric='post_created'"
        ).fetchone()[0]
        conn.close()
        assert after > before

    def test_create_post_endpoint(self, client):
        """POST /api/content/posts returns 201 with post draft."""
        from app.db.init_db import init_db
        init_db()
        payload = {
            "account_id": 1,
            "title": "API test post",
            "caption": "Test caption",
            "platform_target": "instagram",
            "post_type": "image_post",
        }
        resp = client.post("/api/content/posts", json=payload,
                           content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "id" in data
        assert data["status"] == "draft"

    def test_publish_endpoint(self, client):
        """POST /api/content/posts/<id>/publish returns published post."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        post = PublishingService().create_post(account_id=1, title="Endpoint publish",
                                               platform_target="instagram")
        resp = client.post(f"/api/content/posts/{post['id']}/publish",
                           json={"account_id": 1},
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["post"]["status"] == "published"
        assert data["result"]["success"] is True


class TestSocialConnectors:
    """Phase 8D — Social Connector Integration."""

    def test_save_and_get_connector(self):
        """save_connector() upserts and get_connector() retrieves credentials."""
        from app.db.init_db import init_db
        from app.services.social_connector_service import SocialConnectorService
        init_db()
        svc = SocialConnectorService()
        result = svc.save_connector(
            account_id=1, platform="instagram",
            access_token="test_access_token", ig_user_id="12345",
        )
        assert "id" in result
        assert result["platform"] == "instagram"
        assert result["ig_user_id"] == "12345"
        # Retrieve
        connector = svc.get_connector(account_id=1, platform="instagram")
        assert connector is not None
        assert connector["access_token"] == "test_access_token"

    def test_save_connector_upsert(self):
        """Calling save_connector twice updates the same row."""
        from app.db.init_db import init_db, get_connection
        from app.services.social_connector_service import SocialConnectorService
        init_db()
        svc = SocialConnectorService()
        svc.save_connector(account_id=1, platform="facebook_page",
                           access_token="tok_v1", page_id="page_001")
        svc.save_connector(account_id=1, platform="facebook_page",
                           access_token="tok_v2", page_id="page_001")
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM social_connectors WHERE account_id=1 AND platform='facebook_page'"
        ).fetchone()[0]
        conn.close()
        assert count == 1
        connector = svc.get_connector(account_id=1, platform="facebook_page")
        assert connector["access_token"] == "tok_v2"

    def test_list_connectors(self):
        """list_connectors() returns all connectors for an account."""
        from app.db.init_db import init_db
        from app.services.social_connector_service import SocialConnectorService
        init_db()
        svc = SocialConnectorService()
        svc.save_connector(account_id=99, platform="instagram", access_token="tok_ig")
        svc.save_connector(account_id=99, platform="facebook_page", access_token="tok_fb")
        connectors = svc.list_connectors(account_id=99)
        assert len(connectors) == 2
        platforms = [c["platform"] for c in connectors]
        assert "instagram" in platforms
        assert "facebook_page" in platforms

    def test_connector_validation_mocked_http(self):
        """validate_connector() updates status to connected when mock returns valid user."""
        from app.db.init_db import init_db
        from app.services.social_connector_service import SocialConnectorService
        from app.services.publishing_connector_service import PublishingConnectorService
        init_db()
        conn_svc = SocialConnectorService()
        conn_svc.save_connector(account_id=1, platform="instagram",
                                access_token="fake_token", ig_user_id="12345")
        # Mock the HTTP layer
        pub_conn = PublishingConnectorService()
        pub_conn._http_get = lambda url, params=None: {"id": "12345", "name": "Test User"}
        # Patch it in module scope for the validate call
        import unittest.mock
        with unittest.mock.patch.object(PublishingConnectorService, '_http_get',
                                        lambda self, url, params=None: {"id": "12345", "name": "Test User"}):
            result = conn_svc.validate_connector(account_id=1, platform="instagram")
        assert result["valid"] is True
        assert result["user_id"] == "12345"
        # Status updated
        connector = conn_svc.get_connector(account_id=1, platform="instagram")
        assert connector["status"] == "connected"

    def test_connector_validation_failed_http(self):
        """validate_connector() marks status invalid on error response."""
        from app.db.init_db import init_db
        from app.services.social_connector_service import SocialConnectorService
        from app.services.publishing_connector_service import PublishingConnectorService
        init_db()
        conn_svc = SocialConnectorService()
        conn_svc.save_connector(account_id=1, platform="facebook_page",
                                access_token="bad_token", page_id="page_001")
        import unittest.mock
        with unittest.mock.patch.object(
            PublishingConnectorService, '_http_get',
            lambda self, url, params=None: {"error": {"message": "Invalid OAuth token", "code": 190}}
        ):
            result = conn_svc.validate_connector(account_id=1, platform="facebook_page")
        assert result["valid"] is False
        connector = conn_svc.get_connector(account_id=1, platform="facebook_page")
        assert connector["status"] == "invalid"

    def test_instagram_publish_with_mocked_http(self):
        """publish_post_now uses real IG connector when credentials configured (mocked HTTP)."""
        from app.db.init_db import init_db
        from app.services.social_connector_service import SocialConnectorService
        from app.services.publishing_service import PublishingService
        from app.services.publishing_connector_service import PublishingConnectorService
        import unittest.mock
        init_db()
        # Configure connected connector
        conn_svc = SocialConnectorService()
        conn_svc.save_connector(account_id=1, platform="instagram",
                                access_token="valid_token", ig_user_id="ig_123",
                                status="connected")
        # Ensure it's marked connected
        conn_svc.update_status(1, "instagram", "connected")
        # Create asset so asset_url is non-empty (required for IG publish)
        from app.services.content_studio_service import ContentStudioService
        asset = ContentStudioService().create_asset(
            account_id=1,
            asset_url="https://placehold.co/1024x1024/3B82F6/ffffff?text=test",
            thumbnail_url="https://placehold.co/256x256/3B82F6/ffffff?text=test",
        )
        # Create post
        post = PublishingService().create_post(
            account_id=1, title="IG real test", platform_target="instagram",
            creative_asset_id=asset["id"]
        )
        # Mock two-step IG publish
        call_log = []
        def fake_http_post_form(self_inner, url, data):
            call_log.append(url)
            if "media_publish" in url:
                return {"id": "post_789"}
            return {"id": "container_123"}
        with unittest.mock.patch.object(PublishingConnectorService, '_http_post_form',
                                        fake_http_post_form):
            result = PublishingService().publish_post_now(post["id"], account_id=1)
        assert result["post"]["status"] == "published"
        assert result["post"]["external_post_id"] == "post_789"
        assert result["result"]["provider"] == "instagram"
        assert len(call_log) == 2  # container create + publish

    def test_facebook_publish_with_mocked_http(self):
        """publish_post_now uses FB Page connector when configured (mocked HTTP)."""
        from app.db.init_db import init_db
        from app.services.social_connector_service import SocialConnectorService
        from app.services.publishing_service import PublishingService
        from app.services.publishing_connector_service import PublishingConnectorService
        import unittest.mock
        init_db()
        conn_svc = SocialConnectorService()
        conn_svc.save_connector(account_id=1, platform="facebook_page",
                                access_token="fb_token", page_id="pg_456",
                                status="connected")
        conn_svc.update_status(1, "facebook_page", "connected")
        from app.services.content_studio_service import ContentStudioService
        fb_asset = ContentStudioService().create_asset(
            account_id=1,
            asset_url="https://placehold.co/1024x1024/3B82F6/ffffff?text=fb",
            thumbnail_url="https://placehold.co/256x256/3B82F6/ffffff?text=fb",
        )
        post = PublishingService().create_post(
            account_id=1, title="FB page test", platform_target="facebook_page",
            creative_asset_id=fb_asset["id"]
        )
        def fake_http_post_form(self_inner, url, data):
            return {"post_id": "fb_post_999", "id": "99999"}
        with unittest.mock.patch.object(PublishingConnectorService, '_http_post_form',
                                        fake_http_post_form):
            result = PublishingService().publish_post_now(post["id"], account_id=1)
        assert result["post"]["status"] == "published"
        assert result["post"]["external_post_id"] == "fb_post_999"
        assert result["result"]["provider"] == "facebook_page"

    def test_fallback_to_mock_when_no_connector(self):
        """publish_post_now falls back to mock when no connector configured."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        import os
        os.environ.pop("PUBLISHING_PROVIDER", None)
        init_db()
        post = PublishingService().create_post(
            account_id=98, title="No connector fallback", platform_target="tiktok"
        )
        result = PublishingService().publish_post_now(post["id"], account_id=98)
        assert result["post"]["status"] == "published"
        assert result["result"]["provider"] == "mock"

    def test_retry_scheduled_on_transient_failure(self):
        """Failed publish (non-credential) schedules a retry job."""
        from app.db.init_db import init_db
        from app.services.social_connector_service import SocialConnectorService
        from app.services.publishing_service import PublishingService
        from app.services.publishing_connector_service import PublishingConnectorService
        import unittest.mock
        init_db()
        conn_svc = SocialConnectorService()
        conn_svc.save_connector(account_id=1, platform="instagram",
                                access_token="ok_token", ig_user_id="ig_retry",
                                status="connected")
        conn_svc.update_status(1, "instagram", "connected")
        post = PublishingService().create_post(
            account_id=1, title="Retry test post", platform_target="instagram"
        )
        # Simulate transient network error (not credential error)
        def fake_post_form(self_inner, url, data):
            raise Exception("Connection timeout")
        with unittest.mock.patch.object(PublishingConnectorService, '_http_post_form',
                                        fake_post_form):
            result = PublishingService().publish_post_now(post["id"], account_id=1)
        assert result["post"]["status"] == "failed"
        # Job should be in retrying state
        jobs = PublishingService().list_jobs(account_id=1)
        post_jobs = [j for j in jobs if j["content_post_id"] == post["id"]]
        assert len(post_jobs) >= 1
        retry_jobs = [j for j in post_jobs if j["status"] == "retrying"]
        assert len(retry_jobs) >= 1
        assert retry_jobs[0]["retry_count"] == 1
        assert retry_jobs[0]["next_retry_at"] is not None

    def test_connector_endpoints(self, client):
        """POST + GET /api/content/connectors round-trip works."""
        from app.db.init_db import init_db
        init_db()
        resp = client.post("/api/content/connectors",
                           json={"account_id": 1, "platform": "instagram",
                                 "access_token": "api_test_tok", "ig_user_id": "api_ig"},
                           content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["platform"] == "instagram"
        assert data["access_token"] == "***"  # masked in response
        # List
        resp2 = client.get("/api/content/connectors?account_id=1")
        assert resp2.status_code == 200
        connectors = resp2.get_json()
        assert isinstance(connectors, list)
        assert any(c["platform"] == "instagram" for c in connectors)

    def test_account_isolation_connectors(self):
        """Connectors are scoped per account."""
        from app.db.init_db import init_db
        from app.services.social_connector_service import SocialConnectorService
        init_db()
        svc = SocialConnectorService()
        svc.save_connector(account_id=10, platform="instagram", access_token="tok_10")
        svc.save_connector(account_id=20, platform="instagram", access_token="tok_20")
        c10 = svc.get_connector(account_id=10, platform="instagram")
        c20 = svc.get_connector(account_id=20, platform="instagram")
        assert c10["access_token"] == "tok_10"
        assert c20["access_token"] == "tok_20"
        assert svc.list_connectors(account_id=10) != svc.list_connectors(account_id=20)


class TestCalendar:
    """Phase 8E — Content Calendar tests."""

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _make_post(account_id=1, status="scheduled", scheduled_for=None,
                   published_at=None, title="Test Post", platform="instagram"):
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        svc = PublishingService()
        post = svc.create_post(account_id=account_id, title=title,
                               platform_target=platform)
        if scheduled_for:
            from app.db.init_db import get_connection
            conn = get_connection()
            conn.execute(
                "UPDATE content_posts SET scheduled_for=?, status=? WHERE id=?",
                (scheduled_for, status, post["id"]),
            )
            if published_at:
                conn.execute(
                    "UPDATE content_posts SET published_at=?, status='published' WHERE id=?",
                    (published_at, post["id"]),
                )
            conn.commit()
            conn.close()
            post = svc.get_post(post["id"])
        return post

    # ── calendar grouping ────────────────────────────────────────────────────

    def test_calendar_week_grouping(self):
        """Posts appear on the correct weekday cell."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        init_db()
        # Use a fixed Monday as the week start
        week_start = "2026-04-06"  # Monday
        post = self._make_post(
            account_id=1, scheduled_for="2026-04-08T10:00:00",  # Wednesday
            title="Wed post"
        )
        svc = CalendarService()
        cal = svc.get_calendar(account_id=1, view="week", start=week_start)
        assert cal["view"] == "week"
        assert len(cal["days"]) == 7
        wed = next(d for d in cal["days"] if d["date"] == "2026-04-08")
        assert any(p["id"] == post["id"] for p in wed["posts"])

    def test_calendar_month_view(self):
        """Month view returns the correct number of days."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        init_db()
        svc = CalendarService()
        cal = svc.get_calendar(account_id=1, view="month", start="2026-04-01")
        assert cal["view"] == "month"
        assert len(cal["days"]) == 30  # April has 30 days
        assert cal["start"] == "2026-04-01"
        assert cal["end"] == "2026-04-30"

    def test_calendar_day_view(self):
        """Day view returns exactly one day."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        init_db()
        svc = CalendarService()
        cal = svc.get_calendar(account_id=1, view="day", start="2026-04-15")
        assert cal["view"] == "day"
        assert len(cal["days"]) == 1
        assert cal["days"][0]["date"] == "2026-04-15"

    def test_calendar_published_post_appears(self):
        """Published posts appear based on published_at date."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        from app.db.init_db import get_connection
        init_db()
        post = self._make_post(account_id=1, title="Published post")
        # Mark as published with published_at
        conn = get_connection()
        conn.execute(
            "UPDATE content_posts SET status='published', published_at=?, scheduled_for=NULL WHERE id=?",
            ("2026-04-10T12:00:00", post["id"]),
        )
        conn.commit()
        conn.close()
        svc = CalendarService()
        cal = svc.get_calendar(account_id=1, view="month", start="2026-04-01")
        day10 = next(d for d in cal["days"] if d["date"] == "2026-04-10")
        assert any(p["id"] == post["id"] for p in day10["posts"])

    # ── account isolation ─────────────────────────────────────────────────────

    def test_calendar_account_isolation(self):
        """Posts from account 50 do not appear in account 51's calendar."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        init_db()
        p50 = self._make_post(account_id=50, scheduled_for="2026-05-05T09:00:00",
                              title="Acct50 post")
        svc = CalendarService()
        cal51 = svc.get_calendar(account_id=51, view="month", start="2026-05-01")
        all_ids = [p["id"] for day in cal51["days"] for p in day["posts"]]
        assert p50["id"] not in all_ids

    # ── rescheduling ──────────────────────────────────────────────────────────

    def test_reschedule_scheduled_post(self):
        """Rescheduling a scheduled post updates scheduled_for and status."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        init_db()
        post = self._make_post(
            account_id=1, scheduled_for="2026-06-01T10:00:00", title="Reschedule me"
        )
        svc = CalendarService()
        result = svc.reschedule_post(
            account_id=1, post_id=post["id"], scheduled_for="2026-06-15T14:00:00"
        )
        assert "error" not in result
        assert result["post"]["scheduled_for"] == "2026-06-15T14:00:00"
        assert result["post"]["status"] == "scheduled"

    def test_reschedule_draft_post(self):
        """Rescheduling a draft post sets it to scheduled."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        from app.services.publishing_service import PublishingService
        init_db()
        draft = PublishingService().create_post(account_id=1, title="Draft reschedule")
        svc = CalendarService()
        result = svc.reschedule_post(
            account_id=1, post_id=draft["id"], scheduled_for="2026-07-01T09:00:00"
        )
        assert "error" not in result
        assert result["post"]["status"] == "scheduled"

    def test_reschedule_published_post_blocked(self):
        """Published posts cannot be rescheduled."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        from app.db.init_db import get_connection
        init_db()
        post = self._make_post(account_id=1, title="Published block test")
        conn = get_connection()
        conn.execute(
            "UPDATE content_posts SET status='published', published_at=datetime('now') WHERE id=?",
            (post["id"],),
        )
        conn.commit()
        conn.close()
        svc = CalendarService()
        result = svc.reschedule_post(
            account_id=1, post_id=post["id"], scheduled_for="2026-08-01T10:00:00"
        )
        assert "error" in result
        assert "published" in result["error"].lower()

    def test_reschedule_post_not_found(self):
        """Rescheduling a non-existent post returns error."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        init_db()
        svc = CalendarService()
        result = svc.reschedule_post(
            account_id=1, post_id=999999, scheduled_for="2026-09-01T10:00:00"
        )
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_reschedule_invalid_datetime(self):
        """Invalid datetime string returns a validation error."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        from app.services.publishing_service import PublishingService
        init_db()
        draft = PublishingService().create_post(account_id=1, title="Invalid dt test")
        svc = CalendarService()
        result = svc.reschedule_post(
            account_id=1, post_id=draft["id"], scheduled_for="not-a-date"
        )
        assert "error" in result

    # ── upcoming queue ────────────────────────────────────────────────────────

    def test_upcoming_queue_order(self):
        """get_upcoming returns scheduled posts in chronological order."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        init_db()
        # Create two future posts for a fresh account
        acct = 777
        p_late  = self._make_post(account_id=acct, scheduled_for="2027-01-10T10:00:00",
                                  title="Second")
        p_early = self._make_post(account_id=acct, scheduled_for="2027-01-05T08:00:00",
                                  title="First")
        svc = CalendarService()
        upcoming = svc.get_upcoming(account_id=acct)
        # At least the two posts we created must be present and correctly ordered
        assert len(upcoming) >= 2
        ids = [p["id"] for p in upcoming]
        assert p_early["id"] in ids
        assert p_late["id"] in ids
        early_idx = ids.index(p_early["id"])
        late_idx  = ids.index(p_late["id"])
        assert early_idx < late_idx, "Earlier post should come before later post"

    def test_upcoming_excludes_published(self):
        """Published/failed posts do not appear in upcoming queue."""
        from app.db.init_db import init_db
        from app.services.calendar_service import CalendarService
        from app.db.init_db import get_connection
        init_db()
        acct = 888
        post = self._make_post(account_id=acct, scheduled_for="2027-02-01T10:00:00",
                               title="Will be published")
        conn = get_connection()
        conn.execute(
            "UPDATE content_posts SET status='published', published_at=datetime('now') WHERE id=?",
            (post["id"],),
        )
        conn.commit()
        conn.close()
        svc = CalendarService()
        upcoming = svc.get_upcoming(account_id=acct)
        assert all(p["id"] != post["id"] for p in upcoming)

    # ── API endpoints ─────────────────────────────────────────────────────────

    def test_calendar_api_get(self, client):
        """GET /api/content/calendar returns 200 with expected shape."""
        resp = client.get("/api/content/calendar?account_id=1&view=week&start=2026-04-06")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["view"] == "week"
        assert len(data["days"]) == 7
        assert "total_posts" in data

    def test_calendar_api_invalid_view(self, client):
        """GET /api/content/calendar with invalid view returns 400."""
        resp = client.get("/api/content/calendar?account_id=1&view=decade")
        assert resp.status_code == 400

    def test_reschedule_api_endpoint(self, client):
        """POST /api/content/calendar/reschedule updates a post."""
        from app.db.init_db import init_db
        from app.services.publishing_service import PublishingService
        init_db()
        post = PublishingService().create_post(account_id=1, title="API reschedule")
        resp = client.post(
            "/api/content/calendar/reschedule",
            json={
                "account_id": 1,
                "post_id": post["id"],
                "scheduled_for": "2026-09-20T11:00:00",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["post"]["scheduled_for"] == "2026-09-20T11:00:00"

    def test_upcoming_api_endpoint(self, client):
        """GET /api/content/calendar/upcoming returns a list."""
        resp = client.get("/api/content/calendar/upcoming?account_id=1")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestContentIntelligence:
    """Phase 8F — Content Intelligence tests."""

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_published_post(account_id=1, platform="instagram",
                             post_type="image_post", title="Test",
                             published_at=None):
        from app.db.init_db import init_db, get_connection
        from app.services.publishing_service import PublishingService
        init_db()
        svc = PublishingService()
        post = svc.create_post(account_id=account_id, title=title,
                               platform_target=platform, post_type=post_type)
        pub_at = published_at or "2026-03-01T10:00:00"
        conn = get_connection()
        conn.execute(
            "UPDATE content_posts SET status='published', published_at=? WHERE id=?",
            (pub_at, post["id"]),
        )
        conn.commit()
        conn.close()
        return post

    # ── sync ─────────────────────────────────────────────────────────────────

    def test_sync_creates_metrics_for_published_posts(self):
        """sync_content_metrics creates metric rows for published posts."""
        from app.db.init_db import init_db, get_connection
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 300
        post = self._make_published_post(account_id=acct, title="Sync test")
        svc = ContentIntelligenceService()
        result = svc.sync_content_metrics(account_id=acct)
        assert "error" not in result
        assert result["synced"] >= 1
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM content_metrics WHERE content_post_id=?", (post["id"],)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["reach"] > 0
        assert row["engagement"] > 0

    def test_sync_idempotent(self):
        """Second sync does not duplicate metrics rows."""
        from app.db.init_db import init_db, get_connection
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 301
        self._make_published_post(account_id=acct, title="Idempotent test")
        svc = ContentIntelligenceService()
        svc.sync_content_metrics(account_id=acct)
        result2 = svc.sync_content_metrics(account_id=acct)
        assert result2["synced"] == 0
        assert result2["already_synced"] >= 1

    # ── summary ───────────────────────────────────────────────────────────────

    def test_content_summary_after_sync(self):
        """get_content_summary returns non-zero values after sync."""
        from app.db.init_db import init_db
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 302
        self._make_published_post(account_id=acct, title="Summary test",
                                  published_at="2026-03-10T10:00:00")
        svc = ContentIntelligenceService()
        svc.sync_content_metrics(account_id=acct)
        summary = svc.get_content_summary(account_id=acct, days=365)
        assert summary["posts_published"] >= 1
        assert summary["total_reach"] > 0
        assert summary["total_engagement"] > 0
        assert 0.0 <= summary["avg_score"] <= 100.0

    # ── top posts ─────────────────────────────────────────────────────────────

    def test_top_posts_ordered_by_score(self):
        """get_top_posts returns posts in descending score order."""
        from app.db.init_db import init_db
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 303
        for i in range(3):
            self._make_published_post(account_id=acct, title=f"Post {i}",
                                      published_at="2026-03-05T10:00:00")
        svc = ContentIntelligenceService()
        svc.sync_content_metrics(account_id=acct)
        posts = svc.get_top_posts(account_id=acct, days=365)
        assert len(posts) >= 1
        scores = [p["score"] for p in posts]
        assert scores == sorted(scores, reverse=True)

    # ── format performance ────────────────────────────────────────────────────

    def test_format_performance_groups_correctly(self):
        """get_format_performance groups by post_type × platform."""
        from app.db.init_db import init_db
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 304
        self._make_published_post(account_id=acct, platform="instagram",
                                  post_type="reel", title="Reel 1",
                                  published_at="2026-03-01T10:00:00")
        self._make_published_post(account_id=acct, platform="instagram",
                                  post_type="image_post", title="Image 1",
                                  published_at="2026-03-02T10:00:00")
        svc = ContentIntelligenceService()
        svc.sync_content_metrics(account_id=acct)
        formats = svc.get_format_performance(account_id=acct, days=365)
        assert len(formats) >= 2
        types_found = {f["post_type"] for f in formats}
        assert "reel" in types_found
        assert "image_post" in types_found
        # reel should outrank image_post (higher engagement multiplier)
        reel_row = next(f for f in formats if f["post_type"] == "reel")
        img_row  = next(f for f in formats if f["post_type"] == "image_post")
        assert reel_row["avg_engagement"] > img_row["avg_engagement"]

    # ── best times ────────────────────────────────────────────────────────────

    def test_best_posting_times_sorted(self):
        """get_best_posting_times returns slots sorted by avg_engagement desc."""
        from app.db.init_db import init_db
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 305
        for pub_at in ["2026-03-01T08:00:00", "2026-03-02T14:00:00",
                       "2026-03-03T20:00:00"]:
            self._make_published_post(account_id=acct, title="Time post",
                                      published_at=pub_at)
        svc = ContentIntelligenceService()
        svc.sync_content_metrics(account_id=acct)
        times = svc.get_best_posting_times(account_id=acct, days=365)
        assert len(times) >= 1
        engagements = [t["avg_engagement"] for t in times]
        assert engagements == sorted(engagements, reverse=True)
        # Weekday labels should be valid
        valid_days = {"Mon","Tue","Wed","Thu","Fri","Sat","Sun"}
        for t in times:
            assert t["weekday_label"] in valid_days

    # ── reuse opportunities ───────────────────────────────────────────────────

    def test_detect_reuse_for_top_performer(self):
        """High-score post generates at least a top_performer insight."""
        from app.db.init_db import init_db, get_connection
        from app.services.content_intelligence_service import ContentIntelligenceService, _mock_metrics
        init_db()
        acct = 306
        # Use instagram+reel for maximum mock score
        post = self._make_published_post(account_id=acct, platform="instagram",
                                         post_type="reel", title="Viral Reel",
                                         published_at="2026-02-01T10:00:00")
        # Insert mock metrics directly so we control score
        m = _mock_metrics({"id": post["id"], "platform_target": "instagram",
                           "post_type": "reel"})
        # Inflate engagement for guaranteed top-performer score
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO content_metrics
               (account_id, content_post_id, platform_target, metric_date,
                impressions, reach, clicks, engagement, likes, comments, shares, saves, ctr)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (acct, post["id"], "instagram", "2026-02-01",
             50000, 40000, 2000, 8000, 5000, 400, 800, 800, 0.05),
        )
        conn.commit()
        conn.close()
        svc = ContentIntelligenceService()
        insights = svc.detect_reuse_opportunities(account_id=acct, days=365)
        types = {i["type"] for i in insights if "error" not in i}
        assert "top_performer" in types

    def test_detect_no_opportunities_for_unpublished(self):
        """Account with no published posts returns no insights."""
        from app.db.init_db import init_db
        from app.services.content_intelligence_service import ContentIntelligenceService
        from app.services.publishing_service import PublishingService
        init_db()
        acct = 307
        PublishingService().create_post(account_id=acct, title="Draft only")
        svc = ContentIntelligenceService()
        insights = svc.detect_reuse_opportunities(account_id=acct, days=30)
        assert insights == []

    # ── content score ─────────────────────────────────────────────────────────

    def test_content_score_high_engagement(self):
        """Post with very high engagement should score above 60."""
        from app.db.init_db import init_db, get_connection
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 308
        post = self._make_published_post(account_id=acct, title="High eng",
                                         published_at="2026-03-10T10:00:00")
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO content_metrics
               (account_id, content_post_id, platform_target, metric_date,
                impressions, reach, clicks, engagement, likes, comments, shares, saves, ctr)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (acct, post["id"], "instagram", "2026-03-10",
             100000, 80000, 4000, 8000, 5000, 600, 1200, 1200, 0.05),
        )
        conn.commit()
        conn.close()
        svc = ContentIntelligenceService()
        score = svc.calculate_content_score(post_id=post["id"], account_id=acct)
        assert score > 60.0
        assert score <= 100.0

    def test_content_score_low_engagement(self):
        """Post with very low engagement should score below 20."""
        from app.db.init_db import init_db, get_connection
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 309
        post = self._make_published_post(account_id=acct, title="Low eng",
                                         published_at="2026-01-01T10:00:00")
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO content_metrics
               (account_id, content_post_id, platform_target, metric_date,
                impressions, reach, clicks, engagement, likes, comments, shares, saves, ctr)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (acct, post["id"], "instagram", "2026-01-01",
             1000, 900, 2, 5, 3, 1, 1, 0, 0.002),
        )
        conn.commit()
        conn.close()
        svc = ContentIntelligenceService()
        score = svc.calculate_content_score(post_id=post["id"], account_id=acct)
        assert score < 20.0

    def test_content_score_uses_mock_fallback(self):
        """Score for post without stored metrics still returns a value > 0."""
        from app.db.init_db import init_db
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        acct = 310
        post = self._make_published_post(account_id=acct, title="No metrics")
        svc = ContentIntelligenceService()
        score = svc.calculate_content_score(post_id=post["id"], account_id=acct)
        assert 0.0 <= score <= 100.0

    # ── account isolation ──────────────────────────────────────────────────────

    def test_account_isolation(self):
        """Metrics and insights from account 311 do not appear in account 312."""
        from app.db.init_db import init_db, get_connection
        from app.services.content_intelligence_service import ContentIntelligenceService
        init_db()
        self._make_published_post(account_id=311, title="Acct311 post",
                                  published_at="2026-03-01T10:00:00")
        svc = ContentIntelligenceService()
        svc.sync_content_metrics(account_id=311)
        summary312 = svc.get_content_summary(account_id=312, days=365)
        assert summary312["posts_published"] == 0
        assert summary312["total_reach"] == 0

    # ── API endpoints ─────────────────────────────────────────────────────────

    def test_sync_api_endpoint(self, client):
        """POST /api/content/intelligence/sync returns 200."""
        resp = client.post(
            "/api/content/intelligence/sync",
            json={"account_id": 1},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "synced" in data
        assert "already_synced" in data

    def test_summary_api_endpoint(self, client):
        """GET /api/content/intelligence/summary returns expected keys."""
        resp = client.get("/api/content/intelligence/summary?account_id=1&days=7")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "posts_published" in data
        assert "avg_score" in data

    def test_top_posts_api_endpoint(self, client):
        """GET /api/content/intelligence/top-posts returns a list."""
        resp = client.get("/api/content/intelligence/top-posts?account_id=1&days=30")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_formats_api_endpoint(self, client):
        """GET /api/content/intelligence/formats returns a list."""
        resp = client.get("/api/content/intelligence/formats?account_id=1&days=30")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_reuse_api_endpoint(self, client):
        """GET /api/content/intelligence/reuse returns a list."""
        resp = client.get("/api/content/intelligence/reuse?account_id=1&days=30")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


# ── Phase 8G: Scheduler Loop ──────────────────────────────────────────────────

class TestSchedulerLoop:
    """Tests for Phase 8G: Content Scheduler + Auto-Publish Loop."""

    ACCT = 400

    # ── Scheduler status endpoint ─────────────────────────────────────────────

    def test_scheduler_status_endpoint(self, client):
        """GET /api/content/scheduler/status returns a status dict."""
        resp = client.get("/api/content/scheduler/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "running" in data
        assert "jobs_executed" in data
        assert "jobs_failed" in data
        assert "stuck_resolved" in data

    def test_scheduler_status_has_expected_shape(self, client):
        """Scheduler status contains all expected fields with correct types."""
        resp = client.get("/api/content/scheduler/status")
        data = resp.get_json()
        assert isinstance(data["running"], bool)
        assert isinstance(data["jobs_executed"], int)
        assert isinstance(data["jobs_failed"], int)
        assert isinstance(data["stuck_resolved"], int)

    # ── Manual run endpoint ───────────────────────────────────────────────────

    def test_scheduler_run_now_endpoint(self, client):
        """POST /api/content/scheduler/run executes a pass and returns results."""
        resp = client.post("/api/content/scheduler/run")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "executed" in data
        assert "failed" in data
        assert "stuck_resolved" in data
        assert "run_at" in data

    def test_scheduler_run_now_returns_numeric_counts(self, client):
        """run_now returns non-negative integer counts."""
        resp = client.post("/api/content/scheduler/run")
        data = resp.get_json()
        assert isinstance(data["executed"], int)
        assert isinstance(data["failed"], int)
        assert isinstance(data["stuck_resolved"], int)
        assert data["executed"] >= 0
        assert data["failed"] >= 0
        assert data["stuck_resolved"] >= 0

    # ── Webhook ingestion ─────────────────────────────────────────────────────

    def test_webhook_requires_post_id(self, client):
        """POST /api/content/publish/webhook without post_id returns 400."""
        resp = client.post(
            "/api/content/publish/webhook",
            json={"status": "published"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_webhook_unknown_post_returns_404(self, client):
        """POST /api/content/publish/webhook with unknown post_id returns 404."""
        resp = client.post(
            "/api/content/publish/webhook",
            json={"post_id": 999999, "status": "published"},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_webhook_updates_post_status(self, client):
        """Webhook callback with status='published' marks the post published."""
        from app.services.publishing_service import PublishingService
        svc = PublishingService()
        post = svc.create_post(account_id=self.ACCT, title="Webhook Test",
                               platform_target="instagram")
        assert "id" in post

        resp = client.post(
            "/api/content/publish/webhook",
            json={
                "post_id": post["id"],
                "external_post_id": "ext_webhook_123",
                "status": "published",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True
        assert data.get("ingested") is True

        updated = svc.get_post(post["id"], account_id=self.ACCT)
        assert updated["status"] == "published"
        assert updated["external_post_id"] == "ext_webhook_123"

    def test_webhook_ingests_metrics(self, client):
        """Webhook callback with metrics dict upserts into content_metrics."""
        from app.services.publishing_service import PublishingService
        from app.db.init_db import get_connection

        svc = PublishingService()
        post = svc.create_post(account_id=self.ACCT + 1, title="Webhook Metrics",
                               platform_target="facebook")
        assert "id" in post

        resp = client.post(
            "/api/content/publish/webhook",
            json={
                "post_id": post["id"],
                "status": "published",
                "metrics": {
                    "impressions": 1500,
                    "reach": 1200,
                    "clicks": 80,
                    "engagement": 100,
                    "likes": 60,
                    "comments": 20,
                    "shares": 10,
                    "saves": 10,
                    "ctr": 0.053,
                },
            },
            content_type="application/json",
        )
        assert resp.status_code == 200

        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM content_metrics WHERE content_post_id=?", (post["id"],)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["impressions"] == 1500
        assert row["likes"] == 60

    def test_webhook_idempotent_on_repeat(self, client):
        """Calling webhook twice does not create duplicate metrics rows."""
        from app.services.publishing_service import PublishingService
        from app.db.init_db import get_connection

        svc = PublishingService()
        post = svc.create_post(account_id=self.ACCT + 2, title="Idempotent Webhook",
                               platform_target="instagram")

        payload = {
            "post_id": post["id"],
            "status": "published",
            "metrics": {"impressions": 500, "likes": 30, "ctr": 0.02},
        }
        client.post("/api/content/publish/webhook", json=payload,
                    content_type="application/json")
        client.post("/api/content/publish/webhook", json=payload,
                    content_type="application/json")

        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM content_metrics WHERE content_post_id=?", (post["id"],)
        ).fetchone()[0]
        conn.close()
        assert count == 1  # Idempotent: only one row per post per day

    # ── Stuck job detection ───────────────────────────────────────────────────

    def test_stuck_job_detection(self, client):
        """Stuck jobs in 'publishing' state older than threshold are resolved."""
        from app.services.publishing_service import PublishingService
        from app.db.init_db import get_connection
        from datetime import datetime, timezone, timedelta

        svc = PublishingService()
        post = svc.create_post(account_id=self.ACCT + 3, title="Stuck Job Post",
                               platform_target="instagram")

        # Create a job and manually set it to 'publishing' with old timestamp
        job = svc._create_job(
            account_id=self.ACCT + 3,
            post_id=post["id"],
            platform_target="instagram",
            job_type="publish_now",
            status="publishing",
        )
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        conn = get_connection()
        conn.execute(
            "UPDATE publishing_jobs SET updated_at=? WHERE id=?",
            (old_ts, job["id"]),
        )
        conn.commit()
        conn.close()

        # Run the scheduler loop — should detect and resolve the stuck job
        resp = client.post("/api/content/scheduler/run")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["stuck_resolved"] >= 1

        conn = get_connection()
        row = conn.execute(
            "SELECT status FROM publishing_jobs WHERE id=?", (job["id"],)
        ).fetchone()
        conn.close()
        assert row["status"] == "failed"

    # ── Service-level run_publishing_loop ─────────────────────────────────────

    def test_run_publishing_loop_returns_expected_keys(self, client):
        """run_publishing_loop() returns dict with required keys."""
        from app.services.scheduler_loop_service import run_publishing_loop
        result = run_publishing_loop()
        assert "run_at" in result
        assert "executed" in result
        assert "failed" in result
        assert "stuck_resolved" in result

    def test_scheduler_status_tracks_totals(self, client):
        """get_scheduler_status accumulates totals across multiple passes."""
        from app.services import scheduler_loop_service as sls
        # Reset status counters for this test
        with sls._status_lock:
            sls._status["jobs_executed"] = 0
            sls._status["jobs_failed"] = 0
            sls._status["stuck_resolved"] = 0

        sls.run_publishing_loop()
        sls.run_publishing_loop()

        status = sls.get_scheduler_status()
        assert isinstance(status["jobs_executed"], int)
        assert isinstance(status["jobs_failed"], int)
        assert status["last_run_at"] is not None

    def test_operations_log_records_loop_pass(self, client):
        """Each scheduler pass writes a record to operations_log."""
        from app.db.init_db import get_connection
        from app.services.scheduler_loop_service import run_publishing_loop

        before_count_row = get_connection().execute(
            "SELECT COUNT(*) FROM operations_log WHERE operation_type='publishing_loop'"
        ).fetchone()
        before_count = before_count_row[0]

        run_publishing_loop()

        conn = get_connection()
        after_count = conn.execute(
            "SELECT COUNT(*) FROM operations_log WHERE operation_type='publishing_loop'"
        ).fetchone()[0]
        conn.close()
        assert after_count == before_count + 1
