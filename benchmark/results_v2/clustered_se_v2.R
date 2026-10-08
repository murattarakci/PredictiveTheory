###############################################################################
# Firm-clustered standard errors for the v2 benchmark.
# The dependent variable is a firm mean repeated across a firm's years, so
# conventional OLS standard errors overstate precision. This script adds
# gvkey-clustered SEs for the CSP marginal effect on training and validation
# firms. Run from the PredictiveTheorizing folder after rerun_v2_corrected.R.
###############################################################################
suppressMessages({ library(dplyr); library(sandwich) })
src <- readLines("rerun_v2_corrected.R")
eval(parse(text = src[1:(grep("^# ---------------------------------------------------------------- main loop", src) - 1)]))
r <- read.csv("results_v2/results_v2.csv", stringsAsFactors = FALSE)

me_cl <- function(fit, f, data_full) {
  rows <- as.integer(rownames(model.frame(fit)))
  ft <- focal_terms(f); b <- coef(fit)
  V <- tryCatch(vcovCL(fit, cluster = data_full$gvkey[rows], type = "HC1"), error = function(e) NULL)
  if (is.null(V)) return(NA_real_)
  b <- b[rownames(V)]
  g <- setNames(rep(0, length(b)), names(b))
  if (!ft$iv %in% names(b)) return(NA_real_)
  g[ft$iv] <- 1
  mf <- model.frame(fit)
  if (ft$sq %in% names(b)) g[ft$sq] <- 2 * mean(mf[[ft$iv]], na.rm = TRUE)
  for (it in ft$int) if (it %in% names(b)) g[it] <- mean(mf$RD, na.rm = TRUE)
  sqrt(as.numeric(t(g) %*% V %*% g))
}
r$se_train_cl <- NA_real_; r$se_val_cl <- NA_real_
pb <- txtProgressBar(min = 0, max = nrow(r), style = 3)
for (j in seq_len(nrow(r))) {
  f <- r$formula[j]; fo <- as.formula(f)
  fit <- lm(fo, data = train_data); r$se_train_cl[j] <- me_cl(fit, f, train_data)
  fv <- tryCatch(lm(fo, data = validation_data), error = function(e) NULL)
  if (!is.null(fv)) r$se_val_cl[j] <- me_cl(fv, f, validation_data)
  setTxtProgressBar(pb, j)
}
close(pb)
r$ci_excludes0_cl <- abs(r$me_train) > 1.96 * r$se_train_cl
r$coverage_cl <- abs(r$me_train - r$me_val) <= 1.96 * r$se_val_cl
write.csv(r, "results_v2/results_v2_clustered.csv", row.names = FALSE)
for (d in c("mean_roa", "mean_mva")) {
  s <- r[r$dv == d, ]; t50 <- s[order(s$test_rmse), ][1:50, ]
  cat("\n", d, ": SE inflation (clustered/OLS), median:", round(median(s$se_train_cl / s$se_train, na.rm = TRUE), 2), "\n")
  cat("  CI excludes 0 (clustered): all", sum(s$ci_excludes0_cl, na.rm = TRUE), "of", nrow(s), "| top50", sum(t50$ci_excludes0_cl, na.rm = TRUE), "of 50\n")
  cat("  coverage (clustered): all", round(mean(s$coverage_cl, na.rm = TRUE), 3), "| top50", round(mean(t50$coverage_cl, na.rm = TRUE), 3), "\n")
  cat("  top50 ME train range", round(range(t50$me_train), 3), "| ME validation range", round(range(t50$me_val, na.rm = TRUE), 3), "\n")
  cat("  top50 clustered SE train range", round(range(t50$se_train_cl, na.rm = TRUE), 3), "\n")
}
