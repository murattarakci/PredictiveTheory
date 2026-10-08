###############################################################################
# Predictive theorizing benchmark: corrected rerun (v2), 2026-10-08
#
# Reruns the 2,400 Berchicci-King (2022) between-firm specifications on the
# lockbox split (train/test: Data/repo_1_*.csv; validation: Data/repo_5_*.csv,
# split by gvkey), with three corrections to the April 2026 run:
#
#  1. Lagged dependent variable. The original formulas used
#     dplyr::lag(mean_roa), which takes the previous ROW of the firm-mean DV.
#     Because mean_roa is constant within firm (egen mean_roa=mean(roa),
#     by(cusip_id)), this mostly fed the outcome back in as a predictor.
#     v2 uses last year's ANNUAL value of the same firm (roa_lag1 / mva_lag1),
#     computed within gvkey and only when the previous year is t-1.
#     Set LAG_MODE <- "original_rowlag" to reproduce the old behavior.
#
#  2. Cross-validation folds. caret::groupKFold returns TRAINING indices; the
#     old loop fit on train_data[-folds[[i]], ] (15-32% of rows). v2 fits on
#     folds[[i]] and scores on the remainder. Folds are grouped by gvkey.
#
#  3. Fixed effects. Specifications with factor(sic_2) failed because some
#     held-out firms sit in industries absent from the fitting data, and
#     factor(year) failed inside the (inverted) small folds. v2 predicts NA
#     for rows whose factor level was not seen in fitting and reports the
#     number of rows scored.
#
# Outputs go to results_v2/. Nothing from the April run is overwritten.
###############################################################################

suppressMessages({ library(dplyr) })
set.seed(2026)

LAG_MODE <- "annual_within_firm"   # or "original_rowlag"
K_FOLDS  <- 5
OUT_DIR  <- "results_v2"
dir.create(OUT_DIR, showWarnings = FALSE)

# ---------------------------------------------------------------- data
read_split <- function(path) read.csv(path, stringsAsFactors = FALSE)
train_data <- read_split("Data/repo_1_train.csv")
test_data  <- read_split("Data/repo_1_test.csv")
validation_data <- read_split("Data/repo_5_validation.csv")

add_lags <- function(d) {
  d %>%
    arrange(gvkey, year) %>%
    group_by(gvkey) %>%
    mutate(prev_year = dplyr::lag(year),
           roa_lag1  = ifelse(!is.na(prev_year) & prev_year == year - 1, dplyr::lag(roa), NA),
           mva_lag1  = ifelse(!is.na(prev_year) & prev_year == year - 1, dplyr::lag(mva), NA)) %>%
    ungroup() %>%
    as.data.frame()
}
train_data      <- add_lags(train_data)
test_data       <- add_lags(test_data)
validation_data <- add_lags(validation_data)

stopifnot(length(intersect(train_data$gvkey, test_data$gvkey)) == 0,
          length(intersect(train_data$gvkey, validation_data$gvkey)) == 0,
          length(intersect(test_data$gvkey, validation_data$gvkey)) == 0)

# ---------------------------------------------------------------- formulas
source("./modelCombinations.R")   # builds between_combinations$formula (unchanged)
formulas <- between_combinations$formula
if (LAG_MODE == "annual_within_firm") {
  formulas <- gsub("dplyr::lag(mean_roa)", "roa_lag1", formulas, fixed = TRUE)
  formulas <- gsub("dplyr::lag(mean_mva)", "mva_lag1", formulas, fixed = TRUE)
}
spec <- between_combinations
spec$formula_v2 <- formulas
spec$spec_id <- seq_len(nrow(spec))

# ---------------------------------------------------------------- helpers
safe_predict <- function(model, newdata) {
  # NA for rows whose factor levels were not seen when fitting
  keep <- rep(TRUE, nrow(newdata))
  for (v in names(model$xlevels)) {
    raw <- sub("^factor\\((.*)\\)$", "\\1", v)
    if (raw %in% names(newdata)) keep <- keep & (as.character(newdata[[raw]]) %in% model$xlevels[[v]])
  }
  out <- rep(NA_real_, nrow(newdata))
  if (any(keep)) out[keep] <- suppressWarnings(predict(model, newdata = newdata[keep, , drop = FALSE]))
  out
}
rmse_n <- function(y, yhat) {
  ok <- !is.na(y) & !is.na(yhat)
  c(rmse = sqrt(mean((y[ok] - yhat[ok])^2)), n = sum(ok))
}
focal_terms <- function(f) {
  iv <- regmatches(f, regexpr("(mean_BS|mean_HK_SM|mean_HR|mean_WG|MS4)", f))
  list(iv = iv,
       sq = paste0("I(", iv, "^2)"),
       int = c(paste0(iv, ":RD"), paste0("RD:", iv)))
}
marginal_effect <- function(model, f, data) {
  ft <- focal_terms(f); b <- coef(model); b[is.na(b)] <- 0
  V <- vcov(model, complete = TRUE); V[is.na(V)] <- 0
  g <- setNames(rep(0, length(b)), names(b))
  if (!ft$iv %in% names(b)) return(c(me = NA, se = NA))
  g[ft$iv] <- 1
  if (ft$sq %in% names(b)) g[ft$sq] <- 2 * mean(data[[ft$iv]], na.rm = TRUE)
  for (it in ft$int) if (it %in% names(b)) g[it] <- mean(data$RD, na.rm = TRUE)
  me <- sum(g * b); se <- sqrt(as.numeric(t(g) %*% V %*% g))
  c(me = me, se = se)
}

