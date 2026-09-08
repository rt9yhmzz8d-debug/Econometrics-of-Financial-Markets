
# ==============================================================================
# ECMT3150 GROUP PROJECT — IEM FED POLICY DIRECT DOWNLOADER V4
# Who Prices the Fed First?
# Iowa Electronic Markets (IEM) FedPolicy + FedPolicyB
# Mac / Windows / Linux friendly
# ==============================================================================
#
# BREAKTHROUGH
#   A public IEM data-recovery script identifies the live historical-price endpoint:
#
#   https://iemweb.biz.uiowa.edu/iem_pricehistory/pricehistory/
#       ?Market_ID=<ID>&Month=<Month>&Year=<Year>
#
#   Historical market IDs:
#     20 = FedPolicy  (1999-2001)
#     51 = FedPolicyB (2001-2023)
#
# PURPOSE
#   Download the historical IEM price-history tables DIRECTLY from the IEM
#   price-history endpoint, rather than scraping Wayback landing pages.
#
# OUTPUTS
#   ecmt3150_iem_v4_results/
#     01_request_audit.csv
#     02_iem_fedpolicy_raw.csv
#     03_iem_fedpolicy_clean.csv
#     04_contract_inventory.csv
#     05_monthly_coverage.csv
#     06_audit_summary.csv
#
# IMPORTANT
#   This is acquisition + cleaning only. Do not run econometrics until contract
#   definitions and meeting mappings have been manually checked.
# ==============================================================================

rm(list = ls())
options(scipen = 999, repos = c(CRAN = "https://cloud.r-project.org"))

# ==============================================================================
# 1. PACKAGES + FOLDERS
# ==============================================================================

R_PKGS <- c("tidyverse", "httr2", "rvest", "xml2", "lubridate")

missing <- R_PKGS[!R_PKGS %in% rownames(installed.packages())]
if (length(missing)) install.packages(missing)
invisible(lapply(R_PKGS, library, character.only = TRUE))

OUT_DIR <- "ecmt3150_iem_v4_results"
CACHE_DIR <- "ecmt3150_iem_v4_cache"

dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)
dir.create(CACHE_DIR, showWarnings = FALSE, recursive = TRUE)

cat("\n============================================================\n")
cat(" ECMT3150 — IEM FED POLICY DIRECT DOWNLOADER V4\n")
cat("============================================================\n")
cat("Direct IEM price-history endpoint\n")
cat("Market 20: FedPolicy  |  1999-2001\n")
cat("Market 51: FedPolicyB |  2001-2023\n\n")

# ==============================================================================
# 2. CONFIGURATION
# ==============================================================================

BASE_URL <- "https://iemweb.biz.uiowa.edu/iem_pricehistory/pricehistory/"

MARKETS <- tibble::tribble(
  ~market_id, ~market_code, ~start_year, ~end_year,
  20L,        "FedPolicy",   1999L,       2001L,
  51L,        "FedPolicyB",  2001L,       2023L
)

MONTHS <- month.name

REQUEST_PAUSE <- 0.15
HTTP_TRIES <- 4L
TIMEOUT_SEC <- 45

# ==============================================================================
# 3. HELPERS
# ==============================================================================

clean_names_simple <- function(x) {
  x |>
    stringr::str_to_lower() |>
    stringr::str_replace_all("[^a-z0-9]+", "_") |>
    stringr::str_replace_all("^_|_$", "")
}

safe_get <- function(url, tries = HTTP_TRIES) {
  last_error <- NA_character_

  for (i in seq_len(tries)) {
    ans <- tryCatch({
      req <- httr2::request(url) |>
        httr2::req_user_agent("USyd-ECMT3150-Academic-Research/4.0") |>
        httr2::req_timeout(TIMEOUT_SEC)

      resp <- httr2::req_perform(req)

      list(
        ok = TRUE,
        status = httr2::resp_status(resp),
        raw = httr2::resp_body_raw(resp),
        text = httr2::resp_body_string(resp),
        error = NA_character_
      )
    }, error = function(e) {
      last_error <<- conditionMessage(e)
      NULL
    })

    if (!is.null(ans)) return(ans)

    if (i < tries) {
      Sys.sleep(min(2^(i - 1), 8) + runif(1, 0, .2))
    }
  }

  list(
    ok = FALSE,
    status = NA_integer_,
    raw = raw(),
    text = "",
    error = last_error
  )
}

