import re
import pycountry


def extract_country(vendor_name: str) -> str:
    # Vendor name pattern: "Vendor Name - Country - ID"
    # e.g. "Agrizo - India - 0002" -> "India"
    m = re.search(r"-\s*([A-Za-z][A-Za-z\s]+?)\s*(?:-\s*[\w]+)?\s*$", vendor_name)
    if not m:
        return ""
    candidate = m.group(1).strip()
    try:
        match = pycountry.countries.lookup(candidate)
        return match.name
    except LookupError:
        return ""


def get_vendor_countries(vendors: list) -> list:
    # Takes list of {vendor_id, vendor_name} dicts, returns with country added.
    result = []
    for v in vendors:
        country = extract_country(v.get("vendor_name", ""))
        result.append({
            "vendor_id":   v["vendor_id"],
            "vendor_name": v["vendor_name"],
            "country":     country,
        })
    return result
