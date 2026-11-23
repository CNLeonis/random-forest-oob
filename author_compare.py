"""Run Breiman and Cutler's 2004 Fortran release on the frozen Ionosphere splits.

This is a separately labelled author-implementation comparison, not a claim
that the 2004 public release is the exact unpublished code used in 2001.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from stage2_pilot import DATASETS, ROOT, load_dataset, sha256_file, write_csv


SOURCE = ROOT / "author_code" / "breiman_cutler_rf51_2004.f"
SOURCE_URL = "https://www.stat.berkeley.edu/~breiman/RandomForests/cc_examples/prog.f"
EXPECTED_SOURCE_SHA256 = "a985f3a0bef2b4f270c6d3064039ff086bd45c613fde3c72e5d72a156f72f09b"
SPLITS = ROOT / "results" / "stage2_fresh20_runs.csv"
STEM = "author_ionosphere20"
REPEATS = 20
SEED_BASE = 410000

# These replace only fixed configuration, file input seed, and disabled extras.
# The tree growing, OOB and test prediction routines remain the downloaded code.
CONFIG_PATCHES = {
    "mdim=9,ntrain=214,nclass=6,maxcat=1,": "mdim=34,ntrain=315,nclass=2,maxcat=1,",
    "ntest=0,labelts=0,labeltr=1,": "ntest=36,labelts=1,labeltr=1,",
    "mtry0=2,ndsize=1,jbt=500,look=100,lookcls=1,":
        "mtry0=MTRY_VALUE,ndsize=1,jbt=100,look=100,lookcls=0,",
    "imp=1,interact=0,impn=1,": "imp=0,interact=0,impn=0,",
    "nprox=1,nrnn=ntrain,": "nprox=0,nrnn=ntrain,",
    "iprotout=\t1,": "iprotout=\t0,",
    "iproxout=\t1,": "iproxout=\t0,",
    "ioutlierout=\t1)": "ioutlierout=\t0)",
    "iseed=4351": "open(30,file='seed.txt',status='old')\n\tread(30,*) iseed\n\tclose(30)",
}
COMPILE_FLAGS = (
    "-std=legacy", "-fallow-argument-mismatch", "-ffixed-line-length-none",
    "-fno-range-check", "-O2",
)
ERROR_PATTERN = re.compile(r"final error (rate|test) %\s+([0-9]+(?:\.[0-9]+)?)")
LABEL_TO_NUMBER = {"b": 1, "g": 2}


def adapted_source(mtry: int) -> str:
    """Create a configuration-only adaptation from the verified author file."""
    if not SOURCE.is_file():
        raise FileNotFoundError(
            "Missing local author Fortran source. Download it using the README.md "
            "instructions before running this comparison."
        )
    if sha256_file(SOURCE) != EXPECTED_SOURCE_SHA256:
        raise ValueError("The downloaded author source differs from its recorded SHA-256.")
    code = SOURCE.read_text(encoding="latin-1")
    for old, new in CONFIG_PATCHES.items():
        if code.count(old) != 1:
            raise ValueError(f"Expected exactly one source occurrence of {old!r}.")
        code = code.replace(old, new)
    return code.replace("MTRY_VALUE", str(mtry))


def frozen_splits() -> list[dict[str, object]]:
    """Read all original 20 Ionosphere partitions in the saved order."""
    with SPLITS.open(encoding="utf-8", newline="") as source:
        rows = [row for row in csv.DictReader(source) if row["dataset"] == "ionosphere"]
    rows.sort(key=lambda row: int(row["repeat"]))
    if len(rows) != REPEATS or [int(row["repeat"]) for row in rows] != list(
        range(1, REPEATS + 1)
    ):
        raise ValueError("Expected the 20 frozen Ionosphere splits.")
    return rows


def write_fortran_data(
    path: Path, features: np.ndarray, labels: np.ndarray, indices: np.ndarray
) -> None:
    """Write features and 1/2 class labels in the author's documented format."""
    with path.open("w", encoding="ascii", newline="\n") as target:
        for index in indices:
            values = " ".join(f"{value:.17g}" for value in features[index])
            target.write(f"{values} {LABEL_TO_NUMBER[str(labels[index])]}\n")


