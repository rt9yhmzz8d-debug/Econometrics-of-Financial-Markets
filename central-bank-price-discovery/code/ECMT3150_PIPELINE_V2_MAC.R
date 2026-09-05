# ==============================================================================
# ECMT3150 GROUP PROJECT — PIPELINE V2 — macOS
#
# WHO PRICES THE FED FIRST?
#
# Lead-Lag Price Discovery Between Prediction Markets
# and Fed Funds Futures Around FOMC Decisions
#
# PRIMARY:
#   15-minute revisions
#   VAR(4) = 60-minute lag horizon
#   HAC / Newey-West Granger inference
#
# ROBUSTNESS:
#   VAR(1)
#   HC3
#   conventional F
#   5m VAR(12)
#   30m VAR(2)
#   +/-2% Polymarket coherence
#   +/-75bp open-tail mapping
#
# FINAL MULTIPLE TESTING:
#   Holm ONCE across all primary HAC meeting-direction tests
#
# IMPORTANT:
#   Keep LSEG Workspace open and logged in.
#   This script does NOT reinstall Miniconda or Python.
# ==============================================================================


# ==============================================================================
# 0. SETUP
# ==============================================================================

rm(list = ls())

options(
  scipen = 999,
  repos = c(CRAN = "https://cloud.r-project.org")
)

packages <- c(
  "reticulate",
  "tidyverse",
  "httr2",
  "jsonlite",
  "lubridate",
  "urca",
  "sandwich",
  "car"
)

missing <- packages[
  !packages %in% rownames(installed.packages())
]

if (length(missing) > 0) {
  install.packages(missing)
}

invisible(
  lapply(
    packages,
    library,
    character.only = TRUE
  )
)

OUTPUT_DIR <- "output_v2"

dir.create(
  OUTPUT_DIR,
  showWarnings = FALSE
)


# ==============================================================================
# 1. PROJECT CONFIGURATION
# ==============================================================================

MEETINGS <- tribble(

  ~meeting_id,
  ~event_slug,
  ~announcement_et,
  ~target_lower,
  ~target_upper,
  ~futures_ric,

  "2026-07",
  "fed-decision-in-july-181",
  "2026-07-29 14:00:00",
  3.50,
  3.75,
  "FFc2"

)

PRIMARY_GRID <- 15
PRIMARY_P <- 4

MAX_PM_AGE <- 30
MAX_FUT_AGE <- 10

COHERENCE_PRIMARY <- 0.05
COHERENCE_TIGHT <- 0.02

MATERIAL_MASS <- 0.99

TAIL_PRIMARY <- 50
TAIL_ROBUST <- 75

MIN_COVERAGE <- 0.70
MIN_PRIMARY_ROWS <- 100

LSEG_BAR_MIN <- 5

PM_PREWINDOW_HOURS <- 72

ALPHA <- 0.05


# ==============================================================================
# 2. CONNECT R -> PYTHON -> LSEG — macOS
# ==============================================================================

# Optional:
# If you already know exactly which Python executable contains lseg.data,
# set it before running the script, for example:
#
# Sys.setenv(
#   ECMT3150_PYTHON = "/Users/YOURNAME/miniconda3/envs/ecmt3150_lseg/bin/python"
# )

forced_python <- Sys.getenv(
  "ECMT3150_PYTHON",
  unset = ""
)

home <- path.expand("~")

python_candidates <- unique(
  c(
    forced_python,

    file.path(
      home,
      "ecmt3150-miniconda",
      "envs",
      "ecmt3150_lseg",
      "bin",
      "python"
    ),

    file.path(
      home,
      "miniconda3",
      "envs",
      "ecmt3150_lseg",
      "bin",
      "python"
    ),

    file.path(
      home,
      "anaconda3",
      "envs",
      "ecmt3150_lseg",
      "bin",
      "python"
    ),

    file.path(
      home,
      ".conda",
      "envs",
      "ecmt3150_lseg",
      "bin",
      "python"
    ),

    "/opt/homebrew/bin/python3",
    "/opt/homebrew/bin/python",

    "/usr/local/bin/python3",
    "/usr/local/bin/python",

    unname(Sys.which("python3")),
    unname(Sys.which("python"))
  )
)

python_candidates <- python_candidates[
  nzchar(python_candidates)
]

python_candidates <- python_candidates[
  file.exists(python_candidates)
]

if (length(python_candidates) == 0) {

  stop(
    paste0(
      "\nNo Python executable was found on this Mac.\n\n",
      "Nothing has been installed or changed.\n",
      "In Terminal run:\n\n",
      "which python3\n\n",
      "and/or:\n\n",
      "conda env list\n"
    )
  )
}


python_has_lseg <- function(python) {

  result <- tryCatch(
    system2(
      python,
      c(
        "-c",
        shQuote(
          paste0(
            "import importlib.util; ",
            "print('YES' if importlib.util.find_spec('lseg.data') else 'NO')"
          )
        )
      ),
      stdout = TRUE,
      stderr = FALSE
    ),
    error = function(e) {
      character()
    }
  )

  any(trimws(result) == "YES")
}


has_lseg <- vapply(
  python_candidates,
  python_has_lseg,
  logical(1)
)

working_python <- python_candidates[
  has_lseg
]

if (length(working_python) == 0) {

  cat(
    "\nPython installations found on this Mac:\n\n"
  )

  cat(
    paste0(
      "  ",
      python_candidates,
      collapse = "\n"
    ),
    "\n"
  )

  stop(
    paste0(
      "\n\nNone of the Python installations above contains lseg.data.\n\n",
      "Do NOT reinstall Miniconda yet.\n",
      "Locate the existing environment that contains lseg.data.\n\n",
      "Useful Terminal commands:\n\n",
      "conda env list\n",
      "which -a python3\n"
    )
  )
}

PYTHON_EXE <- normalizePath(
  working_python[1],
  mustWork = TRUE
)

cat(
  "\nUsing Python:\n",
  PYTHON_EXE,
  "\n",
  sep = ""
)

reticulate::use_python(
  PYTHON_EXE,
  required = TRUE
)

cat("\nPython configuration:\n")
print(reticulate::py_config())

if (!reticulate::py_module_available("lseg.data")) {
  stop(
    paste0(
      "\nreticulate cannot import lseg.data from:\n",
      PYTHON_EXE,
      "\n"
    )
  )
}

ld <- reticulate::import(
  "lseg.data",
  convert = TRUE
)

SESSION_OK <- tryCatch(
  {
    ld$open_session(
      name = "desktop.workspace"
    )
    TRUE
  },
  error = function(e) {
    message(
      "\nLSEG connection error:\n",
      conditionMessage(e)
    )
    FALSE
  }
)

if (!SESSION_OK) {
  stop(
    paste0(
      "\nCould not connect to LSEG Workspace.\n\n",
      "Check that LSEG Workspace is open and logged in on this Mac.\n"
    )
  )
}

cat("\nLSEG Workspace connected successfully.\n")


# ==============================================================================
# 3. GENERAL HELPERS
# ==============================================================================

get_json <- function(
    url,
    query = list(),
    simplify = TRUE
) {

  req <- httr2::request(url) |>
    httr2::req_user_agent(
      "USyd-ECMT3150-Academic-Research"
    )

  if (length(query) > 0) {

    req <- do.call(
      httr2::req_url_query,
      c(
        list(req),
        query
      )
    )
  }

  response <- req |>
    httr2::req_retry(
      max_tries = 5
    ) |>
    httr2::req_perform()

  httr2::resp_check_status(response)

  httr2::resp_body_json(
    response,
    simplifyVector = simplify
  )
}