build_url <- function(market_id, month, year) {
  paste0(
    BASE_URL,
    "?Market_ID=", market_id,
    "&Month=", utils::URLencode(month),
    "&Year=", year
  )
}

parse_iem_page <- function(html_text) {
  if (!nzchar(html_text)) return(tibble())

  doc <- tryCatch(rvest::read_html(html_text), error = function(e) NULL)
  if (is.null(doc)) return(tibble())

  # The historical IEM page has a striped/static table. Use that first.
  node <- rvest::html_element(
    doc,
    "table.table.table--is-striped.table--static.table--width-default"
  )

  # Fallback: inspect every table if CSS class changed.
  if (inherits(node, "xml_missing") || length(node) == 0) {
    tabs <- tryCatch(rvest::html_table(doc, fill = TRUE), error = function(e) list())
    if (!length(tabs)) return(tibble())

    scores <- vapply(tabs, function(x) {
      if (!is.data.frame(x) || nrow(x) == 0) return(-Inf)
      nms <- clean_names_simple(names(x))
      10 * any(str_detect(nms, "date|day")) +
        10 * any(str_detect(nms, "contract|symbol|ticker")) +
        10 * any(str_detect(nms, "price|last|high|low|average|avg")) +
        5 * any(str_detect(nms, "volume|quantity|dollar")) +
        min(nrow(x), 100) / 100
    }, numeric(1))

    if (!any(is.finite(scores))) return(tibble())

    out <- as_tibble(tabs[[which.max(scores)]], .name_repair = "unique")
  } else {
    out <- tryCatch(
      as_tibble(rvest::html_table(node, fill = TRUE), .name_repair = "unique"),
      error = function(e) tibble()
    )
  }

  if (!nrow(out)) return(tibble())

  names(out) <- make.unique(clean_names_simple(names(out)), sep = "_")
  out
}

parse_date_flexible <- function(x) {
  z <- suppressWarnings(
    lubridate::parse_date_time(
      as.character(x),
      orders = c(
        "mdY", "m/d/Y", "m/d/y",
        "Ymd", "Y-m-d",
        "dmY", "d/m/Y", "d/m/y",
        "b d Y", "B d Y"
      ),
      quiet = TRUE,
      tz = "America/Chicago"
    )
  )

  as.Date(z, tz = "America/Chicago")
}

numeric_clean <- function(x) {
  suppressWarnings(
    as.numeric(
      str_replace_all(as.character(x), "[^0-9eE+\\-.]", "")
    )
  )
}

first_matching_col <- function(nms, patterns) {
  for (p in patterns) {
    hit <- nms[str_detect(nms, regex(p, ignore_case = TRUE))]
    if (length(hit)) return(hit[1])
  }
  NA_character_
}

# ==============================================================================
# 4. BUILD REQUEST GRID
# ==============================================================================

request_grid <- purrr::pmap_dfr(MARKETS, function(market_id, market_code, start_year, end_year) {
  tidyr::crossing(
    market_id = market_id,
    market_code = market_code,
    year = seq.int(start_year, end_year),
    month = factor(MONTHS, levels = MONTHS, ordered = TRUE)
  ) |>
    arrange(year, month) |>
    mutate(month = as.character(month))
}) |>
  mutate(
    url = purrr::pmap_chr(
      list(market_id, month, year),
      build_url
    )
  )

cat("[1/5] Request grid built: ", nrow(request_grid), " month-market requests\n", sep = "")

# ==============================================================================
# 5. DOWNLOAD DIRECT FROM IEM
# ==============================================================================

cat("\n[2/5] Downloading historical IEM price-history pages...\n")

audit_rows <- vector("list", nrow(request_grid))
data_rows <- list()

