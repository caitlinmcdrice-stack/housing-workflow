import re
import pandas as pd

# ── Street type rules ─────────────────────────────────────────────────────────
STREET_TYPES = {
    # → st
    "street": "st", "str": "st", "st": "st",
    # → ave
    "avenue": "ave", "av": "ave", "ave": "ave",
    # → ct
    "court": "ct", "crt": "ct", "ct": "ct",
    # → ln
    "lane": "ln", "ln": "ln",
    # → rd
    "road": "rd", "rd": "rd",
    # → pkwy
    "parkway": "pkwy", "parkwy": "pkwy", "pky": "pkwy", "pkwy": "pkwy",
    # → dr
    "drive": "dr", "drv": "dr", "dr": "dr",
    # → way
    "way": "way", "wy": "way",
    # → ter
    "terrace": "ter", "terr": "ter", "ter": "ter",
    # → hwy
    "highway": "hwy", "hiway": "hwy", "hiwy": "hwy", "hwy": "hwy",
    # → blvd
    "boulevard": "blvd", "boul": "blvd", "blvd": "blvd",
    # → cir
    "circle": "cir", "crcl": "cir", "cir": "cir",
    # → pl
    "place": "pl", "pl": "pl",
    # → trl
    "trail": "trl", "trl": "trl",
    # → pike
    "pike": "pike",
}

# ── Direction rules ───────────────────────────────────────────────────────────
# Single directions abbreviate
DIRECTIONS = {
    "north": "n", "n": "n",
    "south": "s", "s": "s",
    "east":  "e", "e": "e",
    "west":  "w", "w": "w",
}

# These are proper names — never abbreviate
DIRECTION_PROPER_NAMES = {
    "northwest", "northeast", "southwest", "southeast"
}

# ── Unit patterns to strip ────────────────────────────────────────────────────
UNIT_PATTERNS = [
    r'\bapt\.?\s*#?\s*\w*',
    r'\bunit\.?\s*#?\s*\w*',
    r'\bsuite\.?\s*#?\s*\w*',
    r'\bste\.?\s*#?\s*\w*',
    r'\bfloor\.?\s*\w*',
    r'\bfl\.?\s*\w*',
    r'\broom\.?\s*\w*',
    r'\brm\.?\s*\w*',
    r'#\s*\w+',
    r'\bno\.?\s*\d+',
]

def clean_address(raw_address: str) -> str:
    if not raw_address or pd.isna(raw_address):
        return ""

    addr = str(raw_address).lower().strip()

    # Strip unit/apt references
    for pattern in UNIT_PATTERNS:
        addr = re.sub(pattern, "", addr, flags=re.IGNORECASE)

    # Fix "e west" → "east west" before anything else
    addr = re.sub(r'\be\s+west\b', 'east west', addr)

    # Clean up extra spaces before word processing
    addr = re.sub(r'\s+', ' ', addr).strip()

    # Process word by word
    words = addr.split()
    cleaned_words = []
    i = 0
    while i < len(words):
        word = words[i].strip(".,;:#")

        # Check if this word + next word is "east west" — protect it
        if (word == "east" and
                i + 1 < len(words) and
                words[i + 1].strip(".,;:#") == "west"):
            cleaned_words.append("east")
            cleaned_words.append("west")
            i += 2
            continue

        # Proper direction names — never abbreviate
        if word in DIRECTION_PROPER_NAMES:
            cleaned_words.append(word)
            i += 1
            continue

        # Single direction abbreviation
        if word in DIRECTIONS:
            cleaned_words.append(DIRECTIONS[word])
            i += 1
            continue

        # Street type standardization
        if word in STREET_TYPES:
            cleaned_words.append(STREET_TYPES[word])
            i += 1
            continue

        # Everything else stays as-is
        cleaned_words.append(word)
        i += 1

    addr = " ".join(cleaned_words)
    addr = re.sub(r'\s+', ' ', addr).strip().strip(",").strip()

    return addr


def build_full_address(street: str, city: str, state: str, zipcode: str) -> str:
    street  = clean_address(street)
    city    = str(city).lower().strip()  if city    else ""
    state   = str(state).lower().strip() if state   else ""
    zipcode = str(zipcode).strip()[:5]   if zipcode else ""

    parts = [p for p in [street, city, state, zipcode] if p]
    return ", ".join(parts)


# ── Tests ─────────────────────────────────────────────────────────────────────
test_cases = [
    # street                            city              st    zip      expected
    ("5033 57TH AVENUE APT 2B",        "BLADENSBURG",   "MD", "20710", "5033 57th ave, bladensburg, md, 20710"),
    ("1029 QUEBEC TERRACE",            "SILVER SPRING", "MD", "20903", "1029 quebec ter, silver spring, md, 20903"),
    ("800 N HOWARD STREET #301",       "BALTIMORE",     "MD", "21201", "800 n howard st, baltimore, md, 21201"),
    ("123 MAIN ROAD UNIT 4A",          "ROCKVILLE",     "MD", "20850", "123 main rd, rockville, md, 20850"),
    ("456 OAK LANE APT. 12",           "GAITHERSBURG",  "MD", "20877", "456 oak ln, gaithersburg, md, 20877"),
    ("789 RIVER PKWY Suite 100",       "BETHESDA",      "MD", "20814", "789 river pkwy, bethesda, md, 20814"),
    ("321 ELM DRIVE FL 3",             "ANNAPOLIS",     "MD", "21401", "321 elm dr, annapolis, md, 21401"),
    ("UNIVERSITY BLVD E",              "SILVER SPRING", "MD", "20902", "university blvd e, silver spring, md, 20902"),
    ("EAST WEST HIGHWAY",              "SILVER SPRING", "MD", "20910", "east west hwy, silver spring, md, 20910"),
    ("E WEST HIGHWAY",                 "SILVER SPRING", "MD", "20910", "east west hwy, silver spring, md, 20910"),
    ("E WEST HWY",                     "SILVER SPRING", "MD", "20910", "east west hwy, silver spring, md, 20910"),
    ("1500 NORTHWEST BRANCH TRAIL",    "HYATTSVILLE",   "MD", "20782", "1500 northwest branch trl, hyattsville, md, 20782"),
    ("400 NORTHEAST BLVD",             "TAKOMA PARK",   "MD", "20912", "400 northeast blvd, takoma park, md, 20912"),
    ("200 NORTH MAIN STREET",          "ROCKVILLE",     "MD", "20850", "200 n main st, rockville, md, 20850"),
    ("100 WEST CIRCLE DR",             "COLLEGE PARK",  "MD", "20740", "100 w cir dr, college park, md, 20740"),
    ("50 SOUTH COURT",                 "ANNAPOLIS",     "MD", "21401", "50 s ct, annapolis, md, 21401"),
    ("3000 PENNSYLVANIA AVE NW",       "WASHINGTON",    "DC", "20037", "3000 pennsylvania ave nw, washington, dc, 20037"),
]

print(f"\n{'INPUT ADDRESS':<45} {'OUTPUT':<50} {'PASS?'}")
print("-" * 120)

all_passed = True
for street, city, state, zip_, expected in test_cases:
    result = build_full_address(street, city, state, zip_)
    if result == expected:
        status = "✓"
    else:
        status = f"✗  expected: {expected}"
        all_passed = False
    print(f"{(street + ', ' + city):<45} {result:<50} {status}")

print()
if all_passed:
    print("All tests passed! Address standardization is ready.")
else:
    print("Some tests failed — check the ✗ rows above.")