# ============================================================
# RT Exercise 2.3
# U.S. Monthly Unemployment Rate
# January 1948 - March 2009
#
# Tasks:
# 1. Inspect the unemployment-rate series.
# 2. Examine its ACF and PACF.
# 3. Fit an autoregressive AR(p) model.
# 4. Check whether the fitted AR model is stationary.
# 5. Examine residual diagnostics.
# 6. Forecast unemployment for April-July 2009.
# 7. Examine whether the fitted AR model implies cyclical
#    behaviour / business-cycle dynamics.
# ============================================================


# ------------------------------------------------------------
# 1. LOAD AND CREATE THE TIME SERIES
# ------------------------------------------------------------

# Read the unemployment-rate data.
#urtab <- read.table("INSERT YOUR PATH HERE", header = TRUE)

# Inspect the imported data.
head(urtab)
tail(urtab)
str(urtab)

# Extract the unemployment-rate variable and create a monthly
# time-series object beginning in January 1948.
ur <- ts(
  urtab$Rate,
  frequency = 12,
  start = c(1948, 1)
)

# Inspect the time series.
ur
start(ur)
end(ur)
frequency(ur)
length(ur)


# ------------------------------------------------------------
# 2. PLOT THE UNEMPLOYMENT RATE
# ------------------------------------------------------------

plot(
  ur,
  type = "l",
  main = "U.S. Monthly Unemployment Rate",
  xlab = "Year",
  ylab = "Unemployment Rate (%)"
)


# ------------------------------------------------------------
# 3. ACF AND PACF OF UNEMPLOYMENT IN LEVELS
# ------------------------------------------------------------

# ACF:
# Measures Corr(u_t, u_(t-k)) at each lag k.
acf(
  ur,
  main = "ACF: U.S. Unemployment Rate"
)

# PACF:
# Measures the relationship between u_t and u_(t-k)
# after controlling for the intervening lags.
pacf(
  ur,
  main = "PACF: U.S. Unemployment Rate"
)


# ------------------------------------------------------------
# 4. ESTIMATE AN AR(p) MODEL
# ------------------------------------------------------------

# Estimate the autoregressive model using maximum likelihood.
#
# ar() selects the AR order p using AIC unless order.max is
# otherwise restricted.
#
# The fitted model has the form:
#
# u_t = c
#       + phi_1 u_(t-1)
#       + phi_2 u_(t-2)
#       + ...
#       + phi_p u_(t-p)
#       + epsilon_t

ur_fit <- ar(
  ur,
  method = "mle"
)

# Display complete model output.
ur_fit


# ------------------------------------------------------------
# 5. EXTRACT THE SELECTED AR ORDER
# ------------------------------------------------------------

p <- ur_fit$order

p

cat(
  "The selected autoregressive model is AR(",
  p,
  ").\n",
  sep = ""
)


# ------------------------------------------------------------
# 6. EXTRACT ESTIMATED AR COEFFICIENTS
# ------------------------------------------------------------

phi <- ur_fit$ar

phi

# Estimated mean of the process.
ur_mean <- ur_fit$x.mean

ur_mean

# Innovation variance.
innovation_variance <- ur_fit$var.pred

innovation_variance


# ------------------------------------------------------------
# 7. WRITE THE FITTED AR MODEL
# ------------------------------------------------------------

# ar() reports the unconditional mean separately.
#
# The model can therefore be expressed as:
#
# (u_t - mu)
#   = phi_1(u_(t-1) - mu)
#   + phi_2(u_(t-2) - mu)
#   + ...
#   + phi_p(u_(t-p) - mu)
#   + epsilon_t
#
# where:
#
# mu = ur_fit$x.mean


# ------------------------------------------------------------
# 8. APPROXIMATE STANDARD ERRORS AND t-STATISTICS
# ------------------------------------------------------------

# ar() reports the covariance matrix of the AR coefficients.

ar_se <- sqrt(diag(ur_fit$asy.var.coef))

ar_tstat <- phi / ar_se

coefficient_table <- data.frame(
  Lag = 1:p,
  AR_Coefficient = phi,
  Standard_Error = ar_se,
  t_Statistic = ar_tstat
)

coefficient_table


