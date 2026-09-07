# ==============================================================================
# ECMT3150 GROUP PROJECT — FINAL PUBLICATION-QUALITY VISUALS
# WHO PRICES THE FED FIRST?
#
# Run AFTER ECMT3150_final_reproducible.R has completed successfully.
# It can be run in the same R session OR a fresh R session.
#
# This script DOES NOT re-estimate any model.
# It only reads the frozen CSV outputs and visualises them.
# ==============================================================================

# ------------------------------
# 0. PACKAGES
# ------------------------------
required_visual_packages <- c(
  "tidyverse",
  "patchwork",
  "ggrepel",
  "scales"
)

missing_visual_packages <- required_visual_packages[
  !required_visual_packages %in% rownames(installed.packages())
]

if (length(missing_visual_packages) > 0) {
  install.packages(missing_visual_packages)
}

suppressPackageStartupMessages({
  library(tidyverse)
  library(patchwork)
  library(ggrepel)
  library(scales)
})

# ------------------------------
# 1. LOCATIONS
# ------------------------------
if (!exists("OUT_DIR")) OUT_DIR <- "ecmt3150_final_results"

if (!dir.exists(OUT_DIR)) {
  stop(
    "Could not find '", OUT_DIR,
    "'. Run ECMT3150_final_reproducible.R first."
  )
}

VIS_DIR <- file.path(OUT_DIR, "figures_publication")
dir.create(VIS_DIR, recursive = TRUE, showWarnings = FALSE)

# ------------------------------
# 2. READ FROZEN OUTPUTS
# ------------------------------
read_result <- function(filename) {
  path <- file.path(OUT_DIR, filename)
  if (!file.exists(path)) stop("Missing result file: ", path)
  readr::read_csv(path, show_col_types = FALSE, progress = FALSE)
}

to_numeric <- function(data, columns) {
  data |>
    mutate(across(any_of(columns), ~ suppressWarnings(as.numeric(.x))))
}

to_logical_safe <- function(x) {
  if (is.logical(x)) return(x)
  if (is.numeric(x)) return(ifelse(is.na(x), NA, x != 0))
  z <- tolower(trimws(as.character(x)))
  out <- rep(NA, length(z))
  out[z %in% c("true", "t", "1", "yes")] <- TRUE
  out[z %in% c("false", "f", "0", "no")] <- FALSE
  out
}

screening      <- read_result("01_preinference_screening.csv")
primary_tests  <- read_result("02_primary_granger_blockHAC_Holm.csv")
classification <- read_result("03_meeting_classification.csv")
stability      <- read_result("04_VAR1_stability.csv")
bvar_coef      <- read_result("05_BVAR_coefficients.csv")
bvar_girf      <- read_result("06_BVAR_GIRF.csv")
bvar_stability <- read_result("07_BVAR_stability.csv")
loo             <- read_result("08_leave_one_event_out.csv")
loo_summary     <- read_result("09_leave_one_event_out_summary.csv")
master          <- read_result("10_FINAL_MASTER_RESULTS.csv")
primary_paths   <- read_result("11_primary_synchronized_paths.csv")

screening <- to_numeric(
  screening,
  c(
    "calendar_joint_share", "joint_given_futures",
    "synchronized_blocks", "longest_block_hours",
    "VAR1_rows", "PM_revisions", "FUT_revisions",
    "lagged_FUT_predictor_events", "rank", "columns"
  )
)

primary_tests <- to_numeric(
  primary_tests,
  c(
    "coefficient",
    "conventional_se", "conventional_F", "conventional_p",
    "HC3_se", "HC3_Wald", "HC3_p",
    "block_HAC_lag", "block_HAC_minutes",
    "block_HAC_se", "block_HAC_Wald", "block_HAC_p", "block_HAC_p_Holm"
  )
) |>
  mutate(significant_Holm = to_logical_safe(significant_Holm))

bvar_coef <- to_numeric(
  bvar_coef,
  c("median", "lower", "upper", "Pr_positive", "Pr_negative")
)

bvar_girf <- to_numeric(
  bvar_girf,
  c(
    "horizon", "horizon_minutes",
    "median", "lower", "upper",
    "Pr_positive", "Pr_negative"
  )
)

loo <- to_numeric(
  loo,
  c("deletion", "removed_futures_predictor", "coefficient", "block_HAC_p")
) |>
  mutate(removed_time = as.POSIXct(removed_time, tz = "UTC"))