safe_chr <- function(x) {

  if (
    is.null(x) ||
    length(x) == 0
  ) {
    return(NA_character_)
  }

  as.character(x[[1]])
}


parse_json_vector <- function(x) {

  if (
    is.null(x) ||
    length(x) == 0
  ) {
    return(character())
  }

  if (
    is.character(x) &&
    length(x) == 1
  ) {

    z <- stringr::str_trim(x)

    if (
      nchar(z) > 0 &&
      substr(z, 1, 1) == "["
    ) {

      return(
        as.character(
          jsonlite::fromJSON(z)
        )
      )
    }
  }

  as.character(unlist(x))
}


records_to_tibble <- function(x) {

  if (
    is.null(x) ||
    length(x) == 0
  ) {
    return(tibble())
  }

  if (is.data.frame(x)) {
    return(as_tibble(x))
  }

  bind_rows(x)
}


format_lseg_time <- function(x) {

  format(
    lubridate::with_tz(
      x,
      "UTC"
    ),
    "%Y-%m-%dT%H:%M:%SZ"
  )
}


first_numeric <- function(
    data,
    candidates
) {

  available <- intersect(
    candidates,
    names(data)
  )

  if (length(available) == 0) {
    return(rep(NA_real_, nrow(data)))
  }

  suppressWarnings(
    as.numeric(
      data[[available[1]]]
    )
  )
}


# ==============================================================================
# 4. STRICT AS-OF LOOKUP
# ==============================================================================

asof_lookup <- function(
    source_time,
    source_value,
    grid_time
) {

  good <- (
    !is.na(source_time) &
      is.finite(source_value)
  )

  source_time <- source_time[good]
  source_value <- source_value[good]

  if (length(source_time) == 0) {

    return(
      tibble(
        grid_time = grid_time,
        value = NA_real_,
        source_time = as.POSIXct(
          NA,
          tz = "UTC"
        ),
        age_minutes = NA_real_
      )
    )
  }

  o <- order(source_time)

  source_time <- source_time[o]
  source_value <- source_value[o]

  s <- as.numeric(source_time)
  g <- as.numeric(grid_time)

  idx <- findInterval(g, s)

  value <- rep(
    NA_real_,
    length(g)
  )

  used_time <- rep(
    NA_real_,
    length(g)
  )

  valid <- idx > 0

  value[valid] <- source_value[
    idx[valid]
  ]

  used_time[valid] <- s[
    idx[valid]
  ]

  used_time <- lubridate::as_datetime(
    used_time,
    tz = "UTC"
  )

  tibble(
    grid_time = grid_time,
    value = value,
    source_time = used_time,
    age_minutes = as.numeric(
      difftime(
        grid_time,
        used_time,
        units = "mins"
      )
    )
  )
}


# ==============================================================================
# 5. POLYMARKET OUTCOME MAPPING
# ==============================================================================

policy_change <- function(
    label,
    tail_bp
) {

  x <- stringr::str_to_lower(label)

  if (
    stringr::str_detect(
      x,
      "no change"
    )
  ) {
    return(0)
  }

  n <- readr::parse_number(x)

  direction <- case_when(

    stringr::str_detect(
      x,
      "decrease|cut"
    ) ~ -1,

    stringr::str_detect(
      x,
      "increase|hike"
    ) ~ 1,

    TRUE ~ NA_real_
  )

  if (
    is.na(n) ||
    is.na(direction)
  ) {
    return(NA_real_)
  }

  tail_market <- stringr::str_detect(
    x,
    "50\\+|50 or more|at least 50"
  )

  if (tail_market) {
    return(direction * tail_bp)
  }

  direction * n
}


# ==============================================================================
# 6. DOWNLOAD + CLEAN FUTURES
# ==============================================================================

download_futures <- function(
    ric,
    window_start,
    window_end
) {

  start_download <- window_start - minutes(30)
  end_download <- window_end + minutes(10)

  x <- ld$get_history(

    universe = ric,

    start = format_lseg_time(
      start_download
    ),

    end = format_lseg_time(
      end_download
    ),

    interval = "5min"
  )

  x <- as.data.frame(x)

  if (nrow(x) == 0) {
    stop("Zero LSEG rows returned.")
  }

  timestamp_raw <- rownames(x)

  # LSEG Workspace on this machine returns timezone-naive row timestamps
  # in Australia/Sydney local clock time, even when the requested start/end
  # are supplied in UTC. Interpret the returned clock times as Sydney time,
  # then convert them to UTC before strict as-of matching.
  #
  # Confirmed example:
  #   request: 2026-07-27 17:15 UTC
  #   returned: 2026-07-28 03:15 (Sydney, UTC+10 in July)

  timestamp_local <- suppressWarnings(
    lubridate::ymd_hms(
      timestamp_raw,
      tz = "Australia/Sydney",
      quiet = TRUE
    )
  )

  bar_start_utc <- lubridate::with_tz(
    timestamp_local,
    "UTC"
  )

  if (
    length(bar_start_utc) != nrow(x) ||
    mean(is.na(bar_start_utc)) > 0.05
  ) {

    cat(
      "\nExample LSEG timestamps returned:\n"
    )

    print(
      head(
        timestamp_raw,
        10
      )
    )

    stop("LSEG timestamp parsing failed.")
  }

  information_time <- (
    bar_start_utc +
      minutes(LSEG_BAR_MIN)
  )

  bid <- first_numeric(
    x,
    "BID"
  )

  ask <- first_numeric(
    x,
    "ASK"
  )

  last <- first_numeric(
    x,
    "TRDPRC_1"
  )

  midpoint <- ifelse(
    is.finite(bid) &
      is.finite(ask) &
      ask >= bid,
    (bid + ask) / 2,
    NA_real_
  )

  price <- ifelse(
    is.finite(midpoint),
    midpoint,
    last
  )

  out <- tibble(
    bar_start_utc = bar_start_utc,
    information_time_utc = information_time,
    bid = bid,
    ask = ask,
    last_trade = last,
    futures_price = price,
    price_source = ifelse(
      is.finite(midpoint),
      "midpoint",
      "last_trade"
    )
  ) |>
    filter(
      is.finite(futures_price)
    ) |>
    arrange(
      information_time_utc
    )

  if (nrow(out) == 0) {
    stop("LSEG returned rows, but no usable futures prices were found.")
  }

  if (
    median(
      out$futures_price,
      na.rm = TRUE
    ) <= 90 ||
    median(
      out$futures_price,
      na.rm = TRUE
    ) >= 100
  ) {
    stop("Futures price sanity check failed.")
  }

  out
}


# ==============================================================================
# 7. POLYMARKET TRADE DOWNLOAD
# ==============================================================================

fetch_trade_page <- function(
    event_id,
    start_epoch,
    end_epoch,
    offset = 0
) {

  records_to_tibble(

    get_json(

      "https://data-api.polymarket.com/trades",

      query = list(
        eventId = event_id,
        start = floor(start_epoch),
        end = floor(end_epoch),
        limit = 10000,
        offset = offset,
        takerOnly = "true"
      )
    )
  )
}


fetch_trade_window <- function(
    event_id,
    start_epoch,
    end_epoch
) {

  p1 <- fetch_trade_page(
    event_id,
    start_epoch,
    end_epoch,
    0
  )

  if (nrow(p1) < 10000) {
    return(p1)
  }

  p2 <- fetch_trade_page(
    event_id,
    start_epoch,
    end_epoch,
    10000
  )

  if (nrow(p2) < 10000) {
    return(bind_rows(p1, p2))
  }

  if (
    end_epoch -
    start_epoch <= 60
  ) {

    stop(
      "Polymarket trade density exceeds safe pagination limit."
    )
  }

  middle <- floor(
    (start_epoch + end_epoch) / 2
  )

  bind_rows(

    fetch_trade_window(
      event_id,
      start_epoch,
      middle
    ),

    fetch_trade_window(
      event_id,
      middle + 1,
      end_epoch
    )
  )
}


