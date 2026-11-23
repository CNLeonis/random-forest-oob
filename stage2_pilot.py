"""Run a fresh 20-repeat experiment on the three Stage 2 datasets."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import zero_one_loss
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
RESULTS_DIR = ROOT / "results"
BASE_SEED = 20261123
REPEATS = 20
N_TREES = 100
TEST_SIZE = 0.1
PREDICTION = (
    "Across 20 fresh repeats, mtry=F will have a lower mean training OOB "
    "error than mtry=1 on each dataset; mean test error will not be lower "
    "for mtry=F on all three datasets."
)


@dataclass(frozen=True)
class DatasetSpec:
    """Describes a source archive and the expected shape of its data."""

    name: str
    archive: str
    member: str
    source_url: str
    sha256: str
    expected_rows: int
    expected_features: int
    expected_classes: int
    drop_identifier: bool = False


DATASETS = (
    DatasetSpec(
        name="ionosphere",
        archive="ionosphere.zip",
        member="ionosphere.data",
        source_url="https://archive.ics.uci.edu/static/public/52/ionosphere.zip",
        sha256="4d218ece62756c99659011a13052d06464f13cb2b3d0410ce2aef16de1403860",
        expected_rows=351,
        expected_features=34,
        expected_classes=2,
    ),
    DatasetSpec(
        name="sonar",
        archive="sonar.zip",
        member="sonar.all-data",
        source_url=(
            "https://archive.ics.uci.edu/static/public/151/"
            "connectionist+bench+sonar+mines+vs+rocks.zip"
        ),
        sha256="088b0b6813fb5ab84736bc2a1e3d6bb886e317520d2f2c04152e2ed65af7a18d",
        expected_rows=208,
        expected_features=60,
        expected_classes=2,
    ),
    DatasetSpec(
        name="glass",
        archive="glass.zip",
        member="glass.data",
        source_url="https://archive.ics.uci.edu/static/public/42/glass+identification.zip",
        sha256="499c07a17115bf63100bb19cc1fdefad7f464bf5dc2b168930fa2071fd6b6e65",
        expected_rows=214,
        expected_features=9,
        expected_classes=6,
        drop_identifier=True,
    ),
)


def sha256_file(path: Path) -> str:
    """Calculates the SHA-256 digest used to identify a source archive.

    Args:
        path: Archive whose content should be fingerprinted.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset(spec: DatasetSpec) -> tuple[np.ndarray, np.ndarray]:
    """Loads and validates one UCI dataset without modifying its source archive.

    Args:
        spec: Expected archive name, member path, dimensions, and digest.

    Returns:
        A numeric feature matrix and the original class labels.

    Raises:
        FileNotFoundError: If the expected archive or member is absent.
        ValueError: If the archive digest, dimensions, or values are unexpected.
    """
    archive_path = RAW_DIR / spec.archive
    if not archive_path.is_file():
        raise FileNotFoundError(
            f"Missing {archive_path}. Download the source archive from {spec.source_url}."
        )

    actual_digest = sha256_file(archive_path)
    if actual_digest != spec.sha256:
        raise ValueError(
            f"SHA-256 mismatch for {archive_path.name}: "
            f"expected {spec.sha256}, got {actual_digest}"
        )

    with ZipFile(archive_path) as archive:
        try:
            data = archive.read(spec.member)
        except KeyError as error:
            raise FileNotFoundError(
                f"Archive {archive_path.name} has no member {spec.member!r}."
            ) from error

    frame = pd.read_csv(BytesIO(data), header=None)
    expected_columns = spec.expected_features + 1 + int(spec.drop_identifier)
    if frame.shape != (spec.expected_rows, expected_columns):
        raise ValueError(
            f"Unexpected shape for {spec.name}: {frame.shape}; "
            f"expected {(spec.expected_rows, expected_columns)} before identifier removal."
        )
    if spec.drop_identifier:
        frame = frame.iloc[:, 1:]

    features = frame.iloc[:, :-1].to_numpy(dtype=np.float64)
    labels = frame.iloc[:, -1].to_numpy()
    if features.shape != (spec.expected_rows, spec.expected_features):
        raise ValueError(f"Unexpected feature shape for {spec.name}: {features.shape}.")
    if not np.isfinite(features).all() or pd.isna(labels).any():
        raise ValueError(f"{spec.name} contains missing or non-finite values.")
    if len(np.unique(labels)) != spec.expected_classes:
        raise ValueError(
            f"Unexpected number of classes for {spec.name}: {len(np.unique(labels))}."
        )
    return features, labels