# ------------------------------------------------------------
# 9. CHECK AR STATIONARITY USING CHARACTERISTIC ROOTS
# ------------------------------------------------------------

# For an AR(p) model:
#
# u_t = phi_1 u_(t-1) + ... + phi_p u_(t-p) + epsilon_t
#
# the characteristic polynomial is:
#
# 1 - phi_1 z - phi_2 z^2 - ... - phi_p z^p = 0
#
# The AR process is stationary if ALL roots lie outside
# the unit circle:
#
# |z_i| > 1


# Construct characteristic polynomial:
ar_polynomial <- c(
  1,
  -phi
)

# Find its roots.
ar_roots <- polyroot(ar_polynomial)

ar_roots


# ------------------------------------------------------------
# 10. CALCULATE THE MODULUS OF EACH ROOT
# ------------------------------------------------------------

root_modulus <- Mod(ar_roots)

root_modulus

root_table <- data.frame(
  Root = ar_roots,
  Modulus = root_modulus
)

root_table


# ------------------------------------------------------------
# 11. DETERMINE WHETHER THE AR MODEL IS STATIONARY
# ------------------------------------------------------------

if (all(root_modulus > 1)) {
  
  cat(
    "\nAll characteristic roots have modulus greater than 1.\n",
    "Therefore, the fitted AR(",
    p,
    ") model is stationary.\n",
    sep = ""
  )
  
} else {
  
  cat(
    "\nAt least one characteristic root has modulus less than ",
    "or equal to 1.\n",
    "Therefore, the fitted AR(",
    p,
    ") model is not stationary.\n",
    sep = ""
  )
  
}


# ------------------------------------------------------------
# 12. OBTAIN MODEL RESIDUALS
# ------------------------------------------------------------

res <- ur_fit$resid

# Remove initial NA values caused by the AR lags.
res_clean <- na.omit(res)


# ------------------------------------------------------------
# 13. PLOT RESIDUALS
# ------------------------------------------------------------

plot(
  res,
  type = "l",
  main = paste(
    "Residuals from AR(",
    p,
    ") Model",
    sep = ""
  ),
  xlab = "Year",
  ylab = "Residual"
)

abline(h = 0)


# ------------------------------------------------------------
# 14. RESIDUAL ACF
# ------------------------------------------------------------

# If the AR model adequately captures serial dependence,
# there should be little significant autocorrelation remaining
# in the residuals.

acf(
  res_clean,
  main = paste(
    "ACF of AR(",
    p,
    ") Residuals",
    sep = ""
  )
)


# ------------------------------------------------------------
# 15. LJUNG-BOX TEST FOR RESIDUAL SERIAL CORRELATION
# ------------------------------------------------------------

# Null hypothesis:
#
# H0: residual autocorrelations up to the selected lag are zero.
#
# A large p-value means we fail to reject H0, which supports
# the adequacy of the AR specification.

Box.test(
  res_clean,
  lag = 24,
  type = "Ljung-Box",
  fitdf = p
)


# ------------------------------------------------------------
# 16. RESIDUAL NORMALITY CHECK
# ------------------------------------------------------------

hist(
  res_clean,
  breaks = 30,
  main = "Histogram of AR Model Residuals",
  xlab = "Residual"
)

qqnorm(
  res_clean,
  main = "Normal Q-Q Plot of AR Model Residuals"
)

qqline(res_clean)


# ------------------------------------------------------------
# 17. FORECAST APRIL-JULY 2009
# ------------------------------------------------------------

# The data finish in March 2009.
#
# Therefore:
#
# h = 1 -> April 2009
# h = 2 -> May 2009
# h = 3 -> June 2009
# h = 4 -> July 2009

ur_forecast <- predict(
  ur_fit,
  n.ahead = 4
)

ur_forecast


# ------------------------------------------------------------
# 18. EXTRACT POINT FORECASTS
# ------------------------------------------------------------

forecast_values <- as.numeric(
  ur_forecast$pred
)

forecast_values


# ------------------------------------------------------------
# 19. EXTRACT FORECAST STANDARD ERRORS
# ------------------------------------------------------------

forecast_se <- as.numeric(
  ur_forecast$se
)

forecast_se