download_polymarket <- function(
    slug,
    window_start,
    window_end
) {

  event <- get_json(
    paste0(
      "https://gamma-api.polymarket.com/events/slug/",
      slug
    ),
    simplify = FALSE
  )

  event_id <- as.numeric(
    event$id
  )

  markets <- purrr::map_dfr(

    event$markets,

    function(m) {

      outcomes <- parse_json_vector(
        m$outcomes
      )

      tokens <- parse_json_vector(
        m$clobTokenIds
      )

      if (
        length(outcomes) !=
        length(tokens) ||
        length(outcomes) == 0
      ) {
        return(tibble())
      }

      yes <- which(
        stringr::str_to_lower(
          stringr::str_trim(outcomes)
        ) == "yes"
      )

      if (length(yes) != 1) {
        return(tibble())
      }

      group_title <- safe_chr(
        m$groupItemTitle
      )

      question <- safe_chr(
        m$question
      )

      label <- if (
        !is.na(group_title) &&
        nzchar(group_title)
      ) {
        group_title
      } else {
        question
      }

      tibble(
        condition_id = safe_chr(
          m$conditionId
        ),
        label = label,
        question = question,
        yes_token = tokens[yes],
        lifetime_volume = suppressWarnings(
          as.numeric(
            safe_chr(m$volume)
          )
        )
      )
    }
  ) |>
    mutate(
      search_text = stringr::str_to_lower(
        paste(label, question)
      )
    ) |>
    filter(
      stringr::str_detect(
        search_text,
        "decrease|increase|no change"
      )
    ) |>
    select(-search_text) |>
    mutate(
      delta50 = map_dbl(
        label,
        policy_change,
        tail_bp = TAIL_PRIMARY
      ),
      delta75 = map_dbl(
        label,
        policy_change,
        tail_bp = TAIL_ROBUST
      )
    ) |>
    arrange(delta50)

  if (nrow(markets) != 5) {

    stop(
      paste0(
        "Expected 5 FOMC outcome markets; found ",
        nrow(markets),
        "."
      )
    )
  }

  download_start <- (
    window_start -
      hours(PM_PREWINDOW_HOURS)
  )

  chunk_seconds <- 6 * 60 * 60

  starts <- seq(
    as.numeric(download_start),
    as.numeric(window_end),
    by = chunk_seconds
  )

  trade_chunks <- map(
    starts,
    function(s) {

      e <- min(
        s + chunk_seconds - 1,
        as.numeric(window_end)
      )

      out <- fetch_trade_window(
        event_id,
        s,
        e
      )

      Sys.sleep(0.05)

      out
    }
  )

  raw <- bind_rows(trade_chunks)

  required <- c(
    "conditionId",
    "timestamp",
    "outcome",
    "price",
    "size"
  )

  if (
    length(
      setdiff(
        required,
        names(raw)
      )
    ) > 0
  ) {
    stop("Required Polymarket trade fields are missing.")
  }

  trades <- raw |>
    transmute(
      condition_id = as.character(
        conditionId
      ),
      timestamp = lubridate::as_datetime(
        as.numeric(timestamp),
        tz = "UTC"
      ),
      outcome = stringr::str_to_lower(
        stringr::str_trim(
          as.character(outcome)
        )
      ),
      price = as.numeric(price),
      size = as.numeric(size),
      yes_probability = case_when(
        outcome == "yes" ~ price,
        outcome == "no" ~ 1 - price,
        TRUE ~ NA_real_
      )
    ) |>
    filter(
      condition_id %in%
        markets$condition_id,
      !is.na(timestamp),
      is.finite(yes_probability),
      between(
        yes_probability,
        0,
        1
      )
    ) |>
    distinct() |>
    arrange(timestamp)

  if (nrow(trades) == 0) {
    stop("No usable Polymarket trades.")
  }

  updates <- trades |>
    group_by(
      condition_id,
      timestamp
    ) |>
    summarise(
      yes_probability = median(
        yes_probability,
        na.rm = TRUE
      ),
      traded_size = sum(
        size,
        na.rm = TRUE
      ),
      .groups = "drop"
    ) |>
    left_join(
      markets |>
        select(
          condition_id,
          label,
          delta50,
          delta75
        ),
      by = "condition_id"
    ) |>
    arrange(timestamp)

  initialization <- updates |>
    filter(
      timestamp <= window_start
    ) |>
    group_by(condition_id) |>
    summarise(
      n = n(),
      .groups = "drop"
    )

  if (
    nrow(initialization) != 5
  ) {
    stop(
      "Not all five PM outcomes have pre-window initialization."
    )
  }

  activity <- trades |>
    filter(
      timestamp >= window_start,
      timestamp <= window_end
    ) |>
    group_by(condition_id) |>
    summarise(
      trades = n(),
      volume_tokens = sum(
        size,
        na.rm = TRUE
      ),
      .groups = "drop"
    ) |>
    right_join(
      markets |>
        select(
          condition_id,
          label
        ),
      by = "condition_id"
    )

  list(
    event = event,
    markets = markets,
    trades = trades,
    updates = updates,
    activity = activity
  )
}


# ==============================================================================
# 8. EFFR-TARGET BASIS
# ==============================================================================

get_effr_basis <- function(
    window_start,
    target_midpoint
) {

  tryCatch(
    {

      response <- get_json(
        paste0(
          "https://markets.newyorkfed.org/api/rates/",
          "unsecured/effr/last/100.json"
        )
      )

      x <- as_tibble(
        response$refRates
      ) |>
        transmute(
          date = as.Date(effectiveDate),
          effr = as.numeric(percentRate)
        ) |>
        filter(
          is.finite(effr)
        ) |>
        arrange(date)

      cutoff <- as.Date(
        with_tz(
          window_start,
          "America/New_York"
        )
      )

      x <- x |>
        filter(
          date < cutoff
        ) |>
        slice_tail(
          n = 20
        )

      if (nrow(x) < 20) {
        stop("Insufficient EFFR history.")
      }

      mean(
        x$effr -
          target_midpoint
      )
    },

    error = function(e) {

      warning(
        paste0(
          "EFFR basis unavailable: ",
          conditionMessage(e),
          ". Using zero for level plotting. ",
          "VAR revisions are unaffected."
        )
      )

      0
    }
  )
}


# ==============================================================================
# 9. BUILD POLYMARKET GRID
# ==============================================================================

