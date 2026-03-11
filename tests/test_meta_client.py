"""
Testes para MetaAdsClient — parsing de respostas e comportamento de retry.
"""

import pytest
from unittest.mock import patch, MagicMock, call
import requests as real_requests


@pytest.fixture
def patched_client():
    """Cria MetaAdsClient com requests mockado (patch mantido durante o teste)."""
    with patch("meta_client.requests") as mock_requests:
        from meta_client import MetaAdsClient
        client = MetaAdsClient()
        yield client, mock_requests


class TestMetaAdsClient:
    """Testes para o cliente Meta Ads."""

    def test_auth_header_used(self, patched_client):
        """Token deve ser enviado via Authorization header, não query param."""
        client, mock_requests = patched_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        client._request("GET", "test_endpoint")

        _, kwargs = mock_requests.get.call_args
        assert "Authorization" in kwargs["headers"]
        assert kwargs["headers"]["Authorization"] == "Bearer test_access_token_abc123"
        assert "access_token" not in kwargs["params"]

    def test_request_timeout(self, patched_client):
        """Requisições devem ter timeout configurado."""
        client, mock_requests = patched_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        client._request("GET", "test_endpoint")

        _, kwargs = mock_requests.get.call_args
        assert kwargs["timeout"] == 30

    def test_retry_on_500(self, patched_client):
        """Deve retentar automaticamente em erro 500."""
        client, mock_requests = patched_client

        error_response = MagicMock()
        error_response.status_code = 500
        error_response.json.return_value = {"error": "server error"}
        mock_requests.exceptions = real_requests.exceptions
        error_response.raise_for_status.side_effect = real_requests.exceptions.HTTPError(
            response=error_response
        )

        success_response = MagicMock()
        success_response.json.return_value = {"data": [{"id": "123"}]}
        success_response.raise_for_status = MagicMock()

        mock_requests.get.side_effect = [error_response, success_response]

        with patch("meta_client.time.sleep"):
            result = client._request("GET", "test_endpoint")

        assert result == {"data": [{"id": "123"}]}
        assert mock_requests.get.call_count == 2

    def test_no_retry_on_400(self, patched_client):
        """NÃO deve retentar em erro 400 (erro do cliente)."""
        client, mock_requests = patched_client

        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {"error": {"message": "bad request"}}
        mock_requests.exceptions = real_requests.exceptions
        error_response.raise_for_status.side_effect = real_requests.exceptions.HTTPError(
            response=error_response
        )
        mock_requests.get.return_value = error_response

        with pytest.raises(real_requests.exceptions.HTTPError):
            client._request("GET", "test_endpoint")

        assert mock_requests.get.call_count == 1

    def test_retry_on_connection_error(self, patched_client):
        """Deve retentar em erro de conexão."""
        client, mock_requests = patched_client

        mock_requests.exceptions = real_requests.exceptions

        success_response = MagicMock()
        success_response.json.return_value = {"ok": True}
        success_response.raise_for_status = MagicMock()

        mock_requests.get.side_effect = [
            real_requests.exceptions.ConnectionError("Connection refused"),
            success_response,
        ]

        with patch("meta_client.time.sleep"):
            result = client._request("GET", "test_endpoint")

        assert result == {"ok": True}
        assert mock_requests.get.call_count == 2

    def test_retry_on_timeout(self, patched_client):
        """Deve retentar em timeout."""
        client, mock_requests = patched_client

        mock_requests.exceptions = real_requests.exceptions

        success_response = MagicMock()
        success_response.json.return_value = {"ok": True}
        success_response.raise_for_status = MagicMock()

        mock_requests.get.side_effect = [
            real_requests.exceptions.Timeout("Request timed out"),
            success_response,
        ]

        with patch("meta_client.time.sleep"):
            result = client._request("GET", "test_endpoint")

        assert result == {"ok": True}

    def test_list_campaigns_returns_data(self, patched_client):
        """list_campaigns deve retornar lista de campanhas."""
        client, mock_requests = patched_client

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "c1", "name": "Campaign 1", "status": "ACTIVE"},
                {"id": "c2", "name": "Campaign 2", "status": "PAUSED"},
            ],
            "paging": {},
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        campaigns = client.list_campaigns()

        assert len(campaigns) == 2
        assert campaigns[0]["id"] == "c1"

    def test_list_campaigns_with_filter(self, patched_client):
        """list_campaigns com status_filter deve incluir filtering."""
        client, mock_requests = patched_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [], "paging": {}}
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        client.list_campaigns(status_filter="ACTIVE")

        _, kwargs = mock_requests.get.call_args
        assert "filtering" in kwargs["params"]

    def test_get_headers(self, patched_client):
        """_get_headers deve retornar header Bearer correto."""
        client, _ = patched_client
        headers = client._get_headers()
        assert headers == {"Authorization": "Bearer test_access_token_abc123"}

    def test_paginated_request(self, patched_client):
        """_paginated_request deve seguir cursores."""
        client, mock_requests = patched_client

        page1 = MagicMock()
        page1.json.return_value = {
            "data": [{"id": "1"}, {"id": "2"}],
            "paging": {"cursors": {"after": "cursor_abc"}, "next": "https://next"},
        }
        page1.raise_for_status = MagicMock()

        page2 = MagicMock()
        page2.json.return_value = {
            "data": [{"id": "3"}],
            "paging": {"cursors": {}},
        }
        page2.raise_for_status = MagicMock()

        mock_requests.get.side_effect = [page1, page2]

        result = client._paginated_request("test", {"limit": 2})

        assert len(result) == 3
        assert [r["id"] for r in result] == ["1", "2", "3"]

    def test_paginated_request_max_items(self, patched_client):
        """_paginated_request deve respeitar max_items."""
        client, mock_requests = patched_client

        page1 = MagicMock()
        page1.json.return_value = {
            "data": [{"id": str(i)} for i in range(100)],
            "paging": {},
        }
        page1.raise_for_status = MagicMock()

        mock_requests.get.return_value = page1

        result = client._paginated_request("test", {"limit": 100}, max_items=50)

        assert len(result) == 50

    def test_post_request(self, patched_client):
        """POST requests devem usar método correto."""
        client, mock_requests = patched_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "new_123"}
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        result = client._request("POST", "test_endpoint", params={"name": "test"})

        assert result == {"id": "new_123"}
        mock_requests.post.assert_called_once()

    def test_delete_request(self, patched_client):
        """DELETE requests devem funcionar."""
        client, mock_requests = patched_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()
        mock_requests.delete.return_value = mock_response

        result = client._request("DELETE", "test_endpoint")

        assert result == {"success": True}
        mock_requests.delete.assert_called_once()