# ------------------------------------------------------------
# 20. CONSTRUCT APPROXIMATE 95% FORECAST INTERVALS
# ------------------------------------------------------------

lower_95 <- forecast_values - 1.96 * forecast_se

upper_95 <- forecast_values + 1.96 * forecast_se


# ------------------------------------------------------------
# 21. CREATE FORECAST TABLE
# ------------------------------------------------------------

forecast_table <- data.frame(
  
  Month = c(
    "April 2009",
    "May 2009",
    "June 2009",
    "July 2009"
  ),
  
  Forecast = round(
    forecast_values,
    3
  ),
  
  Standard_Error = round(
    forecast_se,
    3
  ),
  
  Lower_95 = round(
    lower_95,
    3
  ),
  
  Upper_95 = round(
    upper_95,
    3
  )
)

forecast_table


# ------------------------------------------------------------
# 22. PLOT THE HISTORICAL DATA AND FOUR FORECASTS
# ------------------------------------------------------------

# Restrict historical graph to recent years so that the
# forecasts can be seen clearly.

#plot(
 # window(
  #  ur,
   # start = c(2005, 1)
  #),
  #type = "l",
  #xlim = c(2005, 2009.7),
  #ylim = range(
    #c(
     # window(ur, start = c(2005, 1)),
      #lower_95,
      #upper_95
    #)
  #),
  #main = "U.S. Unemployment Rate and Apr-Jul 2009 Forecasts",
  #xlab = "Year",
  #ylab = "Unemployment Rate (%)"
#)


# Create forecast time points.
#forecast_time <- seq(
  #from = 2009 + 3 / 12,
  #by = 1 / 12,
  #length.out = 4
#)

# Add point forecasts.
#lines(
 # forecast_time,
  #forecast_values,
  #type = "o"
#)

# Add approximate 95% forecast intervals.
#lines(
 # forecast_time,
  #lower_95,
  #lty = 2
#)

#lines(
#  forecast_time,
#  upper_95,
#  lty = 2
#)

# ------------------------------------------------------------

# 22. PLOT ACTUAL DATA FOLLOWED BY THE FORECAST

# ------------------------------------------------------------

# Show the observed unemployment rate from 2005 to March 2009,

# followed directly by the forecasts for April-July 2009.

# Historical data to display.

ur_recent <- window(
  
  ur,
  
  start = c(2005, 1)
  
)

# Forecast dates:

# April, May, June and July 2009.

forecast_time <- seq(
  
  from = 2009 + 3/12,
  
  by = 1/12,
  
  length.out = 4
  
)

# Plot the ACTUAL unemployment data first.

plot(
  
  ur_recent,
  
  type = "l",
  
  xlim = c(2005, 2009.6),
  
  ylim = range(
    
    c(
      
      ur_recent,
      
      forecast_values,
      
      lower_95,
      
      upper_95
      
    )
    
  ),
  
  main = "U.S. Unemployment Rate: Actual and Forecast",
  
  xlab = "Year",
  
  ylab = "Unemployment Rate (%)",
  
  lwd = 2
  
)

# ------------------------------------------------------------

# CONNECT LAST OBSERVATION TO FIRST FORECAST

# ------------------------------------------------------------

# Last observed value is March 2009.

last_actual_time <- as.numeric(
  
  tail(time(ur), 1)
  
)

last_actual_value <- as.numeric(
  
  tail(ur, 1)
  
)

# Draw forecast beginning from the final actual observation.

lines(
  
  c(last_actual_time, forecast_time),
  
  c(last_actual_value, forecast_values),
  
  type = "o",
  
  lty = 2,
  
  lwd = 2
  
)

# ------------------------------------------------------------

# ADD 95% FORECAST INTERVALS

# ------------------------------------------------------------

lines(
  
  forecast_time,
  
  lower_95,
  
  lty = 3
  
)

lines(
  
  forecast_time,
  
  upper_95,
  
  lty = 3
  
)

# ------------------------------------------------------------

# MARK WHERE THE FORECAST BEGINS

# ------------------------------------------------------------

abline(
  
  v = last_actual_time,
  
  lty = 3
  
)

# ------------------------------------------------------------

# ADD LEGEND

