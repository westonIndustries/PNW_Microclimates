# Error Propagation and Uncertainty Bounds for Effective HDD

## Overview

Task 11.5 implements error propagation and uncertainty quantification for the effective HDD calculations in the Regional Microclimate Modeling Engine. This enhancement adds lower and upper bounds (`effective_hdd_low`, `effective_hdd_high`) to each cell's effective HDD estimate, quantifying the uncertainty in the final microclimate values.

## Motivation

The effective HDD formula combines multiple correction components, each with its own measurement or model error:

```
effective_hdd = base_hdd × terrain_mult + elev_addition − uhi_reduction − traffic_reduction
```

Each component has uncertainty:
- **Base HDD**: PRISM spatial interpolation and station calibration error (~±200 HDD)
- **Terrain multiplier**: TPI-based classification boundary effects (~±0.05)
- **Elevation addition**: Lapse rate atmospheric variability and DEM vertical accuracy (~±50 HDD)
- **UHI reduction**: Landsat LST calibration and surface heterogeneity (~±100 HDD)
- **Traffic reduction**: AADT estimation and traffic pattern variability (~±75 HDD)

By propagating these uncertainties through the formula, we can quantify the total uncertainty in the final effective HDD value, providing users with a confidence interval around each estimate.

## Approach

### Error Propagation Formula

The implementation uses standard error propagation techniques:

1. **For multiplicative terms** (base_hdd × terrain_mult):
   ```
   σ_product = sqrt((σ_base × terrain_mult)² + (base_hdd × σ_terrain)²)
   ```

2. **For additive/subtractive terms** (elev_addition, uhi_reduction, traffic_reduction):
   ```
   σ_sum = sqrt(σ_elev² + σ_uhi² + σ_traffic²)
   ```

3. **Combined uncertainty** (root-sum-of-squares):
   ```
   σ_total = sqrt(σ_product² + σ_sum²)
   ```

4. **Bounds** (±1 standard deviation, ~68% confidence interval):
   ```
   effective_hdd_low = effective_hdd - σ_total
   effective_hdd_high = effective_hdd + σ_total
   ```

### Uncertainty Estimates

Default uncertainty values (in °F-days for HDD) are defined in `uncertainty_quantification.py`:

| Component | Default σ | Rationale |
|-----------|-----------|-----------|
| Base HDD | 200 HDD | PRISM interpolation error and station calibration |
| Terrain multiplier | 0.05 | TPI classification boundary effects |
| Elevation addition | 50 HDD | Lapse rate variability and DEM vertical accuracy (±1-2 m) |
| UHI reduction | 100 HDD | Landsat LST calibration and surface heterogeneity |
| Traffic reduction | 75 HDD | AADT estimation error and traffic pattern variability |

These values can be customized by passing different `sigma` parameters to the functions.

## Implementation

### Core Functions

#### `compute_effective_hdd_bounds()`

Computes lower and upper bounds on effective HDD using error propagation.

```python
from src.processors.uncertainty_quantification import compute_effective_hdd_bounds

# Scalar inputs
low, high = compute_effective_hdd_bounds(
    base_hdd=5000.0,
    terrain_mult=1.05,
    elev_addition=200.0,
    uhi_reduction=150.0,
    traffic_reduction=50.0
)
# Returns: (4700.0, 5300.0) approximately

# Array inputs
low, high = compute_effective_hdd_bounds(
    base_hdd=np.array([4000, 5000, 6000]),
    terrain_mult=np.array([0.95, 1.05, 1.15]),
    elev_addition=np.array([100, 200, 300]),
    uhi_reduction=np.array([100, 150, 200]),
    traffic_reduction=np.array([25, 50, 75])
)
# Returns: arrays of bounds for each element
```

#### `compute_effective_hdd_bounds_per_cell()`

Applies uncertainty quantification to a DataFrame of cells.

```python
from src.processors.uncertainty_quantification import compute_effective_hdd_bounds_per_cell

# Input DataFrame with one row per cell
cell_df = pd.DataFrame({
    'prism_annual_hdd': [5000.0, 5100.0],
    'hdd_terrain_mult': [1.05, 1.10],
    'hdd_elev_addition': [200.0, 250.0],
    'hdd_uhi_reduction': [150.0, 175.0],
    'hdd_traffic_reduction': [50.0, 60.0]
})

# Compute bounds
result = compute_effective_hdd_bounds_per_cell(cell_df)
# Adds columns: effective_hdd_low, effective_hdd_high
```

#### `compute_aggregate_bounds()`

Computes aggregate bounds for a ZIP code from cell-level bounds.

```python
from src.processors.uncertainty_quantification import compute_aggregate_bounds

# Cell-level bounds
cell_df = pd.DataFrame({
    'effective_hdd_low': [4800.0, 4900.0, 5000.0],
    'effective_hdd_high': [5200.0, 5300.0, 5400.0]
})

# Aggregate bounds (mean of cell bounds)
agg_low, agg_high = compute_aggregate_bounds(cell_df)
# Returns: (4900.0, 5300.0)
```

#### `validate_bounds_physically_reasonable()`

Validates that bounds satisfy the constraint: low < nominal < high.

```python
from src.processors.uncertainty_quantification import validate_bounds_physically_reasonable

is_valid = validate_bounds_physically_reasonable(
    effective_hdd=5000.0,
    effective_hdd_low=4800.0,
    effective_hdd_high=5200.0
)
# Returns: True
```

### Integration with Pipeline

The uncertainty bounds are automatically computed in `combine_corrections_cells.py`:

