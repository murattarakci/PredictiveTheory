import pandas as pd
from sklearn.model_selection import train_test_split
import logging

logger = logging.getLogger("app_debug")

def get_stratification_series(df: pd.DataFrame, split_col_input):
    """
    Generates a pandas Series to be used for stratification.
    If split_col_input is a list, it creates an interaction term.
    Returns None if no valid stratification columns are provided.
    Raises ValueError if columns are not found in DataFrame.
    """
    if not split_col_input: # Handles None or empty list/tuple
        return None

    current_split_cols = []
    if isinstance(split_col_input, str) and split_col_input.strip():
        current_split_cols = [split_col_input.strip()]
    elif isinstance(split_col_input, (list, tuple)):
        current_split_cols = [str(col).strip() for col in split_col_input if str(col).strip()]
    
    if not current_split_cols: # If, after stripping, the list is empty
        return None

    missing_cols = [col for col in current_split_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Stratification column(s) not found in DataFrame: {', '.join(missing_cols)}")

    if len(current_split_cols) == 1:
        # Ensure the column is treated as string for robust value_counts and stratification
        return df[current_split_cols[0]].astype(str) 
    else: # Multiple columns, create interaction term
        try:
            # Ensure all stratification columns are treated as strings for reliable interaction
            return df[current_split_cols].astype(str).agg('__'.join, axis=1)
        except Exception as e:
            # This might happen if a column name is duplicated or other pandas issues
            raise ValueError(f"Could not create stratification key from columns {current_split_cols}: {e}")

def is_stratifiable(df_series: pd.Series, min_samples_per_group: int = 2) -> bool:
    """
    Checks if a pandas Series is suitable for stratification.
    Each unique group in the series must have at least min_samples_per_group.
    """
    if df_series is None or df_series.empty:
        return False # Cannot stratify on None or empty series
    value_counts = df_series.value_counts()
    if (value_counts < min_samples_per_group).any():
        problematic_classes = value_counts[value_counts < min_samples_per_group].index.tolist()
        logger.debug( # Use debug instead of warning if this is just a check
            f"Stratifiability check: The following class(es) have fewer than "
            f"{min_samples_per_group} members: {problematic_classes}"
        )
        return False
    return True

def split_dataset(df: pd.DataFrame, split_col_input, split_ratio_tuple=(0.7, 0.15, 0.15)):
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Input 'df' must be a pandas DataFrame.")
    if not (isinstance(split_ratio_tuple, tuple) and len(split_ratio_tuple) == 3 and abs(sum(split_ratio_tuple) - 1.0) < 1e-9):
        raise ValueError("'split_ratio_tuple' must be a tuple of three floats that sum to 1.0.")

    train_prop, val_prop, test_prop = split_ratio_tuple
    
    stratify_series_original = None
    can_stratify_overall = False # Flag to indicate if initial stratification is viable

    if split_col_input: # If user provided any column(s) for stratification
        try:
            stratify_series_original = get_stratification_series(df, split_col_input)
            if stratify_series_original is not None:
                # For two splits (val, then test from remainder), each original group needs at least 2 members.
                if not is_stratifiable(stratify_series_original, min_samples_per_group=2):
                    # This error will be caught by the handler and shown to the user
                    raise ValueError(
                        f"Stratification error: One or more selected stratification groups in the original dataset "
                        f"have fewer than 2 members, which is too few for repeated stratified splitting. "
                        f"Problematic groups (showing up to 5): {stratify_series_original.value_counts()[stratify_series_original.value_counts() < 2].index.tolist()[:5]}. "
                        f"Please choose different columns, ensure sufficient samples per group, or do not stratify."
                    )
                can_stratify_overall = True # Stratification is viable based on original data
        except ValueError as e: # Catch errors from get_stratification_series or is_stratifiable check
            raise e # Re-raise the specific error to be caught by the handler

    # Initialize empty DataFrames for return values
    df_train_final = pd.DataFrame(columns=df.columns)
    df_test_final = pd.DataFrame(columns=df.columns)
    df_val_final = pd.DataFrame(columns=df.columns)
    
    df_remaining = df.copy() # Start with all data

    # First, split out the validation set
    stratify_for_val_split = stratify_series_original.loc[df_remaining.index] if can_stratify_overall else None
    if val_prop > 0 and val_prop < 1.0: # val_prop must be between 0 and 1 (exclusive for splitting)
        df_remaining, df_val_final = train_test_split(
            df_remaining, test_size=val_prop, stratify=stratify_for_val_split, random_state=42
        )
    elif val_prop == 1.0: # All data goes to validation
        df_val_final = df_remaining.copy(); df_remaining = pd.DataFrame(columns=df.columns)
    
    # Now, split df_remaining into train and test
    if not df_remaining.empty:
        if test_prop == 0 and train_prop > 0 : # All remaining is train
            df_train_final = df_remaining.copy()
        elif train_prop == 0 and test_prop > 0 : # All remaining is test
            df_test_final = df_remaining.copy()
        elif train_prop > 0 and test_prop > 0: # Need to split further
            test_prop_adjusted = test_prop / (train_prop + test_prop)
            stratify_for_train_test_split = stratify_series_original.loc[df_remaining.index] if can_stratify_overall else None
            
            # Final check for the second split's stratification viability on the *remaining* data
            if stratify_for_train_test_split is not None and not is_stratifiable(stratify_for_train_test_split, min_samples_per_group=2):
                logger.warning(
                    "Stratification for train/test split might be imperfect or fail due to small group sizes "
                    "in the data remaining after validation split. Attempting split, sklearn may raise an error."
                )
                # Sklearn will raise an error if it truly cannot stratify.
                # Alternatively, could set stratify_for_train_test_split = None here to force non-stratified.

            df_train_final, df_test_final = train_test_split(
                df_remaining, test_size=test_prop_adjusted, stratify=stratify_for_train_test_split, random_state=42
            )
        elif train_prop > 0 : # Only train_prop is left after val_prop (test_prop must be 0)
             df_train_final = df_remaining.copy()
        elif test_prop > 0 : # Only test_prop is left after val_prop (train_prop must be 0)
             df_test_final = df_remaining.copy()
        # If both train_prop and test_prop are 0 (meaning val_prop was 1.0), df_train_final and df_test_final remain empty.
            
    return df_train_final, df_test_final, df_val_final