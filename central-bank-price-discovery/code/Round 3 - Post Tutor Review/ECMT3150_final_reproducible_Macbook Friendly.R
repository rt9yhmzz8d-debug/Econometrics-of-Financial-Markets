# ECMT3150 GROUP PROJECT — FINAL REPRODUCIBLE PIPELINE
# Who Prices the Fed First?
# Kalshi vs CME Fed Funds futures around scheduled FOMC decisions
#
# Final frozen design:
#   - final 7 calendar days, ending T-15m
#   - 15-minute grid
#   - VAR(1)
#   - Kalshi freshness <= 120m; futures freshness <= 10m
#   - exact synchronized blocks; no lag crosses a closure/gap
#   - primary meetings: Sep-2025 and Dec-2025
#   - primary inference: block-aware HAC(6) + Holm across 4 directional tests
#
# PORTABILITY:
#   1) Keep LSEG Workspace open and logged in.
#   2) R packages are installed automatically if missing.
#   3) The script tries to auto-discover a Python containing `lseg.data`.
#      If that fails, set this BEFORE running the script:
#      Sys.setenv(LSEG_PYTHON = "C:/path/to/python.exe")

rm(list = ls())
options(scipen = 999, repos = c(CRAN = "https://cloud.r-project.org"))

# ==============================================================================
# 1. SETUP
# ==============================================================================

R_PKGS <- c("tidyverse", "httr2", "lubridate", "reticulate", "sandwich")
missing <- R_PKGS[!R_PKGS %in% rownames(installed.packages())]
if (length(missing)) install.packages(missing)
invisible(lapply(R_PKGS, library, character.only = TRUE))

set.seed(315032)

OUT_DIR   <- "ecmt3150_final_results"
CACHE_DIR <- "ecmt3150_final_cache"
dir.create(OUT_DIR, showWarnings = FALSE)
dir.create(CACHE_DIR, showWarnings = FALSE)

# Portable LSEG/Python discovery.
lseg_python <- Sys.getenv("LSEG_PYTHON")
if (nzchar(lseg_python)) {
  reticulate::use_python(lseg_python, required = TRUE)
} else {
  cfg <- tryCatch(
    reticulate::py_discover_config(required_module = "lseg.data"),
    error = function(e) NULL
  )
  if (!is.null(cfg) && !is.null(cfg$python) && file.exists(cfg$python)) {
    reticulate::use_python(cfg$python, required = TRUE)
  }
}

if (!reticulate::py_module_available("lseg.data")) {
  stop(
    paste0(
      "\nPython module `lseg.data` was not found.\n",
      "Set LSEG_PYTHON to the Python executable where the LSEG Data Library is installed,\n",
      "restart R, keep LSEG Workspace open, and rerun this script.\n"
    )
  )
}

py_cfg <- reticulate::py_config()
ld <- reticulate::import("lseg.data", convert = TRUE)

tryCatch(
  ld$open_session(name = "desktop.workspace"),
  error = function(e) stop(
    "\nCould not connect to LSEG Workspace. Keep Workspace open/logged in.\n",
    conditionMessage(e)
  )
)

cat("LSEG connected via: ", py_cfg$python, "\n", sep = "")

# ==============================================================================
# 2. FROZEN CONFIGURATION
# ==============================================================================

GRID_MIN        <- 15L
PM_MAX_AGE      <- 120
FUT_MAX_AGE     <- 10
COHERENCE_TOL   <- 0.05
MATERIAL_MASS   <- 0.99
WINDOW_HOURS    <- 168
PREWINDOW_HOURS <- 168
HAC_LAG         <- 6L
ALPHA           <- 0.05
BVAR_LAMBDA     <- 0.25
BVAR_DRAWS      <- 5000L
BVAR_CI         <- 0.90
GIRF_HORIZON    <- 4L
TOL             <- 1e-10
RUN_SIX_MEETING_AUDIT <- TRUE  # set FALSE for the fastest primary-only rerun

# Six recent meetings used in the pre-inference availability audit.
# Exact expired RICs are fixed historical CME Fed Funds instruments.
MEETINGS <- tibble::tribble(
  ~meeting_id, ~event_ticker,            ~announcement_et,       ~target_lower, ~target_upper, ~futures_ric, ~futures_mode,
  "2025-09",   "KXFEDDECISION-25SEP",   "2025-09-17 14:00:00",  4.25,          4.50,          "FFU25^2",    "current_month_corrected",
  "2025-10",   "KXFEDDECISION-25OCT",   "2025-10-29 14:00:00",  4.00,          4.25,          "FFX25^2",    "next_month",
  "2025-12",   "KXFEDDECISION-25DEC",   "2025-12-10 14:00:00",  3.75,          4.00,          "FFZ25^2",    "current_month_corrected",
  "2026-01",   "KXFEDDECISION-26JAN",   "2026-01-28 14:00:00",  3.50,          3.75,          "FFG26^2",    "next_month",
  "2026-03",   "KXFEDDECISION-26MAR",   "2026-03-18 14:00:00",  3.50,          3.75,          "FFH26^2",    "current_month_corrected",
  "2026-04",   "KXFEDDECISION-26APR",   "2026-04-29 14:00:00",  3.50,          3.75,          "FFK26^2",    "next_month"
) |>
  dplyr::mutate(
    role = dplyr::case_when(
      meeting_id %in% c("2025-09", "2025-12") ~ "Primary",
      meeting_id == "2026-04" ~ "Excluded: no Kalshi expected-rate revisions",
      TRUE ~ "Descriptive only: sparse two-market repricing"
    )
  )