# grouped folds: caret::groupKFold semantics without the dependency
make_group_folds <- function(groups, k) {
  ug <- unique(groups); ug <- ug[sample.int(length(ug))]
  fold_of_group <- setNames(rep_len(seq_len(k), length(ug)), ug)
  fid <- fold_of_group[as.character(groups)]
  lapply(seq_len(k), function(i) which(fid != i))   # TRAINING rows for fold i
}
folds <- make_group_folds(train_data$gvkey, K_FOLDS)

# ---------------------------------------------------------------- main loop
res <- vector("list", nrow(spec))
pb <- txtProgressBar(min = 0, max = nrow(spec), style = 3)
for (j in seq_len(nrow(spec))) {
  f <- spec$formula_v2[j]
  fo <- as.formula(f); dv <- all.vars(fo)[1]
  out <- tryCatch({
    cv <- sapply(folds, function(tr_idx) {
      fit <- lm(fo, data = train_data[tr_idx, ])
      hold <- train_data[-tr_idx, ]
      rmse_n(hold[[dv]], safe_predict(fit, hold))[["rmse"]]
    })
    fit <- lm(fo, data = train_data)
    te <- rmse_n(test_data[[dv]], safe_predict(fit, test_data))
    pred_va <- safe_predict(fit, validation_data)
    va <- rmse_n(validation_data[[dv]], pred_va)
    me_tr <- marginal_effect(fit, f, model.frame(fit))
    # focal-term predictive contribution: refit without the CSP terms
    ft <- focal_terms(f)
    rhs <- attr(terms(fo), "term.labels")
    drop <- rhs[grepl(ft$iv, rhs, fixed = TRUE)]
    if (any(grepl(":", drop)) && !"RD" %in% rhs) rhs <- c(rhs, "RD")  # keep R&D main effect
    rhs_wo <- setdiff(rhs, drop)
    f_wo <- as.formula(paste(dv, "~", if (length(rhs_wo)) paste(rhs_wo, collapse = " + ") else "1"))
    used_rows <- as.integer(rownames(model.frame(fit)))          # same training rows as the full model
    fit_wo <- lm(f_wo, data = train_data[used_rows, ])
    same_va <- !is.na(pred_va)                                     # same validation rows as the full model
    va_wo <- rmse_n(validation_data[[dv]][same_va], safe_predict(fit_wo, validation_data[same_va, , drop = FALSE]))
    # coefficient stability: re-estimate the same specification on validation firms
    fit_va <- tryCatch(lm(fo, data = validation_data), error = function(e) NULL)
    me_va <- if (is.null(fit_va)) c(me = NA, se = NA) else marginal_effect(fit_va, f, model.frame(fit_va))
    data.frame(spec_id = j, formula = f, dv = dv,
               cv_rmse = mean(cv, na.rm = TRUE), cv_rmse_sd = sd(cv, na.rm = TRUE),
               test_rmse = te[["rmse"]], test_n = te[["n"]],
               val_rmse = va[["rmse"]], val_n = va[["n"]],
               val_rmse_without_csp = va_wo[["rmse"]],
               me_train = me_tr[["me"]], se_train = me_tr[["se"]],
               me_val = me_va[["me"]], se_val = me_va[["se"]],
               n_train = nobs(fit), error = NA_character_)
  }, error = function(e) data.frame(spec_id = j, formula = f, dv = dv,
        cv_rmse = NA, cv_rmse_sd = NA, test_rmse = NA, test_n = NA, val_rmse = NA, val_n = NA,
        val_rmse_without_csp = NA, me_train = NA, se_train = NA, me_val = NA, se_val = NA,
        n_train = NA, error = conditionMessage(e)))
  res[[j]] <- out
  setTxtProgressBar(pb, j)
}
close(pb)

results <- bind_rows(res)
results <- cbind(spec[, c("set", "dependent", "iv", "functional_form", "sizeControl", "advFE",
                          "FEtime", "laggedDV", "R_and_D", "Risk")], results)
results$csp_contribution <- results$val_rmse_without_csp - results$val_rmse   # > 0: CSP helps on new firms
results$sign_agree <- sign(results$me_train) == sign(results$me_val)
results$coverage   <- abs(results$me_train - results$me_val) <= 1.96 * results$se_val

write.csv(results, file.path(OUT_DIR, "results_v2.csv"), row.names = FALSE)
saveRDS(list(results = results, LAG_MODE = LAG_MODE, K_FOLDS = K_FOLDS,
             n = c(train = nrow(train_data), test = nrow(test_data), val = nrow(validation_data)),
             firms = c(train = length(unique(train_data$gvkey)), test = length(unique(test_data$gvkey)),
                       val = length(unique(validation_data$gvkey))),
             session = sessionInfo()),
        file.path(OUT_DIR, "results_v2.rds"))

cat("\nScored specifications:", sum(!is.na(results$test_rmse)), "of", nrow(results), "\n")
cat("Errors:", sum(!is.na(results$error)), "\n")
if (any(!is.na(results$error))) print(head(unique(results$error[!is.na(results$error)]), 5))
