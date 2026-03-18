"""
Monday.com API Connector
Sprint 2 — Ingredient Intelligence Knowledge Base

Monday.com stores:
- Ingredient list (name, category, supplier, specs)
- Supplier performance data
- Certifications and compliance info

Auth: API Token (v2)
Get token from: monday.com → Profile picture → Admin → API → Copy token

Requires in .env:
- MONDAY_API_KEY   ← your personal API token from monday.com
"""

import requests
from config import MONDAY_API_KEY

MONDAY_API_URL = "https://api.monday.com/v2"


def _headers() -> dict:
    if not MONDAY_API_KEY:
        raise RuntimeError(
            "MONDAY_API_KEY not set in .env\n"
            "Get it from: monday.com → Profile → Admin → API → Copy token"
        )
    return {
        "Authorization": MONDAY_API_KEY,
        "Content-Type":  "application/json",
        "API-Version":   "2023-10",
    }


# Run a GraphQL query against the Monday.com API.
def _query(gql: str) -> dict:
    r = requests.post(
        MONDAY_API_URL,
        headers=_headers(),
        json={"query": gql},
        timeout=30,
    )
    if r.status_code != 200:
        raise Exception(f"Monday.com API error {r.status_code}: {r.text[:300]}")
    data = r.json()
    if "errors" in data:
        raise Exception(f"Monday.com GraphQL error: {data['errors']}")
    return data.get("data", {})


# List all boards the API token has access to.
# Use this to find the board IDs for ingredients, suppliers, etc.
def get_boards() -> list:
    data = _query("""
    {
      boards(limit: 50) {
        id
        name
        description
        state
        items_count
      }
    }
    """)
    return data.get("boards", [])


# Get all items (rows) from a Monday.com board.
# board_id: The Monday.com board ID (get from get_boards())
# limit:    Max items to fetch (default 500)
# Returns list of items with all column values.
def get_board_items(board_id: str, limit: int = 500) -> list:
    data = _query(f"""
    {{
      boards(ids: [{board_id}]) {{
        name
        items_page(limit: {limit}) {{
          items {{
            id
            name
            column_values {{
              id
              text
              value
              column {{
                title
                type
              }}
            }}
          }}
        }}
      }}
    }}
    """)
    boards = data.get("boards", [])
    if not boards:
        return []
    items = boards[0].get("items_page", {}).get("items", [])
    return items


# Parse a Monday.com board into a clean ingredient list.
# Returns list of dicts — one per ingredient with all fields flattened.
def get_ingredient_list(board_id: str) -> list:
    items = get_board_items(board_id)
    ingredients = []

    for item in items:
        ingredient = {"name": item["name"], "monday_id": item["id"]}
        for col in item.get("column_values", []):
            title = col["column"]["title"].lower().replace(" ", "_")
            ingredient[title] = col.get("text") or ""
        ingredients.append(ingredient)

    return ingredients


# Search for a specific ingredient by name in a Monday.com board (case-insensitive).
# Returns ingredient dict if found, None if not found.
def search_ingredient(board_id: str, name: str) -> dict | None:
    ingredients = get_ingredient_list(board_id)
    name_lower = name.lower()
    for ing in ingredients:
        if name_lower in ing["name"].lower():
            return ing
    return None


# Get all column definitions for a board.
# Use this to understand what fields are available.
def get_board_columns(board_id: str) -> list:
    data = _query(f"""
    {{
      boards(ids: [{board_id}]) {{
        name
        columns {{
          id
          title
          type
          description
        }}
      }}
    }}
    """)
    boards = data.get("boards", [])
    if not boards:
        return []
    return boards[0].get("columns", [])