def read_errors(stdout: str, n_train: int, n_test: int) -> tuple[int, int]:
    """Convert printed percentages back to exact mistake counts."""
    values = {name: float(value) for name, value in ERROR_PATTERN.findall(stdout)}
    if set(values) != {"rate", "test"}:
        raise ValueError(f"Missing author errors in output: {stdout[-800:]}")
    oob_count = round(values["rate"] * n_train / 100)
    test_count = round(values["test"] * n_test / 100)
    if abs(values["rate"] - 100 * oob_count / n_train) > 1e-4 or abs(
        values["test"] - 100 * test_count / n_test
    ) > 1e-4:
        raise ValueError("Author percentages do not match integer mistake counts.")
    for title, total, mistakes in (
        ("Training set confusion matrix (OOB):", n_train, oob_count),
        ("Test set confusion matrix:", n_test, test_count),
    ):
        block = stdout.split(title, 1)
        if len(block) != 2:
            raise ValueError(f"Missing {title} in author output.")
        matrix = re.search(
            r"\n\s*1\s+2\s*\n\s*1\s+(\d+)\s+(\d+)\s*\n\s*2\s+(\d+)\s+(\d+)",
            block[1],
        )
        if matrix is None:
            raise ValueError(f"Cannot read {title}.")
        cells = [int(value) for value in matrix.groups()]
        if sum(cells) != total or cells[1] + cells[2] != mistakes:
            raise ValueError(f"{title} disagrees with the printed error rate.")
    return oob_count, test_count