build_pm_grid <- function(
    pm,
    window_start,
    window_end,
    grid_minutes,
    tolerance
) {

  grid <- seq(
    window_start,
    window_end,
    by = paste(
      grid_minutes,
      "mins"
    )
  )

  long <- map_dfr(
    seq_len(
      nrow(pm$markets)
    ),
    function(i) {

      m <- pm$markets[i, ]

      u <- pm$updates |>
        filter(
          condition_id ==
            m$condition_id
        )

      asof_lookup(
        u$timestamp,
        u$yes_probability,
        grid
      ) |>
        transmute(
          grid_time,
          probability = value,
          source_time,
          age_minutes,
          condition_id =
            m$condition_id,
          label =
            m$label,
          delta50 =
            m$delta50,
          delta75 =
            m$delta75
        )
    }
  )

  snapshot <- function(x) {

    if (
      any(
        !is.finite(
          x$probability
        )
      )
    ) {

      return(
        tibble(
          pm_probability_sum = NA_real_,
          pm_expected_change_bp = NA_real_,
          pm_expected_change_tail75_bp = NA_real_,
          max_material_age = NA_real_,
          coherent = FALSE,
          fresh = FALSE,
          pm_valid = FALSE
        )
      )
    }

    s <- sum(
      x$probability
    )

    if (
      !is.finite(s) ||
      s <= 0
    ) {

      return(
        tibble(
          pm_probability_sum = s,
          pm_expected_change_bp = NA_real_,
          pm_expected_change_tail75_bp = NA_real_,
          max_material_age = NA_real_,
          coherent = FALSE,
          fresh = FALSE,
          pm_valid = FALSE
        )
      )
    }

    p <- x$probability / s

    order_p <- order(
      p,
      decreasing = TRUE
    )

    sorted <- p[order_p]

    before <- c(
      0,
      head(
        cumsum(sorted),
        -1
      )
    )

    material_sorted <- (
      before <
        MATERIAL_MASS
    )

    material <- rep(
      FALSE,
      length(p)
    )

    material[order_p] <- material_sorted

    ages <- x$age_minutes[
      material
    ]

    fresh <- (
      length(ages) > 0 &&
        all(is.finite(ages)) &&
        all(ages >= 0) &&
        all(ages <= MAX_PM_AGE)
    )

    coherent <- (
      abs(s - 1) <=
        tolerance
    )

    tibble(
      pm_probability_sum = s,
      pm_expected_change_bp =
        sum(p * x$delta50),
      pm_expected_change_tail75_bp =
        sum(p * x$delta75),
      max_material_age =
        ifelse(
          length(ages) > 0 &&
            all(is.finite(ages)),
          max(ages),
          NA_real_
        ),
      coherent = coherent,
      fresh = fresh,
      pm_valid = coherent & fresh
    )
  }

  summary <- long |>
    group_by(grid_time) |>
    group_modify(
      ~ snapshot(.x)
    ) |>
    ungroup()

  list(
    long = long,
    summary = summary
  )
}


# ==============================================================================
# 10. BUILD FUTURES GRID
# ==============================================================================

build_futures_grid <- function(
    futures,
    window_start,
    window_end,
    grid_minutes,
    target_midpoint,
    basis
) {

  grid <- seq(
    window_start,
    window_end,
    by = paste(
      grid_minutes,
      "mins"
    )
  )

  asof_lookup(
    futures$information_time_utc,
    futures$futures_price,
    grid
  ) |>
    transmute(
      grid_time,
      futures_price = value,
      futures_source_time =
        source_time,
      futures_age_minutes =
        age_minutes,

      implied_effr =
        100 -
        futures_price,

      fut_expected_change_bp =
        (
          implied_effr -
            basis -
            target_midpoint
        ) * 100,

      fut_valid =
        is.finite(futures_price) &
        is.finite(
          futures_age_minutes
        ) &
        futures_age_minutes >= 0 &
        futures_age_minutes <=
        MAX_FUT_AGE
    )
}


build_combined <- function(
    pm,
    futures,
    window_start,
    window_end,
    grid_minutes,
    tolerance,
    target_midpoint,
    basis
) {

  pm_grid <- build_pm_grid(
    pm,
    window_start,
    window_end,
    grid_minutes,
    tolerance
  )$summary

  fut_grid <- build_futures_grid(
    futures,
    window_start,
    window_end,
    grid_minutes,
    target_midpoint,
    basis
  )

  left_join(
    pm_grid,
    fut_grid,
    by = "grid_time"
  ) |>
    arrange(grid_time) |>
    mutate(
      valid_level =
        pm_valid &
        fut_valid
    )
}


# ==============================================================================
# 11. EXACT-TIME DIFFERENCES + LAGS
# ==============================================================================

prepare_design <- function(
    combined,
    p
) {

  x <- combined |>
    arrange(grid_time) |>
    mutate(
      previous_valid = lag(
        valid_level,
        default = FALSE
      ),

      d_pm = if_else(
        valid_level &
          previous_valid,
        pm_expected_change_bp -
          lag(
            pm_expected_change_bp
          ),
        NA_real_
      ),

      d_fut = if_else(
        valid_level &
          previous_valid,
        fut_expected_change_bp -
          lag(
            fut_expected_change_bp
          ),
        NA_real_
      )
    )

  for (j in seq_len(p)) {

    x[[paste0("pm_l", j)]] <-
      lag(
        x$d_pm,
        j
      )

    x[[paste0("fut_l", j)]] <-
      lag(
        x$d_fut,
        j
      )
  }

  pm_terms <- paste0(
    "pm_l",
    seq_len(p)
  )

  fut_terms <- paste0(
    "fut_l",
    seq_len(p)
  )

  required <- c(
    "d_pm",
    "d_fut",
    pm_terms,
    fut_terms
  )

  model_data <- x |>
    filter(
      if_all(
        all_of(required),
        is.finite
      )
    )

  list(
    complete_grid = x,
    model_data = model_data,
    pm_terms = pm_terms,
    fut_terms = fut_terms
  )
}


# ==============================================================================
# 12. JOINT TEST HELPERS
# ==============================================================================

extract_p <- function(x) {

  p_col <- grep(
    "^Pr\\(",
    colnames(x),
    value = TRUE
  )

  if (length(p_col) == 0) {
    return(NA_real_)
  }

  p <- as.numeric(
    x[, p_col[1]]
  )

  p <- p[
    is.finite(p)
  ]

  if (length(p) == 0) {
    return(NA_real_)
  }

  tail(p, 1)
}


joint_p <- function(
    fit,
    terms,
    V
) {

  out <- tryCatch(

    car::linearHypothesis(
      fit,
      paste0(
        terms,
        " = 0"
      ),
      vcov. = V,
      test = "F"
    ),

    error = function(e) NULL
  )

  if (is.null(out)) {
    return(NA_real_)
  }

  extract_p(out)
}


hac_vcov <- function(
    fit,
    minimum_lag
) {

  auto_bw <- tryCatch(
    floor(
      sandwich::bwNeweyWest(
        fit,
        prewhite = FALSE
      )
    ),
    error = function(e) minimum_lag
  )

  lag_used <- max(
    minimum_lag,
    auto_bw,
    1
  )

  list(
    lag = lag_used,
    V = sandwich::NeweyWest(
      fit,
      lag = lag_used,
      prewhite = FALSE,
      adjust = TRUE
    )
  )
}


# ==============================================================================
# 13. ESTIMATE VAR + THREE GRANGER INFERENCE METHODS
# ==============================================================================

