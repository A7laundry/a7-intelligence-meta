"""
A7 Lavanderia - Facebook Ads Automation
Configurações e credenciais

INSTRUÇÕES: Copie este arquivo para config.py e preencha com suas credenciais reais.
    cp config.example.py config.py
"""

# ==============================================================
# CONFIGURAÇÃO DA META API
# ==============================================================
# Preencha com suas credenciais do Meta for Developers
# https://developers.facebook.com/
#
# Token Management:
#   Verificar validade: python3 main.py --check-token
#   Renovar token:      python3 main.py --refresh-token
#   O token longo prazo expira em ~60 dias. O sistema alerta quando faltam 7 dias.

META_CONFIG = {
    "app_id": "SEU_APP_ID",                      # Necessário para verificar/renovar token
    "app_secret": "SEU_APP_SECRET",               # Necessário para verificar/renovar token
    "access_token": "SEU_ACCESS_TOKEN_LONGO_PRAZO",
    "ad_account_id": "act_SEU_AD_ACCOUNT_ID",     # Sempre com prefixo "act_"
    "page_id": "SEU_PAGE_ID",                     # ID da página A7 Lavanderia no Facebook
    "pixel_id": "SEU_PIXEL_ID",                   # Facebook Pixel (para conversões)
}

# ==============================================================
# CONFIGURAÇÕES DE CAMPANHA PADRÃO - A7 LAVANDERIA
# ==============================================================

# Públicos-alvo pré-definidos para A7
AUDIENCES = {
    "sao_paulo_premium": {
        "name": "SP - Premium 25-55",
        "description": "Público premium em São Paulo",
        "targeting": {
            "age_min": 25,
            "age_max": 55,
            "genders": [0],  # 0=All, 1=Male, 2=Female
            "geo_locations": {
                "cities": [
                    {"key": "2428980", "name": "São Paulo", "region": "São Paulo"}
                ]
            },
            "interests": [
                {"id": "6003349442621", "name": "Luxury goods"},
                {"id": "6003384248805", "name": "Fashion"},
                {"id": "6003382982634", "name": "Home improvement"},
            ],
            "behaviors": [],
            "income": [],  # Segmentação por renda (onde disponível)
        },
    },
    "manaus_geral": {
        "name": "Manaus - Geral 22-50",
        "description": "Público geral em Manaus",
        "targeting": {
            "age_min": 22,
            "age_max": 50,
            "genders": [0],
            "geo_locations": {
                "cities": [
                    {"key": "2427583", "name": "Manaus", "region": "Amazonas"}
                ]
            },
            "interests": [
                {"id": "6003382982634", "name": "Home improvement"},
                {"id": "6003020834693", "name": "Cleaning"},
            ],
        },
    },
    "orlando_vacation_rental": {
        "name": "Orlando - Vacation Rental Owners",
        "description": "Proprietários de imóveis para aluguel temporário em Orlando",
        "targeting": {
            "age_min": 30,
            "age_max": 60,
            "genders": [0],
            "geo_locations": {
                "cities": [
                    {"key": "2418956", "name": "Orlando", "region": "Florida"}
                ]
            },
            "interests": [
                {"id": "6003349442621", "name": "Vacation rental"},
                {"id": "6003384248805", "name": "Airbnb"},
                {"id": "6003382982634", "name": "Real estate investing"},
            ],
        },
    },
}

# Templates de campanhas pré-configurados
CAMPAIGN_TEMPLATES = {
    "captacao_novos": {
        "name": "A7 - Captação Novos Clientes",
        "objective": "OUTCOME_LEADS",
        "status": "PAUSED",  # Sempre começa pausado para revisão
        "special_ad_categories": [],
        "daily_budget_cents": 5000,  # R$ 50,00 / dia
    },
    "retargeting": {
        "name": "A7 - Retargeting Visitantes",
        "objective": "OUTCOME_SALES",
        "status": "PAUSED",
        "special_ad_categories": [],
        "daily_budget_cents": 3000,  # R$ 30,00 / dia
    },
    "brand_awareness": {
        "name": "A7 - Reconhecimento de Marca",
        "objective": "OUTCOME_AWARENESS",
        "status": "PAUSED",
        "special_ad_categories": [],
        "daily_budget_cents": 2000,  # R$ 20,00 / dia
    },
    "whatsapp_conversao": {
        "name": "A7 - Click to WhatsApp",
        "objective": "OUTCOME_ENGAGEMENT",
        "status": "PAUSED",
        "special_ad_categories": [],
        "daily_budget_cents": 4000,  # R$ 40,00 / dia
    },
}

