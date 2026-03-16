import logging
import requests
from box.client import get_headers, get_folder_contents
from db.client import get_client

logger = logging.getLogger(__name__)

BOX_API_URL = "https://api.box.com/2.0"


# Determine file type based on file name
def _file_type(name: str) -> str:
    name_lower = name.lower()
    if "coa" in name_lower:
        return "COA"
    if "spec" in name_lower or "qms" in name_lower:
        return "SPEC"
    if "msds" in name_lower or "sds" in name_lower:
        return "MSDS"
    if "pif" in name_lower:
        return "PIF"
    return "OTHER"


# Get all files recursively inside a folder (one level deep)
def _get_files_in_folder(folder_id: str) -> list:
    items = get_folder_contents(folder_id)
    files = []
    for item in items:
        if item["type"] == "file":
            files.append(item)
        elif item["type"] == "folder" and item["name"] not in ("Archive", "Photos"):
            # Go one level deeper for Product Spec and PIF subfolders
            sub_items = get_folder_contents(item["id"])
            files += [i for i in sub_items if i["type"] == "file"]
    return files



# Sync all ingredient spec sheets from Box to Supabase ingredient_specs table
def sync_specs_to_supabase() -> dict:
    from os import getenv
    root_folder_id = getenv("BOX_INGREDIENTS_FOLDER_ID")
    if not root_folder_id:
        raise Exception("BOX_INGREDIENTS_FOLDER_ID not set in .env")

    db = get_client()

    # Clear existing records
    db.table("ingredient_specs").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    logger.info("Cleared existing ingredient_specs records")

    # Get all ingredient folders
    items = get_folder_contents(root_folder_id)
    folders = [i for i in items if i["type"] == "folder" and not i["name"].startswith(("Archive", "Photos", "Needs"))]

    total_files = 0
    records = []

    for folder in folders:
        ingredient_name = folder["name"]
        folder_id = folder["id"]

        files = _get_files_in_folder(folder_id)

        for f in files:
            records.append({
                "ingredient_name": ingredient_name,
                "folder_id":       folder_id,
                "file_id":         f["id"],
                "file_name":       f["name"],
                "file_type":       _file_type(f["name"]),
                "size_kb":         round(f.get("size", 0) / 1024, 1),
                "updated_at":      f.get("modified_at", ""),
                "download_url":    "",
            })
            total_files += 1

        logger.debug("  %s: %d files", ingredient_name, len(files))

    # Insert in batches of 100
    for i in range(0, len(records), 100):
        db.table("ingredient_specs").insert(records[i:i+100]).execute()

    logger.info("Synced %d files from %d ingredient folders", total_files, len(folders))
    return {"folders": len(folders), "files": total_files}


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    result = sync_specs_to_supabase()
    print(f"Done: {result}")