fit_var <- function(
    design,
    p
) {

  d <- design$model_data

  if (nrow(d) < 30) {
    stop("Too few VAR observations.")
  }

  all_terms <- c(
    design$pm_terms,
    design$fut_terms
  )

  fit_pm <- lm(
    reformulate(
      all_terms,
      response = "d_pm"
    ),
    data = d
  )

  fit_fut <- lm(
    reformulate(
      all_terms,
      response = "d_fut"
    ),
    data = d
  )

  pm_R <- lm(
    reformulate(
      design$pm_terms,
      response = "d_pm"
    ),
    data = d
  )

  fut_R <- lm(
    reformulate(
      design$fut_terms,
      response = "d_fut"
    ),
    data = d
  )

  conventional_FUT_PM <- anova(
    pm_R,
    fit_pm
  )

  conventional_PM_FUT <- anova(
    fut_R,
    fit_fut
  )

  HC3_pm <- sandwich::vcovHC(
    fit_pm,
    type = "HC3"
  )

  HC3_fut <- sandwich::vcovHC(
    fit_fut,
    type = "HC3"
  )

  HAC_pm <- hac_vcov(
    fit_pm,
    minimum_lag = p
  )

  HAC_fut <- hac_vcov(
    fit_fut,
    minimum_lag = p
  )

  results <- tibble(

    direction = c(
      "FUT -> PM",
      "PM -> FUT"
    ),

    F_statistic = c(
      conventional_FUT_PM$F[2],
      conventional_PM_FUT$F[2]
    ),

    conventional_p = c(
      conventional_FUT_PM$`Pr(>F)`[2],
      conventional_PM_FUT$`Pr(>F)`[2]
    ),

    HC3_p = c(
      joint_p(
        fit_pm,
        design$fut_terms,
        HC3_pm
      ),
      joint_p(
        fit_fut,
        design$pm_terms,
        HC3_fut
      )
    ),

    HAC_p = c(
      joint_p(
        fit_pm,
        design$fut_terms,
        HAC_pm$V
      ),
      joint_p(
        fit_fut,
        design$pm_terms,
        HAC_fut$V
      )
    ),

    HAC_lag = c(
      HAC_pm$lag,
      HAC_fut$lag
    )
  )

  list(
    data = d,
    fit_pm = fit_pm,
    fit_fut = fit_fut,
    Sigma = cov(
      cbind(
        residuals(fit_pm),
        residuals(fit_fut)
      )
    ),
    results = results
  )
}


# ==============================================================================
# 14. VAR STABILITY
# ==============================================================================

var_stability <- function(
    fit,
    p
) {

  A <- vector(
    "list",
    p
  )

  for (j in seq_len(p)) {

    A[[j]] <- matrix(

      c(
        coef(fit$fit_pm)[
          paste0("pm_l", j)
        ],
        coef(fit$fit_pm)[
          paste0("fut_l", j)
        ],
        coef(fit$fit_fut)[
          paste0("pm_l", j)
        ],
        coef(fit$fit_fut)[
          paste0("fut_l", j)
        ]
      ),

      nrow = 2,
      byrow = TRUE
    )
  }

  if (p == 1) {

    companion <- A[[1]]

  } else {

    companion <- rbind(

      do.call(
        cbind,
        A
      ),

      cbind(
        diag(
          2 * (p - 1)
        ),
        matrix(
          0,
          2 * (p - 1),
          2
        )
      )
    )
  }

  root <- max(
    Mod(
      eigen(
        companion,
        only.values = TRUE
      )$values
    )
  )

  tibble(
    maximum_root_modulus = root,
    stable = root < 1
  )
}


# ==============================================================================
# 15. GIRF
# ==============================================================================

compute_girf <- function(
    fit,
    p,
    horizon
) {

  Sigma <- fit$Sigma

  A <- vector(
    "list",
    p
  )

  for (j in seq_len(p)) {

    A[[j]] <- matrix(

      c(
        coef(fit$fit_pm)[
          paste0("pm_l", j)
        ],
        coef(fit$fit_pm)[
          paste0("fut_l", j)
        ],
        coef(fit$fit_fut)[
          paste0("pm_l", j)
        ],
        coef(fit$fit_fut)[
          paste0("fut_l", j)
        ]
      ),

      2,
      2,
      byrow = TRUE
    )
  }

  Phi <- vector(
    "list",
    horizon + 1
  )

  Phi[[1]] <- diag(2)

  for (h in seq_len(horizon)) {

    current <- matrix(
      0,
      2,
      2
    )

    for (
      j in seq_len(
        min(p, h)
      )
    ) {

      current <- (
        current +
          A[[j]] %*%
          Phi[[h - j + 1]]
      )
    }

    Phi[[h + 1]] <- current
  }

  names_var <- c(
    "PM",
    "FUT"
  )

  out <- list()
  counter <- 1

  for (shock in 1:2) {

    shock_sd <- sqrt(
      Sigma[
        shock,
        shock
      ]
    )

    generalized_shock <- (
      Sigma[, shock] /
        shock_sd
    )

    for (h in 0:horizon) {

      response <- as.numeric(
        Phi[[h + 1]] %*%
          generalized_shock
      )

      per_1bp <- (
        response /
          shock_sd
      )

      out[[counter]] <- tibble(
        horizon = h,
        shock = names_var[shock],
        response_PM_per_1bp =
          per_1bp[1],
        response_FUT_per_1bp =
          per_1bp[2]
      )

      counter <- counter + 1
    }
  }

  bind_rows(out) |>
    group_by(shock) |>
    arrange(
      horizon,
      .by_group = TRUE
    ) |>
    mutate(
      cumulative_PM =
        cumsum(
          response_PM_per_1bp
        ),
      cumulative_FUT =
        cumsum(
          response_FUT_per_1bp
        ),

      cross_cumulative =
        if_else(
          shock == "PM",
          cumulative_FUT,
          cumulative_PM
        ),

      dynamic_cross =
        cross_cumulative -
        first(
          cross_cumulative
        )
    ) |>
    ungroup()
}


# ==============================================================================
# 16. STATIONARITY HELPERS
# ==============================================================================

longest_finite_run <- function(x) {

  r <- rle(
    is.finite(x)
  )

  valid <- which(
    r$values
  )

  if (length(valid) == 0) {
    return(numeric())
  }

  starts <- cumsum(
    c(
      1,
      head(
        r$lengths,
        -1
      )
    )
  )

  best <- valid[
    which.max(
      r$lengths[valid]
    )
  ]

  idx <- starts[best]:
    (
      starts[best] +
        r$lengths[best] -
        1
    )

  x[idx]
}


critical_5pct <- function(cv) {

  if (is.matrix(cv)) {

    cn <- gsub(
      "\\s",
      "",
      tolower(
        colnames(cv)
      )
    )

    if (
      length(cn) > 0 &&
      "5pct" %in% cn
    ) {

      return(
        as.numeric(
          cv[
            1,
            which(cn == "5pct")[1]
          ]
        )
      )
    }

    rn <- gsub(
      "\\s",
      "",
      tolower(
        rownames(cv)
      )
    )

    if (
      length(rn) > 0 &&
      "5pct" %in% rn
    ) {

      return(
        as.numeric(
          cv[
            which(rn == "5pct")[1],
            1
          ]
        )
      )
    }
  }

  nm <- gsub(
    "\\s",
    "",
    tolower(
      names(cv)
    )
  )

  if (
    length(nm) > 0 &&
    "5pct" %in% nm
  ) {

    return(
      as.numeric(
        cv[
          which(nm == "5pct")[1]
        ]
      )
    )
  }

  NA_real_
}


stationarity_test <- function(
    x,
    name
) {

  x <- longest_finite_run(x)

  if (
    length(x) < 30 ||
    sd(x) <= 0
  ) {

    return(
      tibble(
        series = name,
        n = length(x),
        ADF_stat = NA_real_,
        ADF_5pct = NA_real_,
        KPSS_stat = NA_real_,
        KPSS_5pct = NA_real_
      )
    )
  }

  maxlag <- min(
    8,
    max(
      1,
      floor(
        length(x)^(1 / 3)
      )
    )
  )

  adf <- urca::ur.df(
    x,
    type = "drift",
    lags = maxlag,
    selectlags = "AIC"
  )

  kpss <- urca::ur.kpss(
    x,
    type = "mu",
    lags = "short"
  )

  tibble(
    series = name,
    n = length(x),

    ADF_stat =
      as.numeric(
        adf@teststat[1]
      ),

    ADF_5pct =
      critical_5pct(
        adf@cval
      ),

    KPSS_stat =
      as.numeric(
        kpss@teststat[1]
      ),

    KPSS_5pct =
      critical_5pct(
        kpss@cval
      )
  )
}


