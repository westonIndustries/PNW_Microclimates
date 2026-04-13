# ZIP Code Source Files (optional)

Drop pre-downloaded ZIP code boundary files here before running
`python scripts/generate_region1_boundary.py`. Both are optional —
the script falls back to Census TIGER/Line if neither is present.

---

## rlis_zipcodes.geojson

Oregon Metro RLIS ZIP code boundaries. Tax-lot accurate geometry for the
Portland metro area — more precise than Census data for the core service region.

**How to get it**:
1. Go to https://rlisdiscovery.oregonmetro.gov
2. Search for "ZIP Codes"
3. Download as GeoJSON
4. Save here as `rlis_zipcodes.geojson`

**Coverage**: Portland metro area (Multnomah, Washington, Clackamas, Clark counties)

---

## opendata_zipcodes_orwa.geojson

OpenDataSoft US ZIP Code Boundaries filtered to Oregon and Washington.

**How to get it**:
1. Go to https://public.opendatasoft.com/explore/dataset/us-zip-code-territory/
2. Filter by `state_code = OR` and `state_code = WA`
3. Export as GeoJSON
4. Save here as `opendata_zipcodes_orwa.geojson`

**Coverage**: All OR + WA ZIP codes
