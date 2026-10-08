#########################
# Between-firm variance Combinations
#########################

# --- Upper left panel in Appendix 2 of Berchicci and King (2022): ---
dep_vars <- c("mean_roa", "mean_mva") # Dependent variables
iv_vars <- c("mean_BS", "mean_HK_SM", "mean_HR", "mean_WG", "MS4") # Independent variables
#functional form can be "linear" or "quadratic" (but note: if iv is "MS", only "linear" is allowed)
functional_form_options <- c("linear", "quadratic")

# Control variables:
sizeControl_options <- c("yes", "no")   # if "yes", include variable "size"
advFE_options       <- c("adv_exp", "sic_2", "none")  # if not "none", include that variable name
FEtime_options      <- c("yes", "no")   # if "yes", include variable year fixed effects
laggedDV_options    <- c("yes", "no")   # if "yes", include lag(dependent variable)
R_and_D_options     <- c("yes", "no")   # if "yes", include "RD"
Risk_options        <- c("yes", "no")   # if "yes", include "Risk"

# Build  Combinations ---
# For each independent variable, assign available functional forms.
# For "MS", only "linear" is allowed.
set1_iv <- do.call(rbind, lapply(iv_vars, function(iv) {
    if (iv == "MS") {
        data.frame(iv = iv, functional_form = "linear", stringsAsFactors = FALSE)
    } else {
        data.frame(iv = iv, functional_form = functional_form_options, stringsAsFactors = FALSE)
    }
}))

# Create a grid for the other categories.
set1_controls <- expand.grid(dependent   = dep_vars,
                             sizeControl = sizeControl_options,
                             advFE       = advFE_options,
                             FEtime      = FEtime_options,
                             laggedDV    = laggedDV_options,
                             R_and_D     = R_and_D_options,
                             Risk        = Risk_options,
                             stringsAsFactors = FALSE)

# Merge the IV info with the control grid (cartesian join)
set1 <- merge(set1_iv, set1_controls, all = TRUE)
set1$set <- "set1"

# --- Upper right panel in Appendix 2 of Berchicci and King (2022): ---
#The functional form is fixed as "moderation" and R&D is fixed to "yes"
functional_form_set2 <- "moderation"
set2 <- expand.grid(dependent   = dep_vars,
                    iv          = iv_vars,
                    sizeControl = sizeControl_options,
                    advFE       = advFE_options,
                    FEtime      = FEtime_options,
                    laggedDV    = laggedDV_options,
                    Risk        = Risk_options,
                    stringsAsFactors = FALSE)
set2$R_and_D <- "yes"         # fixed
set2$functional_form <- functional_form_set2  # fixed to "moderation"
set2$set <- "set2"

# Combine both sets
between_combinations <- rbind(set1, set2)

# --- Function to Generate the Regression Formula String ---
generate_formula <- function(dep, iv, func_form, sizeControl, advFE, FEtime, laggedDV, R_and_D, Risk) {
    terms <- c()

    if (func_form == "linear") {
        terms <- c(terms, iv)
    } else if (func_form == "quadratic") {
        terms <- c(terms, iv, paste0("I(", iv, "^2)"))
    } else if (func_form == "moderation") {
        terms <- c(terms, paste(iv, "*", "RD"))
    }

    if (sizeControl == "yes") {
        terms <- c(terms, "size_e")
    }
    if (advFE != "none") {
        if (advFE == "sic_2") {
            terms <- c(terms, "factor(sic_2)")
        } else {
            terms <- c(terms, advFE)
        }
    }
    if (FEtime == "yes") {
        terms <- c(terms, "factor(year)")
    }
    if (laggedDV == "yes") {
        terms <- c(terms, paste0("dplyr::lag(", dep, ")"))
    }
    if (R_and_D == "yes" && func_form != "moderation") {
        terms <- c(terms, "mean_RD")
    }
    if (Risk == "yes") {
        terms <- c(terms, "risk")
    }

    formula_str <- paste(dep, "~", paste(terms, collapse = " + "))
    return(formula_str)
}


# --- Generate the Formula for Each Combination ---
between_combinations$formula <- apply(between_combinations, 1, function(row) {
    generate_formula(dep         = row["dependent"],
                     iv          = row["iv"],
                     func_form   = row["functional_form"],
                     sizeControl = row["sizeControl"],
                     advFE       = row["advFE"],
                     FEtime      = row["FEtime"],
                     laggedDV    = row["laggedDV"],
                     R_and_D     = row["R_and_D"],
                     Risk        = row["Risk"])
})

# --- Display the First Few Rows ---
head(between_combinations)