```python
# In compute_effective_hdd_per_cell()
cell_effective_hdd_low, cell_effective_hdd_high = compute_effective_hdd_bounds(
    mean_base_hdd,
    mean_terrain_mult,
    mean_elev_addition,
    uhi_hdd_reduction,
    traffic_hdd_reduction
)

# Added to output DataFrame
row = {
    'cell_effective_hdd': cell_effective_hdd,
    'cell_effective_hdd_low': cell_effective_hdd_low,
    'cell_effective_hdd_high': cell_effective_hdd_high,
    # ... other columns
}
```

## Output Schema

The `terrain_attributes.csv` output now includes three columns for each cell and ZIP-code aggregate:

| Column | Type | Description |
|--------|------|-------------|
| `effective_hdd` | float64 | Nominal effective HDD (°F-days) |
| `effective_hdd_low` | float64 | Lower bound on effective HDD (±1σ) |
| `effective_hdd_high` | float64 | Upper bound on effective HDD (±1σ) |

Example row:
```
microclimate_id,effective_hdd,effective_hdd_low,effective_hdd_high
R1_97201_KPDX_cell_001,5000.0,4700.0,5300.0
R1_97201_KPDX_aggregate,5050.0,4750.0,5350.0
```

## Confidence Intervals

The bounds represent approximately **68% confidence interval** (±1 standard deviation).

For other confidence levels, multiply the uncertainty by the appropriate z-score:

| Confidence Level | Multiplier | Calculation |
|------------------|-----------|-------------|
| 68% (±1σ) | 1.0 | `effective_hdd ± uncertainty` |
| 95% (±2σ) | 1.96 | `effective_hdd ± 1.96 × uncertainty` |
| 99% (±3σ) | 2.576 | `effective_hdd ± 2.576 × uncertainty` |

Example: For 95% confidence interval:
```python
uncertainty = (high - low) / 2
ci_95_low = effective_hdd - 1.96 * uncertainty
ci_95_high = effective_hdd + 1.96 * uncertainty
```

## Physical Reasonableness

The implementation enforces the constraint that bounds must be physically reasonable:

```
effective_hdd_low < effective_hdd < effective_hdd_high
```

This is validated by the `validate_bounds_physically_reasonable()` function, which is tested with property-based tests to ensure it holds for all valid input combinations.

## Testing

The implementation includes comprehensive tests:

### Unit Tests
- Scalar, array, and Series input types
- Bounds physically reasonable (low < nominal < high)
- Bounds scale with uncertainty
- Custom uncertainty values
- Edge cases (zero base HDD, high uncertainty)

### Property-Based Tests (Hypothesis)
- **Bounds always physically reasonable**: For any valid input, bounds must satisfy low < nominal < high
- **Bounds width positive**: Bound width (high - low) must always be positive
- **Bounds scale with uncertainty**: Doubling uncertainties approximately doubles bound width
- **Aggregate bounds within cell range**: Aggregate bounds must fall within the range of cell bounds

Run tests:
```bash
python -m pytest src/processors/test_uncertainty_quantification.py -v
```

## Customization

### Adjusting Uncertainty Values

To use different uncertainty estimates, pass custom `sigma` parameters:

```python
from src.processors.uncertainty_quantification import compute_effective_hdd_bounds

# Use higher uncertainty for PRISM base HDD
low, high = compute_effective_hdd_bounds(
    base_hdd=5000.0,
    terrain_mult=1.05,
    elev_addition=200.0,
    uhi_reduction=150.0,
    traffic_reduction=50.0,
    base_hdd_sigma=300.0,  # Higher uncertainty
    terrain_mult_sigma=0.05,
    elev_addition_sigma=50.0,
    uhi_reduction_sigma=100.0,
    traffic_reduction_sigma=75.0
)
```

### Modifying Default Uncertainties

Edit the constants in `uncertainty_quantification.py`:

```python
BASE_HDD_UNCERTAINTY = 200.0  # Adjust as needed
TERRAIN_MULT_UNCERTAINTY = 0.05
ELEV_ADDITION_UNCERTAINTY = 50.0
UHI_REDUCTION_UNCERTAINTY = 100.0
TRAFFIC_REDUCTION_UNCERTAINTY = 75.0
```

## Limitations and Assumptions

1. **Uncertainty estimates are approximate**: The default uncertainty values are based on typical data quality and model error. They may need adjustment for specific regions or data sources.

2. **Uncertainties are independent**: The error propagation assumes that uncertainties in different components are independent. In reality, there may be correlations (e.g., PRISM and NOAA station errors).

3. **Linear error propagation**: The approach uses first-order error propagation, which is accurate for small uncertainties but may underestimate bounds for very large uncertainties.

4. **Cold air drainage not included**: The cold air drainage multiplier is not included in uncertainty propagation because it is a deterministic correction based on DEM flow accumulation.

5. **Bounds represent ±1σ**: The bounds represent approximately 68% confidence interval. For higher confidence levels, multiply by the appropriate z-score.

## Future Enhancements

Potential improvements to the uncertainty quantification:

1. **Spatial correlation of uncertainties**: Account for spatial correlation in PRISM interpolation error
2. **Adaptive uncertainty**: Adjust uncertainty estimates based on data quality metrics (e.g., number of valid pixels per cell)
3. **Sensitivity analysis**: Compute bounds for each component separately to identify which corrections dominate uncertainty
4. **Bayesian uncertainty**: Use Bayesian methods to combine prior uncertainty with observed data
5. **Temporal uncertainty**: For daily mode, propagate uncertainty through time-series analysis

## References

- Taylor, J. R. (1997). An Introduction to Error Analysis: The Study of Uncertainties in Physical Measurements. University Science Books.
- Bevington, P. R., & Robinson, D. K. (2003). Data Reduction and Error Analysis for the Physical Sciences. McGraw-Hill.
- JCGM (2008). Evaluation of measurement data — Guide to the expression of uncertainty in measurement. International Bureau of Weights and Measures.
