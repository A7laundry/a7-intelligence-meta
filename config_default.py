"""
Runtime config — tries local config.py first (dev), falls back to env vars (Railway/production).
"""
import os

try:
    from config import META_CONFIG, GOOGLE_ADS_CONFIG
except ImportError:
    META_CONFIG = {
        "app_id": os.getenv("META_APP_ID", ""),
        "app_secret": os.getenv("META_APP_SECRET", ""),
        "access_token": os.getenv("META_ACCESS_TOKEN", ""),
        "ad_account_id": os.getenv("META_AD_ACCOUNT_ID", ""),
        "ad_account_id_br": os.getenv("META_AD_ACCOUNT_ID_BR", ""),
        "page_id": os.getenv("META_PAGE_ID", ""),
        "pixel_id": os.getenv("META_PIXEL_ID", ""),
    }
    GOOGLE_ADS_CONFIG = {
        "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
        "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""),
        "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""),
        "customer_id": os.getenv("GOOGLE_ADS_CUSTOMER_ID", ""),
        "login_customer_id": os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
    }