for (i in seq_len(nrow(request_grid))) {

  r <- request_grid[i, ]

  if (i %% 25 == 1 || i == nrow(request_grid)) {
    cat(sprintf(
      "      Request %d / %d | %s | %s %d\n",
      i, nrow(request_grid), r$market_code, r$month, r$year
    ))
  }

  ans <- safe_get(r$url)

  cache_file <- file.path(
    CACHE_DIR,
    sprintf("%s_%d_%02d.html",
            r$market_code,
            r$year,
            match(r$month, MONTHS))
  )

  if (ans$ok && nzchar(ans$text)) {
    writeLines(ans$text, cache_file, useBytes = TRUE)
  }

  tbl <- if (ans$ok) parse_iem_page(ans$text) else tibble()

  if (nrow(tbl)) {
    tbl <- tbl |>
      mutate(
        market_id = r$market_id,
        market_code = r$market_code,
        query_year = r$year,
        query_month = r$month,
        source_url = r$url,
        .before = 1
      )

    data_rows[[length(data_rows) + 1L]] <- tbl
  }

  audit_rows[[i]] <- tibble(
    market_id = r$market_id,
    market_code = r$market_code,
    query_year = r$year,
    query_month = r$month,
    url = r$url,
    http_ok = ans$ok,
    http_status = ans$status,
    bytes = length(ans$raw),
    parsed_rows = nrow(tbl),
    parsed_cols = ncol(tbl),
    cache_file = ifelse(ans$ok, cache_file, NA_character_),
    error = ans$error
  )

  Sys.sleep(REQUEST_PAUSE)
}

request_audit <- bind_rows(audit_rows)

# Historical IEM tables are not perfectly type-consistent across months.
# For example, a column can be numeric in one month and character in another.
# Preserve the raw values first by coercing EVERY parsed column to character
# before row-binding. Numeric/date conversion happens later in the cleaning step.
raw_data <- if (length(data_rows)) {
  data_rows_chr <- purrr::map(
    data_rows,
    ~ dplyr::mutate(.x, dplyr::across(dplyr::everything(), as.character))
  )

  dplyr::bind_rows(data_rows_chr)
} else {
  tibble()
}

write_csv(request_audit, file.path(OUT_DIR, "01_request_audit.csv"))
write_csv(raw_data, file.path(OUT_DIR, "02_iem_fedpolicy_raw.csv"))

cat("      Successful HTTP requests: ",
    sum(request_audit$http_ok %in% TRUE, na.rm = TRUE), "\n", sep = "")
cat("      Requests with parsed rows: ",
    sum(request_audit$parsed_rows > 0, na.rm = TRUE), "\n", sep = "")
cat("      Raw price-history rows: ", nrow(raw_data), "\n", sep = "")

# ==============================================================================
# 6. CLEAN / STANDARDISE
# ==============================================================================

cat("\n[3/5] Standardising IEM fields...\n")

clean_data <- tibble(
  market_id = integer(),
  market_code = character(),
  query_year = integer(),
  query_month = character(),
  observation_date = as.Date(character()),
  contract = character(),
  quantity = double(),
  dollar_volume = double(),
  low_price = double(),
  high_price = double(),
  average_price = double(),
  last_price = double(),
  source_url = character()
)

