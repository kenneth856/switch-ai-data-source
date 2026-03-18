import time
import hmac
import hashlib
import base64
import random
import urllib.parse
import requests
from config import (
    NETSUITE_ACCOUNT_ID,
    NETSUITE_CONSUMER_KEY,
    NETSUITE_CONSUMER_SECRET,
    NETSUITE_TOKEN_KEY,
    NETSUITE_TOKEN_SECRET,
)


# Builds OAuth1 Authorization header using HMAC-SHA256.
# This is the working method confirmed against NetSuite.
def _build_oauth_header(method: str, url: str) -> str:
    consumer_key    = NETSUITE_CONSUMER_KEY
    consumer_secret = NETSUITE_CONSUMER_SECRET
    token_key       = NETSUITE_TOKEN_KEY
    token_secret    = NETSUITE_TOKEN_SECRET
    account_id      = NETSUITE_ACCOUNT_ID

    params = {
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            str(random.randint(100000000, 999999999)),
        "oauth_signature_method": "HMAC-SHA256",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            token_key,
        "oauth_version":          "1.0",
    }

    sorted_params = "&".join(
        f"{k}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(params.items())
    )
    base_string = (
        f"{method}&"
        f"{urllib.parse.quote(url, safe='')}&"
        f"{urllib.parse.quote(sorted_params, safe='')}"
    )
    signing_key = (
        f"{urllib.parse.quote(consumer_secret, safe='')}&"
        f"{urllib.parse.quote(token_secret, safe='')}"
    )
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).digest()
    ).decode()

    params["oauth_signature"] = signature
    parts = ", ".join(
        f'{k}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(params.items())
    )
    return f'OAuth realm="{account_id}", {parts}'


# Runs a SuiteQL query against NetSuite and returns results as a list.
def run_suiteql(query: str) -> list:
    url = f"https://{NETSUITE_ACCOUNT_ID}.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"

    response = requests.post(
        url,
        json={"q": query},
        headers={
            "Authorization": _build_oauth_header("POST", url),
            "Content-Type":  "application/json",
            "Prefer":        "transient",
        }
    )

    if response.status_code == 200:
        return response.json().get("items", [])

    # Return error details for debugging
    error = response.json().get("o:errorDetails", [{}])[0].get("detail", "Unknown error")
    raise Exception(f"NetSuite API error {response.status_code}: {error}")
