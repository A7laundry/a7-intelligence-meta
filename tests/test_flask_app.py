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
        bi._get_dashboard_data = lambda days: dashboard

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
        bi._get_dashboard_data = lambda days: dashboard

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
        bi._get_dashboard_data = lambda days: dashboard

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
        bi._get_dashboard_data = lambda days: dashboard

        score = bi.compute_efficiency_score(days=7)
        assert 0 <= score["score"] <= 100
        assert "components" in score


class TestAlertDeduplication:
    def test_duplicate_not_persisted_twice(self, client):
        from app.services.alerts_service import AlertsService
        svc = AlertsService()
        alert = svc._make_alert(
            alert_type="test_dedup",
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
        coach._get_dashboard_data = lambda days: dashboard
        coach._get_creatives = lambda days: []

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
        coach._get_dashboard_data = lambda days: dashboard
        coach._get_creatives = lambda days: []

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