PRIMARY_MEETINGS <- c("2025-09", "2025-12")

KALSHI_MARKETS_URL <- "https://external-api.kalshi.com/trade-api/v2/historical/markets"
KALSHI_TRADES_URL  <- "https://external-api.kalshi.com/trade-api/v2/historical/trades"

# ==============================================================================
# 3. SMALL HELPERS
# ==============================================================================

nonzero_n <- function(x, tol = TOL) sum(is.finite(x) & abs(x) > tol, na.rm = TRUE)

asof_lookup <- function(source_time, source_value, grid_time) {
  ok <- !is.na(source_time) & is.finite(source_value)
  source_time <- source_time[ok]
  source_value <- source_value[ok]

  if (!length(source_time)) {
    return(tibble(
      grid_time = grid_time,
      value = NA_real_,
      source_time = as.POSIXct(NA, tz = "UTC"),
      age_minutes = NA_real_
    ))
  }

  o <- order(source_time)
  source_time <- source_time[o]
  source_value <- source_value[o]
  idx <- findInterval(as.numeric(grid_time), as.numeric(source_time))

  value <- rep(NA_real_, length(grid_time))
  used  <- rep(NA_real_, length(grid_time))
  good  <- idx > 0
  value[good] <- source_value[idx[good]]
  used[good]  <- as.numeric(source_time)[idx[good]]
  used_time <- lubridate::as_datetime(used, tz = "UTC")

  tibble(
    grid_time = grid_time,
    value = value,
    source_time = used_time,
    age_minutes = as.numeric(difftime(grid_time, used_time, units = "mins"))
  )
}

http_json <- function(url, query = list(), tries = 4L) {
  last_error <- NULL
  for (i in seq_len(tries)) {
    ans <- tryCatch({
      req <- httr2::request(url) |>
        httr2::req_user_agent("USyd-ECMT3150-Academic-Research") |>
        httr2::req_headers(Accept = "application/json") |>
        httr2::req_timeout(seconds = 30)
      if (length(query)) req <- do.call(httr2::req_url_query, c(list(req), query))
      resp <- httr2::req_perform(req)
      httr2::resp_check_status(resp)
      httr2::resp_body_json(resp, simplifyVector = TRUE)
    }, error = function(e) {
      last_error <<- conditionMessage(e)
      NULL
    })

    if (!is.null(ans)) return(ans)
    if (i < tries) Sys.sleep(min(2^(i - 1), 8) + runif(1, 0, 0.3))
  }
  stop("HTTP request failed: ", last_error)
}

records_tbl <- function(x) {
  if (is.null(x) || !length(x)) return(tibble())
  if (is.data.frame(x)) return(as_tibble(x))
  bind_rows(x)
}

first_numeric <- function(x, candidates) {
  nm <- names(x)
  for (cand in candidates) {
    hit <- which(toupper(nm) == toupper(cand))
    if (!length(hit)) hit <- grep(paste0("(^|[._ ])", cand, "$"), nm, ignore.case = TRUE)
    if (length(hit)) return(suppressWarnings(as.numeric(x[[hit[1]]])))
  }
  rep(NA_real_, nrow(x))
}

# ==============================================================================
# 4. LSEG FED FUNDS FUTURES
# ==============================================================================

format_lseg_time <- function(x) {
  format(lubridate::with_tz(x, "UTC"), "%Y-%m-%dT%H:%M:%SZ")
}

parse_lseg_times <- function(raw_times, start_time, end_time) {
  tzs <- c("Australia/Sydney", "UTC", "America/New_York")
  parsed <- lapply(tzs, function(z) {
    lubridate::with_tz(lubridate::ymd_hms(raw_times, tz = z, quiet = TRUE), "UTC")
  })
  scores <- vapply(parsed, function(x) {
    good <- !is.na(x)
    if (!any(good)) return(-Inf)
    mean(x[good] >= start_time - hours(2) & x[good] <= end_time + hours(2))
  }, numeric(1))
  parsed[[which.max(scores)]]
}

load_futures <- function(ric, start_time, end_time) {
  cache <- file.path(
    CACHE_DIR,
    paste0("LSEG_", gsub("[^A-Za-z0-9]", "_", ric), "_",
           format(start_time, "%Y%m%d%H%M"), "_", format(end_time, "%Y%m%d%H%M"), ".csv")
  )

  if (file.exists(cache)) {
    return(readr::read_csv(
      cache, show_col_types = FALSE,
      col_types = cols(
        bar_start_utc = col_datetime(),
        information_time_utc = col_datetime(),
        bid = col_double(), ask = col_double(),
        last_trade = col_double(), futures_price = col_double()
      )
    ))
  }

  raw <- tryCatch(
    as.data.frame(ld$get_history(
      universe = ric,
      start = format_lseg_time(start_time - minutes(30)),
      end = format_lseg_time(end_time + minutes(10)),
      interval = "5min"
    )),
    error = function(e) stop("LSEG failed for ", ric, ": ", conditionMessage(e))
  )

  if (!nrow(raw)) stop("LSEG returned zero rows for ", ric)

  bar_time <- parse_lseg_times(
    rownames(raw),
    start_time - minutes(30),
    end_time + minutes(10)
  )
  if (mean(is.na(bar_time)) > 0.05) stop("Could not parse LSEG timestamps for ", ric)

  bid  <- first_numeric(raw, "BID")
  ask  <- first_numeric(raw, "ASK")
  last <- first_numeric(raw, c("TRDPRC_1", "LAST", "CLOSE"))
  mid  <- ifelse(is.finite(bid) & is.finite(ask) & ask >= bid, (bid + ask) / 2, NA_real_)
  px   <- ifelse(is.finite(mid), mid, last)

  out <- tibble(
    bar_start_utc = bar_time,
    information_time_utc = bar_time + minutes(5),
    bid = bid, ask = ask, last_trade = last, futures_price = px
  ) |>
    filter(is.finite(futures_price)) |>
    arrange(information_time_utc)

  med <- median(out$futures_price, na.rm = TRUE)
  if (!is.finite(med) || med <= 90 || med >= 100) {
    stop("Fed Funds price sanity check failed for ", ric, "; median=", med)
  }

  write_csv(out, cache)
  out
}

