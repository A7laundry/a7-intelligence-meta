"""
Fixtures compartilhadas para testes A7 Intelligence Meta.
Todos os testes usam mocks — nenhuma credencial real é necessária.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Adiciona root do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── Mock config antes de importar qualquer módulo ───
MOCK_META_CONFIG = {
    "app_id": "test_app_id",
    "app_secret": "test_app_secret",
    "access_token": "test_access_token_abc123",
    "ad_account_id": "act_123456789",
    "page_id": "page_123",
    "pixel_id": "pixel_456",
}

MOCK_GOOGLE_ADS_CONFIG = {
    "developer_token": "test_dev_token",
    "client_id": "test_client_id",
    "client_secret": "test_client_secret",
    "refresh_token": "test_refresh_token",
    "customer_id": "1234567890",
    "login_customer_id": "",
}

MOCK_CAMPAIGN_TEMPLATES = {
    "captacao_novos": {
        "name": "A7 - Captação Novos Clientes",
        "objective": "OUTCOME_LEADS",
        "status": "PAUSED",
        "special_ad_categories": [],
        "daily_budget_cents": 5000,
    },
}

MOCK_AUDIENCES = {
    "orlando_vacation_rental": {
        "name": "Orlando - Vacation Rental Owners",
        "targeting": {
            "age_min": 30,
            "age_max": 60,
            "genders": [0],
            "geo_locations": {"cities": [{"key": "2418956", "name": "Orlando"}]},
        },
    },
}

MOCK_AD_COPY_TEMPLATES = {
    "captacao_orlando": {
        "headline": "Professional Laundry for Vacation Rentals",
        "primary_text": "Keep your Airbnb spotless!",
        "description": "Fast turnaround",
        "call_to_action": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },
}

MOCK_OPTIMIZATION_RULES = {
    "pause_high_cpa": {
        "threshold": 50.00,
        "action": "PAUSE",
        "lookback_days": 3,
    },
    "increase_budget_winners": {
        "threshold": 20.00,
        "min_results": 5,
        "action": "INCREASE_BUDGET",
        "increase_pct": 20,
        "lookback_days": 7,
    },
    "pause_low_ctr": {
        "threshold": 0.5,
        "min_impressions": 1000,
        "action": "PAUSE",
        "lookback_days": 3,
    },
}


@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    """Mock config module para todos os testes."""
    import types
    mock_module = types.ModuleType("config")
    mock_module.META_CONFIG = MOCK_META_CONFIG
    mock_module.GOOGLE_ADS_CONFIG = MOCK_GOOGLE_ADS_CONFIG
    mock_module.CAMPAIGN_TEMPLATES = MOCK_CAMPAIGN_TEMPLATES
    mock_module.AUDIENCES = MOCK_AUDIENCES
    mock_module.AD_COPY_TEMPLATES = MOCK_AD_COPY_TEMPLATES
    mock_module.OPTIMIZATION_RULES = MOCK_OPTIMIZATION_RULES
    monkeypatch.setitem(sys.modules, "config", mock_module)


@pytest.fixture
def mock_meta_response():
    """Factory para criar mock responses da Meta API."""
    def _make(data=None, status_code=200):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = data or {}
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            from requests.exceptions import HTTPError
            response.raise_for_status.side_effect = HTTPError(response=response)
        return response
    return _make


@pytest.fixture
def sample_ad_set_insights():
    """Dados de insights de ad set para testes do optimizer."""
    return [{
        "adset_name": "Test Ad Set",
        "impressions": "5000",
        "clicks": "150",
        "ctr": "3.0",
        "cpc": "0.50",
        "spend": "75.00",
        "reach": "4000",
        "actions": [
            {"action_type": "lead", "value": "10"},
            {"action_type": "link_click", "value": "150"},
        ],
        "cost_per_action_type": [
            {"action_type": "lead", "value": "7.50"},
            {"action_type": "link_click", "value": "0.50"},
        ],
    }]


@pytest.fixture
def sample_ad_set_high_cpa_insights():
    """Ad set com CPA alto (deve ser pausado)."""
    return [{
        "adset_name": "High CPA Ad Set",
        "impressions": "2000",
        "clicks": "40",
        "ctr": "2.0",
        "cpc": "2.50",
        "spend": "100.00",
        "reach": "1800",
        "actions": [
            {"action_type": "lead", "value": "1"},
        ],
        "cost_per_action_type": [
            {"action_type": "lead", "value": "100.00"},
        ],
    }]


@pytest.fixture
def sample_ad_set_low_ctr_insights():
    """Ad set com CTR baixo (deve ser pausado)."""
    return [{
        "adset_name": "Low CTR Ad Set",
        "impressions": "5000",
        "clicks": "10",
        "ctr": "0.2",
        "cpc": "5.00",
        "spend": "50.00",
        "reach": "4500",
        "actions": [],
        "cost_per_action_type": [],
    }]