loo_summary <- to_numeric(
  loo_summary,
  c(
    "predictor_events_tested",
    "coefficient_min", "coefficient_max", "coefficient_median",
    "smallest_HAC_p", "largest_HAC_p", "share_HAC_p_below_05"
  )
)

primary_paths <- to_numeric(
  primary_paths,
  c(
    "sync_block_id", "hours_to_FOMC",
    "pm_expected_change_bp", "fut_expected_change_bp"
  )
)

required_primary_numeric <- c(
  "coefficient", "block_HAC_se", "block_HAC_p", "block_HAC_p_Holm"
)

if (
  nrow(primary_tests) != 4L ||
  any(!is.finite(as.matrix(primary_tests[required_primary_numeric])))
) {
  stop(
    "The primary-results CSV is incomplete or contains NA/non-finite values. ",
    "Rerun ECMT3150_final_reproducible.R before running visuals."
  )
}

if (nrow(bvar_coef) != 4L || nrow(bvar_girf) == 0L || nrow(loo) == 0L) {
  stop(
    "One or more Bayesian/sensitivity result files are incomplete. ",
    "Rerun the reproducible script first."
  )
}

# ------------------------------
# 3. VISUAL IDENTITY
# ------------------------------
COL_FUTURES <- "#0072B2"   # blue
COL_KALSHI  <- "#D55E00"   # vermillion
COL_PRIMARY <- "#16324F"   # navy
COL_DESC    <- "#8B95A1"   # grey
COL_EXCL    <- "#B94A48"   # muted red
COL_SIG     <- "#00876C"   # teal-green
COL_NSIG    <- "#A7ADB4"   # grey
COL_GOLD    <- "#C58A1B"
COL_DARK    <- "#20252B"
COL_LIGHT   <- "#F4F6F8"

market_cols <- c(
  "Fed Funds futures" = COL_FUTURES,
  "Kalshi" = COL_KALSHI
)

direction_cols <- c(
  "Fed Funds futures -> Kalshi" = COL_FUTURES,
  "Kalshi -> Fed Funds futures" = COL_KALSHI
)

meeting_labels <- c(
  "2025-09" = "September 2025",
  "2025-10" = "October 2025",
  "2025-12" = "December 2025",
  "2026-01" = "January 2026",
  "2026-03" = "March 2026",
  "2026-04" = "April 2026"
)

direction_labels <- c(
  "FUT_to_K" = "Futures → Kalshi",
  "K_to_FUT" = "Kalshi → Futures"
)

theme_story <- function(base_size = 12) {
  theme_minimal(base_size = base_size, base_family = "sans") +
    theme(
      plot.title.position = "plot",
      plot.caption.position = "plot",
      plot.title = element_text(
        face = "bold", size = rel(1.30), colour = COL_DARK,
        margin = margin(b = 6)
      ),
      plot.subtitle = element_text(
        size = rel(0.98), colour = "#555B61",
        margin = margin(b = 12)
      ),
      plot.caption = element_text(
        size = rel(0.78), colour = "#6A7076", hjust = 0,
        margin = margin(t = 10)
      ),
      axis.title = element_text(face = "bold", colour = COL_DARK),
      axis.text = element_text(colour = "#3B4045"),
      panel.grid.minor = element_blank(),
      panel.grid.major.y = element_blank(),
      strip.text = element_text(face = "bold", colour = COL_DARK),
      strip.background = element_rect(fill = COL_LIGHT, colour = NA),
      legend.position = "top",
      legend.justification = "left",
      legend.title = element_blank(),
      plot.margin = margin(12, 16, 12, 12)
    )
}

save_story_plot <- function(plot, filename, width, height) {
  ggsave(
    filename = file.path(VIS_DIR, paste0(filename, ".png")),
    plot = plot,
    width = width,
    height = height,
    dpi = 400,
    bg = "white"
  )


  ggsave(
    filename = file.path(VIS_DIR, paste0(filename, ".pdf")),
    plot = plot,
    width = width,
    height = height,
    device = "pdf",
    bg = "white"
  )
}

# ==============================================================================
# FIGURE 1 — WHY ONLY SEPTEMBER AND DECEMBER ENTER PRIMARY INFERENCE
# ==============================================================================
# Story:
#   December has the richest two-market repricing.
#   September has enough variation to remain a primary candidate but is sparse.
#   October/January/March have very little futures variation; April has no
#   Kalshi expected-rate revisions.
#
# IMPORTANT: the axes show revision counts, NOT a retrospective eligibility rule.
# ==============================================================================