# ==============================================================================
# 5. KALSHI HISTORICAL MARKETS + TRADES
# ==============================================================================

policy_move_bp <- function(text) {
  x <- stringr::str_to_lower(stringr::str_squish(as.character(text)))
  if (is.na(x) || !nzchar(x)) return(NA_real_)
  if (str_detect(x, "no change|maintain|unchanged|hike rates by 0|cut rates by 0")) return(0)

  direction <- case_when(
    str_detect(x, "cut|decrease|lower") ~ -1,
    str_detect(x, "hike|increase|raise") ~ 1,
    TRUE ~ NA_real_
  )
  magnitude <- suppressWarnings(readr::parse_number(x))
  if (!is.finite(direction) || !is.finite(magnitude)) return(NA_real_)

  # Strict open tails are mapped to the nearest feasible 25bp-grid outcome.
  if (str_detect(x, ">|greater than|more than")) magnitude <- magnitude + 25
  direction * magnitude
}

load_kalshi_markets <- function(event_ticker) {
  pieces <- list()
  cursor <- NULL

  repeat {
    q <- list(event_ticker = event_ticker, limit = 1000)
    if (!is.null(cursor) && nzchar(cursor)) q$cursor <- cursor
    ans <- http_json(KALSHI_MARKETS_URL, q)
    pieces[[length(pieces) + 1L]] <- records_tbl(ans$markets)
    cursor <- if (is.null(ans$cursor) || !length(ans$cursor)) "" else as.character(ans$cursor[[1]])
    if (!nzchar(cursor)) break
  }

  raw <- bind_rows(pieces)
  if (!nrow(raw)) stop("Kalshi returned no markets for ", event_ticker)

  # Required fields are stable for these historical FOMC markets.
  out <- raw |>
    transmute(
      ticker = as.character(ticker),
      title = as.character(title),
      subtitle = as.character(subtitle),
      yes_sub_title = as.character(yes_sub_title),
      close_time = ymd_hms(as.character(close_time), tz = "UTC", quiet = TRUE)
    ) |>
    mutate(
      label = coalesce(
        na_if(str_squish(yes_sub_title), ""),
        na_if(str_squish(subtitle), ""),
        na_if(str_squish(title), "")
      ),
      delta_bp = map_dbl(label, policy_move_bp)
    ) |>
    filter(!is.na(ticker), is.finite(delta_bp)) |>
    distinct(ticker, .keep_all = TRUE) |>
    arrange(delta_bp)

  if (nrow(out) < 3 || sum(out$delta_bp == 0) != 1 ||
      !any(out$delta_bp < 0) || !any(out$delta_bp > 0) ||
      any(duplicated(out$delta_bp))) {
    stop(
      "Kalshi outcome mapping failed for ", event_ticker, ": ",
      paste0(out$label, " -> ", out$delta_bp, "bp", collapse = "; ")
    )
  }

  out |> select(ticker, label, delta_bp, close_time)
}

load_kalshi_trades <- function(ticker, start_time, end_time, meeting_id) {
  meeting_dir <- file.path(CACHE_DIR, "kalshi_7d", meeting_id)
  dir.create(meeting_dir, recursive = TRUE, showWarnings = FALSE)
  cache <- file.path(meeting_dir, paste0(gsub("[^A-Za-z0-9_-]", "_", ticker), ".csv"))

  if (file.exists(cache)) {
    return(read_csv(
      cache, show_col_types = FALSE,
      col_types = cols(
        trade_id = col_character(), ticker = col_character(),
        yes_probability = col_double(), timestamp = col_datetime()
      )
    ))
  }

  pieces <- list()
  cursor <- NULL

  repeat {
    q <- list(
      ticker = ticker,
      min_ts = as.integer(start_time),
      max_ts = as.integer(end_time),
      limit = 1000,
      is_block_trade = "false"
    )
    if (!is.null(cursor) && nzchar(cursor)) q$cursor <- cursor

    ans <- http_json(KALSHI_TRADES_URL, q)
    raw <- records_tbl(ans$trades)

    if (nrow(raw)) {
      pieces[[length(pieces) + 1L]] <- raw |>
        transmute(
          trade_id = as.character(trade_id),
          ticker = as.character(ticker),
          yes_probability = suppressWarnings(as.numeric(yes_price_dollars)),
          timestamp = ymd_hms(as.character(created_time), tz = "UTC", quiet = TRUE)
        ) |>
        filter(!is.na(timestamp), between(yes_probability, 0, 1))
    }

    cursor <- if (is.null(ans$cursor) || !length(ans$cursor)) "" else as.character(ans$cursor[[1]])
    if (!nzchar(cursor)) break
    Sys.sleep(0.05)
  }

  out <- bind_rows(pieces) |>
    distinct(trade_id, .keep_all = TRUE) |>
    arrange(timestamp)

  if (nrow(out)) write_csv(out, cache)
  out
}

