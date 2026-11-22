# Scientific algorithms and critical decision rules — FAB Spatial & Yield Intelligence

## Exact spatial evidence methodology

**W1 Data geometry:** identify coordinate system and origin; units, wafer radius, notch/orientation, edge exclusion, reticle origin/die layout, layer/step, sampling mask and missing sites. Separate sparse measurement points, dense metrology, defect point cloud, die-bin categorical map, and continuous fields into different typed data contracts.

**W2 Feature extraction:** derive radial/edge/center, sector, directional gradients, reticle periodicity and local-cluster statistics from *observed* points. For a sparse map, show points and computed region statistics with coverage; spatial interpolation is a second separately evaluated feature with its own errors and uncertainty. Avoid routine image CNNs until simple descriptors fail a held-out task.

**W3 Anomaly scoring:** compare with matching product/recipe/tool/measurement/sampling baselines; account for missingness, sampled regions and repeated wafer measurements. Calibrate false-alert rate on held-out wafers/lots and periods, not neighboring pixels from training wafers. Require multiplicity correction for multiple spatial searches.

**W4 Historical similarity:** select geometric normalization and descriptor distance appropriate to measurement modality. Lock train/holdout splits by wafer/lot and time, evaluate top-k relevance against independent labeled similar-but-not-causal cases, and explain match regions. Never label top nearest neighbors as verified root cause.

**W5 Evolution:** align coordinate systems and verify measurement meaning, product/layer and wafer identity before subtraction; show registration residuals and transformation uncertainty. Unknown orientation or incompatible units prevents evolution claims. Match sparse-to-sparse observed sites or propagate validated interpolation uncertainty.

**W6 Yield link:** require correct wafer/die/reticle physical correspondence and outcome time ordering. Compare proper holdout populations and quantify uncertainty/confounding/product mix. State observational association, not proof an upstream pattern created failure.

**OSS selection:** scikit-image, PySAL/esda, scikit-learn, NumPy and wafer-map visualization implementations may be useful; for first bootstrap a stdlib-only observed-region baseline is included. Validate transitive dependencies, renderer host and actual geometry. Avoid expensive model training without real added value.


## Minimum correct implementation order
A. Validate source/identity/units/permissions BEFORE scientific analysis. B. Implement an independently understandable deterministic baseline and a fixed positive/negative oracle. C. Create an evidence envelope and show a complete user workflow. D. Add the full required scientific methods with assumption diagnostics and falsifying cases. E. Compare advanced OSS only where it can beat or materially extend that baseline; freeze test cases first. F. Run the combined product and real target-OS/offline qualification. G. Repeat audit until all gates pass.

## Mathematical and evaluation requirements
- For numeric estimates, specify the estimand, unit, effective independent sample, uncertainty method, algorithm/version and declared applicability domain.
- For classification, retrieval and anomaly cases, precommit held-out metrics, precision/recall/calibration or appropriately justified equivalents. Never fit thresholds to evaluation answers.
- Use group/time/device/wafer/lot/experiment-aware holdouts where dependencies require them; random measurement-row splits are not acceptable evidence of broader generalization.
- Distinguish data observed, data estimated and data unknown; refuse if physical constraints or study assumptions cannot be verified.
- Run property, metamorphic, adversarial and counterfactual *tests* where meaningful (e.g. changing labels must not create a spurious causal claim; adding an unapproved join must trigger refusal).
- An LLM explanation must be mechanically checked against the verified evidence object. An independent code-based oracle, not an agent's agreement, determines scientific pass/fail.

## Scientific peer review rubric
Engineer/reviewer should be able to answer: Is the population actually eligible? What was the measured unit and its grain? Which approved sources and joins were used? Could sampling or timing explain the observation? Is the statistical estimand identifiable? Which alternative explanations were tested? Which result is observed rather than predicted? What result would invalidate the conclusion? Does the method generalize to unseen wafers/lots/tools/periods? What is explicitly unknown?
