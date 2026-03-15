"""
Centralised configuration — single source of truth for all env vars.
Every other module imports from here instead of calling os.getenv() directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key} — check your .env file")
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# NetSuite
NETSUITE_ACCOUNT_ID      = _require("NETSUITE_ACCOUNT_ID")
NETSUITE_CONSUMER_KEY    = _require("NETSUITE_CONSUMER_KEY")
NETSUITE_CONSUMER_SECRET = _require("NETSUITE_CONSUMER_SECRET")
NETSUITE_TOKEN_KEY       = _require("NETSUITE_TOKEN_KEY")
NETSUITE_TOKEN_SECRET    = _require("NETSUITE_TOKEN_SECRET")

# Box
BOX_CLIENT_ID        = _optional("BOX_CLIENT_ID")
BOX_CLIENT_SECRET    = _optional("BOX_CLIENT_SECRET")
BOX_DEVELOPER_TOKEN  = _optional("BOX_DEVELOPER_TOKEN")
BOX_REFRESH_TOKEN    = _optional("BOX_REFRESH_TOKEN")

# Supabase
SUPABASE_URL = _optional("SUPABASE_URL")
SUPABASE_KEY = _optional("SUPABASE_KEY")

# Monday.com
MONDAY_API_KEY = _optional("MONDAY_API_KEY")

# Paths
DATA_RAW_DIR       = "data/raw"
DATA_PROCESSED_DIR = "data/processed"
MODEL_PATH         = "model/model.pkl"