# ==============================================================================
# 17. BIC
# ==============================================================================

bic_table <- function(
    combined,
    max_p = 8
) {

  common <- prepare_design(
    combined,
    max_p
  )$model_data

  if (nrow(common) < 40) {
    return(tibble())
  }

  map_dfr(
    1:max_p,
    function(p) {

      terms <- c(
        paste0(
          "pm_l",
          1:p
        ),
        paste0(
          "fut_l",
          1:p
        )
      )

      fit_pm <- lm(
        reformulate(
          terms,
          response = "d_pm"
        ),
        data = common
      )

      fit_fut <- lm(
        reformulate(
          terms,
          response = "d_fut"
        ),
        data = common
      )

      E <- cbind(
        residuals(fit_pm),
        residuals(fit_fut)
      )

      Sigma <- (
        crossprod(E) /
          nrow(E)
      )

      d <- det(Sigma)

      bic <- if (
        is.finite(d) &&
        d > 0
      ) {

        log(d) +
          log(nrow(E)) /
          nrow(E) *
          (
            4 * p +
              2
          )

      } else {

        NA_real_
      }

      tibble(
        p = p,
        lag_minutes =
          p * PRIMARY_GRID,
        n = nrow(E),
        BIC = bic
      )
    }
  )
}


# ==============================================================================
# 18. RESIDUAL SERIAL-CORRELATION DIAGNOSTIC
# ==============================================================================

residual_diagnostics <- function(
    fit,
    grid_minutes,
    p
) {

  d <- fit$data |>
    mutate(
      resid_PM =
        residuals(
          fit$fit_pm
        ),
      resid_FUT =
        residuals(
          fit$fit_fut
        ),

      new_block = c(
        TRUE,
        diff(
          as.numeric(
            grid_time
          )
        ) !=
          grid_minutes * 60
      ),

      block = cumsum(
        new_block
      )
    )

  biggest <- d |>
    count(block) |>
    slice_max(
      n,
      n = 1,
      with_ties = FALSE
    ) |>
    pull(block)

  x <- d |>
    filter(
      block == biggest
    )

  if (nrow(x) < 20) {
    return(tibble())
  }

  test_lag <- min(
    12,
    max(
      5,
      floor(
        nrow(x) / 4
      )
    )
  )

  fitdf <- min(
    2 * p,
    test_lag - 1
  )

  pm <- Box.test(
    x$resid_PM,
    lag = test_lag,
    type = "Ljung-Box",
    fitdf = fitdf
  )

  fut <- Box.test(
    x$resid_FUT,
    lag = test_lag,
    type = "Ljung-Box",
    fitdf = fitdf
  )

  tibble(
    equation = c(
      "PM",
      "FUT"
    ),
    n = nrow(x),
    Ljung_Box = c(
      unname(pm$statistic),
      unname(fut$statistic)
    ),
    p_value = c(
      pm$p.value,
      fut$p.value
    )
  )
}


# ==============================================================================
# 19. DESCRIPTIVE OOS FORECAST GAIN
# ==============================================================================

forecast_gain <- function(fit) {

  d <- fit$data

  if (nrow(d) < 50) {
    return(tibble())
  }

  n_train <- floor(
    0.8 * nrow(d)
  )

  train <- d[
    1:n_train,
  ]

  test <- d[
    (n_train + 1):nrow(d),
  ]

  pm_terms <- grep(
    "^pm_l",
    names(d),
    value = TRUE
  )

  fut_terms <- grep(
    "^fut_l",
    names(d),
    value = TRUE
  )

  all_terms <- c(
    pm_terms,
    fut_terms
  )

  rmse <- function(y, pred) {
    sqrt(
      mean(
        (y - pred)^2
      )
    )
  }

  fut_R <- lm(
    reformulate(
      fut_terms,
      response = "d_fut"
    ),
    train
  )

  fut_U <- lm(
    reformulate(
      all_terms,
      response = "d_fut"
    ),
    train
  )

  r_fut <- rmse(
    test$d_fut,
    predict(
      fut_R,
      test
    )
  )

  u_fut <- rmse(
    test$d_fut,
    predict(
      fut_U,
      test
    )
  )

  pm_R <- lm(
    reformulate(
      pm_terms,
      response = "d_pm"
    ),
    train
  )

  pm_U <- lm(
    reformulate(
      all_terms,
      response = "d_pm"
    ),
    train
  )

  r_pm <- rmse(
    test$d_pm,
    predict(
      pm_R,
      test
    )
  )

  u_pm <- rmse(
    test$d_pm,
    predict(
      pm_U,
      test
    )
  )

  tibble(
    direction = c(
      "PM -> FUT",
      "FUT -> PM"
    ),
    restricted_RMSE = c(
      r_fut,
      r_pm
    ),
    unrestricted_RMSE = c(
      u_fut,
      u_pm
    ),
    forecast_gain = c(
      (r_fut - u_fut) / r_fut,
      (r_pm - u_pm) / r_pm
    )
  )
}


# ==============================================================================
# 20. FIT A ROBUSTNESS SPECIFICATION
# ==============================================================================

safe_spec <- function(
    name,
    combined,
    p,
    minimum_rows
) {

  design <- prepare_design(
    combined,
    p
  )

  if (
    nrow(
      design$model_data
    ) <
    minimum_rows
  ) {

    return(NULL)
  }

  fit <- fit_var(
    design,
    p
  )

  fit$results |>
    mutate(
      specification = name,
      grid_minutes =
        round(
          60 *
            median(
              diff(
                as.numeric(
                  combined$grid_time
                )
              )
            ) /
            3600
        ),
      p = p,
      .before = 1
    )
}


# ==============================================================================
# 21. RUN ONE FOMC MEETING
# ==============================================================================

