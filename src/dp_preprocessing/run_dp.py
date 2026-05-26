from .phenotypes import load_phenotypes
from .phenotype_queries import fetch_all_phenotype_counts, get_max_patient_phenotype_overlap

import opendp.prelude as dp
dp.enable_features("contrib")

import json
from dotenv import load_dotenv
import os
from pathlib import Path
load_dotenv()

"""
Differentially Private Preprocessing Script
"""

def process_phenotypes(phenotypes_json_path):
    with open(phenotypes_json_path, "r") as f:
        phenotypes = json.load(f)
        phenotypes = load_phenotypes()
    return phenotypes

def connect_db(db_path, db_type="duckdb"):
    if db_type == "duckdb":
        import duckdb
        con = duckdb.connect(db_path)
    elif db_type == "sqlite":
        import sqlite3
        con = sqlite3.connect(db_path)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
    return con

def apply_dp_to_counts(counts_df,
                       con=None,
                       phenotypes=None,
                       dp_mode="gaussian",
                       epsilon=1.0,
                       delta=1e-5,
                       verbose=False
                       ):

    if dp_mode == "gaussian":
        from math import sqrt, log

        if con is not None:
            max_overlap = get_max_patient_phenotype_overlap(con, phenotypes)
            L2_SENSITIVITY = sqrt(max_overlap)
            if verbose:
                print(f"Max phenotypes per patient: {max_overlap}")
                print(f"L2 sensitivity: {L2_SENSITIVITY:.4f}")
        else:
            L2_SENSITIVITY = 1.0  # fallback: assumes no patient matches more than one phenotype

        noise_scale = L2_SENSITIVITY * sqrt(2 * log(1.25 / delta)) / epsilon

        # Build the measurement
        input_domain = dp.vector_domain(dp.atom_domain(T=int))  # vector of ints (no NaN)
        input_metric = dp.l2_distance(T=float)

        gaussian_meas = dp.m.make_gaussian(input_domain, input_metric, scale=noise_scale)

        # Extract the true counts as a Python list of ints (required by OpenDP)
        true_counts = counts_df["patient_count"].tolist()

        # Apply the Gaussian measurement (uses OpenDP's internal RNG)
        noisy_counts_raw = gaussian_meas(true_counts)

        # Post-processing: clip to 0 (valid DP post-processing)
        noisy_counts = [max(0, v) for v in noisy_counts_raw]

        result_df = counts_df[["cohort_id", "phenotype_name", "patient_count"]].copy()
        result_df["dp_count"] = noisy_counts
        result_df["noise_added"] = result_df["dp_count"] - result_df["patient_count"]

        result_df.sort_values("patient_count", ascending=False).head(15)

        if verbose:
            # Verify the privacy guarantee (ρ in zCDP)
            rho = gaussian_meas.map(L2_SENSITIVITY)
            print(f"\nPrivacy guarantee: ρ = {rho:.6f}  (zCDP)")
            print(f"Expected:          ρ = {1 / (2 * noise_scale**2):.6f}  (= 1 / 2σ²)")
            print(f"\nThis implies (ε={epsilon}, δ={delta})-DP via: ε = ρ + 2√(ρ · ln(1/δ))")
    else:
        raise ValueError(f"Unsupported DP mode: {dp_mode}")
    return result_df