screen_plot_data <- screening |>
  mutate(
    meeting = factor(meeting_id, levels = screening$meeting_id),
    role_group = case_when(
      role == "Primary" ~ "Primary inference",
      str_detect(role, "Excluded") ~ "Excluded",
      TRUE ~ "Descriptive only"
    ),
    role_group = factor(
      role_group,
      levels = c("Primary inference", "Descriptive only", "Excluded")
    )
  )

p_screen <- ggplot(
  screen_plot_data,
  aes(x = FUT_revisions, y = PM_revisions)
) +
  geom_hline(yintercept = 0, linewidth = 0.3, colour = "#D4D8DC") +
  geom_vline(xintercept = 0, linewidth = 0.3, colour = "#D4D8DC") +
  geom_point(
    aes(size = VAR1_rows, colour = role_group, shape = role_group),
    alpha = 0.92,
    stroke = 1.1
  ) +
  ggrepel::geom_text_repel(
    aes(label = meeting_labels[meeting_id]),
    seed = 3150,
    size = 3.7,
    colour = COL_DARK,
    min.segment.length = 0,
    box.padding = 0.45,
    point.padding = 0.35,
    max.overlaps = Inf
  ) +
  scale_colour_manual(values = c(
    "Primary inference" = COL_PRIMARY,
    "Descriptive only" = COL_DESC,
    "Excluded" = COL_EXCL
  )) +
  scale_shape_manual(values = c(
    "Primary inference" = 16,
    "Descriptive only" = 1,
    "Excluded" = 4
  )) +
  scale_size_continuous(
    range = c(4, 10),
    breaks = c(100, 250, 400),
    name = "VAR(1) rows"
  ) +
  scale_x_continuous(expand = expansion(mult = c(0.03, 0.20))) +
  scale_y_continuous(expand = expansion(mult = c(0.03, 0.18))) +
  labs(
    title = "The inferential bottleneck is two-market repricing, not raw sample size",
    subtitle = paste0(
      "December contains the richest joint variation. January has many Kalshi revisions but only three futures revisions; ",
      "April has no Kalshi expected-rate revisions."
    ),
    x = "Non-zero Fed Funds futures revisions",
    y = "Non-zero Kalshi expected-rate revisions",
    caption = paste0(
      "Point size = usable synchronized VAR(1) rows. Primary/descriptive roles were frozen before the redesigned inference. ",
      "Revision counts are shown as diagnostics, not as a post-hoc hard cutoff."
    )
  ) +
  theme_story() +
  theme(legend.box = "vertical")

save_story_plot(p_screen, "01_meeting_audit_repricing", 10.5, 7.2)

# ==============================================================================
# FIGURE 2 — SYNCHRONIZED EXPECTED-RATE PATHS
# ==============================================================================

path_plot <- primary_paths |>
  transmute(
    meeting_id,
    sync_block_id,
    hours_to_FOMC,
    Kalshi = pm_expected_change_bp,
    `Fed Funds futures` = fut_expected_change_bp
  ) |>
  pivot_longer(
    cols = c(Kalshi, `Fed Funds futures`),
    names_to = "market",
    values_to = "expected_change_bp"
  ) |>
  mutate(
    meeting = factor(
      unname(meeting_labels[meeting_id]),
      levels = c("September 2025", "December 2025")
    )
  )

p_paths <- ggplot(
  path_plot,
  aes(
    x = hours_to_FOMC,
    y = expected_change_bp,
    colour = market,
    group = interaction(market, sync_block_id)
  )
) +
  annotate(
    "rect",
    xmin = -48,
    xmax = -0.25,
    ymin = -Inf,
    ymax = Inf,
    fill = COL_GOLD,
    alpha = 0.055
  ) +
  geom_line(linewidth = 0.72, alpha = 0.95, na.rm = TRUE) +
  geom_vline(
    xintercept = -48,
    linetype = "dashed",
    linewidth = 0.45,
    colour = COL_GOLD
  ) +
  geom_hline(yintercept = 0, linewidth = 0.4, colour = "#9EA5AB") +
  facet_wrap(~ meeting, ncol = 1, scales = "free_y") +
  scale_colour_manual(values = market_cols) +
  scale_x_continuous(
    breaks = c(-168, -144, -120, -96, -72, -48, -24, 0),
    labels = function(x) ifelse(x == 0, "FOMC", paste0(abs(x), "h")),
    expand = expansion(mult = c(0.01, 0.02))
  ) +
  labs(
    title = "Relevant repricing is not confined to the final 48 hours",
    subtitle = paste0(
      "Expected policy-rate changes on the common 15-minute grid. ",
      "Lines break whenever the markets are not continuously synchronized; ",
      "the shaded region is the old final-48h window."
    ),
    x = "Time before scheduled FOMC announcement",
    y = "Expected policy-rate change (bp)",
    colour = NULL,
    caption = "No line connects observations across overnight, weekend or other synchronization gaps."
  ) +
  theme_story() +
  theme(legend.position = "top")