load_kalshi <- function(meeting_id, event_ticker, window_start, window_end) {
  markets <- load_kalshi_markets(event_ticker)
  archive_start <- window_start - hours(PREWINDOW_HOURS)

  trades <- map_dfr(markets$ticker, function(tk) {
    load_kalshi_trades(tk, archive_start, window_end, meeting_id)
  })
  if (!nrow(trades)) stop("No Kalshi trades for ", meeting_id)

  updates <- trades |>
    inner_join(markets |> select(ticker, label, delta_bp), by = "ticker") |>
    group_by(ticker, label, delta_bp, timestamp) |>
    summarise(yes_probability = median(yes_probability), .groups = "drop") |>
    arrange(timestamp)

  seeded <- updates |> filter(timestamp <= window_start) |> distinct(ticker) |> pull(ticker)
  missing_seed <- setdiff(markets$ticker, seeded)
  if (length(missing_seed)) {
    stop("No pre-window Kalshi seed trade for: ", paste(missing_seed, collapse = ", "))
  }

  list(
    markets = markets |> transmute(condition_id = ticker, label, delta_bp),
    updates = updates |> rename(condition_id = ticker)
  )
}

# ==============================================================================
# 6. COMMON 15-MINUTE EXPECTED-RATE GRID
# ==============================================================================

# This basis affects levels, not revisions; failure falls back to zero.
get_effr_basis <- function(reference_start, target_mid) {
  tryCatch({
    cutoff <- as.Date(with_tz(reference_start, "America/New_York"))
    ans <- http_json(
      "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json",
      list(
        startDate = format(cutoff - 70, "%Y-%m-%d"),
        endDate = format(cutoff - 1, "%Y-%m-%d"),
        type = "rate"
      )
    )
    x <- as_tibble(ans$refRates) |>
      transmute(date = as.Date(effectiveDate), effr = as.numeric(percentRate)) |>
      filter(is.finite(effr), date < cutoff) |>
      arrange(date) |>
      slice_tail(n = 20)
    if (nrow(x) < 20) stop("insufficient EFFR history")
    mean(x$effr - target_mid)
  }, error = function(e) {
    warning("EFFR basis unavailable; using zero. VAR revisions are unaffected.")
    0
  })
}

build_pm_grid <- function(pm, grid) {
  long <- map_dfr(seq_len(nrow(pm$markets)), function(i) {
    m <- pm$markets[i, ]
    u <- pm$updates |> filter(condition_id == m$condition_id)
    asof_lookup(u$timestamp, u$yes_probability, grid) |>
      transmute(
        grid_time, probability = value, age_minutes,
        condition_id = m$condition_id, delta_bp = m$delta_bp
      )
  })

  snapshot <- function(x) {
    if (any(!is.finite(x$probability))) {
      return(tibble(pm_probability_sum = NA_real_, pm_expected_change_bp = NA_real_, pm_valid = FALSE))
    }
    s <- sum(x$probability)
    if (!is.finite(s) || s <= 0) {
      return(tibble(pm_probability_sum = s, pm_expected_change_bp = NA_real_, pm_valid = FALSE))
    }

    p <- x$probability / s
    ord <- order(p, decreasing = TRUE)
    material_sorted <- c(0, head(cumsum(p[ord]), -1)) < MATERIAL_MASS
    material <- rep(FALSE, length(p))
    material[ord] <- material_sorted
    ages <- x$age_minutes[material]

    fresh <- length(ages) > 0 && all(is.finite(ages)) &&
      all(ages >= 0) && all(ages <= PM_MAX_AGE)

    tibble(
      pm_probability_sum = s,
      pm_expected_change_bp = sum(p * x$delta_bp),
      pm_valid = abs(s - 1) <= COHERENCE_TOL && fresh
    )
  }

  long |>
    group_by(grid_time) |>
    group_modify(~ snapshot(.x)) |>
    ungroup()
}

build_futures_grid <- function(futures, grid, target_mid, basis, mode, announcement_et) {
  z <- asof_lookup(futures$information_time_utc, futures$futures_price, grid)
  ann <- ymd_hms(announcement_et, tz = "America/New_York")
  d <- day(ann)
  D <- days_in_month(as.Date(ann))
  implied <- 100 - z$value

  if (mode == "next_month") {
    post_effr <- implied
  } else if (mode == "current_month_corrected") {
    post_effr <- (D * implied - d * (target_mid + basis)) / (D - d)
  } else stop("Unknown futures_mode: ", mode)

  tibble(
    grid_time = grid,
    futures_price = z$value,
    futures_age_minutes = z$age_minutes,
    fut_expected_change_bp = (post_effr - basis - target_mid) * 100,
    fut_valid = is.finite(z$value) & is.finite(z$age_minutes) &
      z$age_minutes >= 0 & z$age_minutes <= FUT_MAX_AGE
  )
}