if (nrow(raw_data)) {

  nms <- names(raw_data)

  # ---------------------------------------------------------------------------
  # DIRECT IEM PRICE-HISTORY TABLE FORMAT
  # ---------------------------------------------------------------------------
  # The live IEM historical endpoint frequently returns unnamed table columns
  # (x1 ... x7). Inspection of the recovered data shows the schema is:
  #
  #   x1 = Date
  #   x2 = Contract
  #   x3 = Quantity
  #   x4 = Dollar Volume
  #   x5 = Low Price
  #   x6 = High Price
  #   x7 = Last Price
  #
  # Average transaction price is therefore Dollar Volume / Quantity when
  # Quantity > 0. This is preferable to guessing from x7, which is the LAST price.
  #
  # If named columns are ever returned in future, use those first and fall back
  # to the positional x1:x7 mapping.
  # ---------------------------------------------------------------------------

  date_col <- first_matching_col(
    nms,
    c("^date$", "^day$", "trade_date", "trading_date", "date")
  )
  if (is.na(date_col) && "x1" %in% nms) date_col <- "x1"

  contract_col <- first_matching_col(
    nms,
    c("^contract$", "contract_name", "^ticker$", "^symbol$")
  )
  if (is.na(contract_col) && "x2" %in% nms) contract_col <- "x2"

  quantity_col <- first_matching_col(
    nms,
    c("^quantity$", "^qty$", "contract_volume", "^volume$")
  )
  if (is.na(quantity_col) && "x3" %in% nms) quantity_col <- "x3"

  dollar_col <- first_matching_col(
    nms,
    c("dollar_volume", "dollar", "value")
  )
  if (is.na(dollar_col) && "x4" %in% nms) dollar_col <- "x4"

  low_col <- first_matching_col(
    nms,
    c("^low$", "low_price")
  )
  if (is.na(low_col) && "x5" %in% nms) low_col <- "x5"

  high_col <- first_matching_col(
    nms,
    c("^high$", "high_price")
  )
  if (is.na(high_col) && "x6" %in% nms) high_col <- "x6"

  last_col <- first_matching_col(
    nms,
    c("^last$", "last_price", "^close$", "closing")
  )
  if (is.na(last_col) && "x7" %in% nms) last_col <- "x7"

  avg_col <- first_matching_col(
    nms,
    c("^average$", "^avg$", "average_price", "avg_price")
  )

  cat("      Detected columns:\n")
  cat("        Date:          ", date_col, "\n", sep = "")
  cat("        Contract:      ", contract_col, "\n", sep = "")
  cat("        Quantity:      ", quantity_col, "\n", sep = "")
  cat("        Dollar volume: ", dollar_col, "\n", sep = "")
  cat("        Low:           ", low_col, "\n", sep = "")
  cat("        High:          ", high_col, "\n", sep = "")
  cat("        Average:       ",
      ifelse(is.na(avg_col), "derived as dollar_volume / quantity", avg_col),
      "\n", sep = "")
  cat("        Last:          ", last_col, "\n", sep = "")

  clean_data <- raw_data |>
    transmute(
      market_id = as.integer(market_id),
      market_code = as.character(market_code),
      query_year = as.integer(query_year),
      query_month = as.character(query_month),

      observation_date =
        if (!is.na(date_col))
          parse_date_flexible(.data[[date_col]])
        else
          as.Date(NA),

      contract =
        if (!is.na(contract_col))
          str_trim(as.character(.data[[contract_col]]))
        else
          NA_character_,

      quantity =
        if (!is.na(quantity_col))
          numeric_clean(.data[[quantity_col]])
        else NA_real_,

      dollar_volume =
        if (!is.na(dollar_col))
          numeric_clean(.data[[dollar_col]])
        else NA_real_,

      low_price =
        if (!is.na(low_col))
          numeric_clean(.data[[low_col]])
        else NA_real_,

      high_price =
        if (!is.na(high_col))
          numeric_clean(.data[[high_col]])
        else NA_real_,

      last_price =
        if (!is.na(last_col))
          numeric_clean(.data[[last_col]])
        else NA_real_,

      average_price_reported =
        if (!is.na(avg_col))
          numeric_clean(.data[[avg_col]])
        else NA_real_,

      average_price = case_when(
        is.finite(average_price_reported) ~ average_price_reported,
        is.finite(quantity) & quantity > 0 & is.finite(dollar_volume) ~
          dollar_volume / quantity,
        TRUE ~ NA_real_
      ),

      source_url = source_url
    ) |>
    select(-average_price_reported) |>
    filter(
      !is.na(observation_date) |
        !is.na(contract) |
        is.finite(last_price) |
        is.finite(average_price)
    ) |>
    distinct() |>
    arrange(observation_date, contract)
}

write_csv(clean_data, file.path(OUT_DIR, "03_iem_fedpolicy_clean.csv"))

cat("      Clean rows: ", nrow(clean_data), "\n", sep = "")
cat("      Distinct contracts: ",
    n_distinct(clean_data$contract, na.rm = TRUE), "\n", sep = "")
cat("      Pre-2008 dated rows: ",
    sum(clean_data$observation_date < as.Date("2008-01-01"), na.rm = TRUE),
    "\n", sep = "")
cat("      Earliest observation: ",
    as.character(if (all(is.na(clean_data$observation_date))) as.Date(NA) else
                   min(clean_data$observation_date, na.rm = TRUE)),
    "\n", sep = "")
cat("      Latest observation:   ",
    as.character(if (all(is.na(clean_data$observation_date))) as.Date(NA) else
                   max(clean_data$observation_date, na.rm = TRUE)),
    "\n", sep = "")

# ==============================================================================
# 7. CONTRACT + COVERAGE AUDITS
# ==============================================================================

cat("\n[4/5] Building contract and coverage inventories...\n")

contract_inventory <- clean_data |>
  filter(!is.na(contract), nzchar(contract)) |>
  group_by(market_id, market_code, contract) |>
  summarise(
    first_date = {
      z <- observation_date[!is.na(observation_date)]
      if (length(z)) min(z) else as.Date(NA)
    },
    last_date = {
      z <- observation_date[!is.na(observation_date)]
      if (length(z)) max(z) else as.Date(NA)
    },
    n_rows = n(),
    n_last_prices = sum(is.finite(last_price)),
    n_average_prices = sum(is.finite(average_price)),
    .groups = "drop"
  ) |>
  arrange(first_date, contract)