save_story_plot(p_paths, "02_synchronized_expected_rate_paths", 11, 8.2)

# ==============================================================================
# FIGURE 3 — HERO FIGURE: PRIMARY BLOCK-HAC DIRECTIONAL RESULTS
# ==============================================================================
# Story:
#   Only December Futures -> Kalshi survives the Holm correction.
# ==============================================================================

freq_plot <- primary_tests |>
  mutate(
    ci_low = coefficient - qnorm(0.975) * block_HAC_se,
    ci_high = coefficient + qnorm(0.975) * block_HAC_se,
    meeting = factor(
      meeting_labels[meeting_id],
      levels = c("September 2025", "December 2025")
    ),
    direction_short = factor(
      direction_labels[direction_code],
      levels = c("Futures → Kalshi", "Kalshi → Futures")
    ),
    sig_label = if_else(
      significant_Holm,
      paste0("Holm p = ", sprintf("%.4f", block_HAC_p_Holm), "  ✓"),
      paste0("Holm p = ", sprintf("%.3f", block_HAC_p_Holm))
    )
  )

p_hero <- ggplot(freq_plot) +
  geom_vline(xintercept = 0, linewidth = 0.55, colour = "#70777D") +
  geom_segment(
    aes(
      x = ci_low,
      xend = ci_high,
      y = direction_short,
      yend = direction_short,
      colour = direction
    ),
    linewidth = 1.15,
    lineend = "round"
  ) +
  geom_point(
    aes(
      x = coefficient,
      y = direction_short,
      colour = direction,
      fill = significant_Holm
    ),
    shape = 21,
    size = 4.7,
    stroke = 1.25
  ) +
  geom_text(
    aes(
      x = ci_high,
      y = direction_short,
      label = sig_label
    ),
    hjust = -0.08,
    size = 3.65,
    colour = COL_DARK
  ) +
  facet_wrap(~ meeting, ncol = 1) +
  scale_colour_manual(values = direction_cols) +
  scale_fill_manual(values = c(`TRUE` = COL_SIG, `FALSE` = "white"), guide = "none") +
  scale_x_continuous(expand = expansion(mult = c(0.08, 0.34))) +
  labs(
    title = "December shows one-way predictive leadership from Fed Funds futures to Kalshi",
    subtitle = "Point estimates and 95% confidence intervals use the block-aware HAC covariance estimator; p-values are Holm-adjusted across the four primary directional tests.",
    x = "Cross-lag coefficient: effect of previous 15-minute revision",
    y = NULL,
    caption = {
      dec_fk <- freq_plot |>
        filter(meeting_id == "2025-12", direction_code == "FUT_to_K")

      paste0(
        "December Futures → Kalshi: coefficient = ",
        sprintf("%.3f", dec_fk$coefficient[[1]]),
        ", raw block-HAC p = ",
        sprintf("%.4f", dec_fk$block_HAC_p[[1]]),
        ", Holm p = ",
        sprintf("%.4f", dec_fk$block_HAC_p_Holm[[1]]),
        ". September: neither direction is statistically significant."
      )
    }
  ) +
  theme_story() +
  theme(
    legend.position = "none",
    panel.spacing.y = grid::unit(1.0, "lines")
  )

save_story_plot(p_hero, "03_HERO_blockHAC_directional_results", 11, 7.2)

# ==============================================================================
# FIGURE 4 — FREQUENTIST VS BAYESIAN EVIDENCE
# ==============================================================================
# Story:
#   Frequentist HAC finds a December effect; the BVAR shrinks the magnitude
#   toward zero and its 90% credible interval crosses zero.
# ==============================================================================

