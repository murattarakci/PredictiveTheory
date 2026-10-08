###############################################################################
# Final summary of the v2 benchmark for the appendix.
# - Drops the 192 MS4-quadratic specifications (MS4 is binary, so MS4^2 = MS4;
#   modelCombinations.R meant to exclude them but tests "MS" instead of "MS4").
#   The remaining universe (2,208) matches Berchicci & King (2022), Appendix 2,
#   upper panels: 1,728 linear/quadratic + 480 moderated between-firm models.
# - Adds within-stratum diagnostics and a firm-level bootstrap of the CSP
#   predictive contribution on validation firms for the 50 best ROA specs.
###############################################################################
suppressMessages({ library(dplyr) })
src <- readLines("rerun_v2_corrected.R")
eval(parse(text = src[1:(grep("^# ---------------------------------------------------------------- main loop", src) - 1)]))
r <- read.csv("results_v2/results_v2_clustered.csv", stringsAsFactors = FALSE)
r <- r[!(r$iv == "MS4" & r$functional_form == "quadratic"), ]
write.csv(r, "results_v2/results_v2_final.csv", row.names = FALSE)
sink("results_v2/final_summary_v2.txt", split = TRUE)
cat("universe:", nrow(r), "| ROA", sum(r$dv == "mean_roa"), "| MVA", sum(r$dv == "mean_mva"), "\n")
for (d in c("mean_roa", "mean_mva")) {
  s <- r[r$dv == d, ]; o <- s[order(s$test_rmse), ]; t50 <- o[1:50, ]; L <- s$laggedDV == "yes"
  cat("\n==", d, "==\n")
  cat("test RMSE", round(range(s$test_rmse), 3), "| val RMSE", round(range(s$val_rmse), 3), "\n")
  cat("test-val all: P", round(cor(s$test_rmse, s$val_rmse), 3), "S", round(cor(s$test_rmse, s$val_rmse, method = "spearman"), 3),
      "| lag=yes: P", round(cor(s$test_rmse[L], s$val_rmse[L]), 3), "S", round(cor(s$test_rmse[L], s$val_rmse[L], method = "spearman"), 3),
      "| lag=no: P", round(cor(s$test_rmse[!L], s$val_rmse[!L]), 3), "S", round(cor(s$test_rmse[!L], s$val_rmse[!L], method = "spearman"), 3),
      "| top200 S", round(cor(o$test_rmse[1:200], o$val_rmse[1:200], method = "spearman"), 3), "\n")
  cat("cv-test P", round(cor(s$cv_rmse, s$test_rmse), 3), "| mean test RMSE lag yes/no", round(mean(s$test_rmse[L]), 2), round(mean(s$test_rmse[!L]), 2),
      "| mean test n lag yes/no", round(mean(s$test_n[L])), round(mean(s$test_n[!L])), "\n")
  bt <- o[1, ]; bv <- s[which.min(s$val_rmse), ]
  cat("best by test:", bt$formula, "| val rank", rank(s$val_rmse, ties.method = "first")[s$spec_id == bt$spec_id], "of", nrow(s), "\n")
  cat("best by val:", bv$formula, "| test rank", rank(s$test_rmse, ties.method = "first")[s$spec_id == bv$spec_id], "\n")
  cat("top50 val range", round(range(t50$val_rmse), 3), "| test spread", round(diff(range(t50$test_rmse)), 3), "| median CV fold SD", round(median(t50$cv_rmse_sd), 3), "\n")
  cat("top50 composition: lag", sum(t50$laggedDV == "yes"), "| yearFE", sum(t50$FEtime == "yes"), "| sicFE", sum(t50$advFE == "sic_2"),
      "| moderation", sum(t50$functional_form == "moderation"), "| R&D present", sum(t50$functional_form == "moderation" | t50$R_and_D == "yes"), "\n")
  cat("train ME CI excl 0 (clustered): all", sum(s$ci_excludes0_cl, na.rm = TRUE), "| top50", sum(t50$ci_excludes0_cl, na.rm = TRUE),
      "| top50 ME train", round(range(t50$me_train), 3), "\n")
  cat("validation ME CI excl 0 (clustered): all", sum(abs(s$me_val) > 1.96 * s$se_val_cl, na.rm = TRUE), "| top50", sum(abs(t50$me_val) > 1.96 * t50$se_val_cl, na.rm = TRUE),
      "| top50 ME val", round(range(t50$me_val), 3), "\n")
  cat("sign agree all", round(mean(s$sign_agree, na.rm = TRUE), 3), "| shrink ratio median all", round(median(s$me_val / s$me_train), 2),
      "| top50 range", round(range(t50$me_val / t50$me_train), 2), "median", round(median(t50$me_val / t50$me_train), 2), "\n")
  cat("coverage clustered all/top50", round(mean(s$coverage_cl, na.rm = TRUE), 3), round(mean(t50$coverage_cl, na.rm = TRUE), 3),
      "| conventional", round(mean(s$coverage, na.rm = TRUE), 3), round(mean(t50$coverage, na.rm = TRUE), 3), "\n")
  cat("CSP helps validation: all", sum(s$csp_contribution > 0, na.rm = TRUE), "of", nrow(s), "median", signif(median(s$csp_contribution), 3),
      "median among helpful", signif(median(s$csp_contribution[s$csp_contribution > 0]), 3), "| top50", sum(t50$csp_contribution > 0), "\n")
  cat("Spearman(test RMSE, CSP contribution):", round(cor(s$test_rmse, s$csp_contribution, method = "spearman"), 3), "\n")
}
# ---------------------------------------------------------------- bootstrap, top 50 ROA
set.seed(20261008); B <- 1000
s <- r[r$dv == "mean_roa", ]; t50 <- s[order(s$test_rmse), ][1:50, ]
firms <- unique(validation_data$gvkey); idx_by_firm <- split(seq_len(nrow(validation_data)), validation_data$gvkey)
boot <- t(sapply(seq_len(nrow(t50)), function(k) {
  f <- t50$formula[k]; fo <- as.formula(f); dv <- all.vars(fo)[1]
  fit <- lm(fo, data = train_data); ft <- focal_terms(f)
  rhs <- attr(terms(fo), "term.labels"); drop <- rhs[grepl(ft$iv, rhs, fixed = TRUE)]
  if (any(grepl(":", drop)) && !"RD" %in% rhs) rhs <- c(rhs, "RD")
  f_wo <- as.formula(paste(dv, "~", paste(setdiff(rhs, drop), collapse = " + ")))
  fit_wo <- lm(f_wo, data = train_data[as.integer(rownames(model.frame(fit))), ])
  p1 <- safe_predict(fit, validation_data); p0 <- safe_predict(fit_wo, validation_data)
  y <- validation_data[[dv]]; ok <- !is.na(y) & !is.na(p1) & !is.na(p0)
  e1 <- (y - p1)^2; e0 <- (y - p0)^2
  stat <- function(rows) { rows <- rows[ok[rows]]; sqrt(mean(e0[rows])) - sqrt(mean(e1[rows])) }
  point <- stat(seq_len(nrow(validation_data)))
  bs <- replicate(B, stat(unlist(idx_by_firm[sample(names(idx_by_firm), replace = TRUE)], use.names = FALSE)))
  c(point = point, lo = unname(quantile(bs, .025)), hi = unname(quantile(bs, .975)))
}))
t50 <- cbind(t50, boot)
write.csv(t50, "results_v2/top50_roa_final.csv", row.names = FALSE)
cat("\n== bootstrap of CSP contribution on validation firms (", B, "firm resamples) ==\n")
cat("top50 point range", round(range(t50$point), 3), "| CI excludes 0 and positive:", sum(t50$lo > 0), "| CI excludes 0 and negative:", sum(t50$hi < 0),
    "| CI includes 0:", sum(t50$lo <= 0 & t50$hi >= 0), "\n")
cat("best-by-test: point", round(t50$point[1], 3), "CI [", round(t50$lo[1], 3), ",", round(t50$hi[1], 3), "]\n")
sink()
