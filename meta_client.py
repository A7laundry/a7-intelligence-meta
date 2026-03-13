"""
A7 Lavanderia - Facebook Ads Automation
Core API Client - Gerenciamento de Campanhas via Meta Marketing API
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Optional
try:
    from config import META_CONFIG, CAMPAIGN_TEMPLATES, AUDIENCES, AD_COPY_TEMPLATES
except ImportError:
    from config_default import META_CONFIG
    CAMPAIGN_TEMPLATES = {}
    AUDIENCES = {}
    AD_COPY_TEMPLATES = {}


class MetaAdsClient:
    """Cliente principal para interagir com a Meta Marketing API."""

    BASE_URL = "https://graph.facebook.com/v21.0"
    RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
    MAX_RETRIES = 3
    REQUEST_TIMEOUT = 30  # segundos

    def __init__(self, access_token=None):
        self.access_token = META_CONFIG["access_token"]
        self.ad_account_id = META_CONFIG["ad_account_id"]
        self.page_id = META_CONFIG["page_id"]
        self.pixel_id = META_CONFIG["pixel_id"]
        if access_token:
            self.access_token = access_token

    def _get_headers(self) -> dict:
        """Retorna headers de autenticação."""
        return {"Authorization": f"Bearer {self.access_token}"}

    def _request(self, method: str, endpoint: str, params: dict = None, data: dict = None) -> dict:
        """Faz requisição à API da Meta com retry automático para erros transientes."""
        url = f"{self.BASE_URL}/{endpoint}"

        if params is None:
            params = {}
        headers = self._get_headers()

        last_exception = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if method == "GET":
                    response = requests.get(url, params=params, headers=headers, timeout=self.REQUEST_TIMEOUT)
                elif method == "POST":
                    response = requests.post(url, params=params, json=data, headers=headers, timeout=self.REQUEST_TIMEOUT)
                elif method == "DELETE":
                    response = requests.delete(url, params=params, headers=headers, timeout=self.REQUEST_TIMEOUT)
                else:
                    raise ValueError(f"Método HTTP não suportado: {method}")

                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 0
                if status_code in self.RETRYABLE_STATUS_CODES and attempt < self.MAX_RETRIES:
                    delay = 2 ** attempt  # 1s, 2s, 4s
                    print(f"⚠️ API retornou {status_code}. Retry {attempt + 1}/{self.MAX_RETRIES} em {delay}s...")
                    time.sleep(delay)
                    last_exception = e
                    continue
                error_data = e.response.json() if e.response else {}
                print(f"❌ Erro API Meta: {error_data}")
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < self.MAX_RETRIES:
                    delay = 2 ** attempt
                    print(f"⚠️ Erro de conexão. Retry {attempt + 1}/{self.MAX_RETRIES} em {delay}s...")
                    time.sleep(delay)
                    last_exception = e
                    continue
                print(f"❌ Erro na requisição após {self.MAX_RETRIES} tentativas: {e}")
                raise
            except Exception as e:
                print(f"❌ Erro na requisição: {e}")
                raise

        raise last_exception

    def _paginated_request(self, endpoint: str, params: dict, max_items: int = 500) -> list:
        """Faz requisições paginadas automaticamente, seguindo cursores da API."""
        all_data = []
        while len(all_data) < max_items:
            result = self._request("GET", endpoint, params=params)
            all_data.extend(result.get("data", []))

            paging = result.get("paging", {})
            cursors = paging.get("cursors", {})
            after = cursors.get("after")

            if after and paging.get("next"):
                params = dict(params)
                params["after"] = after
            else:
                break

        return all_data[:max_items]

    # ==============================================================
    # CAMPANHAS
    # ==============================================================

    def create_campaign(self, template_key: str, name_suffix: str = "") -> dict:
        """
        Cria uma campanha baseada em um template pré-definido.

        Args:
            template_key: Chave do template em CAMPAIGN_TEMPLATES
            name_suffix: Sufixo opcional para o nome (ex: data, região)

        Returns:
            dict com o ID da campanha criada
        """
        template = CAMPAIGN_TEMPLATES[template_key]

        campaign_name = template["name"]
        if name_suffix:
            campaign_name += f" - {name_suffix}"
        campaign_name += f" [{datetime.now().strftime('%d/%m/%Y')}]"

        params = {
            "name": campaign_name,
            "objective": template["objective"],
            "status": template["status"],
            "special_ad_categories": json.dumps(template.get("special_ad_categories", [])),
        }

        result = self._request("POST", f"{self.ad_account_id}/campaigns", params=params)
        print(f"✅ Campanha criada: {campaign_name} (ID: {result['id']})")
        return result

    def list_campaigns(self, status_filter: str = None) -> list:
        """Lista todas as campanhas da conta (com paginação automática)."""
        params = {
            "fields": "id,name,objective,status,daily_budget,lifetime_budget,created_time",
            "limit": 100,
        }
        if status_filter:
            params["filtering"] = json.dumps([
                {"field": "effective_status", "operator": "IN", "value": [status_filter]}
            ])

        return self._paginated_request(f"{self.ad_account_id}/campaigns", params)

    def update_campaign_status(self, campaign_id: str, status: str) -> dict:
        """Atualiza o status de uma campanha (ACTIVE, PAUSED, ARCHIVED)."""
        params = {"status": status}
        result = self._request("POST", campaign_id, params=params)
        print(f"✅ Campanha {campaign_id} → {status}")
        return result

    def update_campaign_budget(self, campaign_id: str, daily_budget_cents: int) -> dict:
        """Update campaign daily budget via Meta Ads API."""
        params = {"daily_budget": daily_budget_cents}
        result = self._request("POST", campaign_id, params=params)
        print(f"✅ Campaign {campaign_id} daily_budget → {daily_budget_cents} cents")
        return result

    # ==============================================================
    # AD SETS (Conjuntos de Anúncios)
    # ==============================================================

    def create_ad_set(
        self,
        campaign_id: str,
        audience_key: str,
        daily_budget_cents: int,
        name: str = None,
        optimization_goal: str = "CONVERSATIONS",
        billing_event: str = "IMPRESSIONS",
        start_time: str = None,
        end_time: str = None,
    ) -> dict:
        """
        Cria um Ad Set com público-alvo pré-definido.

        Args:
            campaign_id: ID da campanha pai
            audience_key: Chave do público em AUDIENCES
            daily_budget_cents: Orçamento diário em centavos
            name: Nome customizado (opcional)
            optimization_goal: Objetivo de otimização
            billing_event: Evento de cobrança
        """
        audience = AUDIENCES[audience_key]

        if not name:
            name = f"A7 - {audience['name']} [{datetime.now().strftime('%d/%m')}]"

        params = {
            "name": name,
            "campaign_id": campaign_id,
            "daily_budget": daily_budget_cents,
            "billing_event": billing_event,
            "optimization_goal": optimization_goal,
            "targeting": json.dumps(audience["targeting"]),
            "status": "PAUSED",
        }

        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        # Se tem pixel, adiciona para tracking de conversões
        if self.pixel_id and self.pixel_id != "SEU_PIXEL_ID":
            params["promoted_object"] = json.dumps({"pixel_id": self.pixel_id})

        result = self._request("POST", f"{self.ad_account_id}/adsets", params=params)
        print(f"✅ Ad Set criado: {name} (ID: {result['id']})")
        return result

    def list_ad_sets(self, campaign_id: str = None) -> list:
        """Lista ad sets com paginação automática, opcionalmente filtrado por campanha."""
        params = {
            "fields": "id,name,status,daily_budget,targeting,optimization_goal,campaign_id",
            "limit": 100,
        }

        endpoint = f"{campaign_id}/adsets" if campaign_id else f"{self.ad_account_id}/adsets"
        return self._paginated_request(endpoint, params)

    def update_ad_set_budget(self, ad_set_id: str, new_daily_budget_cents: int) -> dict:
        """Atualiza o orçamento diário de um ad set."""
        params = {"daily_budget": new_daily_budget_cents}
        result = self._request("POST", ad_set_id, params=params)
        print(f"✅ Budget atualizado: {ad_set_id} → R$ {new_daily_budget_cents/100:.2f}/dia")
        return result

    def update_ad_set_status(self, ad_set_id: str, status: str) -> dict:
        """Atualiza status de um ad set."""
        params = {"status": status}
        result = self._request("POST", ad_set_id, params=params)
        print(f"✅ Ad Set {ad_set_id} → {status}")
        return result

    # ==============================================================
    # ADS (Anúncios)
    # ==============================================================

    def create_ad(
        self,
        ad_set_id: str,
        copy_template_key: str,
        image_hash: str = None,
        video_id: str = None,
        name: str = None,
    ) -> dict:
        """
        Cria um anúncio usando template de copy pré-definido.

        Args:
            ad_set_id: ID do Ad Set pai
            copy_template_key: Chave do template em AD_COPY_TEMPLATES
            image_hash: Hash da imagem (upload via upload_image)
            video_id: ID do vídeo (upload via upload_video)
            name: Nome customizado
        """
        copy = AD_COPY_TEMPLATES[copy_template_key]

        if not name:
            name = f"A7 Ad - {copy['headline'][:30]} [{datetime.now().strftime('%d/%m')}]"

        # Monta o creative spec
        object_story_spec = {
            "page_id": self.page_id,
            "link_data": {
                "message": copy["primary_text"],
                "link": copy["link"],
                "name": copy["headline"],
                "description": copy["description"],
                "call_to_action": {
                    "type": copy["call_to_action"],
                    "value": {"link": copy["link"]},
                },
            },
        }

        if image_hash:
            object_story_spec["link_data"]["image_hash"] = image_hash
        if video_id:
            object_story_spec["link_data"]["video_id"] = video_id

        creative_params = {
            "name": f"Creative - {name}",
            "object_story_spec": json.dumps(object_story_spec),
        }

        # Cria o creative primeiro
        creative_result = self._request(
            "POST", f"{self.ad_account_id}/adcreatives", params=creative_params
        )
        creative_id = creative_result["id"]
        print(f"✅ Creative criado: {creative_id}")

        # Cria o ad com o creative
        ad_params = {
            "name": name,
            "adset_id": ad_set_id,
            "creative": json.dumps({"creative_id": creative_id}),
            "status": "PAUSED",
        }

        result = self._request("POST", f"{self.ad_account_id}/ads", params=ad_params)
        print(f"✅ Ad criado: {name} (ID: {result['id']})")
        return result

    def list_ads(self, ad_set_id: str = None) -> list:
        """Lista anúncios com paginação automática."""
        params = {
            "fields": "id,name,status,creative,adset_id",
            "limit": 100,
        }
        endpoint = f"{ad_set_id}/ads" if ad_set_id else f"{self.ad_account_id}/ads"
        return self._paginated_request(endpoint, params)

    # ==============================================================
    # UPLOAD DE CRIATIVOS
    # ==============================================================

    def upload_image(self, image_path: str) -> str:
        """
        Faz upload de uma imagem para usar nos anúncios.

        Returns:
            image_hash para uso na criação de ads
        """
        url = f"{self.BASE_URL}/{self.ad_account_id}/adimages"

        with open(image_path, "rb") as img_file:
            files = {"filename": img_file}
            response = requests.post(url, headers=self._get_headers(), files=files, timeout=60)
            response.raise_for_status()

        data = response.json()
        images = data.get("images", {})
        if images:
            image_info = list(images.values())[0]
            image_hash = image_info["hash"]
            print(f"🖼️ Imagem uploaded: {image_hash}")
            return image_hash

        raise Exception("Falha no upload da imagem")

    def upload_video(self, video_path: str, title: str = "A7 Video Ad") -> str:
        """
        Faz upload de um vídeo para usar nos anúncios.

        Returns:
            video_id para uso na criação de ads
        """
        url = f"{self.BASE_URL}/{self.ad_account_id}/advideos"

        with open(video_path, "rb") as vid_file:
            files = {"source": vid_file}
            params = {"title": title}
            response = requests.post(url, params=params, headers=self._get_headers(), files=files, timeout=120)
            response.raise_for_status()

        data = response.json()
        video_id = data.get("id")
        print(f"🎬 Vídeo uploaded: {video_id}")

        return video_id

    # ==============================================================
    # RELATÓRIOS E INSIGHTS
    # ==============================================================

    def get_campaign_insights(
        self,
        campaign_id: str,
        date_preset: str = "last_7d",
        fields: str = None,
    ) -> list:
        """
        Puxa métricas de performance de uma campanha.

        Args:
            campaign_id: ID da campanha
            date_preset: Período (today, yesterday, last_7d, last_30d, etc)
            fields: Campos específicos (padrão: métricas principais)
        """
        if not fields:
            fields = (
                "campaign_name,impressions,clicks,ctr,cpc,cpm,spend,"
                "actions,action_values,cost_per_action_type,purchase_roas,"
                "reach,frequency"
            )

        params = {
            "fields": fields,
            "date_preset": date_preset,
        }

        result = self._request("GET", f"{campaign_id}/insights", params=params)
        return result.get("data", [])

    def get_account_insights(self, date_preset: str = "last_7d") -> list:
        """Puxa métricas gerais da conta de anúncios."""
        params = {
            "fields": (
                "impressions,clicks,ctr,cpc,cpm,spend,actions,"
                "action_values,cost_per_action_type,reach,frequency"
            ),
            "date_preset": date_preset,
        }

        result = self._request("GET", f"{self.ad_account_id}/insights", params=params)
        return result.get("data", [])

    def get_ad_set_insights(self, ad_set_id: str, date_preset: str = "last_7d") -> list:
        """Puxa métricas de um ad set específico."""
        params = {
            "fields": (
                "adset_name,impressions,clicks,ctr,cpc,spend,"
                "actions,action_values,cost_per_action_type,reach"
            ),
            "date_preset": date_preset,
        }

        result = self._request("GET", f"{ad_set_id}/insights", params=params)
        return result.get("data", [])

    def get_daily_insights(self, date_preset: str = "last_7d") -> list:
        """Puxa métricas diárias da conta (para trend charts)."""
        params = {
            "fields": "spend,impressions,clicks,actions,action_values",
            "date_preset": date_preset,
            "time_increment": 1,
        }

        result = self._request("GET", f"{self.ad_account_id}/insights", params=params)
        return result.get("data", [])

    # ==============================================================
    # AUDIÊNCIAS CUSTOMIZADAS
    # ==============================================================

    def create_custom_audience_website(
        self,
        name: str,
        description: str,
        retention_days: int = 30,
        rule: dict = None,
    ) -> dict:
        """
        Cria uma audiência customizada baseada em visitantes do site.
        Requer pixel ativo.
        """
        params = {
            "name": name,
            "description": description,
            "subtype": "WEBSITE",
            "rule": json.dumps(rule or {"inclusions": {"operator": "or", "rules": [
                {"event_sources": [{"id": self.pixel_id, "type": "pixel"}],
                 "retention_seconds": retention_days * 86400}
            ]}}),
        }

        result = self._request("POST", f"{self.ad_account_id}/customaudiences", params=params)
        print(f"✅ Custom Audience criada: {name} (ID: {result['id']})")
        return result

    def create_lookalike_audience(
        self,
        source_audience_id: str,
        country: str = "BR",
        ratio: float = 0.02,  # Top 2% mais similar
        name: str = None,
    ) -> dict:
        """Cria uma audiência Lookalike baseada em uma custom audience."""
        if not name:
            name = f"A7 Lookalike {int(ratio*100)}% - {country}"

        params = {
            "name": name,
            "subtype": "LOOKALIKE",
            "origin_audience_id": source_audience_id,
            "lookalike_spec": json.dumps({
                "country": country,
                "ratio": ratio,
                "type": "similarity",
            }),
        }

        result = self._request("POST", f"{self.ad_account_id}/customaudiences", params=params)
        print(f"✅ Lookalike criada: {name} (ID: {result['id']})")
        return result

    # ==============================================================
    # TOKEN MANAGEMENT
    # ==============================================================

    def check_token_validity(self) -> dict:
        """
        Verifica validade do access token via debug_token endpoint.

        Returns:
            dict com is_valid, expires_at, days_left
        """
        app_id = META_CONFIG.get("app_id", "")
        app_secret = META_CONFIG.get("app_secret", "")

        if not app_id or not app_secret or app_id == "SEU_APP_ID":
            print("⚠️ app_id/app_secret não configurados. Não é possível verificar token.")
            return {"is_valid": None, "expires_at": 0, "days_left": None}

        params = {
            "input_token": self.access_token,
            "access_token": f"{app_id}|{app_secret}",
        }

        try:
            response = requests.get(
                f"{self.BASE_URL}/debug_token",
                params=params,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json().get("data", {})

            is_valid = data.get("is_valid", False)
            expires_at = data.get("expires_at", 0)

            result = {"is_valid": is_valid, "expires_at": expires_at, "days_left": None}

            if not is_valid:
                print("❌ Token expirado ou inválido! Renove com: python3 main.py --refresh-token")
            elif expires_at > 0:
                expiry = datetime.fromtimestamp(expires_at)
                days_left = (expiry - datetime.now()).days
                result["days_left"] = days_left

                if days_left < 0:
                    print(f"❌ Token expirou em {expiry.strftime('%d/%m/%Y')}")
                elif days_left < 7:
                    print(f"⚠️ Token expira em {days_left} dias ({expiry.strftime('%d/%m/%Y')})")
                else:
                    print(f"✅ Token válido — expira em {days_left} dias ({expiry.strftime('%d/%m/%Y')})")
            else:
                print("✅ Token válido (sem data de expiração — token permanente)")

            return result

        except Exception as e:
            print(f"⚠️ Não foi possível verificar token: {e}")
            return {"is_valid": None, "expires_at": 0, "days_left": None}

    def refresh_long_lived_token(self) -> str:
        """
        Renova o access token de longa duração.
        Requer app_id e app_secret configurados.

        Returns:
            Novo access token (ou None se falhar)
        """
        app_id = META_CONFIG.get("app_id", "")
        app_secret = META_CONFIG.get("app_secret", "")

        if not app_id or not app_secret or app_id == "SEU_APP_ID":
            print("❌ app_id e app_secret são obrigatórios para renovar token.")
            return None

        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": self.access_token,
        }

        try:
            response = requests.get(
                f"{self.BASE_URL}/oauth/access_token",
                params=params,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            new_token = data.get("access_token")
            if new_token:
                print(f"✅ Token renovado com sucesso!")
                print(f"   Novo token: {new_token[:20]}...{new_token[-10:]}")
                print(f"\n⚠️ IMPORTANTE: Atualize o access_token em config.py com o novo valor!")
                return new_token
            else:
                print(f"❌ Resposta inesperada: {data}")
                return None

        except Exception as e:
            print(f"❌ Erro ao renovar token: {e}")
            return None

    # ==============================================================
    # FUNÇÕES DE CONVENIÊNCIA
    # ==============================================================

    def create_full_campaign(
        self,
        template_key: str,
        audience_key: str,
        copy_key: str,
        image_path: str = None,
        video_path: str = None,
        name_suffix: str = "",
    ) -> dict:
        """
        Cria uma campanha completa em um único comando:
        Campanha → Ad Set → Creative → Ad

        Args:
            template_key: Template de campanha (config.CAMPAIGN_TEMPLATES)
            audience_key: Público-alvo (config.AUDIENCES)
            copy_key: Template de copy (config.AD_COPY_TEMPLATES)
            image_path: Caminho da imagem (opcional)
            video_path: Caminho do vídeo (opcional)
            name_suffix: Sufixo para nomes
        """
        template = CAMPAIGN_TEMPLATES[template_key]

        print("=" * 60)
        print(f"✅ Criando campanha completa: {template['name']}")
        print("=" * 60)

        # 1. Cria campanha
        campaign = self.create_campaign(template_key, name_suffix)
        campaign_id = campaign["id"]

        # 2. Cria ad set com público-alvo
        ad_set = self.create_ad_set(
            campaign_id=campaign_id,
            audience_key=audience_key,
            daily_budget_cents=template["daily_budget_cents"],
        )
        ad_set_id = ad_set["id"]

        # 3. Upload de criativo (se fornecido)
        image_hash = None
        video_id = None
        if image_path:
            image_hash = self.upload_image(image_path)
        if video_path:
            video_id = self.upload_video(video_path)

        # 4. Cria o anúncio
        ad = self.create_ad(
            ad_set_id=ad_set_id,
            copy_template_key=copy_key,
            image_hash=image_hash,
            video_id=video_id,
        )

        result = {
            "campaign_id": campaign_id,
            "ad_set_id": ad_set_id,
            "ad_id": ad["id"],
        }

        print("=" * 60)
        print(f"✅ Campanha criada com sucesso!")
        print(f"   Campaign: {campaign_id}")
        print(f"   Ad Set:   {ad_set_id}")
        print(f"   Ad:       {ad['id']}")
        print(f"⚠️  Status: PAUSADO (revise e ative manualmente)")
        print("=" * 60)

        return result