build_bundle <- function(meeting_row) {
  id <- meeting_row$meeting_id[[1]]
  ann_et <- ymd_hms(meeting_row$announcement_et[[1]], tz = "America/New_York")
  ann_utc <- with_tz(ann_et, "UTC")
  window_end <- ann_utc - minutes(15)
  window_start <- window_end - hours(WINDOW_HOURS)
  target_mid <- mean(c(meeting_row$target_lower[[1]], meeting_row$target_upper[[1]]))

  message("Loading ", id, " ...")
  futures <- load_futures(meeting_row$futures_ric[[1]], window_start, window_end)
  pm <- load_kalshi(id, meeting_row$event_ticker[[1]], window_start, window_end)
  basis <- get_effr_basis(window_end - hours(48), target_mid)

  grid <- seq(window_start, window_end, by = paste(GRID_MIN, "mins"))
  combined <- left_join(
    build_pm_grid(pm, grid),
    build_futures_grid(
      futures, grid, target_mid, basis,
      meeting_row$futures_mode[[1]], meeting_row$announcement_et[[1]]
    ),
    by = "grid_time"
  ) |>
    arrange(grid_time) |>
    mutate(valid_level = pm_valid & fut_valid)

  list(
    meeting_id = id,
    combined = combined,
    pm = pm,
    futures = futures,
    target_mid = target_mid
  )
}

# ==============================================================================
# 7. SYNCHRONIZED BLOCKS + FROZEN VAR(1) SAMPLE
# ==============================================================================

make_sync_model <- function(combined) {
  joint <- combined |>
    filter(valid_level) |>
    arrange(grid_time)

  if (!nrow(joint)) return(list(path = joint, model = tibble()))

  gap_min <- c(NA_real_, diff(as.numeric(joint$grid_time)) / 60)
  joint <- joint |>
    mutate(
      sync_block_id = cumsum(is.na(gap_min) | abs(gap_min - GRID_MIN) > 1e-8)
    ) |>
    group_by(sync_block_id) |>
    mutate(
      d_pm_sync = pm_expected_change_bp - lag(pm_expected_change_bp),
      d_fut_sync = fut_expected_change_bp - lag(fut_expected_change_bp),
      pm_l1_sync = lag(d_pm_sync),
      fut_l1_sync = lag(d_fut_sync)
    ) |>
    ungroup()

  model <- joint |>
    filter(if_all(
      c(d_pm_sync, d_fut_sync, pm_l1_sync, fut_l1_sync),
      is.finite
    ))

  list(path = joint, model = model)
}

screen_one <- function(id, bundle, sync) {
  c <- bundle$combined
  d <- sync$model

  X <- if (nrow(d)) model.matrix(~ pm_l1_sync + fut_l1_sync, d) else matrix(nrow = 0, ncol = 3)
  block_sizes <- sync$path |> count(sync_block_id, name = "n")
  role <- MEETINGS |> filter(meeting_id == id) |> pull(role)

  tibble(
    meeting_id = id,
    role = role,
    calendar_joint_share = mean(c$valid_level, na.rm = TRUE),
    joint_given_futures = sum(c$valid_level, na.rm = TRUE) / sum(c$fut_valid, na.rm = TRUE),
    synchronized_blocks = n_distinct(sync$path$sync_block_id),
    longest_block_hours = ifelse(nrow(block_sizes), (max(block_sizes$n) - 1) * GRID_MIN / 60, 0),
    VAR1_rows = nrow(d),
    PM_revisions = nonzero_n(d$d_pm_sync),
    FUT_revisions = nonzero_n(d$d_fut_sync),
    lagged_FUT_predictor_events = nonzero_n(d$fut_l1_sync),
    rank = ifelse(nrow(d), qr(X)$rank, 0),
    columns = ifelse(nrow(d), ncol(X), 3),
    mechanically_estimable = nrow(d) >= 100 &&
      qr(X)$rank == ncol(X) &&
      sd(d$d_pm_sync) > 0 && sd(d$d_fut_sync) > 0
  )
}

# Load audit meetings once. Descriptive failures do not stop the primary analysis.
RUN_MEETINGS <- if (RUN_SIX_MEETING_AUDIT) MEETINGS else MEETINGS |> filter(meeting_id %in% PRIMARY_MEETINGS)
bundles <- setNames(vector("list", nrow(MEETINGS)), MEETINGS$meeting_id)
sync_data <- setNames(vector("list", nrow(MEETINGS)), MEETINGS$meeting_id)
screening <- list()

for (i in seq_len(nrow(RUN_MEETINGS))) {
  m <- RUN_MEETINGS[i, ]
  id <- m$meeting_id[[1]]

  ans <- tryCatch({
    b <- build_bundle(m)
    s <- make_sync_model(b$combined)
    bundles[[id]] <- b
    sync_data[[id]] <- s
    screen_one(id, b, s)
  }, error = function(e) {
    tibble(
      meeting_id = id, role = m$role[[1]],
      calendar_joint_share = NA_real_, joint_given_futures = NA_real_,
      synchronized_blocks = NA_integer_, longest_block_hours = NA_real_,
      VAR1_rows = NA_integer_, PM_revisions = NA_integer_,
      FUT_revisions = NA_integer_, lagged_FUT_predictor_events = NA_integer_,
      rank = NA_integer_, columns = 3L, mechanically_estimable = FALSE,
      error = conditionMessage(e)
    )
  })

  screening[[id]] <- ans
}

screening <- bind_rows(screening)
write_csv(screening, file.path(OUT_DIR, "01_preinference_screening.csv"))
print(screening, width = Inf)

for (id in PRIMARY_MEETINGS) {
  if (is.null(sync_data[[id]]) || !nrow(sync_data[[id]]$model)) {
    stop("Primary meeting ", id, " could not be constructed. See screening output.")
  }
  write_csv(sync_data[[id]]$model, file.path(OUT_DIR, paste0("model_data_", id, ".csv")))
}

# ==============================================================================
# 8. BLOCK-AWARE FREQUENTIST INFERENCE
# ==============================================================================