def manual_oob_error(
    model: RandomForestClassifier, labels: np.ndarray
) -> tuple[float, float]:
    """Checks scikit-learn's OOB score against a direct vote-based calculation.

    Args:
        model: A fitted random forest with OOB scoring enabled.
        labels: Training labels in the same order used to fit the model.

    Returns:
        The manually calculated OOB error and its absolute difference from
        ``1 - model.oob_score_``.

    Raises:
        ValueError: If any training row has no valid OOB vote.
        RuntimeError: If the direct and library calculations disagree.
    """
    decisions = model.oob_decision_function_
    if not np.isfinite(decisions).all() or np.any(decisions.sum(axis=1) <= 0):
        raise ValueError("At least one training row has no valid OOB prediction.")

    predictions = model.classes_[np.argmax(decisions, axis=1)]
    direct_error = float(zero_one_loss(labels, predictions))
    library_error = 1.0 - float(model.oob_score_)
    difference = abs(direct_error - library_error)
    if not math.isclose(direct_error, library_error, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(
            f"Direct OOB error {direct_error} differs from library value {library_error}."
        )
    return direct_error, difference


def fit_random_forest(
    features: np.ndarray,
    labels: np.ndarray,
    mtry: int,
    seed: int,
) -> tuple[RandomForestClassifier, float]:
    """Fits one 100-tree Forest-RI approximation.

    Args:
        features: Training feature matrix.
        labels: Training class labels.
        mtry: Number of candidate features considered at each split.
        seed: Random seed for bootstrap samples and feature selection.

    Returns:
        The fitted model and elapsed fitting time in seconds.
    """
    model = RandomForestClassifier(
        n_estimators=N_TREES,
        criterion="gini",
        max_features=mtry,
        bootstrap=True,
        oob_score=True,
        n_jobs=1,
        random_state=seed,
    )
    start = time.perf_counter()
    model.fit(features, labels)
    return model, time.perf_counter() - start


def class_counts(labels: np.ndarray) -> str:
    """Serializes class counts in a stable format for the raw results table.

    Args:
        labels: Class labels from one training or test partition.

    Returns:
        A sorted JSON object mapping class labels to their counts.
    """
    counts = Counter(str(label) for label in labels)
    return json.dumps(dict(sorted(counts.items())), ensure_ascii=False)


def summarize_rows(
    rows: list[dict[str, object]], mtry_rule: int
) -> dict[str, object]:
    """Calculates per-dataset means and sample deviations for repeated runs.

    Args:
        rows: Non-empty run records from one dataset.
        mtry_rule: Dataset-specific value of ``int(log2(M) + 1)``.

    Returns:
        A summary row with sample size, model-selection count, metric means,
        and sample standard deviations.
    """
    summary: dict[str, object] = {
        "dataset": rows[0]["dataset"],
        "repeats": len(rows),
        "n_total": rows[0]["n_total"],
        "features": rows[0]["features"],
        "classes": rows[0]["classes"],
        "mtry_rule": mtry_rule,
        "selection_mtry_rule_count": sum(
            int(row["selected_mtry_by_oob"]) == mtry_rule for row in rows
        ),
    }
    metric_columns = (
        "oob_error_mtry_1",
        "oob_error_mtry_rule",
        "test_error_mtry_1_single_input",
        "test_error_mtry_rule",
        "test_error_selection",
        "cart_test_error",
    )
    for column in metric_columns:
        values = [float(row[column]) for row in rows]
        summary[f"{column}_mean"] = statistics.mean(values)
        summary[f"{column}_sample_sd"] = statistics.stdev(values)
    return summary


def run_experiment() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Runs 20 fresh paired 90/10 splits for each of the three datasets.

    Returns:
        Run-level results and one 20-repeat summary per dataset.

    Notes:
        The base seed differs from the original pilot, so this run uses a fresh
        sequence of splits. Each split is shared by both forests and CART.
    """
    raw_results: list[dict[str, object]] = []
    summary_results: list[dict[str, object]] = []

    for dataset_index, spec in enumerate(DATASETS):
        features, labels = load_dataset(spec)
        feature_count = features.shape[1]
        mtry_rule = int(math.log2(feature_count) + 1)

        dataset_rows: list[dict[str, object]] = []
        for repeat in range(REPEATS):
            split_seed = BASE_SEED + dataset_index * 100 + repeat
            train_indices, test_indices = train_test_split(
                np.arange(len(labels)),
                test_size=TEST_SIZE,
                random_state=split_seed,
                stratify=None,
            )
            x_train, x_test = features[train_indices], features[test_indices]
            y_train, y_test = labels[train_indices], labels[test_indices]

            model_one, time_one = fit_random_forest(
                x_train, y_train, mtry=1, seed=split_seed + 1
            )
            model_rule, time_rule = fit_random_forest(
                x_train, y_train, mtry=mtry_rule, seed=split_seed + 2
            )
            oob_one, check_one = manual_oob_error(model_one, y_train)
            oob_rule, check_rule = manual_oob_error(model_rule, y_train)
            test_one = float(zero_one_loss(y_test, model_one.predict(x_test)))
            test_rule = float(zero_one_loss(y_test, model_rule.predict(x_test)))

            selected_mtry = mtry_rule if oob_rule < oob_one else 1
            selected_test_error = test_rule if selected_mtry == mtry_rule else test_one

            cart = DecisionTreeClassifier(
                criterion="gini",
                random_state=split_seed + 3,
            )
            start = time.perf_counter()
            cart.fit(x_train, y_train)
            cart_fit_seconds = time.perf_counter() - start
            cart_test_error = float(zero_one_loss(y_test, cart.predict(x_test)))

            row: dict[str, object] = {
                "dataset": spec.name,
                "repeat": repeat + 1,
                "split_seed": split_seed,
                "rf_seed_mtry_1": split_seed + 1,
                "rf_seed_mtry_rule": split_seed + 2,
                "cart_seed": split_seed + 3,
                "n_total": len(labels),
                "n_train": len(train_indices),
                "n_test": len(test_indices),
                "train_indices": json.dumps(train_indices.tolist()),
                "test_indices": json.dumps(test_indices.tolist()),
                "features": feature_count,
                "classes": spec.expected_classes,
                "train_class_counts": class_counts(y_train),
                "test_class_counts": class_counts(y_test),
                "mtry_one": 1,
                "mtry_rule": mtry_rule,
                "oob_probability_theoretical": (1.0 - 1.0 / len(y_train)) ** len(
                    y_train
                ),
                "expected_oob_votes_100_trees": N_TREES
                * (1.0 - 1.0 / len(y_train)) ** len(y_train),
                "oob_error_mtry_1": oob_one,
                "oob_error_mtry_rule": oob_rule,
                "oob_check_delta_mtry_1": check_one,
                "oob_check_delta_mtry_rule": check_rule,
                "test_error_mtry_1_single_input": test_one,
                "test_error_mtry_rule": test_rule,
                "selected_mtry_by_oob": selected_mtry,
                "test_error_selection": selected_test_error,
                "cart_test_error": cart_test_error,
                "fit_seconds_mtry_1": time_one,
                "fit_seconds_mtry_rule": time_rule,
                "fit_seconds_cart": cart_fit_seconds,
            }
            raw_results.append(row)
            dataset_rows.append(row)

        summary_results.append(summarize_rows(dataset_rows, mtry_rule))

    return raw_results, summary_results


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Writes homogeneous result rows as UTF-8 CSV with a stable column order.

    Args:
        path: Destination file.
        rows: Non-empty rows sharing the same fields.

    Raises:
        ValueError: If there are no rows to write.
    """
    if not rows:
        raise ValueError(f"Cannot write empty results to {path}.")
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Runs 20 repeats and saves results separately from earlier runs.

    Side Effects:
        Creates the results directory and writes the run-level CSV, summary CSV,
        and provenance metadata without replacing earlier outputs.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_results, summary_results = run_experiment()

    write_csv(RESULTS_DIR / "stage2_fresh20_runs.csv", raw_results)
    write_csv(RESULTS_DIR / "stage2_fresh20_summary.csv", summary_results)

    metadata = {
        "status": (
            "fresh 20-repeat run on three datasets; not a full reproduction "
            "of Breiman (2001)"
        ),
        "repeats_per_dataset": REPEATS,
        "prospective_prediction": PREDICTION,
        "pilot_outputs_preserved": True,
        "random_forest_trees": N_TREES,
        "test_size": TEST_SIZE,
        "stratify": None,
        "selection_metric": "lower training OOB classification error",
        "tie_breaker": "mtry=1",
        "model_fit_count": len(raw_results) * 3,
        "base_seed": BASE_SEED,
        "seed_rationale": (
            "Fixed before this run; date-coded to distinguish this fresh "
            "sequence from the earlier pilot. It has no scientific meaning."
        ),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "datasets": [
            {
                **asdict(spec),
                "archive_sha256_verified": sha256_file(RAW_DIR / spec.archive),
                "mtry_rule": int(math.log2(spec.expected_features) + 1),
            }
            for spec in DATASETS
        ],
    }
    (RESULTS_DIR / "stage2_fresh20_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(summary_results, ensure_ascii=False, indent=2))
    print(
        f"\nWrote {len(raw_results)} runs ({metadata['model_fit_count']} model fits)."
    )


if __name__ == "__main__":
    main()
