######################################################################################################
# Greg's first feasibility test
#
# Tests the feasibility of retrieving intraday Polymarket data for FOMC interest-rate decisions.
# The script identifies relevant outcome contracts, extracts historical YES-token prices,
# aligns observations at 15-minute intervals,
# and prepares the data for constructing a prediction-market-implied expected policy rate.
######################################################################################################


# ============================================================
# REQUIRED PACKAGES
# ============================================================

required_packages <- c(
  "httr",
  "jsonlite",
  "dplyr",
  "purrr",
  "tidyr",
  "lubridate"
)

# Identify packages that are not currently installed
missing_packages <- required_packages[
  !required_packages %in% rownames(installed.packages())
]

# Install only missing packages
if (length(missing_packages) > 0) {
  
  message(
    "Installing missing packages: ",
    paste(missing_packages, collapse = ", ")
  )
  
  install.packages(
    missing_packages,
    repos = "https://cloud.r-project.org"
  )
  
} else {
  
  message("All required packages are already installed.")
}

# Load all required packages
invisible(
  lapply(
    required_packages,
    library,
    character.only = TRUE
  )
)

message("All required packages loaded successfully.")


# ============================================================
# 1. GET JULY 2026 FOMC EVENT METADATA
# ============================================================

slug <- "fed-decision-in-july-181"

event_url <- paste0(
  "https://gamma-api.polymarket.com/events/slug/",
  slug
)

event_response <- GET(event_url)

stop_for_status(event_response)

event <- fromJSON(
  content(
    event_response,
    "text",
    encoding = "UTF-8"
  )
)

markets <- event$markets


# Inspect the five FOMC outcome markets
markets |>
  select(
    question,
    groupItemTitle,
    clobTokenIds
  )


# ============================================================
# 2. EXTRACT YES TOKEN FOR EACH OUTCOME
# ============================================================

markets <- markets |>
  mutate(
    token_list = map(
      clobTokenIds,
      fromJSON
    ),
    
    # First token in each pair is the YES token
    yes_token = map_chr(
      token_list,
      1
    )
  )


# Check extracted YES tokens
yes_tokens <- markets |>
  select(
    groupItemTitle,
    yes_token
  )

print(yes_tokens)


# ============================================================
# 3. DEFINE TEST WINDOW
# ============================================================

# July 2026 FOMC decision announcement:
# 29 July 2026 at 2:00 PM New York time
#
# For this first feasibility test, we examine approximately
# one week of pre-announcement trading and stop 15 minutes
# before the policy announcement.

start_time <- as.POSIXct(
  "2026-07-22 09:00:00",
  tz = "America/New_York"
)

end_time <- as.POSIXct(
  "2026-07-29 13:45:00",
  tz = "America/New_York"
)

# Convert to Unix timestamps for the Polymarket API
start_ts <- as.numeric(start_time)
end_ts   <- as.numeric(end_time)


# ============================================================
# 4. FUNCTION TO DOWNLOAD POLYMARKET PRICE HISTORY
# ============================================================

get_history <- function(token_id, outcome_name) {
  
  url <- paste0(
    "https://clob.polymarket.com/prices-history?",
    "market=", token_id,
    "&startTs=", start_ts,
    "&endTs=", end_ts,
    "&fidelity=15"
  )
  
  response <- GET(url)
  
  stop_for_status(response)
  
  x <- fromJSON(
    content(
      response,
      "text",
      encoding = "UTF-8"
    )
  )
  
  # Return empty data frame if no observations are available
  if (is.null(x$history) || length(x$history) == 0) {
    
    warning(
      paste(
        "No price history returned for:",
        outcome_name
      )
    )
    
    return(
      data.frame(
        datetime = as.POSIXct(character()),
        outcome = character(),
        probability = numeric()
      )
    )
  }
  
  history <- as.data.frame(
    x$history
  )
  
  history |>
    mutate(
      datetime = as.POSIXct(
        t,
        origin = "1970-01-01",
        tz = "UTC"
      ),
      
      datetime = with_tz(
        datetime,
        "America/New_York"
      ),
      
      outcome = outcome_name
    ) |>
    select(
      datetime,
      outcome,
      probability = p
    )
}


# ============================================================
# 5. DOWNLOAD ALL FIVE FOMC OUTCOME SERIES
# ============================================================

pm_raw <- map2_dfr(
  markets$yes_token,
  markets$groupItemTitle,
  get_history
)


# ============================================================
# 6. BASIC DATA CHECKS
# ============================================================

# First observations
head(
  pm_raw,
  20
)

# Number of observations per outcome
table(
  pm_raw$outcome
)

# Overall time range
range(
  pm_raw$datetime
)

# Summary of probabilities
summary(
  pm_raw$probability
)


# ============================================================
# 7. FEASIBILITY SUMMARY BY OUTCOME
# ============================================================

feasibility_summary <- pm_raw |>
  group_by(
    outcome
  ) |>
  summarise(
    observations = n(),
    
    first_time = min(
      datetime,
      na.rm = TRUE
    ),
    
    last_time = max(
      datetime,
      na.rm = TRUE
    ),
    
    min_probability = min(
      probability,
      na.rm = TRUE
    ),
    
    max_probability = max(
      probability,
      na.rm = TRUE
    ),
    
    .groups = "drop"
  )

print(
  feasibility_summary
)

# ============================================================
# 8. ALIGN OBSERVATIONS TO 15-MINUTE GRID
# ============================================================

pm_aligned <- pm_raw |>
  mutate(
    datetime_15 = floor_date(
      datetime,
      unit = "15 minutes"
    )
  ) |>
  group_by(
    datetime_15,
    outcome
  ) |>
  summarise(
    probability = last(probability),
    .groups = "drop"
  )

head(pm_aligned, 20)

# ============================================================
# 9. RESHAPE OUTCOME PROBABILITIES TO WIDE FORMAT
# ============================================================

pm_wide <- pm_aligned |>
  pivot_wider(
    names_from = outcome,
    values_from = probability
  ) |>
  arrange(datetime_15)

head(pm_wide, 20)

# ============================================================
# 10. CHECK SUM OF OUTCOME PROBABILITIES
# ============================================================

pm_wide <- pm_wide |>
  mutate(
    probability_sum =
      `No change` +
      `25 bps increase` +
      `25 bps decrease` +
      `50+ bps increase` +
      `50+ bps decrease`
  )

summary(pm_wide$probability_sum)

head(
  pm_wide |>
    select(
      datetime_15,
      probability_sum
    ),
  20
)