import requests
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from clean_addresses import build_full_address
import os

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_NAME = "at-risk-buildings-TEST"
SERVICE_ACCOUNT_FILE = "service_account.json"
RUN_ID = datetime.now().strftime("run_%Y%m%d_%H%M")
RUN_DATE = datetime.now().strftime("%Y-%m-%d %H:%M")

# ── Column name mapping from form to dataset ──────────────────────────────────
FIELD_MAP = {
    "community name": "communityname",
    "street address": "streetaddress",
    "street_address": "streetaddress",
    "streetaddress": "streetaddress",
    "city": "city",
    "zip code": "zipcode",
    "zipcode": "zipcode",
    "compliance status": "compliantind",
    "compliantind": "compliantind",
    "unit count": "unitcount",
    "unitcount": "unitcount",
}

# ── Connect to Google Sheets ──────────────────────────────────────────────────
print("Connecting to Google Sheets...")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sh = gc.open(SHEET_NAME)

# ── Pull Montgomery County Troubled Properties ────────────────────────────────
print("Pulling Montgomery County data...")
URL = "https://data.montgomerycountymd.gov/resource/bw2r-araf.json"
params = {"$limit": 5000, "$offset": 0}
response = requests.get(URL, params=params)
response.raise_for_status()
df = pd.DataFrame(response.json())
print(f"  Got {len(df)} records.")

# ── Standardize addresses ─────────────────────────────────────────────────────
print("Standardizing addresses...")
df["clean_address"] = df.apply(
    lambda row: build_full_address(
        str(row.get("streetaddress", "")),
        str(row.get("city", "")),
        "md",
        str(row.get("zipcode", ""))
    ), axis=1
)

# ── Build output dataframe ────────────────────────────────────────────────────
output_df = df[[
    "clean_address",
    "streetaddress",
    "city",
    "zipcode",
    "communityname",
    "compliantind",
    "unitcount",
]].copy()
output_df = output_df.drop_duplicates(subset=["clean_address"], keep="first")
print(f"  After deduplication: {len(output_df)} records.")

output_df["source"] = "montgomery_troubled"
output_df["run_id"] = RUN_ID
output_df["run_date"] = RUN_DATE

# ── Read corrections from Form Responses tab ──────────────────────────────────
print("Reading corrections...")
try:
    form_ws = sh.worksheet("Form_Responses")
except gspread.WorksheetNotFound:
    form_ws = sh.worksheet("Form Responses 1")

form_data = form_ws.get_all_records()
corrections_applied = []

for i, row in enumerate(form_data):

    property_addr = str(list(row.values())[1]).strip().lower()
    field_name    = str(row.get("Which fields needs to be corrected?", "")).strip().lower()
    new_value = str(row.get("What should the correct value be? ", "")).strip()
    if not new_value:
        new_value = str(row.get("What should the correct value be?", "")).strip()
    source = str(list(row.values())[4]).strip()
    submitter     = str(row.get("Email Address", "")).strip()
    timestamp     = str(row.get("Timestamp", "")).strip()

    # Find matching property in output
    match = output_df["clean_address"].str.lower() == property_addr
    if not match.any():
        print(f"  No match found for: {property_addr}")
        continue

    # Get the dataset column name
    dataset_field = FIELD_MAP.get(field_name, field_name)
    if dataset_field not in output_df.columns:
        print(f"  Field not found: {field_name}")
        continue

    # Get old value
    old_value = output_df.loc[match, dataset_field].values[0]

    # Run street address through standardization before applying
    if dataset_field == "streetaddress":
        from clean_addresses import clean_address
        new_value = clean_address(new_value)

    # Apply correction
    output_df.loc[match, dataset_field] = new_value
    print(f"  Applied: {property_addr} | {field_name} | {old_value} → {new_value}")

    # Mark as applied in form sheet
    sheet_row = i + 2  # +2 for header row and 1-based index
    form_ws.update(range_name=f"G{sheet_row}", values=[[True]])
    form_ws.update(range_name=f"H{sheet_row}", values=[[RUN_DATE]])
    form_ws.update(range_name=f"I{sheet_row}", values=[[RUN_ID]])

    corrections_applied.append({
        "run_id": RUN_ID,
        "run_date": RUN_DATE,
        "property_address": property_addr,
        "field_corrected": field_name,
        "old_value": str(old_value),
        "new_value": new_value,
        "submitted_by": submitter,
        "submitted_at": timestamp,
        "source": source,
        "change_type": "human_correction"
    })

# ── Write to Change Log tab ───────────────────────────────────────────────────
if corrections_applied:
    print(f"Writing {len(corrections_applied)} corrections to Change Log...")
    change_ws = sh.worksheet("Change Log")
    change_headers = [
        "run_id", "run_date", "property_address", "field_corrected",
        "old_value", "new_value", "submitted_by", "submitted_at",
        "source", "change_type"
    ]
    existing = change_ws.get_all_values()

    # Add headers if sheet is empty
    if not existing:
        change_ws.append_row(change_headers)

    # Write each correction as its own row
    for c in corrections_applied:
        row_data = [
            str(c.get("run_id", "")),
            str(c.get("run_date", "")),
            str(c.get("property_address", "")),
            str(c.get("field_corrected", "")),
            str(c.get("old_value", "")),
            str(c.get("new_value", "")),
            str(c.get("submitted_by", "")),
            str(c.get("submitted_at", "")),
            str(c.get("source", "")),
            str(c.get("change_type", "")),
        ]
        change_ws.append_row(row_data)

# ── Write to Published Output tab ─────────────────────────────────────────────
print("Writing to Published Output tab...")
try:
    output_ws = sh.worksheet("Published Output")
except gspread.WorksheetNotFound:
    output_ws = sh.add_worksheet(title="Published Output", rows=5000, cols=20)

output_ws.clear()
headers = output_df.columns.tolist()
rows = output_df.fillna("").values.tolist()
output_ws.update([headers] + rows)
print(f"  Written {len(rows)} rows to Published Output tab.")

# ── Save local snapshot ───────────────────────────────────────────────────────
os.makedirs("snapshots", exist_ok=True)
snapshot_path = f"snapshots/snapshot_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
output_df.to_csv(snapshot_path, index=False)
print(f"  Snapshot saved to {snapshot_path}")

print(f"\nDone. Run ID: {RUN_ID}")
print(f"Corrections applied: {len(corrections_applied)}")