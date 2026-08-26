# ============================================================
# RT Ex 2.3: US Monthly Unemployment Rate (Jan 1948 - Mar 2009)
# Forecast Apr-Jul 2009. Discuss implied business cycles.
# ============================================================

library(forecast)

# ------------------------------------------------------------
# 1. LOAD DATA
# ------------------------------------------------------------
urtab <- read.table("data/m-unrate.txt", header = TRUE) # <- set your path
ur <- ts(urtab$Rate, frequency = 12, start = c(1948, 1))

plot(ur, type = "l",
     main = "U.S. Monthly Unemployment Rate (1948-2009)",
     ylab = "Unemployment rate (%)", xlab = "Year")

# ------------------------------------------------------------
# 2. FIT AR MODEL ON LEVELS (d = 0)
# ------------------------------------------------------------
# Unemployment is bounded and historically mean-reverting after
# every spike (1949, 1958, 1975, 1982, 1991, 2001, 2009...), so
# we model it as stationary in levels rather than differencing.

ur_fit <- auto.arima(ur, d = 0, max.p = 15, max.q = 5,
                     seasonal = FALSE, stepwise = FALSE,
                     approximation = FALSE)
ur_fit

# Coefficient standard errors and t-stats
se <- sqrt(diag(vcov(ur_fit)))
cbind(coef = ur_fit$coef, se = se, t_stat = ur_fit$coef / se)

# ------------------------------------------------------------
# 3. RESIDUAL DIAGNOSTICS
# ------------------------------------------------------------
tsdiag(ur_fit, gof.lag = 48)

res <- residuals(ur_fit)
Box.test(res, lag = 24, type = "Ljung-Box", fitdf = length(ur_fit$coef) - 1)

qqnorm(res); qqline(res)

# ------------------------------------------------------------
# 4. FORECAST APRIL 2009 - JULY 2011 (28 months = the required
#    4-month forecast, extended another 24 months so you can see
#    whether/when it turns back down)
# ------------------------------------------------------------
fc <- forecast(ur_fit, h = 28, level = 95)
fc

plot(fc, xlim = c(2005, 2011.7),
     main = "U.S. Unemployment Rate: Forecast (Apr 2009 - Jul 2011)",
     ylab = "Unemployment rate (%)")

data.frame(
  Time     = round(as.numeric(time(fc$mean)), 3),
  Forecast = round(as.numeric(fc$mean), 3),
  Lower95  = round(as.numeric(fc$lower), 3),
  Upper95  = round(as.numeric(fc$upper), 3)
)
# The first 4 rows (Time 2009.25 - 2009.50) are your required
# April-July 2009 answer. The remaining rows just show you where
# the model thinks things go from there.

# ------------------------------------------------------------
# 5. DOES THE MODEL IMPLY BUSINESS CYCLES?
# ------------------------------------------------------------
ar_coefs <- coef(ur_fit)[grep("^ar", names(coef(ur_fit)))]
ar_poly  <- c(1, -ar_coefs)
ar_roots <- polyroot(ar_poly)

Mod(ar_roots)                                    # >1 => stationary
cycle_years <- 2 * pi / acos(Re(ar_roots) / Mod(ar_roots))
cycle_years                                       # NaN = real root, no cycle

# Complex roots with modulus > 1 imply damped stochastic cycles of
# the length shown above (in years, since frequency = 12). This
# is the model's implied "business cycle" - compare it to the
# actual recession spacing seen in the plot (roughly every 6-10
# years) to comment on whether it's a plausible match.