"""Run the prespecified Ionosphere experiment with Gaussian noise features."""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import statistics
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from stage2_pilot import (
    DATASETS,
    N_TREES,
    ROOT,
    fit_random_forest,
    load_dataset,
    manual_oob_error,
    sha256_file,
    write_csv,
)


CONDITIONS = (0, 10, 50)
MTRY_VALUES = (1, 6)
REPEATS = 20
FOREST_SEED_BASE = 310000
NOISE_SEED_BASE = 320000
OUTPUT_STEM = "noise_ionosphere20"
HYPOTHESIS = (
    "With 50 Gaussian noise features, mean OOB and test errors will rise "
    "relative to no noise, particularly at mtry=1; mtry=6 may be selected "
    "more often. This prediction was recorded before the noise run."
)
METRICS = (
    "oob_error_mtry_1",
    "oob_error_mtry_6",
    "test_error_mtry_1",
    "test_error_mtry_6",
    "test_error_selection",
)


def chance_of_informative_candidate(
    total_features: int, informative_features: int, mtry: int
) -> float:
    """Calculate the chance that mtry candidates include an informative feature.

    Features are sampled without replacement at one split. The number of
    actually informative Ionosphere features is unknown; K=1 is used only as
    a transparent mathematical illustration, never as an estimated fact.

    Args:
        total_features: Total number of input columns M.
        informative_features: Hypothetical informative count K.
        mtry: Number of sampled candidate columns.

    Returns:
        ``1 - comb(M-K, mtry) / comb(M, mtry)``.

    Raises:
        ValueError: If the feature counts or mtry are invalid.
    """
    if not 0 <= informative_features <= total_features or not 1 <= mtry <= total_features:
        raise ValueError("Require 0 <= K <= M and 1 <= mtry <= M.")
    if total_features - informative_features < mtry:
        return 1.0
    return 1.0 - math.comb(total_features - informative_features, mtry) / math.comb(
        total_features, mtry
    )


def load_frozen_splits() -> list[dict[str, object]]:
    """Read and validate all 20 Ionosphere splits from the earlier fresh run.

    Returns:
        Saved split records in repeat order.
    """
    path = ROOT / "results" / "stage2_fresh20_runs.csv"
    with path.open(newline="", encoding="utf-8") as source:
        rows = [row for row in csv.DictReader(source) if row["dataset"] == "ionosphere"]
    rows.sort(key=lambda row: int(row["repeat"]))
    if len(rows) != REPEATS or [int(row["repeat"]) for row in rows] != list(
        range(1, REPEATS + 1)
    ):
        raise ValueError("Expected exactly the 20 frozen Ionosphere splits.")
    return rows