monthly_coverage <- request_audit |>
  mutate(
    requested_month = as.Date(
      sprintf(
        "%04d-%02d-01",
        query_year,
        match(query_month, MONTHS)
      )
    ),
    has_data = parsed_rows > 0
  ) |>
  select(
    market_id, market_code, requested_month,
    http_ok, http_status, parsed_rows, has_data
  ) |>
  arrange(requested_month, market_id)

write_csv(contract_inventory, file.path(OUT_DIR, "04_contract_inventory.csv"))
write_csv(monthly_coverage, file.path(OUT_DIR, "05_monthly_coverage.csv"))

# ==============================================================================
# 8. FINAL SUMMARY
# ==============================================================================

cat("\n[5/5] Writing summary...\n")

safe_min_date <- function(x) {
  z <- x[!is.na(x)]
  if (!length(z)) as.Date(NA) else min(z)
}

safe_max_date <- function(x) {
  z <- x[!is.na(x)]
  if (!length(z)) as.Date(NA) else max(z)
}

summary_tbl <- tibble(
  metric = c(
    "Total month-market requests",
    "Successful HTTP requests",
    "Requests containing parsed rows",
    "Raw IEM rows",
    "Clean standardised rows",
    "Distinct contracts",
    "Rows dated before 2008",
    "Earliest observation date",
    "Latest observation date",
    "Earliest FedPolicy observation",
    "Earliest FedPolicyB observation"
  ),
  value = c(
    as.character(nrow(request_audit)),
    as.character(sum(request_audit$http_ok %in% TRUE, na.rm = TRUE)),
    as.character(sum(request_audit$parsed_rows > 0, na.rm = TRUE)),
    as.character(nrow(raw_data)),
    as.character(nrow(clean_data)),
    as.character(n_distinct(clean_data$contract, na.rm = TRUE)),
    as.character(sum(clean_data$observation_date < as.Date("2008-01-01"), na.rm = TRUE)),
    as.character(safe_min_date(clean_data$observation_date)),
    as.character(safe_max_date(clean_data$observation_date)),
    as.character(safe_min_date(
      clean_data$observation_date[clean_data$market_id == 20]
    )),
    as.character(safe_min_date(
      clean_data$observation_date[clean_data$market_id == 51]
    ))
  )
)

write_csv(summary_tbl, file.path(OUT_DIR, "06_audit_summary.csv"))

cat("\n============================================================\n")
cat(" IEM DIRECT DOWNLOAD COMPLETE\n")
cat("============================================================\n")
cat("Successful HTTP requests:       ",
    sum(request_audit$http_ok %in% TRUE, na.rm = TRUE), "\n", sep = "")
cat("Requests with data:             ",
    sum(request_audit$parsed_rows > 0, na.rm = TRUE), "\n", sep = "")
cat("Raw price-history rows:         ", nrow(raw_data), "\n", sep = "")
cat("Clean rows:                     ", nrow(clean_data), "\n", sep = "")
cat("Distinct contracts:             ",
    n_distinct(clean_data$contract, na.rm = TRUE), "\n", sep = "")
cat("Pre-2008 dated rows:            ",
    sum(clean_data$observation_date < as.Date("2008-01-01"), na.rm = TRUE),
    "\n", sep = "")
cat("Earliest observation:           ",
    as.character(safe_min_date(clean_data$observation_date)), "\n", sep = "")
cat("Earliest FedPolicy observation: ",
    as.character(safe_min_date(
      clean_data$observation_date[clean_data$market_id == 20]
    )), "\n", sep = "")
cat("Earliest FedPolicyB observation:",
    as.character(safe_min_date(
      clean_data$observation_date[clean_data$market_id == 51]
    )), "\n", sep = "")

cat("\nOutputs saved to: ",
    normalizePath(OUT_DIR, mustWork = FALSE), "\n", sep = "")

if (nrow(raw_data) == 0) {
  cat("\nWARNING:\n")
  cat("The direct IEM endpoint returned no parseable rows.\n")
  cat("Open 01_request_audit.csv and send the final console block back.\n")
} else {
  cat("\nSUCCESS:\n")
  cat("We recovered IEM price-history rows directly from the IEM endpoint.\n")
  cat("Next inspect 03_iem_fedpolicy_clean.csv and 04_contract_inventory.csv.\n")
}

cat("============================================================\n\n")
