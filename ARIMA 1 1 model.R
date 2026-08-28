set.seed(3150)

nsim = 5 
burn = 100
n = 200
tp = (burn=1):n
sigerr = 1
a1 = 0.9
b1 = 0.9
a0 = 0

#create data series and error
y = array(0,c(n,nsim)) #data series
err = array(rnorm(n*nsim,0,sigerr),c(n,nsim)) #iid errors
          
# simulate y from ARMA(1,1) prcoess
for (k in 1:nsim) {
  for (i in 2:n) {
    y[i,k] = a0 +a1*y[i-1,k] + err[i,k] + b1*err[i-1,k]
  }
}

#ALTERNATIVELY, use arima.sim
#y = arima.sim(list(order-(1,0,1), ar-a1, ma-b1),n)

#plot simulated path s of y
graphics.off()
matplot(y[tp,], type = c("l"), pch=2, col = 1:nsim)
title(bquote("ARMA(1,1) with " ~ phi[1] == .(a1) ~ " and " ~ theta[1] == .(b1)))


#graphics.off()

#par(mfrow = c(2, 2)) 

# Plot simulated paths of y 
#matplot(y[tp, ], type = "l", pch = 2, col = 1:nsim, ylab = "Value", xlab = "Time") 
#title(bquote("ARMA(1,1) with " ~ phi[1] == .(a1) ~ " and " ~ theta[1] == .(b1))) 

# Plot sample ACF and PACF for the first simulation 
#acf(y[tp, 1], main = "ACF of Series 1") 
#pacf(y[tp, 1], main = "PACF of Series 1")






#Plot sample ACF and PACF
par(mfcol=c(2,1))
acf(y[tp,1])
pacf(y[tp,1])