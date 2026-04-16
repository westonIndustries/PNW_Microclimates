# QA Report — Microclimate Pipeline

**Generated**: 2026-04-15T21:23:47.784890
**Pipeline Version**: 1.0.0

## Summary

### Cell-Level Statistics

- **Total Cells**: 2
- **Effective HDD Mean**: 4850.0
- **Effective HDD Median**: 4850.0
- **Effective HDD Range**: 4500.0 — 5200.0
- **Effective HDD Std Dev**: 495.0
- **Effective HDD IQR**: 4675.0 — 5025.0

### ZIP-Level Statistics

- **Total ZIP Codes**: 2
- **Effective HDD Mean**: 4850.0
- **Effective HDD Median**: 4850.0
- **Effective HDD Range**: 4500.0 — 5200.0
- **Effective HDD Std Dev**: 495.0
- **Effective HDD IQR**: 4675.0 — 5025.0

### Correction Statistics (Cell-Level)

**Hdd Terrain Mult**:
- Mean: 1.075
- Range: 1.050 — 1.100
- Std Dev: 0.035

**Hdd Elev Addition**:
- Mean: 150.000
- Range: 100.000 — 200.000
- Std Dev: 70.711

**Hdd Uhi Reduction**:
- Mean: 35.000
- Range: 20.000 — 50.000
- Std Dev: 21.213

## QA Check Results

- **Passed**: 5/6
- **Errors**: 0
- **Warnings**: 1

### Aggregate HDD Consistency

**Status**: ✓ PASS
**Severity**: INFO
**Issues**: 0

### Effective HDD Range

**Status**: ✓ PASS
**Severity**: INFO
**Issues**: 0

### Directional Sanity

**Status**: ✗ FAIL
**Severity**: WARNING
**Issues**: 1

**Details**:

- Windward cells have lower HDD than leeward cells. Windward=4500.0, Leeward=5200.0. Expected: Windward > Leeward (wind exposure)

### Cell Reliability

**Status**: ✓ PASS
**Severity**: INFO
**Issues**: 0

### Hard Failure Check

**Status**: ✓ PASS
**Severity**: INFO
**Issues**: 0

### Billing Comparison

**Status**: ✓ PASS
**Severity**: INFO
**Issues**: 0

**Details**:

- Skipped: no billing data provided