freq_compare <- primary_tests |>
  transmute(
    meeting_id,
    direction_code,
    direction,
    method = "Block-HAC VAR(1)\n95% confidence interval",
    estimate = coefficient,
    lower = coefficient - qnorm(0.975) * block_HAC_se,
    upper = coefficient + qnorm(0.975) * block_HAC_se
  )

bayes_compare <- bvar_coef |>
  transmute(
    meeting_id,
    direction_code,
    direction,
    method = "Shrinkage BVAR(1)\n90% credible interval",
    estimate = median,
    lower,
    upper
  )

compare_plot <- bind_rows(freq_compare, bayes_compare) |>
  mutate(
    meeting = factor(
      meeting_labels[meeting_id],
      levels = c("September 2025", "December 2025")
    ),
    direction_short = factor(
      direction_labels[direction_code],
      levels = c("Futures → Kalshi", "Kalshi → Futures")
    ),
    method = factor(
      method,
      levels = c(
        "Block-HAC VAR(1)\n95% confidence interval",
        "Shrinkage BVAR(1)\n90% credible interval"
      )
    )
  )

p_compare <- ggplot(compare_plot) +
  geom_vline(xintercept = 0, linewidth = 0.55, colour = "#7A8187") +
  geom_segment(
    aes(
      x = lower,
      xend = upper,
      y = direction_short,
      yend = direction_short,
      colour = direction
    ),
    linewidth = 1.05,
    lineend = "round"
  ) +
  geom_point(
    aes(x = estimate, y = direction_short, colour = direction),
    size = 3.8
  ) +
  facet_grid(meeting ~ method, scales = "free_x") +
  scale_colour_manual(values = direction_cols) +
  labs(
    title = "Bayesian shrinkage makes the December effect smaller and more uncertain",
    subtitle = paste0(
      "The primary block-HAC estimate rejects zero for December Futures → Kalshi, while the shrinkage BVAR posterior remains directionally negative but its 90% interval includes zero."
    ),
    x = "Cross-market lag coefficient",
    y = NULL,
    caption = "Different interval levels are intentional: frequentist panels show 95% confidence intervals; Bayesian panels show the pre-specified 90% credible intervals."
  ) +
  theme_story() +
  theme(legend.position = "none")

save_story_plot(p_compare, "04_frequentist_vs_BVAR", 12, 8.1)

# ==============================================================================
# FIGURE 5 — LEAVE-ONE-FUTURES-PREDICTOR-OUT ROBUSTNESS
# ==============================================================================
# Story:
#   December is not generated by one single futures predictor observation.
#   September remains non-significant throughout.
# ==============================================================================

loo_plot_data <- loo |>
  arrange(meeting_id, removed_time) |>
  group_by(meeting_id) |>
  mutate(event_number = row_number()) |>
  ungroup() |>
  left_join(
    primary_tests |>
      filter(direction_code == "FUT_to_K") |>
      select(
        meeting_id,
        original_coefficient = coefficient,
        original_p = block_HAC_p
      ),
    by = "meeting_id"
  ) |>
  mutate(
    meeting = factor(
      meeting_labels[meeting_id],
      levels = c("September 2025", "December 2025")
    ),
    significant_raw = block_HAC_p < 0.05
  )

p_loo_coef <- ggplot(
  loo_plot_data,
  aes(event_number, coefficient)
) +
  geom_hline(yintercept = 0, linewidth = 0.45, colour = "#8D949A") +
  geom_line(colour = COL_FUTURES, linewidth = 0.7, alpha = 0.75) +
  geom_point(
    aes(fill = significant_raw),
    shape = 21,
    colour = COL_FUTURES,
    size = 3.5,
    stroke = 1
  ) +
  geom_hline(
    aes(yintercept = original_coefficient),
    linetype = "dashed",
    linewidth = 0.7,
    colour = COL_DARK
  ) +
  facet_wrap(~ meeting, ncol = 1, scales = "free_x") +
  scale_fill_manual(
    values = c(`TRUE` = COL_SIG, `FALSE` = "white"),
    labels = c(`TRUE` = "Raw HAC p < 0.05", `FALSE` = "Raw HAC p ≥ 0.05")
  ) +
  scale_x_continuous(breaks = scales::breaks_pretty(n = 8)) +
  labs(
    title = "Coefficient after deleting each lagged futures predictor event",
    x = "Predictor event removed (chronological order)",
    y = "Re-estimated Futures → Kalshi coefficient",
    fill = NULL
  ) +
  theme_story(base_size = 11.5)