def run(compiler: Path) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object], str]:
    """Compile two configurations and run both on every frozen partition."""
    features, labels = load_dataset(DATASETS[0])
    if set(map(str, labels)) != set(LABEL_TO_NUMBER):
        raise ValueError("Unexpected Ionosphere class labels.")
    compiler = compiler.resolve()
    env = os.environ.copy()
    env["PATH"] = str(compiler.parent) + os.pathsep + env.get("PATH", "")
    version = subprocess.run(
        [str(compiler), "--version"], capture_output=True, text=True, check=True, env=env
    ).stdout.splitlines()[0]
    records: list[dict[str, object]] = []
    first_stdout = ""
    compilation_warnings: list[str] = []

    with tempfile.TemporaryDirectory(prefix="breiman_author_") as temp:
        work = Path(temp)
        executables: dict[int, Path] = {}
        for mtry in (1, 6):
            adapted = work / f"rf_mtry{mtry}.f"
            adapted.write_text(adapted_source(mtry), encoding="latin-1")
            executable = work / f"rf_mtry{mtry}.exe"
            result = subprocess.run(
                [str(compiler), *COMPILE_FLAGS, "-o", str(executable), str(adapted)],
                capture_output=True, text=True, env=env, timeout=120,
            )
            if result.returncode:
                raise RuntimeError(f"Compilation failed for mtry={mtry}:\n{result.stderr}")
            if result.stderr.strip():
                compilation_warnings.append(
                    result.stderr.strip().replace(str(adapted), adapted.name)
                )
            executables[mtry] = executable

        for repeat_index, split in enumerate(frozen_splits()):
            train = np.asarray(json.loads(str(split["train_indices"])), dtype=int)
            test = np.asarray(json.loads(str(split["test_indices"])), dtype=int)
            if len(train) != 315 or len(test) != 36 or len(
                np.unique(np.concatenate([train, test]))
            ) != len(labels):
                raise ValueError(f"Invalid frozen partition {repeat_index + 1}.")
            seed = SEED_BASE + repeat_index
            pair: dict[int, tuple[int, int]] = {}
            for mtry in (1, 6):
                # The original program creates output files with status='new'.
                # An isolated directory avoids collisions between runs.
                run_dir = work / f"r{repeat_index + 1:02d}_m{mtry}"
                run_dir.mkdir()
                write_fortran_data(run_dir / "data.train", features, labels, train)
                write_fortran_data(run_dir / "data.test", features, labels, test)
                (run_dir / "seed.txt").write_text(f"{seed}\n", encoding="ascii")
                result = subprocess.run(
                    [str(executables[mtry])], cwd=run_dir, capture_output=True,
                    text=True, env=env, timeout=120,
                )
                if result.returncode:
                    raise RuntimeError(
                        f"Author program failed for repeat={repeat_index + 1}, "
                        f"mtry={mtry}:\n{result.stdout[-1000:]}\n{result.stderr[-1000:]}"
                    )
                if repeat_index == 0:
                    first_stdout += f"=== repeat 1, mtry={mtry}, seed={seed} ===\n{result.stdout}\n"
                pair[mtry] = read_errors(result.stdout, len(train), len(test))
            selected = 6 if pair[6][0] < pair[1][0] else 1
            records.append({
                "dataset": "ionosphere", "repeat": repeat_index + 1,
                "split_seed": int(split["split_seed"]), "author_forest_seed": seed,
                "n_train": len(train), "n_test": len(test),
                "train_indices": json.dumps(train.tolist()),
                "test_indices": json.dumps(test.tolist()),
                "oob_mistakes_mtry_1": pair[1][0],
                "oob_mistakes_mtry_6": pair[6][0],
                "oob_error_mtry_1": pair[1][0] / len(train),
                "oob_error_mtry_6": pair[6][0] / len(train),
                "test_mistakes_mtry_1": pair[1][1],
                "test_mistakes_mtry_6": pair[6][1],
                "test_error_mtry_1": pair[1][1] / len(test),
                "test_error_mtry_6": pair[6][1] / len(test),
                "selected_mtry_by_oob": selected,
                "test_mistakes_selection": pair[selected][1],
                "test_error_selection": pair[selected][1] / len(test),
            })

    summary: dict[str, object] = {"dataset": "ionosphere", "repeats": REPEATS}
    for metric in (
        "oob_error_mtry_1", "oob_error_mtry_6", "test_error_mtry_1",
        "test_error_mtry_6", "test_error_selection",
    ):
        values = [float(row[metric]) for row in records]
        summary[f"{metric}_mean"] = statistics.mean(values)
        summary[f"{metric}_sample_sd"] = statistics.stdev(values)
    summary["selection_mtry_6_count"] = sum(
        int(row["selected_mtry_by_oob"]) == 6 for row in records
    )
    metadata = {
        "source": SOURCE_URL,
        "source_release": "Breiman and Cutler classification code, version 5.1, 2004-06-15",
        "not_exact_2001_experiment_code": True,
        "source_file": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": sha256_file(SOURCE),
        "adaptations": [
            "Ionosphere dimensions, two labelled classes and 36 labelled test cases",
            "100 trees and mtry=1 or 6",
            "class mapping b=1, g=2",
            "disable importance, proximity and other nonessential outputs",
            "read a distinct forest seed from seed.txt for each frozen split",
        ],
        "no_changes_to_tree_oob_or_test_prediction_routines": True,
        "compiler": version,
        "compile_flags": list(COMPILE_FLAGS),
        "compiler_warning_count": len(compilation_warnings),
        "compiler_warnings": compilation_warnings,
        "forest_seed_formula_zero_based_repeat": f"{SEED_BASE}+r",
        "frozen_splits_file": str(SPLITS.relative_to(ROOT)).replace("\\", "/"),
        "source_archive_sha256": sha256_file(ROOT / "data" / "raw" / DATASETS[0].archive),
        "author_program_fit_count": REPEATS * 2,
        "selection_rule": "lower training OOB; tie -> mtry=1",
        "all_planned_runs_successful": True,
    }
    return records, [summary], metadata, first_stdout


def main() -> None:
    """Write independent author-code results without overwriting prior runs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default="gfortran", help="Path to gfortran.exe")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    compiler = Path(args.compiler)
    if not compiler.is_file():
        found = shutil.which(args.compiler)
        if found is None:
            parser.error("gfortran not found; install it or pass --compiler PATH")
        compiler = Path(found)
    out_dir = args.out_dir.resolve()
    outputs = [out_dir / f"{STEM}_{suffix}" for suffix in (
        "runs.csv", "summary.csv", "metadata.json", "first_run.txt"
    )]
    if not args.overwrite and any(path.exists() for path in outputs):
        raise FileExistsError("Author results exist; use another --out-dir or --overwrite.")
    records, summary, metadata, first_stdout = run(compiler)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(outputs[0], records)
    write_csv(outputs[1], summary)
    outputs[2].write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs[3].write_text(first_stdout, encoding="utf-8")
    print(json.dumps(summary[0], ensure_ascii=False, indent=2))
    print(f"Saved {len(records)} author-code repeats and {metadata['author_program_fit_count']} fits.")


if __name__ == "__main__":
    main()
