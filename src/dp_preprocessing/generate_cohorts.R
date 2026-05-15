#!/usr/bin/env Rscript
#
# generate_cohorts.R
#
# Uses CirceR + CohortGenerator to translate ATLAS phenotype definitions to SQL
# and execute them against the MIMIC-IV OMOP DuckDB file.
#
# Outputs:
#   outputs/cohort_counts.csv   — cohort_id, phenotype_name, patient_count
#
# Usage:
#   Rscript src/dp_preprocessing/generate_cohorts.R
#
# Env vars:
#   OMOP_DUCKDB_PATH   — path to mimiciv_omop.duckdb (default: data/mimiciv_omop.duckdb)
#   COHORT_DUCKDB_PATH — path for writeable cohort output db (default: data/cohorts.duckdb)
#   PHENOTYPES_JSON    — path to phenotype_library.json (default: data/phenotype_library.json)
#   CDM_SCHEMA         — schema name for OMOP tables (default: main)
#   COHORT_SCHEMA      — schema for cohort output table (default: main)

# ── 0. Install missing packages ───────────────────────────────────────────────
required <- c("CirceR", "CohortGenerator", "duckdb", "DBI", "jsonlite", "dplyr")
missing  <- required[!required %in% installed.packages()[, "Package"]]

if (length(missing) > 0) {
  message("Installing missing packages: ", paste(missing, collapse = ", "))
  if (!requireNamespace("remotes", quietly = TRUE)) install.packages("remotes")
  cran_pkgs   <- intersect(missing, c("duckdb", "DBI", "jsonlite", "dplyr"))
  ohdsi_pkgs  <- setdiff(missing, cran_pkgs)
  if (length(cran_pkgs))  install.packages(cran_pkgs)
  if ("CirceR"          %in% ohdsi_pkgs) remotes::install_github("OHDSI/CirceR")
  if ("CohortGenerator" %in% ohdsi_pkgs) remotes::install_github("OHDSI/CohortGenerator")
}

suppressPackageStartupMessages({
  library(CirceR)
  library(CohortGenerator)
  library(duckdb)
  library(DBI)
  library(jsonlite)
  library(dplyr)
})

# ── 1. Paths from env ─────────────────────────────────────────────────────────
omop_path   <- Sys.getenv("OMOP_DUCKDB_PATH",   "data/mimiciv_omop.duckdb")
cohort_path <- Sys.getenv("COHORT_DUCKDB_PATH",  "data/cohorts.duckdb")
pheno_json  <- Sys.getenv("PHENOTYPES_JSON",     "data/phenotype_library.json")
cdm_schema  <- Sys.getenv("CDM_SCHEMA",          "cdm.main")
cohort_schema <- Sys.getenv("COHORT_SCHEMA",     "main")
output_csv  <- "outputs/cohort_counts.csv"

message("OMOP DuckDB:   ", omop_path)
message("Cohort DuckDB: ", cohort_path)
message("Phenotypes:    ", pheno_json)

# ── 2. Load phenotype definitions ─────────────────────────────────────────────
phenotypes <- fromJSON(pheno_json, simplifyVector = FALSE)
message("Loaded ", length(phenotypes), " phenotypes")

# ── 3. Build cohort definition set from ATLAS JSON ───────────────────────────
# Fetch raw ATLAS JSON for each cohort from PhenotypeLibrary GitHub
base_url <- "https://raw.githubusercontent.com/OHDSI/PhenotypeLibrary/main/inst/cohorts"

cohort_def_set <- CohortGenerator::createEmptyCohortDefinitionSet()

for (p in phenotypes) {
  cohort_id   <- as.integer(p$cohort_id)
  cohort_name <- p$name

  url <- paste0(base_url, "/", cohort_id, ".json")
  atlas_json <- tryCatch(
    readLines(url, warn = FALSE) |> paste(collapse = "\n"),
    error = function(e) {
      message("  SKIP ", cohort_id, " (", cohort_name, "): ", conditionMessage(e))
      NULL
    }
  )
  if (is.null(atlas_json)) next

  # CirceR translates ATLAS JSON → parameterised OMOP SQL
  cohort_sql <- tryCatch(
    CirceR::buildCohortQuery(
      expression = CirceR::cohortExpressionFromJson(atlas_json),
      options    = CirceR::createGenerateOptions(
        cohortIdFieldName = "cohort_definition_id",
        cohortId          = cohort_id,
        cdmSchema         = cdm_schema,
        targetTable       = "cohort",
        resultSchema      = cohort_schema,
        vocabularySchema  = cdm_schema,
        generateStats     = FALSE
      )
    ),
    error = function(e) {
      message("  SKIP ", cohort_id, " (", cohort_name, "): CirceR error — ", conditionMessage(e))
      NULL
    }
  )
  if (is.null(cohort_sql)) next

  cohort_def_set <- rbind(
    cohort_def_set,
    data.frame(
      cohortId         = cohort_id,
      cohortName       = cohort_name,
      sql              = cohort_sql,
      stringsAsFactors = FALSE
    )
  )
  message("  OK  ", cohort_id, ": ", cohort_name)
}

