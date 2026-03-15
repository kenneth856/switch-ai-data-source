"""
Box OAuth2 Token Setup — run this ONCE to get a permanent refresh token.

Usage:
    python3 box/get_token.py

This script starts a local web server on port 8088, opens the Box
authorization page, catches the redirect automatically, exchanges the
code for tokens, and saves BOX_REFRESH_TOKEN to .env.

After this runs once, box/client.py auto-refreshes forever.
"""

import logging
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

CLIENT_ID     = os.getenv("BOX_CLIENT_ID")
CLIENT_SECRET = os.getenv("BOX_CLIENT_SECRET")
REDIRECT_URI  = "http://localhost:8088/callback"
PORT          = 8088

if not CLIENT_ID or not CLIENT_SECRET:
    logger.error("BOX_CLIENT_ID and BOX_CLIENT_SECRET must be set in .env")
    sys.exit(1)

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            if "code" in params:
                auth_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                    <html><body style='font-family:sans-serif;padding:40px'>
                    <h2 style='color:green'>Authorization successful!</h2>
                    <p>You can close this tab and return to the terminal.</p>
                    </body></html>
                """)
            else:
                error = params.get("error", ["unknown"])[0]
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs):
        pass  # Suppress request logs


def save_refresh_token(refresh_token: str):
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    with open(env_path, "r") as f:
        lines = f.readlines()
    with open(env_path, "w") as f:
        replaced = False
        for line in lines:
            if line.startswith("BOX_REFRESH_TOKEN="):
                f.write(f"BOX_REFRESH_TOKEN={refresh_token}\n")
                replaced = True
            else:
                f.write(line)
        if not replaced:
            f.write(f"\nBOX_REFRESH_TOKEN={refresh_token}\n")


def main():
    auth_url = (
        f"https://account.box.com/api/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )

    logger.info("=" * 60)
    logger.info("Box OAuth2 Token Setup")
    logger.info("=" * 60)
    logger.info("Starting local server on port %d...", PORT)

    # Start HTTP server in background thread
    server = HTTPServer(("localhost", PORT), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.daemon = True
    thread.start()

    logger.info("Opening Box authorization page in your browser...")
    logger.info("If browser does not open, visit:\n%s", auth_url)
    webbrowser.open(auth_url)

    logger.info("Waiting for authorization...")
    thread.join(timeout=120)

    if not auth_code:
        logger.error("No authorization code received within 2 minutes.")
        logger.error("Make sure http://localhost:8080 is added as redirect URI in Box Developer Console.")
        sys.exit(1)

    logger.info("Authorization code received. Exchanging for tokens...")

    r = requests.post("https://api.box.com/oauth2/token", data={
        "grant_type":    "authorization_code",
        "code":          auth_code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
    })

    if r.status_code != 200:
        logger.error("Token exchange failed %d: %s", r.status_code, r.text)
        sys.exit(1)

    data = r.json()
    refresh_token = data["refresh_token"]

    save_refresh_token(refresh_token)

    logger.info("=" * 60)
    logger.info("SUCCESS! BOX_REFRESH_TOKEN saved to .env")
    logger.info("box/client.py will now auto-refresh the token forever.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