run_meeting <- function(
    meeting_id,
    event_slug,
    announcement_et,
    target_lower,
    target_upper,
    futures_ric
) {

  cat(
    "\n\n============================================================\n",
    "RUNNING MEETING: ",
    meeting_id,
    "\n",
    "============================================================\n",
    sep = ""
  )

  meeting_dir <- file.path(
    OUTPUT_DIR,
    meeting_id
  )

  dir.create(
    meeting_dir,
    recursive = TRUE,
    showWarnings = FALSE
  )

  ann_et <- lubridate::ymd_hms(
    announcement_et,
    tz = "America/New_York"
  )

  ann_utc <- with_tz(
    ann_et,
    "UTC"
  )

  window_end <- (
    ann_utc -
      minutes(15)
  )

  window_start <- (
    window_end -
      hours(48)
  )

  target_mid <- (
    target_lower +
      target_upper
  ) / 2

  cat(
    "Announcement UTC: ",
    format(ann_utc),
    "\n",
    "Window: ",
    format(window_start),
    " -> ",
    format(window_end),
    "\n",
    sep = ""
  )

  futures <- download_futures(
    futures_ric,
    window_start,
    window_end
  )

  pm <- download_polymarket(
    event_slug,
    window_start,
    window_end
  )

  basis <- get_effr_basis(
    window_start,
    target_mid
  )

  combined <- build_combined(
    pm,
    futures,
    window_start,
    window_end,
    PRIMARY_GRID,
    COHERENCE_PRIMARY,
    target_mid,
    basis
  )

  primary_design <- prepare_design(
    combined,
    PRIMARY_P
  )

  coverage <- mean(
    combined$valid_level,
    na.rm = TRUE
  )

  model_rows <- nrow(
    primary_design$model_data
  )

  quality <- tibble(
    meeting_id = meeting_id,
    grid_points = nrow(combined),
    joint_valid_coverage = coverage,
    VAR4_rows = model_rows,
    pass = (
      coverage >= MIN_COVERAGE &&
        model_rows >=
        MIN_PRIMARY_ROWS
    )
  )

  print(quality)

  write_csv(
    combined,
    file.path(
      meeting_dir,
      "matched_15m_grid.csv"
    )
  )

  write_csv(
    pm$activity,
    file.path(
      meeting_dir,
      "polymarket_activity.csv"
    )
  )

  write_csv(
    quality,
    file.path(
      meeting_dir,
      "data_quality.csv"
    )
  )

  valid_levels <- combined |>
    filter(valid_level)

  if (nrow(valid_levels) > 1) {

    first_pm <- first(
      valid_levels$pm_expected_change_bp
    )

    first_fut <- first(
      valid_levels$fut_expected_change_bp
    )

    centered <- valid_levels |>
      transmute(
        grid_time,
        Polymarket =
          pm_expected_change_bp -
          first_pm,
        `Fed Funds futures` =
          fut_expected_change_bp -
          first_fut
      ) |>
      pivot_longer(
        -grid_time,
        names_to = "market",
        values_to = "change_from_start"
      )

    p_levels <- ggplot(
      centered,
      aes(
        grid_time,
        change_from_start,
        linetype = market
      )
    ) +
      geom_line(
        linewidth = 0.75
      ) +
      geom_hline(
        yintercept = 0
      ) +
      labs(
        title =
          paste0(
            meeting_id,
            ": cumulative repricing"
          ),
        subtitle =
          "Both series centered at first common valid observation",
        x = NULL,
        y =
          "Change from window start (bp)",
        linetype = NULL
      ) +
      theme_minimal()

    ggsave(
      file.path(
        meeting_dir,
        "01_centered_levels.png"
      ),
      p_levels,
      width = 10,
      height = 5,
      dpi = 300
    )
  }

  p_coherence <- ggplot(
    combined,
    aes(
      grid_time,
      pm_probability_sum
    )
  ) +
    geom_line() +
    geom_hline(
      yintercept = 1
    ) +
    geom_hline(
      yintercept = c(
        1 - COHERENCE_PRIMARY,
        1 + COHERENCE_PRIMARY
      ),
      linetype = "dashed"
    ) +
    labs(
      title =
        paste0(
          meeting_id,
          ": Polymarket probability coherence"
        ),
      x = NULL,
      y =
        "Sum of raw YES-equivalent prices"
    ) +
    theme_minimal()

  ggsave(
    file.path(
      meeting_dir,
      "02_coherence.png"
    ),
    p_coherence,
    width = 10,
    height = 5,
    dpi = 300
  )

  if (!quality$pass) {

    warning(
      paste0(
        meeting_id,
        " excluded by the pre-specified data-quality gate."
      )
    )

    return(
      list(
        meeting_id = meeting_id,
        eligible = FALSE,
        quality = quality,
        primary = tibble(),
        robustness = tibble(),
        stationarity = tibble(),
        residuals = tibble(),
        forecast = tibble(),
        BIC = tibble(),
        GIRF = tibble(),
        stability = tibble()
      )
    )
  }

  primary_fit <- fit_var(
    primary_design,
    PRIMARY_P
  )

  primary_results <- primary_fit$results |>
    mutate(
      meeting_id = meeting_id,
      specification =
        "Primary 15m VAR(4)",
      .before = 1
    )

  stability <- var_stability(
    primary_fit,
    PRIMARY_P
  )

  stationarity <- bind_rows(

    stationarity_test(
      primary_design$complete_grid$d_pm,
      "Delta PM"
    ),

    stationarity_test(
      primary_design$complete_grid$d_fut,
      "Delta FUT"
    )
  ) |>
    mutate(
      meeting_id = meeting_id,
      .before = 1
    )

  residuals <- residual_diagnostics(
    primary_fit,
    PRIMARY_GRID,
    PRIMARY_P
  ) |>
    mutate(
      meeting_id = meeting_id,
      .before = 1
    )

  forecast <- forecast_gain(
    primary_fit
  ) |>
    mutate(
      meeting_id = meeting_id,
      .before = 1
    )

  BIC <- bic_table(
    combined,
    max_p = 8
  ) |>
    mutate(
      meeting_id = meeting_id,
      .before = 1
    )

  GIRF <- compute_girf(
    primary_fit,
    PRIMARY_P,
    horizon = 8
  ) |>
    mutate(
      meeting_id = meeting_id,
      minutes_after =
        horizon *
        PRIMARY_GRID,
      .before = 1
    )

  var1 <- safe_spec(
    "15m VAR(1)",
    combined,
    p = 1,
    minimum_rows = 100
  )

  tight <- build_combined(
    pm,
    futures,
    window_start,
    window_end,
    15,
    COHERENCE_TIGHT,
    target_mid,
    basis
  )

  tight_results <- safe_spec(
    "15m VAR(4), +/-2% coherence",
    tight,
    p = 4,
    minimum_rows = 100
  )

  tail <- combined |>
    mutate(
      pm_expected_change_bp =
        pm_expected_change_tail75_bp
    )

  tail_results <- safe_spec(
    "15m VAR(4), tails +/-75bp",
    tail,
    p = 4,
    minimum_rows = 100
  )

  combined_5 <- build_combined(
    pm,
    futures,
    window_start,
    window_end,
    5,
    COHERENCE_PRIMARY,
    target_mid,
    basis
  )

  results_5 <- safe_spec(
    "5m VAR(12)",
    combined_5,
    p = 12,
    minimum_rows = 250
  )

  combined_30 <- build_combined(
    pm,
    futures,
    window_start,
    window_end,
    30,
    COHERENCE_PRIMARY,
    target_mid,
    basis
  )

  results_30 <- safe_spec(
    "30m VAR(2)",
    combined_30,
    p = 2,
    minimum_rows = 50
  )

  robustness <- bind_rows(
    var1,
    tight_results,
    tail_results,
    results_5,
    results_30
  ) |>
    mutate(
      meeting_id = meeting_id,
      .before = 1
    )

  revisions <- primary_design$complete_grid |>
    select(
      grid_time,
      d_pm,
      d_fut
    ) |>
    pivot_longer(
      c(
        d_pm,
        d_fut
      ),
      names_to = "series",
      values_to = "revision"
    ) |>
    mutate(
      market = dplyr::recode(
        series,
        d_pm = "Polymarket",
        d_fut =
          "Fed Funds futures"
      )
    )

  p_revisions <- ggplot(
    revisions,
    aes(
      grid_time,
      revision,
      linetype = market
    )
  ) +
    geom_line(
      linewidth = 0.6,
      na.rm = TRUE
    ) +
    geom_hline(
      yintercept = 0
    ) +
    labs(
      title =
        paste0(
          meeting_id,
          ": 15-minute policy-rate revisions"
        ),
      subtitle =
        "Variables entering primary VAR(4)",
      x = NULL,
      y = "Revision (bp)",
      linetype = NULL
    ) +
    theme_minimal()

  ggsave(
    file.path(
      meeting_dir,
      "03_revisions.png"
    ),
    p_revisions,
    width = 10,
    height = 5,
    dpi = 300
  )

  girf_plot <- GIRF |>
    mutate(
      direction = if_else(
        shock == "PM",
        "PM innovation -> Futures",
        "Futures innovation -> PM"
      )
    )

  p_girf <- ggplot(
    girf_plot,
    aes(
      minutes_after,
      dynamic_cross,
      linetype = direction
    )
  ) +
    geom_line(
      linewidth = 0.8
    ) +
    geom_point() +
    geom_hline(
      yintercept = 0
    ) +
    labs(
      title =
        paste0(
          meeting_id,
          ": dynamic cross-market GIRFs"
        ),
      subtitle =
        "Post-impact cumulative response per 1bp-equivalent innovation",
      x =
        "Minutes after innovation",
      y =
        "Post-impact cumulative response (bp)",
      linetype = NULL
    ) +
    theme_minimal()

  ggsave(
    file.path(
      meeting_dir,
      "04_dynamic_GIRF.png"
    ),
    p_girf,
    width = 10,
    height = 5,
    dpi = 300
  )

  write_csv(
    primary_design$model_data,
    file.path(
      meeting_dir,
      "VAR4_model_data.csv"
    )
  )

  write_csv(
    primary_results,
    file.path(
      meeting_dir,
      "primary_granger.csv"
    )
  )

  write_csv(
    robustness,
    file.path(
      meeting_dir,
      "robustness_granger.csv"
    )
  )

  write_csv(
    stationarity,
    file.path(
      meeting_dir,
      "stationarity.csv"
    )
  )

  write_csv(
    residuals,
    file.path(
      meeting_dir,
      "residual_diagnostics.csv"
    )
  )

  write_csv(
    forecast,
    file.path(
      meeting_dir,
      "forecast_gain.csv"
    )
  )

  write_csv(
    BIC,
    file.path(
      meeting_dir,
      "BIC.csv"
    )
  )

  write_csv(
    GIRF,
    file.path(
      meeting_dir,
      "GIRF.csv"
    )
  )

  cat("\nPRIMARY RESULTS\n")
  print(
    primary_results,
    width = Inf
  )

  cat("\nROBUSTNESS\n")
  print(
    robustness,
    width = Inf
  )

  cat("\nSTABILITY\n")
  print(
    stability,
    width = Inf
  )

  cat("\nRESIDUAL DIAGNOSTICS\n")
  print(
    residuals,
    width = Inf
  )

  list(
    meeting_id = meeting_id,
    eligible = TRUE,
    quality = quality,
    primary = primary_results,
    robustness = robustness,
    stationarity = stationarity,
    residuals = residuals,
    forecast = forecast,
    BIC = BIC,
    GIRF = GIRF,
    stability = stability
  )
}