# Templates de copy para anúncios
AD_COPY_TEMPLATES = {
    "captacao_sp": {
        "headline": "Lavanderia Premium em São Paulo",
        "primary_text": "🔷 Roupas impecáveis sem sair de casa! A A7 Lavanderia cuida das suas peças com carinho profissional.",
        "description": "Coleta e entrega • Roupas delicadas • Desde 2015",
        "call_to_action": "SEND_WHATSAPP_MESSAGE",
        "link": "https://wa.me/5511XXXXXXXXX?text=Olá! Quero agendar uma coleta",
    },
    "captacao_orlando": {
        "headline": "Professional Laundry for Vacation Rentals",
        "primary_text": "🔷 Keep your Airbnb spotless between guests! A7 Lavanderia offers fast turnaround for vacation rental owners in Orlando.",
        "description": "Fast turnaround • Free pickup • Orlando FL",
        "call_to_action": "SEND_WHATSAPP_MESSAGE",
        "link": "https://wa.me/1407XXXXXXX?text=Hi! I need laundry service for my rental",
    },
    "retargeting_geral": {
        "headline": "Ainda pensando? 🔷",
        "primary_text": "Você visitou a A7 Lavanderia e nós estamos prontos para cuidar das suas roupas! Primeira lavagem com desconto especial.",
        "description": "20% OFF na primeira lavagem • Coleta grátis",
        "call_to_action": "SEND_WHATSAPP_MESSAGE",
        "link": "https://wa.me/5511XXXXXXXXX?text=Quero aproveitar o desconto de 20%",
    },
}

# ==============================================================
# REGRAS DE OTIMIZAÇÃO AUTOMÁTICA
# ==============================================================
# ==============================================================
# CONFIGURAÇÃO GOOGLE ADS API
# ==============================================================
# Preencha com suas credenciais do Google Ads
# https://developers.google.com/google-ads/api/docs/get-started/introduction

GOOGLE_ADS_CONFIG = {
    "developer_token": "SEU_DEVELOPER_TOKEN",
    "client_id": "SEU_CLIENT_ID.apps.googleusercontent.com",
    "client_secret": "SEU_CLIENT_SECRET",
    "refresh_token": "SEU_REFRESH_TOKEN",
    "customer_id": "SEU_CUSTOMER_ID",  # Sem hífens (ex: "1234567890")
    "login_customer_id": "",  # Preencher se usar conta gerente (MCC)
}

# ==============================================================
# REGRAS DE OTIMIZAÇÃO AUTOMÁTICA
# ==============================================================
OPTIMIZATION_RULES = {
    "pause_high_cpa": {
        "description": "Pausa ad sets com CPA acima do limite",
        "metric": "cost_per_action_type",
        "threshold": 50.00,  # R$ 50 de CPA máximo
        "action": "PAUSE",
        "lookback_days": 3,
    },
    "increase_budget_winners": {
        "description": "Aumenta orçamento de ad sets com bom desempenho",
        "metric": "cost_per_action_type",
        "threshold": 20.00,  # CPA abaixo de R$ 20
        "min_results": 5,  # Mínimo de 5 conversões
        "action": "INCREASE_BUDGET",
        "increase_pct": 20,  # Aumenta 20%
        "lookback_days": 7,
    },
    "pause_low_ctr": {
        "description": "Pausa ads com CTR muito baixo",
        "metric": "ctr",
        "threshold": 0.5,  # CTR mínimo de 0.5%
        "min_impressions": 1000,
        "action": "PAUSE",
        "lookback_days": 3,
    },
}

# ==============================================================
# CONFIGURAÇÃO DE ALERTAS
# ==============================================================
# Canal: "console" (padrão) ou "webhook" (Slack, Discord, n8n, WhatsApp)
# Alertas não repetem para o mesmo ad set dentro de 24h

ALERT_CONFIG = {
    "enabled": True,
    "channel": "console",  # "console" ou "webhook"
    "webhook_url": "",      # URL do webhook (Slack, Discord, n8n, etc.)
    "thresholds": {
        "cpa_max": 50.00,                 # Alerta quando CPA > R$50
        "ctr_min": 0.5,                   # Alerta quando CTR < 0.5%
        "min_impressions_for_ctr": 1000,  # Mínimo de impressões antes de alertar CTR
        "spend_without_conversions": 100.00,  # Alerta quando gasta R$100+ sem conversão
    },
    "daily_summary": True,  # Enviar sumário diário após cada otimização
}
