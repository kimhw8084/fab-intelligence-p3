# Product-specific risks and mandatory mitigations

| Risk | Mitigation / release condition |
|---|---|
| Invalid spatial orientation | Explicit calibration/geometry metadata, refusal and registration residuals |
| Unobserved areas shown as certain | Separate measured mask from estimates; uncertainty layer and user acknowledgement |
| Mixed wafer-map modalities | Typed sparse/dense/defect/die-bin schemas; compatibility matrix |
| Apparent yield correlation due product mix | Product-aware comparisons, grouped holdout and no causal promotion |
| Similar patterns with different causes | Retrieval explains shape only and links actual verified history separately |
| No downstream data at site | C03 remains gated; C01/C04/C05 still independently useful |