message("\nBuilt SQL for ", nrow(cohort_def_set), " cohorts")

# ── 4. Connect to databases ───────────────────────────────────────────────────
# Read-only connection to the OMOP CDM
omop_con <- dbConnect(duckdb(), omop_path, read_only = TRUE)

# Separate writeable DuckDB for cohort output
if (file.exists(cohort_path)) file.remove(cohort_path)
cohort_con <- dbConnect(duckdb(), cohort_path)

# Constrain memory and threads to prevent OOM on large cohort SQL
dbExecute(cohort_con, "SET memory_limit='15GB'")
dbExecute(cohort_con, "SET threads=2")
dbExecute(cohort_con, "SET preserve_insertion_order=false")

# Attach the OMOP DB as a read-only schema inside the cohort DB so CirceR SQL
# (which references cdm_schema tables) can join across both.
dbExecute(cohort_con, sprintf(
  "ATTACH '%s' AS cdm (READ_ONLY)", omop_path
))

# Create the cohort output table (CohortGenerator writes here)
dbExecute(cohort_con, "
  CREATE TABLE IF NOT EXISTS cohort (
    cohort_definition_id BIGINT,
    subject_id           BIGINT,
    cohort_start_date    DATE,
    cohort_end_date      DATE
  )
")

# ── 5. Execute each cohort SQL ────────────────────────────────────────────────
library(SqlRender)

# All temp tables CirceR may create — drop before each cohort to ensure clean state
TEMP_TABLES <- c(
  "Codesets", "qualified_events", "inclusion_events", "included_events",
  "strategy_ends", "cohort_rows", "final_cohort", "best_events",
  "inclusion_rules", "same_day_events"
)

cleanup_temp_tables <- function(con) {
  for (tbl in TEMP_TABLES) {
    tryCatch(
      dbExecute(con, paste0("DROP TABLE IF EXISTS ", tbl)),
      error = function(e) invisible(NULL)
    )
  }
}

results <- list()

for (i in seq_len(nrow(cohort_def_set))) {
  cid  <- cohort_def_set$cohortId[i]
  name <- cohort_def_set$cohortName[i]
  sql  <- cohort_def_set$sql[i]

  # render() collapses {condition}?{...}:{...} conditional blocks before translation
  rendered <- tryCatch(
    SqlRender::render(sql),
    error = function(e) { message("  RENDER FAIL ", cid, ": ", conditionMessage(e)); NULL }
  )
  if (is.null(rendered)) next

  # Translate to DuckDB dialect (schema names already baked in by createGenerateOptions)
  translated <- tryCatch(
    SqlRender::translate(rendered, targetDialect = "duckdb"),
    error = function(e) { message("  TRANSLATE FAIL ", cid, ": ", conditionMessage(e)); NULL }
  )
  if (is.null(translated)) next

  # Drop any leftover temp tables from a previous failed run before executing
  cleanup_temp_tables(cohort_con)

  # Split into individual statements and execute
  stmts <- SqlRender::splitSql(translated)
  ok <- tryCatch({
    for (stmt in stmts) {
      if (nchar(trimws(stmt)) > 0) dbExecute(cohort_con, stmt)
    }
    TRUE
  }, error = function(e) {
    message("  EXEC FAIL ", cid, " (", name, "): ", conditionMessage(e))
    cleanup_temp_tables(cohort_con)  # clean up even on failure
    FALSE
  })

  if (ok) {
    count <- dbGetQuery(
      cohort_con,
      sprintf("SELECT COUNT(DISTINCT subject_id) AS n FROM cohort WHERE cohort_definition_id = %d", cid)
    )$n
    results[[length(results) + 1]] <- data.frame(
      cohort_id      = cid,
      phenotype_name = name,
      patient_count  = count,
      stringsAsFactors = FALSE
    )
    message("  DONE ", cid, ": ", name, " — ", count, " patients")
  }
}

# ── 6. Write output CSV ───────────────────────────────────────────────────────
if (length(results) == 0) stop("No cohorts were successfully generated.")

dir.create("outputs", showWarnings = FALSE)
counts_df <- bind_rows(results)
write.csv(counts_df, output_csv, row.names = FALSE)
message("\nSaved ", nrow(counts_df), " cohort counts to ", output_csv)

dbDisconnect(omop_con)
dbDisconnect(cohort_con, shutdown = TRUE)