# ------------------------------------------------------------

legend(
  
  "topleft",
  
  legend = c(
    
    "Actual unemployment",
    
    "Forecast",
    
    "95% forecast interval"
    
  ),
  
  lty = c(1, 2, 3),
  
  lwd = c(2, 2, 1),
  
  bty = "n"
  
)
# ------------------------------------------------------------
# 23. INVESTIGATE WHETHER THE AR MODEL IMPLIES CYCLES
# ------------------------------------------------------------

# An AR model can produce damped oscillatory behaviour if its
# characteristic polynomial contains complex-conjugate roots.
#
# For a complex root:
#
# z = r * exp(i theta)
#
# theta gives the angular frequency of the oscillation.
#
# The implied cycle length in observations is:
#
#       2*pi
# T = --------
#      |theta|
#
# Since the unemployment data are monthly, we divide the
# resulting number of months by 12 to convert it to years.


# Find the angle of every root.
root_angle <- Arg(ar_roots)

root_angle


# Identify roots with a genuine imaginary component.
complex_root <- abs(
  Im(ar_roots)
) > 1e-8

complex_root


# ------------------------------------------------------------
# 24. CALCULATE IMPLIED CYCLE LENGTHS
# ------------------------------------------------------------

cycle_months <- rep(
  NA_real_,
  length(ar_roots)
)

cycle_years <- rep(
  NA_real_,
  length(ar_roots)
)

cycle_months[complex_root] <-
  2 * pi /
  abs(root_angle[complex_root])

cycle_years[complex_root] <-
  cycle_months[complex_root] / 12


# ------------------------------------------------------------
# 25. ROOT AND CYCLE TABLE
# ------------------------------------------------------------

cycle_table <- data.frame(
  
  Root_Number = 1:length(ar_roots),
  
  Real_Part = round(
    Re(ar_roots),
    4
  ),
  
  Imaginary_Part = round(
    Im(ar_roots),
    4
  ),
  
  Modulus = round(
    Mod(ar_roots),
    4
  ),
  
  Angle = round(
    root_angle,
    4
  ),
  
  Cycle_Months = round(
    cycle_months,
    2
  ),
  
  Cycle_Years = round(
    cycle_years,
    2
  )
)

cycle_table


# ------------------------------------------------------------
# 26. REPORT UNIQUE COMPLEX-ROOT CYCLES
# ------------------------------------------------------------

# Complex roots occur as conjugate pairs, so each pair generates
# the same implied cycle length.
#
# The following removes duplicated cycle periods.

unique_cycles_years <- unique(
  round(
    cycle_years[complex_root],
    2
  )
)

unique_cycles_years


# ------------------------------------------------------------
# 27. INTERPRET BUSINESS-CYCLE BEHAVIOUR
# ------------------------------------------------------------

if (any(complex_root)) {
  
  cat(
    "\nThe fitted AR model contains complex characteristic roots.\n",
    "Therefore, it is capable of generating damped oscillatory ",
    "behaviour.\n\n"
  )
  
  cat(
    "The implied cycle lengths, in years, are approximately:\n"
  )
  
  print(unique_cycles_years)
  
} else {
  
  cat(
    "\nThe fitted AR model does not contain complex characteristic ",
    "roots.\n",
    "Therefore, the characteristic roots do not imply a conventional ",
    "oscillatory business-cycle pattern.\n"
  )
  
}


# ------------------------------------------------------------
# 28. OPTIONAL: LONGER FORECAST FOR ECONOMIC INTERPRETATION
# ------------------------------------------------------------

# The exercise only requires April-July 2009.
#
# This longer forecast is therefore NOT part of the required
# four-month answer. It is useful only if we want to inspect the
# longer-run dynamic behaviour implied by the fitted AR model.

long_forecast <- predict(
  ur_fit,
  n.ahead = 28
)

long_forecast_values <- ts(
  as.numeric(long_forecast$pred),
  start = c(2009, 4),
  frequency = 12
)

plot(
  long_forecast_values,
  type = "l",
  main = "Longer-Run Forecast Implied by Fitted AR Model",
  xlab = "Year",
  ylab = "Forecast Unemployment Rate (%)"
)


# ============================================================
# END
# ============================================================