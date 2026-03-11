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
