import logging
import os
import time
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

BOX_API_URL   = "https://api.box.com/2.0"
BOX_TOKEN_URL = "https://api.box.com/oauth2/token"

_cached_token: dict = {}


# Returns a valid Box access token, refreshing automatically when expired.
# Falls back to BOX_DEVELOPER_TOKEN if no refresh token is configured.
def _get_access_token() -> str:
    now = time.time()
    if _cached_token.get("token") and now < _cached_token.get("expires_at", 0) - 60:
        return _cached_token["token"]

    client_id     = os.getenv("BOX_CLIENT_ID")
    client_secret = os.getenv("BOX_CLIENT_SECRET")
    refresh_token = os.getenv("BOX_REFRESH_TOKEN")

    if refresh_token and client_id and client_secret:
        r = requests.post(BOX_TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
            "client_id":     client_id,
            "client_secret": client_secret,
        })

        if r.status_code == 200:
            data = r.json()
            _cached_token["token"]      = data["access_token"]
            _cached_token["expires_at"] = now + data.get("expires_in", 3600)

            # Box rotates refresh tokens — save the new one back to .env
            new_refresh = data.get("refresh_token")
            if new_refresh and new_refresh != refresh_token:
                _save_refresh_token(new_refresh)

            return _cached_token["token"]

        raise Exception(f"Box token refresh failed {r.status_code}: {r.text}")

    # Fallback: developer token (manual, expires every 60 min)
    dev_token = os.getenv("BOX_DEVELOPER_TOKEN")
    if dev_token:
        _cached_token["token"]      = dev_token
        _cached_token["expires_at"] = now + 3600
        return dev_token

    raise Exception(
        "Box not configured. Run:  python3 box/get_token.py\n"
        "This sets up BOX_REFRESH_TOKEN in .env for permanent access."
    )


# Persist the latest refresh token to .env
def _save_refresh_token(new_token: str) -> None:
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        with open(env_path, "w") as f:
            replaced = False
            for line in lines:
                if line.startswith("BOX_REFRESH_TOKEN="):
                    f.write(f"BOX_REFRESH_TOKEN={new_token}\n")
                    replaced = True
                else:
                    f.write(line)
            if not replaced:
                f.write(f"\nBOX_REFRESH_TOKEN={new_token}\n")
    except Exception:
        pass


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "Content-Type":  "application/json",
    }


def get_folder_contents(folder_id: str) -> list:
    url = f"{BOX_API_URL}/folders/{folder_id}/items"
    params = {"limit": 1000, "fields": "id,name,type,size,modified_at"}

    r = requests.get(url, headers=get_headers(), params=params)

    if r.status_code == 200:
        return r.json().get("entries", [])

    raise Exception(f"Box API error {r.status_code}: {r.text}")


# Get all ingredient folders from the root ingredients folder.
# Returns a list of folders — one per ingredient.
def get_ingredient_folders() -> list:
    root_folder_id = os.getenv("BOX_INGREDIENTS_FOLDER_ID")
    if not root_folder_id:
        raise Exception(
            "BOX_INGREDIENTS_FOLDER_ID not set in .env"
        )


    items = get_folder_contents(root_folder_id)
    folders = [i for i in items if i["type"] == "folder"]
    logger.debug("Found %d ingredient folders", len(folders))
    return folders


# Get all files inside an ingredient folder (spec sheets, QA certs, COAs).
def get_ingredient_files(ingredient_folder_id: str) -> list:
    items = get_folder_contents(ingredient_folder_id)
    files = [i for i in items if i["type"] == "file"]
    return files


# Download a file from Box by file_id and save it to save_path.
def download_file(file_id: str, save_path: str) -> str:
    url = f"{BOX_API_URL}/files/{file_id}/content"
    r = requests.get(url, headers=get_headers(), stream=True)

    if r.status_code == 200:
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return save_path

    raise Exception(f"Box download error {r.status_code}: {r.text}")


# Maps the full Box folder structure for ingredients.
# Returns { ingredient_name: { folder_id, files: [...] } }
def map_folder_structure() -> dict:
    mapping = {}
    folders = get_ingredient_folders()

    for folder in folders:
        name = folder["name"]
        fid  = folder["id"]
        files = get_ingredient_files(fid)

        mapping[name] = {
            "folder_id": fid,
            "files": [
                {
                    "file_id":   f["id"],
                    "file_name": f["name"],
                    "size_kb":   round(f.get("size", 0) / 1024, 1),
                }
                for f in files
            ]
        }
        logger.debug("  %s: %d files", name, len(files))

    return mapping


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logger.info("=== Box API Folder Mapping ===")
    logger.info("NOTE: Requires BOX_CLIENT_ID, BOX_CLIENT_SECRET, BOX_ENTERPRISE_ID, BOX_INGREDIENTS_FOLDER_ID in .env")

    try:
        mapping = map_folder_structure()
        logger.info("=== Mapping Result ===")
        for ingredient, data in mapping.items():
            logger.info("%s (folder: %s)", ingredient, data["folder_id"])
            for f in data["files"]:
                logger.info("  - %s (%s KB)", f["file_name"], f["size_kb"])
    except Exception as e:
        logger.error("Error: %s", e)
