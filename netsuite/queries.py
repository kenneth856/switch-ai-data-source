# All vendors
VENDOR_QUERY = """
SELECT
    id          AS vendor_id,
    companyname AS vendor_name,
    email,
    phone
FROM vendor
"""

# Vendors with country of origin extracted from company name
# Pattern: "Vendor Name - Country - ID"
VENDOR_COUNTRY_QUERY = """
SELECT
    id          AS vendor_id,
    companyname AS vendor_name
FROM vendor
WHERE isinactive = 'F'
ORDER BY companyname
"""

# All active items with weight data
ITEM_QUERY = """
SELECT
    id          AS item_id,
    itemid,
    displayname AS item_name,
    weight,
    weightunit
FROM item
WHERE isinactive = 'F'
"""

# All transactions
TRANSACTION_QUERY = """
SELECT
    id,
    trandate,
    type,
    entity      AS vendor_id,
    foreigntotal AS total_amount,
    currency,
    status
FROM transaction
ORDER BY trandate DESC
"""

# Transaction line details — shows items, quantities, rates per transaction
TRANSACTION_LINE_QUERY = """
SELECT
    tl.transaction,
    tl.linesequencenumber,
    tl.item,
    tl.quantity,
    tl.rate,
    tl.amount,
    tl.memo
FROM transactionLine tl
"""

# Purchase Orders with freight cost
FREIGHT_COST_QUERY = """
SELECT
    t.id,
    t.trandate           AS shipment_date,
    t.entity             AS vendor_id,
    t.foreigntotal       AS total_amount,
    t.status
FROM transaction t
WHERE t.type = 'PurchOrd'
ORDER BY t.trandate DESC
"""

# SLA query — compares promised vs actual delivery
SLA_QUERY = """
SELECT
    t.id                AS shipment_id,
    t.trandate          AS shipment_date,
    t.duedate           AS promised_delivery_date,
    t.shipdate          AS actual_delivery_date,
    t.entity            AS vendor_id,
    t.foreigntotal      AS freight_cost
FROM transaction t
WHERE t.type = 'PurchOrd'
AND t.shipdate IS NOT NULL
AND t.duedate  IS NOT NULL
ORDER BY t.trandate DESC
"""


# Stock on hand at main warehouse (ID=510)
# Excludes virtual/allocated locations: 520, 523, 524
# Returns items with positive stock only
STOCK_ON_HAND_QUERY = """
SELECT
    il.item              AS item_id,
    i.itemid             AS sku,
    i.displayname        AS item_name,
    il.location          AS location_id,
    il.quantityonhand,
    il.quantityavailable
FROM inventoryBalance il
INNER JOIN item i ON i.id = il.item
WHERE il.location = 510
AND il.quantityonhand > 0
AND i.isinactive = 'F'
ORDER BY i.itemid
"""


# Most recent purchase cost per item — from Purchase Order transaction lines
# rate = actual price Switch Supply paid to the supplier on the latest PO
PURCHASE_COST_QUERY = """
SELECT
    i.id            AS item_id,
    i.itemid        AS sku,
    i.displayname   AS item_name,
    tl.rate         AS purchase_cost,
    t.trandate      AS last_po_date,
    t.entity        AS vendor_id
FROM transactionLine tl
INNER JOIN item i        ON i.id  = tl.item
INNER JOIN transaction t ON t.id  = tl.transaction
WHERE t.type      = 'PurchOrd'
AND   tl.rate     > 0
AND   i.isinactive = 'F'
ORDER BY i.itemid, t.trandate DESC
"""


# Sale pricing matrix — all items with their sale price levels (NOT purchase cost)
# pricelevel 1 = Base Price, 2 = Online Price (verify in NetSuite Admin)
PRICING_MATRIX_QUERY = """
SELECT
    p.item          AS item_id,
    i.itemid        AS sku,
    i.displayname   AS item_name,
    p.pricelevel    AS price_level_id,
    p.unitprice     AS unit_price
FROM pricing p
INNER JOIN item i ON i.id = p.item
WHERE i.isinactive = 'F'
AND p.unitprice > 0
ORDER BY i.itemid, p.pricelevel
"""


# Vendor payment terms
# terms field is a numeric ID — map to human-readable label below:
#   7  = Net 30        34 = 30% Deposit, 70% Before Shipment
#   8  = Net 60        35 = 50% Deposit, 50% Before Shipment
#   23 = Net 45        55 = Due On Receipt
#   61 = Net 90
# (IDs confirmed from live NetSuite query, March 2026)
VENDOR_PAYMENT_TERMS_QUERY = """
SELECT
    v.id            AS vendor_id,
    v.companyname   AS vendor_name,
    v.terms         AS payment_terms_id,
    v.currency      AS currency_id,
    v.email,
    v.phone
FROM vendor v
WHERE v.terms IS NOT NULL
ORDER BY v.companyname
"""