# ==============================================================================
# 22. RUN ALL CONFIGURED MEETINGS
# ==============================================================================

meeting_runs <- purrr::pmap(
  MEETINGS,
  run_meeting
)


# ==============================================================================
# 23. COMBINE PROJECT RESULTS
# ==============================================================================

meeting_quality <- map_dfr(
  meeting_runs,
  "quality"
)

primary_tests <- map_dfr(
  meeting_runs,
  "primary"
)

robustness_tests <- map_dfr(
  meeting_runs,
  "robustness"
)

stationarity_all <- map_dfr(
  meeting_runs,
  "stationarity"
)

residuals_all <- map_dfr(
  meeting_runs,
  "residuals"
)

forecast_all <- map_dfr(
  meeting_runs,
  "forecast"
)

BIC_all <- map_dfr(
  meeting_runs,
  "BIC"
)


# ==============================================================================
# 24. FINAL PROJECT-WIDE HOLM CORRECTION
# ==============================================================================

if (nrow(primary_tests) > 0) {

  project_tests <- primary_tests |>
    mutate(
      Holm_HAC_p =
        p.adjust(
          HAC_p,
          method = "holm"
        ),
      significant_5pct =
        Holm_HAC_p < ALPHA
    )

} else {

  project_tests <- tibble()
}


# ==============================================================================
# 25. CLASSIFY EACH MEETING
# ==============================================================================

if (nrow(project_tests) > 0) {

  meeting_classification <- project_tests |>
    group_by(meeting_id) |>
    summarise(

      FUT_to_PM =
        any(
          direction == "FUT -> PM" &
            significant_5pct,
          na.rm = TRUE
        ),

      PM_to_FUT =
        any(
          direction == "PM -> FUT" &
            significant_5pct,
          na.rm = TRUE
        ),

      .groups = "drop"
    ) |>
    mutate(

      classification = case_when(

        FUT_to_PM &
          !PM_to_FUT ~
          "Futures-led",

        !FUT_to_PM &
          PM_to_FUT ~
          "Polymarket-led",

        FUT_to_PM &
          PM_to_FUT ~
          "Feedback",

        TRUE ~
          "Neither"
      )
    )

} else {

  meeting_classification <- tibble()
}


# ==============================================================================
# 26. SAVE PROJECT-WIDE TABLES
# ==============================================================================

write_csv(
  meeting_quality,
  file.path(
    OUTPUT_DIR,
    "PROJECT_data_quality.csv"
  )
)

write_csv(
  project_tests,
  file.path(
    OUTPUT_DIR,
    "PROJECT_primary_tests_Holm.csv"
  )
)

write_csv(
  robustness_tests,
  file.path(
    OUTPUT_DIR,
    "PROJECT_robustness.csv"
  )
)

write_csv(
  meeting_classification,
  file.path(
    OUTPUT_DIR,
    "PROJECT_meeting_classification.csv"
  )
)

write_csv(
  stationarity_all,
  file.path(
    OUTPUT_DIR,
    "PROJECT_stationarity.csv"
  )
)

write_csv(
  residuals_all,
  file.path(
    OUTPUT_DIR,
    "PROJECT_residual_diagnostics.csv"
  )
)

write_csv(
  forecast_all,
  file.path(
    OUTPUT_DIR,
    "PROJECT_forecast_gain.csv"
  )
)

write_csv(
  BIC_all,
  file.path(
    OUTPUT_DIR,
    "PROJECT_BIC.csv"
  )
)


# ==============================================================================
# 27. FINAL CONSOLE SUMMARY
# ==============================================================================

cat("\n\n")
cat("============================================================\n")
cat("PROJECT PIPELINE COMPLETE\n")
cat("============================================================\n")

cat("\nDATA QUALITY\n")
print(
  meeting_quality,
  width = Inf
)

cat("\nPRIMARY HAC TESTS + PROJECT-WIDE HOLM\n")
print(
  project_tests,
  width = Inf
)

cat("\nMEETING CLASSIFICATIONS\n")
print(
  meeting_classification,
  width = Inf
)

cat("\nROBUSTNESS TESTS\n")
print(
  robustness_tests,
  width = Inf
)

cat("\nRESIDUAL DIAGNOSTICS\n")
print(
  residuals_all,
  width = Inf
)

cat("\nFORECAST GAIN\n")
print(
  forecast_all,
  width = Inf
)

cat("\nBIC\n")
print(
  BIC_all,
  width = Inf
)

cat(
  "\nInterpretation:\n",
  "FUT -> PM means lagged Fed Funds futures revisions contain\n",
  "predictive information for subsequent Polymarket revisions.\n\n",
  "PM -> FUT means lagged Polymarket revisions contain predictive\n",
  "information for subsequent Fed Funds futures revisions.\n\n",
  "Use the HAC p-value for primary within-meeting inference and\n",
  "Holm_HAC_p for final cross-meeting significance.\n\n",
  "Granger predictability is interpreted as short-run price leadership,\n",
  "not structural causality or proof of private information.\n",
  sep = ""
)


# ==============================================================================
# 28. OPTIONAL
# ==============================================================================

# Only when completely finished:
#
# ld$close_session()