p_loo_p <- ggplot(
  loo_plot_data,
  aes(event_number, block_HAC_p)
) +
  geom_hline(yintercept = 0.05, linetype = "dashed", colour = COL_EXCL, linewidth = 0.7) +
  geom_line(colour = COL_PRIMARY, linewidth = 0.7, alpha = 0.75) +
  geom_point(
    aes(colour = significant_raw),
    size = 3.1
  ) +
  facet_wrap(~ meeting, ncol = 1, scales = "free_x") +
  scale_colour_manual(
    values = c(`TRUE` = COL_SIG, `FALSE` = COL_NSIG),
    guide = "none"
  ) +
  scale_x_continuous(breaks = scales::breaks_pretty(n = 8)) +
  scale_y_continuous(
    expand = expansion(mult = c(0.03, 0.10))
  ) +
  labs(
    title = "Raw block-HAC p-value after each deletion",
    x = "Predictor event removed (chronological order)",
    y = "Block-HAC p-value",
    caption = "Dashed line = 5% threshold. These sensitivity p-values are not part of the four-test Holm family."
  ) +
  theme_story(base_size = 11.5) +
  theme(legend.position = "none")

p_loo <- (p_loo_coef | p_loo_p) +
  plot_annotation(
    title = "December's futures-leadership result is not driven by one observation",
    subtitle = {
      dec_loo <- loo_summary |> filter(meeting_id == "2025-12")
      sep_loo <- loo_summary |> filter(meeting_id == "2025-09")

      dec_sig <- round(
        dec_loo$predictor_events_tested[[1]] * dec_loo$share_HAC_p_below_05[[1]]
      )
      sep_sig <- round(
        sep_loo$predictor_events_tested[[1]] * sep_loo$share_HAC_p_below_05[[1]]
      )

      paste0(
        "All deletion estimates preserve the negative sign. In December, ",
        dec_sig, " of ", dec_loo$predictor_events_tested[[1]],
        " re-estimations retain raw block-HAC p < 0.05; in September, ",
        sep_sig, " of ", sep_loo$predictor_events_tested[[1]], " do."
      )
    },
    theme = theme(
      plot.title = element_text(face = "bold", size = 17, colour = COL_DARK),
      plot.subtitle = element_text(size = 11.5, colour = "#555B61")
    )
  )

save_story_plot(p_loo, "05_leave_one_event_out_robustness", 14, 8.4)

# ==============================================================================
# FIGURE 6 — GENERALIZED REDUCED-FORM GIRFs
# ==============================================================================
# These are reduced-form generalized responses, not causal structural IRFs.

girf_plot_data <- bvar_girf |>
  mutate(
    meeting = factor(
      unname(meeting_labels[meeting_id]),
      levels = c("September 2025", "December 2025")
    ),
    direction_short = factor(
      unname(direction_labels[direction_code]),
      levels = c("Futures → Kalshi", "Kalshi → Futures")
    )
  )

girf_cols <- c(
  "Futures → Kalshi" = COL_FUTURES,
  "Kalshi → Futures" = COL_KALSHI
)

p_girf <- ggplot(
  girf_plot_data,
  aes(
    x = horizon_minutes,
    y = median,
    colour = direction_short,
    fill = direction_short,
    group = direction_short
  )
) +
  geom_ribbon(
    aes(ymin = lower, ymax = upper),
    alpha = 0.13,
    colour = NA,
    na.rm = TRUE
  ) +
  geom_line(linewidth = 0.9, na.rm = TRUE) +
  geom_point(size = 2.6, na.rm = TRUE) +
  geom_hline(yintercept = 0, linewidth = 0.45, colour = "#747B81") +
  facet_wrap(~ meeting, ncol = 1, scales = "free_y") +
  scale_colour_manual(values = girf_cols) +
  scale_fill_manual(values = girf_cols) +
  scale_x_continuous(breaks = seq(0, 60, 15)) +
  labs(
    title = "Cross-market responses decay quickly",
    subtitle = "Posterior medians with 90% credible intervals from generalized reduced-form BVAR responses.",
    x = "Minutes after innovation",
    y = "Cross-market response",
    colour = NULL,
    fill = NULL,
    caption = "Generalized responses describe reduced-form dynamics and do not impose a causal contemporaneous ordering."
  ) +
  theme_story()