safe_inv <- function(M, ridge = 1e-12) {
  tryCatch(solve(M), error = function(e) solve(M + diag(ridge, nrow(M))))
}

block_hac <- function(fit, data, L = HAC_LAG) {
  X <- model.matrix(fit)
  u <- residuals(fit)
  G <- X * as.numeric(u)
  meat <- crossprod(G)
  times <- as.numeric(data$grid_time)
  blocks <- data$sync_block_id
  step <- GRID_MIN * 60

  for (h in seq_len(L)) {
    Gh <- matrix(0, ncol(X), ncol(X))
    for (b in unique(blocks)) {
      idx <- which(blocks == b)
      if (length(idx) < 2) next
      match_lag <- match(round(times[idx] - h * step), round(times[idx]))
      good <- which(!is.na(match_lag))
      if (length(good)) {
        Gh <- Gh + t(G[idx[good], , drop = FALSE]) %*%
          G[idx[match_lag[good]], , drop = FALSE]
      }
    }
    w <- 1 - h / (L + 1)
    meat <- meat + w * (Gh + t(Gh))
  }

  bread <- safe_inv(crossprod(X))
  V <- bread %*% meat %*% bread
  V <- nrow(X) / (nrow(X) - ncol(X)) * V
  (V + t(V)) / 2
}

wald_term <- function(fit, term, V, robust = TRUE) {
  coef_names <- names(stats::coef(fit))
  j <- match(term, coef_names)

  if (is.na(j)) {
    stop(
      "Term '", term, "' was not found in the fitted model. Available terms: ",
      paste(coef_names, collapse = ", ")
    )
  }

  b <- unname(stats::coef(fit)[j])
  variance_j <- unname(V[j, j])

  if (!is.finite(b) || !is.finite(variance_j) || variance_j <= 0) {
    stop(
      "Non-finite coefficient/variance for term '", term,
      "'. coefficient=", b, ", variance=", variance_j
    )
  }

  se <- sqrt(variance_j)
  stat <- (b / se)^2

  p <- if (robust) {
    stats::pchisq(stat, df = 1, lower.tail = FALSE)
  } else {
    stats::pf(stat, df1 = 1, df2 = stats::df.residual(fit), lower.tail = FALSE)
  }

  list(
    coef = as.numeric(b),
    se = as.numeric(se),
    stat = as.numeric(stat),
    p = as.numeric(p)
  )
}

test_direction <- function(fit, data, term) {
  classical <- wald_term(fit, term, stats::vcov(fit), robust = FALSE)
  hc3       <- wald_term(fit, term, sandwich::vcovHC(fit, type = "HC3"))
  hac       <- wald_term(fit, term, block_hac(fit, data), robust = TRUE)

  tibble(
    coefficient = hac$coef,
    conventional_se = classical$se,
    conventional_F = classical$stat,
    conventional_p = classical$p,
    HC3_se = hc3$se,
    HC3_Wald = hc3$stat,
    HC3_p = hc3$p,
    block_HAC_lag = HAC_LAG,
    block_HAC_minutes = HAC_LAG * GRID_MIN,
    block_HAC_se = hac$se,
    block_HAC_Wald = hac$stat,
    block_HAC_p = hac$p
  )
}

primary_fits <- list()
primary_tests <- list()
stability <- list()

for (id in PRIMARY_MEETINGS) {
  d <- sync_data[[id]]$model
  fit_pm  <- lm(d_pm_sync  ~ pm_l1_sync + fut_l1_sync, data = d)
  fit_fut <- lm(d_fut_sync ~ pm_l1_sync + fut_l1_sync, data = d)
  primary_fits[[id]] <- list(pm = fit_pm, fut = fit_fut, data = d)

  primary_tests[[id]] <- bind_rows(
    test_direction(fit_pm, d, "fut_l1_sync") |>
      mutate(meeting_id = id, direction_code = "FUT_to_K",
             direction = "Fed Funds futures -> Kalshi", .before = 1),
    test_direction(fit_fut, d, "pm_l1_sync") |>
      mutate(meeting_id = id, direction_code = "K_to_FUT",
             direction = "Kalshi -> Fed Funds futures", .before = 1)
  )

  A <- matrix(c(
    coef(fit_pm)["pm_l1_sync"],  coef(fit_pm)["fut_l1_sync"],
    coef(fit_fut)["pm_l1_sync"], coef(fit_fut)["fut_l1_sync"]
  ), 2, byrow = TRUE)
  roots <- eigen(A, only.values = TRUE)$values
  stability[[id]] <- tibble(
    meeting_id = id,
    max_root_modulus = max(Mod(roots)),
    stable_VAR = max(Mod(roots)) < 1
  )
}

primary_tests <- bind_rows(primary_tests) |>
  mutate(
    block_HAC_p_Holm = p.adjust(block_HAC_p, method = "holm"),
    significant_Holm = block_HAC_p_Holm < ALPHA
  ) |>
  arrange(meeting_id, direction_code)

# Fail loudly if the primary inferential table is incomplete.
primary_numeric_cols <- c(
  "coefficient",
  "conventional_se", "conventional_F", "conventional_p",
  "HC3_se", "HC3_Wald", "HC3_p",
  "block_HAC_se", "block_HAC_Wald", "block_HAC_p", "block_HAC_p_Holm"
)

bad_primary <- primary_tests |>
  summarise(across(all_of(primary_numeric_cols), ~ any(!is.finite(.x)))) |>
  unlist(use.names = TRUE)

