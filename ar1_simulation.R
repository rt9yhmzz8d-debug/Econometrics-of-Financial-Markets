# SIMULATE SAMPLE PATHS FROM AN AR(1) MODEL

set.seed(123) #set a seed to fix the simulated numbers
nsim = 200         #number of simulations
burn = 100       #burn-in periods
n = 200          #sample length + burn-in periods
tp=(burn+1);n   #time points to be sampled
sigerr = 1       # error s.d.
a1 = 0.5         #AR(1) coefficient
a0 = 0 

# Create data series and error series
y = matrix(0, nrow = n, ncol = nsim)
err = matrix(rnorm(n * nsim, mean = 0, sd = sigerr), nrow = n,ncol = nsim)

# Simulate y from AR(1) process
# y_t = a0 + a1*y_(t-1) + error_t
#Current y = intercept + AR coefficient × previous y + current random shock.#
for (i in 1:nsim) {for (t in 2:n) {y[t,i] = a0 + a1*y[t-1,i] + err[t,i]}}

#plot simulated paths of y
# plot simulated paths of y
graphics.off()
matplot(y[tp,], type = c("l"), col = 1:nsim)
title(bquote("AR(1) with " * phi[1] == .(a1)))



set.seed(123) #set a seed to fix the simulated numbers
nsim = 200         #number of simulations
burn = 100       #burn-in periods
n = 200          #sample length + burn-in periods
tp=(burn+1);n   #time points to be sampled
sigerr = 1       # error s.d.
a1 = 0.5         #AR(1) coefficient
a0 = 0 

# Create data series and error series
y = matrix(0, nrow = n, ncol = nsim)
err = matrix(rnorm(n * nsim, mean = 0, sd = sigerr), nrow = n,ncol = nsim)

# Simulate y from AR(1) process
# y_t = a0 + a1*y_(t-1) + error_t
#Current y = intercept + AR coefficient × previous y + current random shock.#
for (i in 1:nsim) {for (t in 2:n) {y[t,i] = a0 + a1*y[t-1,i] + err[t,i]}}

#plot simulated paths of y
# plot simulated paths of y
graphics.off()
matplot(y[tp,], type = c("l"), col = 1:nsim)
title(bquote("AR(1) with " * phi[1] == .(a1)))

