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

# ============================================================
# 11. DIAGNOSE MISSING OUTCOME OBSERVATIONS
# ============================================================

# Count missing observations for each outcome series
missing_summary <- pm_wide |>
  summarise(
    missing_no_change =
      sum(is.na(`No change`)),
    
    missing_25_increase =
      sum(is.na(`25 bps increase`)),
    
    missing_25_decrease =
      sum(is.na(`25 bps decrease`)),
    
    missing_50_increase =
      sum(is.na(`50+ bps increase`)),
    
    missing_50_decrease =
      sum(is.na(`50+ bps decrease`))
  )

print(missing_summary)


# Identify every 15-minute interval for which
# at least one outcome price is unavailable
missing_intervals <- pm_wide |>
  filter(
    is.na(`No change`) |
      is.na(`25 bps increase`) |
      is.na(`25 bps decrease`) |
      is.na(`50+ bps increase`) |
      is.na(`50+ bps decrease`)
  )

print(missing_intervals)

# Number of complete and incomplete 15-minute intervals
pm_wide |>
  summarise(
    total_intervals = n(),
    
    complete_intervals = sum(
      complete.cases(
        `No change`,
        `25 bps increase`,
        `25 bps decrease`,
        `50+ bps increase`,
        `50+ bps decrease`
      )
    ),
    
    incomplete_intervals =
      total_intervals - complete_intervals
  )

# ============================================================
# 12. INSPECT PATTERN OF MISSING OBSERVATIONS
# ============================================================

# Show which outcomes are missing in each incomplete interval
missing_pattern <- pm_wide |>
  filter(
    !complete.cases(
      `No change`,
      `25 bps increase`,
      `25 bps decrease`,
      `50+ bps increase`,
      `50+ bps decrease`
    )
  ) |>
  mutate(
    missing_no_change =
      is.na(`No change`),
    
    missing_25_increase =
      is.na(`25 bps increase`),
    
    missing_25_decrease =
      is.na(`25 bps decrease`),
    
    missing_50_increase =
      is.na(`50+ bps increase`),
    
    missing_50_decrease =
      is.na(`50+ bps decrease`)
  ) |>
  select(
    datetime_15,
    starts_with("missing_")
  )

print(
  missing_pattern,
  n = Inf
)

# ============================================================
# 13. MEASURE LENGTH OF MISSING RUNS
# ============================================================

# Create indicators for missing observations
gap_check <- pm_wide |>
  arrange(datetime_15) |>
  mutate(
    miss_no_change = is.na(`No change`),
    miss_50_increase = is.na(`50+ bps increase`),
    miss_50_decrease = is.na(`50+ bps decrease`)
  )


# Helper function to calculate consecutive runs of TRUE/FALSE
run_summary <- function(x) {
  
  r <- rle(x)
  
  data.frame(
    missing = r$values,
    run_length = r$lengths
  ) |>
    filter(missing == TRUE)
}


# Missing-run lengths for each affected outcome
no_change_runs <- run_summary(
  gap_check$miss_no_change
)

increase_50_runs <- run_summary(
  gap_check$miss_50_increase
)

decrease_50_runs <- run_summary(
  gap_check$miss_50_decrease
)


print(no_change_runs)
print(increase_50_runs)
print(decrease_50_runs)


# Maximum number of consecutive missing 15-minute intervals
cat(
  "Maximum consecutive missing intervals - No change:",
  max(no_change_runs$run_length),
  "\n"
)

cat(
  "Maximum consecutive missing intervals - 50+ increase:",
  max(increase_50_runs$run_length),
  "\n"
)

cat(
  "Maximum consecutive missing intervals - 50+ decrease:",
  max(decrease_50_runs$run_length),
  "\n"
)

# ============================================================
# 14. SAVE FEASIBILITY TEST OUTPUTS
# ============================================================

output_dir <- "/Users/gregcunningham/Desktop/ECMT3150 - Group 9 - Feasibility on PolyMarket"

dir.create(
  output_dir,
  recursive = TRUE,
  showWarnings = FALSE
)

# Raw Polymarket API data
write.csv(
  pm_raw,
  file.path(
    output_dir,
    "01_polymarket_raw_data.csv"
  ),
  row.names = FALSE
)

# 15-minute aligned outcome data
write.csv(
  pm_wide,
  file.path(
    output_dir,
    "02_polymarket_15min_aligned.csv"
  ),
  row.names = FALSE
)

# Feasibility summary by outcome
write.csv(
  feasibility_summary,
  file.path(
    output_dir,
    "03_feasibility_summary.csv"
  ),
  row.names = FALSE
)

# Missing-data summary
write.csv(
  missing_summary,
  file.path(
    output_dir,
    "04_missing_data_summary.csv"
  ),
  row.names = FALSE
)

# Individual incomplete timestamps
write.csv(
  missing_intervals,
  file.path(
    output_dir,
    "05_missing_intervals.csv"
  ),
  row.names = FALSE
)

# Missing-data pattern
write.csv(
  missing_pattern,
  file.path(
    output_dir,
    "06_missing_pattern.csv"
  ),
  row.names = FALSE
)

# Consecutive missing-run lengths
write.csv(
  no_change_runs,
  file.path(
    output_dir,
    "07_missing_runs_no_change.csv"
  ),
  row.names = FALSE
)

write.csv(
  increase_50_runs,
  file.path(
    output_dir,
    "08_missing_runs_50bp_increase.csv"
  ),
  row.names = FALSE
)

write.csv(
  decrease_50_runs,
  file.path(
    output_dir,
    "09_missing_runs_50bp_decrease.csv"
  ),
  row.names = FALSE
)

message(
  "All feasibility outputs saved to: ",
  output_dir
)

# ============================================================
# 14. PLOT FOMC OUTCOME PROBABILITIES
# ============================================================

# Install ggplot2 if required
if (!requireNamespace("ggplot2", quietly = TRUE)) {
  install.packages("ggplot2")
}

library(ggplot2)

pm_plot <- pm_wide |>
  select(
    datetime_15,
    `No change`,
    `25 bps increase`,
    `25 bps decrease`,
    `50+ bps increase`,
    `50+ bps decrease`
  ) |>
  pivot_longer(
    cols = -datetime_15,
    names_to = "outcome",
    values_to = "probability"
  )

ggplot(
  pm_plot,
  aes(
    x = datetime_15,
    y = probability,
    colour = outcome
  )
) +
  geom_line(
    linewidth = 0.7,
    na.rm = TRUE
  ) +
  labs(
    title = "Polymarket Expectations Before the July 2026 FOMC Decision",
    subtitle = "15-minute market-implied probabilities",
    x = NULL,
    y = "Market-implied probability",
    colour = "FOMC outcome"
  ) +
  scale_y_continuous(
    labels = scales::percent_format(accuracy = 1)
  ) +
  theme_minimal()