if (any(bad_primary)) {
  stop(
    "Primary inference produced non-finite values in: ",
    paste(names(bad_primary)[bad_primary], collapse = ", "),
    ". The script is stopping before writing misleading results."
  )
}

classification <- primary_tests |>
  select(meeting_id, direction_code, significant_Holm) |>
  pivot_wider(names_from = direction_code, values_from = significant_Holm) |>
  mutate(
    classification = case_when(
      FUT_to_K & !K_to_FUT ~ "Fed Funds futures-led",
      !FUT_to_K & K_to_FUT ~ "Kalshi-led",
      FUT_to_K & K_to_FUT ~ "Bidirectional predictive content",
      TRUE ~ "No directional leadership detected"
    )
  )

stability <- bind_rows(stability)
write_csv(primary_tests, file.path(OUT_DIR, "02_primary_granger_blockHAC_Holm.csv"))
write_csv(classification, file.path(OUT_DIR, "03_meeting_classification.csv"))
write_csv(stability, file.path(OUT_DIR, "04_VAR1_stability.csv"))

cat("\nPRIMARY RESULTS\n")
print(primary_tests, width = Inf)
print(classification, width = Inf)

# ==============================================================================
# 9. CONJUGATE SHRINKAGE BVAR(1) + GENERALIZED IRFs
# ==============================================================================

make_pd <- function(M, eps = 1e-10) {
  M <- (M + t(M)) / 2
  if (!inherits(try(chol(M), silent = TRUE), "try-error")) return(M)
  for (i in 0:8) {
    z <- M + diag(eps * 10^i, nrow(M))
    if (!inherits(try(chol(z), silent = TRUE), "try-error")) return(z)
  }
  stop("Matrix could not be made positive definite.")
}

post_summary <- function(x, level = BVAR_CI) {
  a <- (1 - level) / 2
  tibble(
    median = median(x),
    lower = unname(quantile(x, a)),
    upper = unname(quantile(x, 1 - a)),
    Pr_positive = mean(x > 0),
    Pr_negative = mean(x < 0)
  )
}

matrix_power <- function(A, h) {
  if (h == 0) return(diag(nrow(A)))
  out <- diag(nrow(A))
  for (i in seq_len(h)) out <- out %*% A
  out
}

fit_bvar1 <- function(d, id, seed) {
  set.seed(seed)
  Y <- cbind(d$d_pm_sync, d$d_fut_sync)
  X <- cbind(1, d$pm_l1_sync, d$fut_l1_sync)
  n <- nrow(X); K <- ncol(X); M <- ncol(Y)

  Bols <- safe_inv(crossprod(X)) %*% crossprod(X, Y)
  Eols <- Y - X %*% Bols
  Sigma_ols <- make_pd(crossprod(Eols) / n)

  B0 <- matrix(0, K, M)
  V0 <- diag(c(1e6, BVAR_LAMBDA^2, BVAR_LAMBDA^2))
  V0i <- safe_inv(V0)
  nu0 <- M + 2L
  S0 <- Sigma_ols * (nu0 - M - 1)

  Vn <- safe_inv(V0i + crossprod(X))
  Bn <- Vn %*% (V0i %*% B0 + crossprod(X, Y))
  E <- Y - X %*% Bn
  D <- Bn - B0
  Sn <- make_pd(S0 + crossprod(E) + t(D) %*% V0i %*% D)
  nun <- nu0 + n
  LV <- t(chol(make_pd(Vn)))

  fut_to_k <- k_to_fut <- max_root <- numeric(BVAR_DRAWS)
  girf_fk <- girf_kf <- matrix(NA_real_, BVAR_DRAWS, GIRF_HORIZON + 1L)

  for (r in seq_len(BVAR_DRAWS)) {
    W <- rWishart(1, nun, safe_inv(Sn))[, , 1]
    Sigma <- make_pd(safe_inv(W))
    B <- Bn + LV %*% matrix(rnorm(K * M), K, M) %*% chol(Sigma)
    A <- t(B[2:3, , drop = FALSE])

    fut_to_k[r] <- A[1, 2]
    k_to_fut[r] <- A[2, 1]
    max_root[r] <- max(Mod(eigen(A, only.values = TRUE)$values))

    for (h in 0:GIRF_HORIZON) {
      Phi <- matrix_power(A, h)
      girf_fk[r, h + 1] <- (Phi %*% Sigma[, 2, drop = FALSE] / sqrt(Sigma[2, 2]))[1]
      girf_kf[r, h + 1] <- (Phi %*% Sigma[, 1, drop = FALSE] / sqrt(Sigma[1, 1]))[2]
    }
  }

  coef_table <- bind_rows(
    post_summary(fut_to_k) |> mutate(meeting_id = id, direction_code = "FUT_to_K",
                                     direction = "Fed Funds futures -> Kalshi", .before = 1),
    post_summary(k_to_fut) |> mutate(meeting_id = id, direction_code = "K_to_FUT",
                                     direction = "Kalshi -> Fed Funds futures", .before = 1)
  )

  girf_table <- map_dfr(0:GIRF_HORIZON, function(h) {
    bind_rows(
      post_summary(girf_fk[, h + 1]) |>
        mutate(meeting_id = id, direction_code = "FUT_to_K",
               direction = "Fed Funds futures -> Kalshi",
               horizon = h, horizon_minutes = h * GRID_MIN, .before = 1),
      post_summary(girf_kf[, h + 1]) |>
        mutate(meeting_id = id, direction_code = "K_to_FUT",
               direction = "Kalshi -> Fed Funds futures",
               horizon = h, horizon_minutes = h * GRID_MIN, .before = 1)
    )
  })

  list(
    coefficients = coef_table,
    girf = girf_table,
    stability = tibble(
      meeting_id = id,
      stable_draw_share = mean(max_root < 1),
      median_max_root = median(max_root),
      q95_max_root = unname(quantile(max_root, 0.95))
    )
  )
}