def run_experiment() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Fit paired forests for original, +10 and +50 feature conditions.

    Returns:
        All 60 run-level rows and three condition summaries.

    Side Effects:
        Fits 120 forests in memory; does not write files.
    """
    spec = DATASETS[0]
    if spec.name != "ionosphere":
        raise RuntimeError("The frozen protocol requires Ionosphere as DATASETS[0].")
    features, labels = load_dataset(spec)
    split_rows = load_frozen_splits()
    raw_rows: list[dict[str, object]] = []

    for repeat_index, split_row in enumerate(split_rows):
        train = np.asarray(json.loads(str(split_row["train_indices"])), dtype=np.int64)
        test = np.asarray(json.loads(str(split_row["test_indices"])), dtype=np.int64)
        if (
            len(train) != 315
            or len(test) != 36
            or len(np.unique(np.concatenate((train, test)))) != len(labels)
        ):
            raise ValueError(f"Invalid frozen split {repeat_index + 1}.")
        noise_seed = NOISE_SEED_BASE + repeat_index
        forest_seed = FOREST_SEED_BASE + repeat_index
        noise = np.random.default_rng(noise_seed).normal(size=(len(labels), 50))

        for added_features in CONDITIONS:
            condition_features = (
                features
                if added_features == 0
                else np.column_stack((features, noise[:, :added_features]))
            )
            x_train, x_test = condition_features[train], condition_features[test]
            y_train, y_test = labels[train], labels[test]
            measured: dict[int, dict[str, object]] = {}

            for mtry in MTRY_VALUES:
                model, _ = fit_random_forest(
                    x_train, y_train, mtry=mtry, seed=forest_seed
                )
                oob_error, oob_delta = manual_oob_error(model, y_train)
                predictions = model.predict(x_test)
                mistakes = int(np.count_nonzero(predictions != y_test))
                measured[mtry] = {
                    "model": model,
                    "oob_error": oob_error,
                    "oob_check_delta": oob_delta,
                    "test_mistakes": mistakes,
                    "test_error": mistakes / len(test),
                }

            first = measured[1]
            second = measured[6]
            model_one = first["model"]
            model_six = second["model"]
            if not all(
                np.array_equal(a, b)
                for a, b in zip(
                    model_one.estimators_samples_,
                    model_six.estimators_samples_,
                    strict=True,
                )
            ):
                raise RuntimeError("Paired forests did not share bootstrap samples.")
            chosen = 6 if float(second["oob_error"]) < float(first["oob_error"]) else 1
            selected = measured[chosen]
            total_features = condition_features.shape[1]
            raw_rows.append(
                {
                    "dataset": "ionosphere",
                    "repeat": repeat_index + 1,
                    "condition_added_noise": added_features,
                    "total_features": total_features,
                    "n_train": len(train),
                    "n_test": len(test),
                    "split_seed": int(split_row["split_seed"]),
                    "forest_seed_both_mtry": forest_seed,
                    "noise_seed": noise_seed,
                    "train_indices": json.dumps(train.tolist()),
                    "test_indices": json.dumps(test.tolist()),
                    "hypothetical_k": 1,
                    "p_candidate_k1_mtry_1": chance_of_informative_candidate(
                        total_features, 1, 1
                    ),
                    "p_candidate_k1_mtry_6": chance_of_informative_candidate(
                        total_features, 1, 6
                    ),
                    "oob_error_mtry_1": first["oob_error"],
                    "oob_error_mtry_6": second["oob_error"],
                    "oob_check_delta_mtry_1": first["oob_check_delta"],
                    "oob_check_delta_mtry_6": second["oob_check_delta"],
                    "test_mistakes_mtry_1": first["test_mistakes"],
                    "test_mistakes_mtry_6": second["test_mistakes"],
                    "test_error_mtry_1": first["test_error"],
                    "test_error_mtry_6": second["test_error"],
                    "selected_mtry_by_oob": chosen,
                    "test_mistakes_selection": selected["test_mistakes"],
                    "test_error_selection": selected["test_error"],
                    "same_bootstrap_for_mtry_1_and_6": True,
                }
            )

    summary_rows: list[dict[str, object]] = []
    baseline = {
        int(row["repeat"]): row
        for row in raw_rows
        if int(row["condition_added_noise"]) == 0
    }
    for added_features in CONDITIONS:
        group = [
            row
            for row in raw_rows
            if int(row["condition_added_noise"]) == added_features
        ]
        summary: dict[str, object] = {
            "dataset": "ionosphere",
            "condition_added_noise": added_features,
            "total_features": group[0]["total_features"],
            "repeats": len(group),
            "hypothetical_k": 1,
            "p_candidate_k1_mtry_1": group[0]["p_candidate_k1_mtry_1"],
            "p_candidate_k1_mtry_6": group[0]["p_candidate_k1_mtry_6"],
            "selection_mtry_6_count": sum(
                int(row["selected_mtry_by_oob"]) == 6 for row in group
            ),
        }
        for metric in METRICS:
            values = [float(row[metric]) for row in group]
            summary[f"{metric}_mean"] = statistics.mean(values)
            summary[f"{metric}_sample_sd"] = statistics.stdev(values)
            differences = [
                float(row[metric]) - float(baseline[int(row["repeat"])][metric])
                for row in group
            ]
            summary[f"{metric}_paired_delta_from_baseline_mean"] = statistics.mean(
                differences
            )
        summary_rows.append(summary)

    return raw_rows, summary_rows


def make_metadata(summary_rows: list[dict[str, object]]) -> dict[str, object]:
    """Build provenance and explicitly compare the prediction with results.

    Args:
        summary_rows: Three condition summaries in 0, +10, +50 order.

    Returns:
        Reproducibility metadata and descriptive hypothesis checks.
    """
    baseline, _, plus_fifty = summary_rows
    checks = {
        "oob_mtry_1_higher_at_plus50": float(plus_fifty["oob_error_mtry_1_mean"])
        > float(baseline["oob_error_mtry_1_mean"]),
        "oob_mtry_6_higher_at_plus50": float(plus_fifty["oob_error_mtry_6_mean"])
        > float(baseline["oob_error_mtry_6_mean"]),
        "test_mtry_1_higher_at_plus50": float(plus_fifty["test_error_mtry_1_mean"])
        > float(baseline["test_error_mtry_1_mean"]),
        "test_mtry_6_higher_at_plus50": float(plus_fifty["test_error_mtry_6_mean"])
        > float(baseline["test_error_mtry_6_mean"]),
        "test_mtry_1_deteriorates_more_than_mtry_6": float(
            plus_fifty["test_error_mtry_1_paired_delta_from_baseline_mean"]
        )
        > float(plus_fifty["test_error_mtry_6_paired_delta_from_baseline_mean"]),
        "mtry_6_selected_more_often_at_plus50": int(
            plus_fifty["selection_mtry_6_count"]
        )
        > int(baseline["selection_mtry_6_count"]),
    }
    return {
        "status": "prespecified Gaussian-noise experiment on Ionosphere",
        "prediction_recorded_before_run": HYPOTHESIS,
        "protocol_file": "ETAP2_PROTOKOL_ETAP3.md",
        "hypothesis_checks_descriptive_not_significance_tests": checks,
        "dataset": "ionosphere",
        "source_archive_sha256": sha256_file(ROOT / "data" / "raw" / DATASETS[0].archive),
        "repeats": REPEATS,
        "conditions_added_noise": list(CONDITIONS),
        "mtry_values_fixed": list(MTRY_VALUES),
        "n_estimators_per_forest": N_TREES,
        "forest_seed_for_repeat_r_zero_based": "310000+r",
        "noise_seed_for_repeat_r_zero_based": "320000+r",
        "noise_generator": "numpy.random.default_rng(seed).normal(size=(351,50))",
        "noise_plus10_is_first_10_of_plus50": True,
        "frozen_splits_file": "results/stage2_fresh20_runs.csv",
        "stratify": None,
        "selection": "minimum training OOB classification error; tie -> mtry=1",
        "hypothetical_k_one_is_not_measured_number_of_informative_features": True,
        "model_fit_count": REPEATS * len(CONDITIONS) * len(MTRY_VALUES),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
    }


def main() -> None:
    """Run the experiment and save raw rows, summaries and metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir", type=Path, default=ROOT / "results", help="Output directory."
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing output files."
    )
    args = parser.parse_args()
    output_dir = args.out_dir.resolve()
    paths = [
        output_dir / f"{OUTPUT_STEM}_runs.csv",
        output_dir / f"{OUTPUT_STEM}_summary.csv",
        output_dir / f"{OUTPUT_STEM}_metadata.json",
    ]
    if not args.overwrite and any(path.exists() for path in paths):
        raise FileExistsError(
            "Noise results already exist. Choose another --out-dir or use --overwrite."
        )
    raw_rows, summary_rows = run_experiment()
    metadata = make_metadata(summary_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(paths[0], raw_rows)
    write_csv(paths[1], summary_rows)
    paths[2].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary_rows, ensure_ascii=False, indent=2))
    print(f"Saved {len(raw_rows)} runs and {metadata['model_fit_count']} forest fits.")


if __name__ == "__main__":
    main()