def main():

    # load phenotypes
    phenotypes_json_path = os.getenv("PHENOTYPES_JSON_PATH")
    env_path = Path(phenotypes_json_path) if phenotypes_json_path else None
    phenotypes = load_phenotypes(env_path) if env_path and env_path.exists() else load_phenotypes()
    print(f"Loaded {len(phenotypes)} phenotypes from {env_path if env_path and env_path.exists() else 'default path'}")

    # Prefer CohortGenerator output (accurate ATLAS definitions) over simple SQL queries
    cohort_counts_csv = Path(os.getenv("COHORT_COUNTS_CSV", "outputs/cohort_counts.csv"))
    if cohort_counts_csv.exists():
        import pandas as pd
        true_df = pd.read_csv(cohort_counts_csv)
        true_df["patient_count"] = true_df["patient_count"].astype(int)
        print(f"Loaded true counts from CohortGenerator output: {cohort_counts_csv}")
        con = None  # no DB connection needed — counts already computed
    else:
        print(f"CohortGenerator output not found at {cohort_counts_csv}")
        print("Falling back to simple SQL queries (run generate_cohorts.R first for accurate counts)")
        db_path = os.getenv("RAW_DUCKDB_PATH")
        con = connect_db(db_path)
        true_df, _ = fetch_all_phenotype_counts(con)

    # Apply DP to the counts
    dp_mode = os.getenv("DP_MODE", "gaussian")
    epsilon = float(os.getenv("EPSILON", "1.0"))
    delta = float(os.getenv("DELTA", "1e-5"))
    dp_df = apply_dp_to_counts(
        true_df, con=con, phenotypes=phenotypes,
        dp_mode=dp_mode, epsilon=epsilon, delta=delta, verbose=True
    )

    # Save both true and DP counts to CSV for downstream use
    output_dir = Path(os.getenv("OUTPUT_DIR", "outputs/"))
    output_dir.mkdir(parents=True, exist_ok=True)

    result_output_path = output_dir / f"phenotype_counts_dp_{dp_mode}_eps{epsilon}_delta{delta}.csv"
    dp_df.to_csv(result_output_path, index=False)
    print(f"Saved DP counts to:   {result_output_path}")

    # put the dp_count in the json format for dashboard use
    dp_count_output_path = "app/public/phenotype_counts_dp.json"

    # remove the true count
    dp_df = dp_df.drop(columns=["patient_count", "noise_added"])

    # attach concept_ids and system from phenotype definitions
    concept_id_map = {p.cohort_id: list(p.concept_ids) for p in phenotypes}
    system_map = {p.cohort_id: p.system for p in phenotypes}
    dp_df["concept_ids"] = dp_df["cohort_id"].map(concept_id_map)
    dp_df["system"] = dp_df["cohort_id"].map(system_map)

    dp_df.to_json(dp_count_output_path, orient="records")

    # Write run summary
    from datetime import datetime

    summary_path = output_dir / f"dp_run_summary_{dp_mode}_eps{epsilon}_delta{delta}.txt"
    with open(summary_path, "w") as f:
        f.write("=== Differential Privacy Run Summary ===\n")
        f.write(f"Timestamp:           {datetime.now().isoformat()}\n\n")
        f.write("--- Parameters ---\n")
        f.write(f"DP mode:             {dp_mode}\n")
        f.write(f"Epsilon (ε):         {epsilon}\n")
        f.write(f"Delta (δ):           {delta}\n")
        if con is not None:
            from math import sqrt, log
            max_overlap = get_max_patient_phenotype_overlap(con, phenotypes)
            l2_sens = sqrt(max_overlap)
            noise_scale = l2_sens * sqrt(2 * log(1.25 / delta)) / epsilon
            f.write(f"Max patient overlap: {max_overlap}\n")
            f.write(f"L2 sensitivity:      {l2_sens:.4f}\n")
            f.write(f"Noise scale (σ):     {noise_scale:.4f}\n")
        f.write(f"Phenotypes loaded:   {len(phenotypes)}\n\n")
        f.write("--- Results ---\n")
        result_df = pd.read_csv(result_output_path)
        f.write(f"Total phenotypes:    {len(result_df)}\n")
        f.write(f"Total true count:    {result_df['patient_count'].sum()}\n")
        f.write(f"Total DP count:      {result_df['dp_count'].sum()}\n")
        f.write(f"Mean noise added:    {result_df['noise_added'].mean():.2f}\n")
        f.write(f"Std noise added:     {result_df['noise_added'].std():.2f}\n\n")
        f.write("--- Top 10 phenotypes by DP count ---\n")
        top10 = result_df.nlargest(10, "dp_count")[["phenotype_name", "patient_count", "dp_count", "noise_added"]]
        f.write(top10.to_string(index=False))
        f.write("\n\n--- Output Files ---\n")
        f.write(f"DP counts CSV:       {result_output_path}\n")
        f.write(f"Dashboard JSON:      {dp_count_output_path}\n")
    print(f"Saved run summary to: {summary_path}")

if __name__ == "__main__":
    main()