bvar <- map2(
  PRIMARY_MEETINGS,
  seq_along(PRIMARY_MEETINGS),
  ~ fit_bvar1(primary_fits[[.x]]$data, .x, 315032L + .y)
)

bvar_coef <- bind_rows(map(bvar, "coefficients"))
bvar_girf <- bind_rows(map(bvar, "girf"))
bvar_stability <- bind_rows(map(bvar, "stability"))

write_csv(bvar_coef, file.path(OUT_DIR, "05_BVAR_coefficients.csv"))
write_csv(bvar_girf, file.path(OUT_DIR, "06_BVAR_GIRF.csv"))
write_csv(bvar_stability, file.path(OUT_DIR, "07_BVAR_stability.csv"))

# ==============================================================================
# 10. LEAVE-ONE-FUTURES-PREDICTOR-EVENT-OUT SENSITIVITY
# ==============================================================================

loo_one <- function(id) {
  d <- primary_fits[[id]]$data
  rows <- which(is.finite(d$fut_l1_sync) & abs(d$fut_l1_sync) > TOL)

  map_dfr(seq_along(rows), function(j) {
    r <- rows[j]
    dd <- d[-r, , drop = FALSE]
    fit <- lm(d_pm_sync ~ pm_l1_sync + fut_l1_sync, data = dd)
    tst <- wald_term(fit, "fut_l1_sync", block_hac(fit, dd))
    tibble(
      meeting_id = id,
      deletion = j,
      removed_time = d$grid_time[r],
      removed_futures_predictor = d$fut_l1_sync[r],
      coefficient = tst$coef,
      block_HAC_p = tst$p
    )
  })
}

loo <- map_dfr(PRIMARY_MEETINGS, loo_one)

loo_summary <- loo |>
  group_by(meeting_id) |>
  summarise(
    predictor_events_tested = n(),
    coefficient_min = min(coefficient),
    coefficient_max = max(coefficient),
    coefficient_median = median(coefficient),
    smallest_HAC_p = min(block_HAC_p),
    largest_HAC_p = max(block_HAC_p),
    share_HAC_p_below_05 = mean(block_HAC_p < ALPHA),
    sign_preserved_all_deletions = n_distinct(sign(coefficient)) == 1,
    .groups = "drop"
  )

write_csv(loo, file.path(OUT_DIR, "08_leave_one_event_out.csv"))
write_csv(loo_summary, file.path(OUT_DIR, "09_leave_one_event_out_summary.csv"))

# ==============================================================================
# 11. FINAL MASTER TABLE + REPRODUCIBILITY EXPORTS
# ==============================================================================
# Plotting is intentionally NOT done in this analysis script.
# Run ECMT3150_final_visuals_FIXED.R after this script. Keeping estimation and
# plotting separate prevents graphics-package changes from interrupting inference.

master <- primary_tests |>
  left_join(
    bvar_coef |>
      select(
        meeting_id,
        direction_code,
        BVAR_median = median,
        BVAR_lower = lower,
        BVAR_upper = upper,
        BVAR_Pr_positive = Pr_positive,
        BVAR_Pr_negative = Pr_negative
      ),
    by = c("meeting_id", "direction_code")
  )

write_csv(master, file.path(OUT_DIR, "10_FINAL_MASTER_RESULTS.csv"))

# Export synchronized expected-rate paths so the visuals script can run in a
# fresh R session without relying on in-memory objects.
primary_path_export <- purrr::map_dfr(PRIMARY_MEETINGS, function(id) {
  d <- sync_data[[id]]$path

  meeting_row <- MEETINGS |>
    filter(meeting_id == id)

  ann_utc <- lubridate::ymd_hms(
    meeting_row$announcement_et[[1]],
    tz = "America/New_York"
  ) |>
    lubridate::with_tz("UTC")

  d |>
    transmute(
      meeting_id = id,
      sync_block_id,
      grid_time,
      hours_to_FOMC = as.numeric(
        difftime(grid_time, ann_utc, units = "hours")
      ),
      pm_expected_change_bp,
      fut_expected_change_bp
    )
})

write_csv(
  primary_path_export,
  file.path(OUT_DIR, "11_primary_synchronized_paths.csv")
)

writeLines(
  capture.output(sessionInfo()),
  file.path(OUT_DIR, "R_sessionInfo.txt")
)

writeLines(
  capture.output(py_cfg),
  file.path(OUT_DIR, "Python_reticulate_config.txt")
)

cat("\n============================================================\n")
cat("FINAL REPRODUCIBLE PIPELINE COMPLETE\n")
cat("============================================================\n")
cat("Results directory: ", OUT_DIR, "\n\n", sep = "")

cat("Primary directional results:\n")
print(primary_tests, width = Inf)

cat("\nMeeting classification:\n")
print(classification, width = Inf)

cat("\nBVAR directional results:\n")
print(bvar_coef, width = Inf)

cat("\nLeave-one-predictor sensitivity:\n")
print(loo_summary, width = Inf)

cat(
  "\nNext step:\n",
  '  source("ECMT3150_final_visuals_FIXED.R")\n',
  sep = ""
)