save_story_plot(p_girf, "06_BVAR_generalized_IRF", 10.8, 8.0)

girf_dec_data <- girf_plot_data |>
  filter(meeting_id == "2025-12")

p_girf_dec <- ggplot(
  girf_dec_data,
  aes(
    x = horizon_minutes,
    y = median,
    colour = direction_short,
    fill = direction_short,
    group = direction_short
  )
) +
  geom_ribbon(
    aes(ymin = lower, ymax = upper),
    alpha = 0.13,
    colour = NA,
    na.rm = TRUE
  ) +
  geom_line(linewidth = 0.95, na.rm = TRUE) +
  geom_point(size = 2.8, na.rm = TRUE) +
  geom_hline(yintercept = 0, linewidth = 0.45, colour = "#747B81") +
  scale_colour_manual(values = girf_cols) +
  scale_fill_manual(values = girf_cols) +
  scale_x_continuous(breaks = seq(0, 60, 15)) +
  labs(
    title = "December: contemporaneous co-movement is followed by a small short-run correction",
    subtitle = "Generalized reduced-form BVAR responses; posterior median and 90% credible interval.",
    x = "Minutes after innovation",
    y = "Cross-market response",
    colour = NULL,
    fill = NULL,
    caption = "Horizon-zero responses reflect reduced-form contemporaneous covariance and are not causal leadership estimates."
  ) +
  theme_story()

save_story_plot(p_girf_dec, "06B_DECEMBER_GIRF_main_text", 10.5, 6.2)

# ==============================================================================
# FIGURE 7 — ONE-PAGE STORYBOARD FOR PRESENTATION / EXECUTIVE SUMMARY
# ==============================================================================
# Uses the most important four figures in one visual.
# ==============================================================================

p_hero_small <- p_hero +
  labs(title = "A. Primary directional evidence", subtitle = NULL, caption = NULL) +
  theme_story(base_size = 9.5)

p_screen_small <- p_screen +
  labs(title = "B. Why only two meetings enter inference", subtitle = NULL, caption = NULL) +
  theme_story(base_size = 9.5) +
  theme(legend.position = "none")

p_compare_small <- p_compare +
  labs(title = "C. Frequentist vs Bayesian evidence", subtitle = NULL, caption = NULL) +
  theme_story(base_size = 9.2)

p_girf_small <- p_girf_dec +
  labs(title = "D. December dynamics", subtitle = NULL, caption = NULL) +
  theme_story(base_size = 9.5)

storyboard <- (p_hero_small | p_screen_small) /
  (p_compare_small | p_girf_small) +
  plot_annotation(
    title = "Who Prices the Fed First?",
    subtitle = paste0(
      "December 2025 shows futures-led predictive price discovery; September shows no detectable leader. ",
      "The result survives event-deletion sensitivity but is more cautious under Bayesian shrinkage."
    ),
    caption = "ECMT3150 group project — final frozen 7-day, 15-minute synchronized VAR(1) design",
    theme = theme(
      plot.title = element_text(face = "bold", size = 22, colour = COL_DARK),
      plot.subtitle = element_text(size = 12.5, colour = "#555B61"),
      plot.caption = element_text(size = 9, colour = "#737A80", hjust = 0)
    )
  )

save_story_plot(storyboard, "07_storyboard_four_panel", 16, 11.5)

# ==============================================================================
# 8. CONSOLE SUMMARY
# ==============================================================================
cat("\n============================================================\n")
cat("PUBLICATION VISUALS COMPLETE\n")
cat("============================================================\n")
cat("Figures written to:\n", VIS_DIR, "\n\n", sep = "")
cat("Recommended MAIN REPORT figures:\n")
cat("  1. 03_HERO_blockHAC_directional_results\n")
cat("  2. 02_synchronized_expected_rate_paths\n")
cat("  3. 05_leave_one_event_out_robustness\n")
cat("  4. 04_frequentist_vs_BVAR\n\n")
cat("Recommended APPENDIX figures:\n")
cat("  5. 01_meeting_audit_repricing\n")
cat("  6. 06_BVAR_generalized_IRF\n\n")
cat("Presentation / executive-summary visual:\n")
cat("  7. 07_storyboard_four_panel\n")
