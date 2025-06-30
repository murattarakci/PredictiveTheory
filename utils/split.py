import pandas as pd
from sklearn.model_selection import train_test_split
from typing import Optional
import numpy as np # For shuffling IDs
import logging

logger = logging.getLogger("app_debug") # Use the same logger as handlers

def split_dataset(df: pd.DataFrame,
                  ratios: tuple[float, float, float], # e.g., (0.7, 0.15, 0.15) for train, test, val
                  exclusive_id_column: Optional[str] = None,
                  random_state: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Splits a DataFrame into train, validation, and test sets.

    Priority:
    1. If exclusive_id_column is provided, splits based on unique IDs in that column,
       ensuring IDs are exclusive to each set.
    2. If exclusive_id_column is None, performs a simple random split of rows.

    Args:
        df: The pandas DataFrame to split.
        ratios: A tuple of three floats (train_ratio, val_ratio, test_ratio)
                that sum to 1.0. These are proportions for the sets.
                Note: The function actually uses (train, test, val) order for ratios internally based on common convention,
                but the input order here is (train, val, test) as per original `split_ratio_tuple`.
                Let's clarify: ratios will be (train_prop, val_prop, test_prop)
        exclusive_id_column: Optional. The name of the column containing IDs that
                             should be unique across the splits.
        random_state: Seed for random number generation for reproducibility.

    Returns:
        A tuple of three DataFrames: (df_train, df_test, df_val).
        Order is Train, Test, Validation based on typical ML workflow.
        The original `split_ratio_tuple` was (train, val, test).
        Let's stick to returning (train, test, val) and adjust ratio usage.
        Ratios input: (train_prop, val_prop, test_prop)
        Output order: (df_train, df_test, df_val) - This is a common convention.
                      The original code returned train, test, val. Let's maintain that.
    """
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Input 'df' must be a pandas DataFrame.")
    if not (isinstance(ratios, tuple) and len(ratios) == 3 and
            abs(sum(ratios) - 1.0) < 1e-9 and all(0 <= r <= 1 for r in ratios)): # Allow 0 ratios
        raise ValueError("'ratios' must be a tuple of three non-negative floats that sum to 1.0.")

    train_prop, val_prop, test_prop = ratios # train_prop, val_prop, test_prop

    # Initialize empty DataFrames
    df_train = pd.DataFrame(columns=df.columns)
    df_val = pd.DataFrame(columns=df.columns)
    df_test = pd.DataFrame(columns=df.columns)

    if df.empty:
        logger.warning("Input DataFrame is empty. Returning empty DataFrames for all sets.")
        return df_train, df_test, df_val # Return order: train, test, val

    # --- Exclusive ID Column Split ---
    if exclusive_id_column:
        if exclusive_id_column not in df.columns:
            raise ValueError(f"Exclusive ID column '{exclusive_id_column}' not found in DataFrame.")
        
        logger.info(f"Performing exclusive split based on ID column: {exclusive_id_column}")
        unique_ids = df[exclusive_id_column].unique()
        
        if len(unique_ids) == 0 : # Should not happen if df is not empty and column exists
             logger.warning(f"No unique IDs found in column '{exclusive_id_column}'. Performing random split instead.")
             # Fall through to random split logic below
        elif len(unique_ids) < 3 and (train_prop > 0 and val_prop > 0 and test_prop > 0) : # Check if we need 3 non-empty sets
             logger.warning(
                f"Not enough unique IDs ({len(unique_ids)}) in '{exclusive_id_column}' to guarantee three non-empty splits "
                f"if all ratios are > 0. Some sets might be empty or split might be skewed. "
                f"Consider using fewer splits or ensure more unique IDs."
            )
            # Proceed with split, but it might result in empty sets

        np.random.seed(random_state)
        np.random.shuffle(unique_ids)

        n_ids = len(unique_ids)
        
        # Calculate number of IDs for each set
        n_train_ids = int(np.round(n_ids * train_prop))
        n_val_ids = int(np.round(n_ids * val_prop))
        # n_test_ids is the remainder to ensure sum is n_ids
        n_test_ids = n_ids - n_train_ids - n_val_ids
        
        # Adjust if rounding caused issues, prioritize train, then val
        if n_train_ids + n_val_ids + n_test_ids != n_ids:
            # This simple adjustment might still have issues if one ratio is very small.
            # A more robust way is to assign test_ids last.
            if n_test_ids < 0 : # Should not happen if ratios sum to 1 and are non-negative
                 n_test_ids = 0
                 # Re-evaluate others if test becomes 0 and sum was off
                 if n_train_ids + n_val_ids > n_ids:
                     # Reduce proportionally or based on some rule.
                     # For now, simple truncation for val if train is too large
                     if n_train_ids >= n_ids:
                         n_train_ids = n_ids
                         n_val_ids = 0
                     else: # n_train_ids < n_ids
                         n_val_ids = n_ids - n_train_ids


        train_ids = unique_ids[:n_train_ids]
        val_ids = unique_ids[n_train_ids : n_train_ids + n_val_ids]
        test_ids = unique_ids[n_train_ids + n_val_ids:] # All remaining IDs go to test

        # Filter DataFrame for each set
        if len(train_ids) > 0:
            df_train = df[df[exclusive_id_column].isin(train_ids)].copy()
        if len(val_ids) > 0:
            df_val = df[df[exclusive_id_column].isin(val_ids)].copy()
        if len(test_ids) > 0:
            df_test = df[df[exclusive_id_column].isin(test_ids)].copy()

        logger.info(f"Exclusive ID split counts: Train IDs={len(train_ids)}, Val IDs={len(val_ids)}, Test IDs={len(test_ids)}")
        logger.info(f"Resulting df sizes: Train={len(df_train)}, Test={len(df_test)}, Val={len(df_val)}")
        
        # Return order: train, test, val
        return df_train, df_test, df_val

    # --- Random Split (if no exclusive_id_column or if ID split failed to find IDs) ---
    logger.info("Performing random split of rows.")
    
    # If only one set has a non-zero proportion, assign all data to it.
    if train_prop == 1.0:
        df_train = df.copy()
        return df_train, df_test, df_val # test and val are empty
    if val_prop == 1.0:
        df_val = df.copy()
        return df_train, df_test, df_val # train and test are empty
    if test_prop == 1.0:
        df_test = df.copy()
        return df_train, df_test, df_val # train and val are empty

    # Split out validation set first if its proportion is > 0
    df_remaining = df.copy()
    if val_prop > 0 and val_prop < 1.0 : # val_prop must be < 1 for train_test_split's test_size
        df_remaining, df_val = train_test_split(
            df_remaining,
            test_size=val_prop, # Proportion of original df for val
            random_state=random_state,
            shuffle=True
        )
    elif val_prop == 1.0: # Should have been caught above, but as safeguard
        df_val = df_remaining.copy()
        df_remaining = pd.DataFrame(columns=df.columns) # Empty remaining

    # Now, split df_remaining into train and test
    if not df_remaining.empty:
        # Adjust test_prop for the remaining data
        # train_prop_new + test_prop_new = 1 (for the remainder)
        # test_prop_new = test_prop / (train_prop + test_prop)
        if train_prop + test_prop > 1e-9: # Avoid division by zero if both are effectively zero
            test_prop_adjusted_for_remainder = test_prop / (train_prop + test_prop)
            
            if test_prop_adjusted_for_remainder > 0 and test_prop_adjusted_for_remainder < 1.0:
                 df_train, df_test = train_test_split(
                    df_remaining,
                    test_size=test_prop_adjusted_for_remainder,
                    random_state=random_state,
                    shuffle=True
                )
            elif test_prop_adjusted_for_remainder == 1.0: # All remaining goes to test
                 df_test = df_remaining.copy()
            else: # All remaining goes to train (test_prop_adjusted_for_remainder is 0)
                 df_train = df_remaining.copy()
        elif train_prop > 1e-9 : # Only train is left from remainder
            df_train = df_remaining.copy()
        elif test_prop > 1e-9 : # Only test is left from remainder
            df_test = df_remaining.copy()
        # If both train_prop and test_prop are zero for the remainder, they stay empty.
            
    logger.info(f"Random split df sizes: Train={len(df_train)}, Test={len(df_test)}, Val={len(df_val)}")
    # Return order: train, test, val
    return df_train, df_test, df_val

# Functions `get_stratification_series` and `is_stratifiable` are removed
# as stratification is no longer the primary mechanism driven by handlers.py.
# If needed for other purposes, they can be kept or moved elsewhere.
