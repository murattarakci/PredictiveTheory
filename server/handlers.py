import logging
from pathlib import Path
import asyncio
import zipfile
import io
from htmltools import tags
import re
import pandas as pd

from typing import Union, Optional
from pathlib import Path
import pandas as pd


from shiny import reactive, ui, render
from db.models import Repository, User, Dataset, VisibilityEnum
from .state import (
    current_user, selected_repo_id, search_query,
    repo_refresh_trigger, handled_clicks, reset_app_state
)
from utils.split import split_dataset
import pyreadr
import shutil

log_path = Path(__file__).resolve().parent / "debug_modal_state.log"
logger = logging.getLogger("app_debug")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.info("Logger initialized for handlers.py")

# --- Module-Level Constants and Helpers ---
PROJECT_ROOT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROJECT_ROOT_DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_SUPPORTED_EXTENSIONS = [".rds", ".rda", ".csv", ".xlsx", ".dta"]

# --- Reactive Values ---
available_columns_for_id_split = reactive.Value([])
is_column_loading = reactive.Value(False)
available_columns_for_resplit_id = reactive.Value([])
creation_preview_content = reactive.Value(None)
resplit_preview_content = reactive.Value(None)
handled_delete_clicks = set()
file_ready_for_split = reactive.Value(False)


# --- LOGIN HANDLER ---
def login_handler(input, db):
    @reactive.effect
    @reactive.event(input.login_main_btn)
    def _show_role_selection_modal():
        ui.modal_remove(); logger.debug("[LOGIN_HANDLER] login_main_btn clicked.")
        ui.modal_show(
            ui.modal(
                ui.h4("Login As"),
                ui.input_action_button("login_as_scholar_btn", "Login as Scholar", class_="btn-primary w-100 mb-2"),
                # ui.input_action_button("login_as_peer_btn", "Login as Peer", class_="btn-secondary w-100"),
                title="Select Login Type", easy_close=True, footer=None
            )
        )
    def _show_credential_modal(role_selected: str):
        ui.modal_remove(); logger.debug(f"[LOGIN_HANDLER] Role {role_selected}, showing credential modal.")
        ui.modal_show(
            ui.modal(
                ui.input_text("username", "Username"), ui.input_password("password", "Password"),
                ui.input_action_button("submit_login_credentials", "Login"),
                title=f"Login as {role_selected}", easy_close=True
            )
        )
    @reactive.effect
    @reactive.event(input.login_as_scholar_btn)
    def _trigger_scholar_login_modal(): _show_credential_modal("Scholar")
    @reactive.effect
    @reactive.event(input.login_as_peer_btn)
    def _trigger_peer_login_modal(): _show_credential_modal("Peer")
    @reactive.effect
    @reactive.event(input.submit_login_credentials)
    def _submit_login_credentials():
        logger.debug("[LOGIN_HANDLER] submit_login_credentials.")
        username_val, password_val = input.username(), input.password()
        if not username_val or not password_val:
            logger.debug("[LOGIN_HANDLER] User/pass empty."); ui.notification_show("Username and password cannot be empty.", type="error"); return
        user = db.query(User).filter_by(username=username_val, password_hash=password_val).one_or_none()
        ui.modal_remove()
        if user:
            logger.debug(f"[LOGIN_HANDLER] User '{user.username}' role '{user.role}'."); current_user.set(user)
            ui.notification_show(f"Login successful as {user.username} ({user.role}).", type="message")
        else:
            logger.debug("[LOGIN_HANDLER] Invalid credentials."); ui.notification_show("Invalid credentials.", type="error")
            current_user.set(None)
# --- END OF LOGIN HANDLER ---

# --- Module-Level Data Processing Helper Functions ---
def _make_unique_columns_final(df: pd.DataFrame) -> pd.DataFrame:
    cols = pd.Series(df.columns)
    if not cols.is_unique:
        original_cols_for_log = list(df.columns)
        df.columns = pd.io.parsers.base_parser.ParserBase({'names': cols})._maybe_dedup_names(cols)
        logger.info(f"Deduplication: Original columns: {original_cols_for_log}. Made unique: {list(df.columns)}")
    return df

def read_dataframe(file_path: Union[Path, str]) -> Optional[pd.DataFrame]:
    df = None
    try:
        file_path_obj = Path(file_path)
        file_suffix_lower = file_path_obj.suffix.lower()
        logger.debug(f"Attempting to read dataframe from: {file_path_obj} (type: {file_suffix_lower})")
        if file_suffix_lower == ".rds":
            result = pyreadr.read_r(str(file_path_obj)); df = next(iter(result.values()))
        elif file_suffix_lower == ".rda":
            result = pyreadr.read_r(str(file_path_obj)); df = next(iter(result.values()))
        elif file_suffix_lower == ".csv":
            df = pd.read_csv(file_path_obj, mangle_dupe_cols=True)
        elif file_suffix_lower == ".xlsx":
            df = pd.read_excel(file_path_obj, mangle_dupe_cols=True)
        elif file_suffix_lower == ".dta":
            df = pd.read_stata(file_path_obj, convert_categoricals=False)
        else:
            logger.warning(f"Unsupported file type for read_dataframe: {file_suffix_lower}")
            return None
        
        if df is not None:
            logger.debug(f"Successfully read dataframe. Shape: {df.shape}. Applying final column processing.")
            df.columns = df.columns.astype(str)
            df = _make_unique_columns_final(df)
        else:
            logger.warning(f"read_dataframe: DataFrame is None after attempting to read {file_path_obj}")
        return df
    except Exception as e:
        logger.error(f"Failed to read or process dataframe from {file_path}: {e}", exc_info=True)
        return None

def _get_column_groups_by_base_name(df: pd.DataFrame) -> tuple[list[str], dict[str, list[str]]]:
    grouped_cols_by_base_name = {}
    base_name_order = []
    seen_base_names_for_order = set()
    logger.debug(f"Getting column groups by base name. Input columns: {list(df.columns)}")
    for col_name in df.columns:
        base_name = re.sub(r'\.\d+$', '', col_name)
        if base_name not in grouped_cols_by_base_name:
            grouped_cols_by_base_name[base_name] = []
        grouped_cols_by_base_name[base_name].append(col_name)
        if base_name not in seen_base_names_for_order:
            base_name_order.append(base_name)
            seen_base_names_for_order.add(base_name)
    logger.debug(f"Base name order: {base_name_order}. Grouped cols: {grouped_cols_by_base_name}")
    return base_name_order, grouped_cols_by_base_name

def _choose_best_column_from_group(df: pd.DataFrame, candidate_col_names: list[str]) -> str:
    if not candidate_col_names:
        logger.error("Choose best column: Candidate column names list is empty.")
        raise ValueError("Candidate column names list cannot be empty.")
    if len(candidate_col_names) == 1:
        return candidate_col_names[0]
    
    best_col = candidate_col_names[0]
    best_score = (-1, -1)
    logger.debug(f"Choosing best column from group: {candidate_col_names}")
    for col_name in candidate_col_names:
        if col_name not in df.columns:
            logger.warning(f"Column '{col_name}' not found in DataFrame during best column selection. Skipping.")
            continue
        series = df[col_name]
        non_nan_count = series.count()
        nunique_count = series.nunique()
        current_score = (non_nan_count, nunique_count)
        logger.debug(f"  Candidate: {col_name}, Score: (non-NaNs: {non_nan_count}, nuniques: {nunique_count})")
        if current_score[0] > best_score[0] or \
           (current_score[0] == best_score[0] and current_score[1] > best_score[1]):
            best_score = current_score
            best_col = col_name
    logger.info(f"Best column chosen from {candidate_col_names}: '{best_col}' with score (non-NaNs: {best_score[0]}, nuniques: {best_score[1]})")
    return best_col

# --- Repository Creation Handler ---
async def repo_creation_handler(input, db, session):
    supported_extensions_for_upload = APP_SUPPORTED_EXTENSIONS

    @reactive.effect
    def _list_columns_for_id_split_on_upload():
        file_info = input.new_repo_dataset_file()
        logger.debug(f"[CREATE_REPO] File input changed: {True if file_info else False}")
        if not file_info or len(file_info) == 0:
            available_columns_for_id_split.set([]); return
        
        # When a new file is uploaded, clear any previous preview
        creation_preview_content.set(None)
        
        file_path = Path(file_info[0]["datapath"])
        is_column_loading.set(True)
        logger.debug(f"[CREATE_REPO] Loading columns from {file_path}")
        try:
            with ui.Progress(min=0, max=3) as p:
                p.set(message="Reading dataset...", value=0)
                df = read_dataframe(file_path)
                if df is None or df.empty:
                    logger.info("[CREATE_REPO] Uploaded dataset is empty or could not be read.")
                    available_columns_for_id_split.set(["Info: Uploaded dataset is empty or could not be read."])
                    is_column_loading.set(False); return

                p.set(message="Analyzing columns...", value=1)
                base_name_order, grouped_cols_by_base = _get_column_groups_by_base_name(df)
                final_columns_for_ui = []
                if not base_name_order and df.columns.any():
                    logger.warning("[CREATE_REPO] Column grouping empty, but df has columns. Using all unique columns.")
                    final_columns_for_ui = list(df.columns)
                elif not base_name_order:
                    logger.info("[CREATE_REPO] Dataset has no identifiable columns after grouping.")
                    available_columns_for_id_split.set(["Info: Dataset has no identifiable columns."])
                    is_column_loading.set(False); return
                
                if not final_columns_for_ui:
                    p.set(message="Selecting representative columns...", value=2)
                    for base_name in base_name_order:
                        actual_cols_for_this_base = grouped_cols_by_base.get(base_name, [])
                        if not actual_cols_for_this_base: continue
                        if len(actual_cols_for_this_base) == 1:
                            final_columns_for_ui.append(actual_cols_for_this_base[0])
                        else:
                            best_col = _choose_best_column_from_group(df, actual_cols_for_this_base)
                            final_columns_for_ui.append(best_col)
                
                logger.debug(f"[CREATE_REPO] Final columns for UI: {final_columns_for_ui}")
                if final_columns_for_ui:
                    available_columns_for_id_split.set(final_columns_for_ui)
                else:
                    available_columns_for_id_split.set(["Info: No columns available after filtering duplicates."])
                p.set(message="Completed", value=3)
        except Exception as e:
            logger.error(f"[CREATE_REPO] Error listing columns for ID split: {e}", exc_info=True)
            available_columns_for_id_split.set([f"Error processing file for column selection: {str(e)[:100]}"])
        finally:
            is_column_loading.set(False)
            logger.debug(f"[CREATE_REPO] Column loading finished. available_columns_for_id_split: {available_columns_for_id_split.get()}")

    @render.ui
    def dynamic_id_column_input_ui():
        cols_or_message = available_columns_for_id_split.get()
        if not cols_or_message:
            return ui.input_selectize("new_repo_id_column", "ID Column for Exclusive Split (Optional):",
                                      selected="", choices={"Upload dataset to see column options.":"Upload dataset to see column options."}, width='100%')
            # return ui.p("Upload dataset to see column options.")
        is_message_list = isinstance(cols_or_message, list) and len(cols_or_message) > 0 and \
                          ("Error:" in str(cols_or_message[0]) or "Info:" in str(cols_or_message[0])) and \
                          len(cols_or_message) == 1
        if is_message_list:
            msg = str(cols_or_message[0])
            return ui.p(msg, class_="text-danger small mt-2" if "Error:" in msg else "text-info small mt-2")
        
        if isinstance(cols_or_message, list) and all(isinstance(c, str) for c in cols_or_message):
            choices = {"": "None (Random Split)"}
            choices.update({col: col for col in cols_or_message})
            return ui.input_selectize("new_repo_id_column", "ID Column for Exclusive Split (Optional):",
                                      choices=choices, multiple=False, selected="")
        return ui.p("Column options processing or unavailable.", class_="text-warning small mt-2")

    @render.ui
    def creation_split_preview_output(): # <<< RENDERER FOR THE PREVIEW AREA
        return creation_preview_content.get()

    @reactive.effect
    @reactive.event(input.create_repo)
    def _show_create_repo_modal():
        logger.info("[CREATE_REPO] Showing create repo modal.")
        available_columns_for_id_split.set([])
        creation_preview_content.set(None) # <<< CLEAR PREVIEW WHEN MODAL OPENS
        user = current_user.get()
        if not user:
            logger.warning("[CREATE_REPO] No current user, cannot show create modal.")
            return
        dataset_input = ui.input_file("new_repo_dataset_file", "Upload Dataset (.rda, .rds, .csv, .xlsx, .dta)",
                                      accept=supported_extensions_for_upload, width='100%')
        ui.modal_show(
            ui.modal(
                ui.input_text("new_repo_name", "Repository Name", width='100%'),
                ui.input_text("new_repo_description", "Description (Optional)", width='100%'),
                ui.input_select("new_repo_visibility", "Visibility",
                    {vis.name: vis.value.capitalize() for vis in VisibilityEnum},
                    selected=VisibilityEnum.PRIVATE.name, width='100%'),
                dataset_input,
                ui.output_ui("dynamic_id_column_input_ui", width='100%'),
                ui.input_select("new_repo_split_ratio_str", "Split Ratio",
                    {"0.7,0.15,0.15": "70/15/15", "0.6,0.2,0.2": "60/20/20", "0.8,0.1,0.1": "80/10/10"},
                    selected="0.7,0.15,0.15", width='100%'),
                ui.input_action_button("preview_creation_split_btn", "Preview Split", class_="btn-info btn-sm mt-2 mb-3 w-100"),
                ui.input_action_button("submit_new_repo_creation", "Create Repository", class_="btn-primary w-100"),
                # --- New Preview Area ---
                ui.hr(),
                ui.div(
                    ui.output_ui("creation_split_preview_output"),
                    # Add some styling if needed
                    style="background-color: #f8f9fa; padding: 1rem; border-radius: 5px; margin-top: 1rem;"
                ),
                # --- End of Preview Area ---
                title="Create New Repository", size="l", easy_close=True
            )
        )

    @reactive.effect
    @reactive.event(input.preview_creation_split_btn)
    async def _handle_creation_split_preview():
        logger.info("[CREATE_REPO] Preview Split button clicked.")
        creation_preview_content.set(ui.p("⏳ Generating preview..."))
        await asyncio.sleep(0.1)

        try:
            file_info = input.new_repo_dataset_file()
            id_col_input_val = input.new_repo_id_column()
            ratio_str_input_val = input.new_repo_split_ratio_str()

            if not file_info:
                raise ValueError("Please upload a dataset first to preview the split.")
            if not ratio_str_input_val:
                raise ValueError("Please select a split ratio to preview.")
            
            file_path = Path(file_info[0]["datapath"])
            df = read_dataframe(file_path)
            if df is None or df.empty:
                raise ValueError("Could not load dataset or dataset is empty for preview.")
            
            exclusive_id_col = id_col_input_val.strip() if id_col_input_val and id_col_input_val.strip() != "" and id_col_input_val.strip().lower() != "none (random split)" else None
            
            if exclusive_id_col and exclusive_id_col not in df.columns:
                 raise ValueError(f"Selected ID column '{exclusive_id_col}' not found in the processed dataset.")

            ratios = tuple(map(float, ratio_str_input_val.split(",")))
            
            df_train, df_test, df_val = split_dataset(df.copy(), ratios=ratios, exclusive_id_column=exclusive_id_col)
            
            ui_elements = [ui.h4("Split Preview")]
            total_rows = len(df)
            for name, df_split_preview in [("Train", df_train), ("Test", df_test), ("Validation", df_val)]:
                summary = f"{name} Set: {len(df_split_preview)} rows ({len(df_split_preview)/total_rows:.1%})"
                if exclusive_id_col and not df_split_preview.empty and exclusive_id_col in df_split_preview.columns:
                    summary += f" | Unique '{exclusive_id_col}' values: {df_split_preview[exclusive_id_col].nunique()}"
                
                ui_elements.extend([
                    ui.h5(f"{name} Set Preview ({df_split_preview.shape[0]} rows total)"),
                    ui.p(summary),
                    ui.div(
                        ui.HTML(df_split_preview.head(5).to_html(escape=False, classes="table table-striped table-bordered table-sm w-auto", max_rows=5, index=False)),
                        style="overflow-x: auto; max-height: 200px; margin-bottom: 1rem;"
                    )
                ])
                if name != "Validation": ui_elements.append(ui.hr())
            
            creation_preview_content.set(ui.tags.div(*ui_elements))

        except ValueError as ve:
            logger.warning(f"[CREATE_REPO] Preview Error: {ve}")
            creation_preview_content.set(ui.p(f"Preview Error: {ve}", class_="text-danger"))
        except Exception as e:
            logger.error(f"[CREATE_REPO] Unexpected Preview Error: {e}", exc_info=True)
            creation_preview_content.set(ui.p(f"An unexpected error occurred during preview.", class_="text-danger"))


    @reactive.effect
    @reactive.event(input.submit_new_repo_creation)
    async def _submit_new_repo_async():
        logger.info(f"[CREATE_REPO] Submit button clicked.")
        user = current_user.get()
        if not user: ui.notification_show("Login required.", type="error"); return
        file_info = input.new_repo_dataset_file()
        if not file_info or len(file_info) == 0:
            ui.notification_show("Dataset file required.", type="error"); return
        new_repo_name_val = input.new_repo_name().strip()
        if not new_repo_name_val:
            ui.notification_show("Repository name required.", type="error"); return

        selected_id_col_input = input.new_repo_id_column() 
        exclusive_id_col: str | None = None
        if selected_id_col_input and selected_id_col_input.strip() != "" and selected_id_col_input.strip().lower() != "none (random split)":
            exclusive_id_col = selected_id_col_input.strip()
        
        ratio_str = input.new_repo_split_ratio_str()
        if not ratio_str: ui.notification_show("Split ratio required.", type="error"); return
        try:
            ratio_tuple = tuple(map(float, ratio_str.split(",")))
            if len(ratio_tuple) != 3 or not all(0 <= r <= 1 for r in ratio_tuple) or abs(sum(ratio_tuple) - 1.0) > 1e-9:
                raise ValueError("Split ratio must be three non-negative numbers that sum to 1.")
        except ValueError as e:
            ui.notification_show(f"Invalid split ratio: {e}", type="error"); return
        
        file_path = Path(file_info[0]["datapath"])
        with ui.Progress(min=0, max=5) as p:
            try:
                p.set(message="Reading dataset for creation...", value=1); await asyncio.sleep(0.1)
                df_for_split = read_dataframe(file_path)
                if df_for_split is None or df_for_split.empty : raise ValueError("Could not load dataset for creation.")
                if exclusive_id_col and exclusive_id_col not in df_for_split.columns:
                    raise ValueError(f"Selected ID column '{exclusive_id_col}' not in processed dataset columns.")

                p.set(message="Splitting dataset...", value=2); await asyncio.sleep(0.1)
                df_train, df_test, df_val = split_dataset(df_for_split.copy(), ratios=ratio_tuple, exclusive_id_column=exclusive_id_col)
                
                # ... (rest of submission logic for saving and DB update) ...
                if df_train.empty and df_test.empty and df_val.empty and not df_for_split.empty and sum(ratio_tuple) > 0:
                    raise ValueError("Dataset splitting resulted in all empty sets.")
                p.set(message="Saving files...", value=3); await asyncio.sleep(0.1)
                repo_dir = PROJECT_ROOT_DATA_DIR / user.username / new_repo_name_val
                repo_dir.mkdir(parents=True, exist_ok=True)
                df_train.to_csv(repo_dir / "train.csv", index=False)
                df_test.to_csv(repo_dir / "test.csv", index=False)
                df_val.to_csv(repo_dir / "validation.csv", index=False)
                p.set(message="Updating database...", value=4); await asyncio.sleep(0.1)
                if db.query(Repository).filter_by(user_id=user.id, repo_name=new_repo_name_val).first():
                    raise ValueError(f"Repository '{new_repo_name_val}' already exists.")
                new_repo = Repository(user_id=user.id, repo_name=new_repo_name_val, description=input.new_repo_description(),
                                      visibility=VisibilityEnum[input.new_repo_visibility()], split_column=exclusive_id_col, 
                                      split_ratio_selection=ratio_str)
                db.add(new_repo); db.commit(); db.refresh(new_repo)
                db.add_all([ Dataset(repository_id=new_repo.id, dataset_type=dt, 
                                     location=f"{user.username}/{new_repo_name_val}/{dt}.csv")
                             for dt in ["train", "test", "validation"] ])
                db.commit()
                p.set(message="Done!", value=5); await asyncio.sleep(0.2)
                ui.modal_remove()
                ui.notification_show("Repository created successfully.", type="message")
                repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)
            except ValueError as ve:
                logger.warning(f"[REPO_CREATION] Error: {ve}", exc_info=True)
                ui.notification_show(str(ve), type="error", duration=10)
            except Exception as e:
                logger.error(f"[REPO_CREATION] Fatal error: {e}", exc_info=True)
                ui.notification_show(f"Unexpected error: {e}", type="error", duration=10)


# --- Logout Handler ---
def logout_handler(input):
    @reactive.effect
    @reactive.event(input.logout_btn)
    def _logout():
        logger.info("[LOGOUT] Logout triggered.")
        reset_app_state()
        ui.notification_show("You have been logged out.", type="message")

# --- Upload and Re-Split Handler ---
async def upload_split_handler(input, db, data_dir=PROJECT_ROOT_DATA_DIR):
    # This handler's logic mirrors the repo_creation_handler for previewing
    
    @render.ui
    def resplit_preview_output(): # <<< RENDERER FOR RESPLIT PREVIEW AREA
        return resplit_preview_content.get()

    @reactive.effect 
    def _read_columns_for_resplit_modal():
        
        file_info = input.uploaded_csv_for_resplit() 
        if not file_info or len(file_info) == 0: available_columns_for_resplit_id.set([]); return
        resplit_preview_content.set(None) # Clear preview on new file upload
        file_path = Path(file_info[0]["datapath"])
        df = None
        try:
            if file_path.suffix.lower() == ".csv": 
                df = read_dataframe(file_path)
            else: 
                available_columns_for_resplit_id.set([f"Error: Use CSV for re-split. ('{file_path.suffix}' unsupported)"]); return
            
            if df is not None:
                if df.empty:
                    available_columns_for_resplit_id.set(["Info: Uploaded CSV for re-split is empty."]); return
                base_name_order, grouped_cols_by_base = _get_column_groups_by_base_name(df)
                final_columns_for_ui_resplit = []
                if base_name_order:
                    for base_name in base_name_order:
                        actual_cols = grouped_cols_by_base.get(base_name, [])
                        if not actual_cols: continue
                        if len(actual_cols) == 1: final_columns_for_ui_resplit.append(actual_cols[0])
                        else: final_columns_for_ui_resplit.append(_choose_best_column_from_group(df, actual_cols))
                
                if final_columns_for_ui_resplit: available_columns_for_resplit_id.set(final_columns_for_ui_resplit)
                elif df.columns.any(): available_columns_for_resplit_id.set(["Info: No suitable columns after analysis."])
                else: available_columns_for_resplit_id.set(["Info: Uploaded CSV has no columns."])
            else: available_columns_for_resplit_id.set(["Error: Could not read data from CSV for re-split."])
        except Exception as e:
            logger.error(f"Error reading/processing columns for resplit: {e}", exc_info=True)
            available_columns_for_resplit_id.set([f"Error processing CSV for column selection: {str(e)[:100]}"])

    @render.ui 
    def dynamic_id_column_for_resplit_ui(): 
        cols_or_message = available_columns_for_resplit_id.get()
        label_text = "ID Column for Exclusive Re-Split (Optional):"
        if not cols_or_message:
            return ui.p("Upload CSV for re-splitting options.", class_="text-muted small")
        is_message_list = isinstance(cols_or_message, list) and len(cols_or_message) > 0 and \
                          ("Error:" in str(cols_or_message[0]) or "Info:" in str(cols_or_message[0])) and \
                          len(cols_or_message) == 1
        if is_message_list:
            msg = str(cols_or_message[0])
            return ui.p(msg, class_="text-danger small" if "Error:" in msg else "text-info small")
        
        if isinstance(cols_or_message, list) and all(isinstance(c, str) for c in cols_or_message):
            choices = {"": "None (Random Split)"}
            choices.update({col: col for col in cols_or_message})
            return ui.input_selectize("resplit_id_column", label_text, choices=choices, multiple=False, selected="")
        return ui.p("Column options for re-split processing.", class_="text-warning small")


    @reactive.effect
    def _watch_upload_clicks():
        _ = repo_refresh_trigger.get(); user = current_user.get()
        if not user: return
        scholar_repos = db.query(Repository).filter(Repository.user_id == user.id).all()
        for repo in scholar_repos:
            btn_id = f"upload_dataset_{repo.id}" 
            try:
                input_val = getattr(input, btn_id, None)
                if callable(input_val) and input_val() > 0 and btn_id not in handled_clicks.get():
                    logger.info(f"[RESPLIT] Upload button {btn_id} clicked for repo {repo.id}. Showing re-split modal.")
                    selected_repo_id.set(repo.id); available_columns_for_resplit_id.set([]) 
                    resplit_preview_content.set(None) # <<< CLEAR PREVIEW FOR RESPLIT MODAL
                    current_handled_set = handled_clicks.get().copy(); current_handled_set.add(btn_id); handled_clicks.set(current_handled_set)
                    ui.modal_show(
                        ui.modal(
                            ui.input_file("uploaded_csv_for_resplit", "Upload New CSV to Re-Split", accept=[".csv"]),
                            ui.output_ui("dynamic_id_column_for_resplit_ui"), 
                            ui.input_select("split_ratio_for_resplit", "New Split Ratio", 
                                            {"0.7-0.15-0.15": "70/15/15", "0.6-0.2-0.2": "60/20/20", "0.8-0.1-0.1": "80/10/10"}, 
                                            selected="0.7-0.15-0.15"),
                            ui.input_action_button("preview_resplit_btn", "Preview Re-Split", class_="btn-info btn-sm mt-2 mb-3 w-100"),
                            ui.input_action_button("submit_resplit_data", "Re-Split & Save", class_="btn-primary w-100"),
                            # --- New Preview Area for Re-Split ---
                            ui.hr(),
                            ui.div(
                                ui.output_ui("resplit_preview_output"),
                                style="background-color: #f8f9fa; padding: 1rem; border-radius: 5px; margin-top: 1rem;"
                            ),
                            # --- End of Preview Area ---
                            title=f"Upload and Re-Split for '{repo.repo_name}'", easy_close=True, size="l"
                        ))
                    break 
            except KeyError: continue
            except Exception as e: logger.error(f"Err in upload_split _watch for {btn_id}: {e}", exc_info=True)

    @reactive.effect
    @reactive.event(input.preview_resplit_btn)
    async def _handle_resplit_preview():
        logger.info("[RESPLIT] Preview Re-Split button clicked.")
        resplit_preview_content.set(ui.p("⏳ Generating preview..."))
        await asyncio.sleep(0.1)
        
        try:
            file_info = input.uploaded_csv_for_resplit()
            id_col_input_val = input.resplit_id_column()
            ratio_str_input_val = input.split_ratio_for_resplit()

            if not file_info:
                raise ValueError("Please upload a CSV file first to preview the re-split.")
            if not ratio_str_input_val:
                raise ValueError("Please select a new split ratio to preview.")
            
            ratio_str_for_logic = ratio_str_input_val.replace("-", ",")
            
            # Reusing the same generation logic, but setting a different reactive value
            file_path = Path(file_info[0]["datapath"])
            df = read_dataframe(file_path)
            if df is None or df.empty:
                raise ValueError("Could not load dataset or dataset is empty for preview.")
            
            exclusive_id_col = id_col_input_val.strip() if id_col_input_val and id_col_input_val.strip() != "" and id_col_input_val.strip().lower() != "none (random split)" else None
            
            if exclusive_id_col and exclusive_id_col not in df.columns:
                 raise ValueError(f"Selected ID column '{exclusive_id_col}' not found in the processed dataset.")

            ratios = tuple(map(float, ratio_str_for_logic.split(",")))
            df_train, df_test, df_val = split_dataset(df.copy(), ratios=ratios, exclusive_id_column=exclusive_id_col)
            
            ui_elements = [ui.h4("Split Preview")]
            total_rows = len(df)
            for name, df_split_preview in [("Train", df_train), ("Test", df_test), ("Validation", df_val)]:
                summary = f"{name} Set: {len(df_split_preview)} rows ({len(df_split_preview)/total_rows:.1%})"
                if exclusive_id_col and not df_split_preview.empty and exclusive_id_col in df_split_preview.columns:
                    summary += f" | Unique '{exclusive_id_col}' values: {df_split_preview[exclusive_id_col].nunique()}"
                
                ui_elements.extend([
                    ui.h5(f"{name} Set Preview ({df_split_preview.shape[0]} rows total)"),
                    ui.p(summary),
                    ui.div(
                        ui.HTML(df_split_preview.head(5).to_html(escape=False, classes="table table-striped table-bordered table-sm w-auto", max_rows=5, index=False)),
                        style="overflow-x: auto; max-height: 200px; margin-bottom: 1rem;"
                    )
                ])
                if name != "Validation": ui_elements.append(ui.hr())
            
            resplit_preview_content.set(ui.tags.div(*ui_elements))

        except ValueError as ve:
            logger.warning(f"[RESPLIT] Preview Error: {ve}")
            resplit_preview_content.set(ui.p(f"Preview Error: {ve}", class_="text-danger"))
        except Exception as e:
            logger.error(f"[RESPLIT] Unexpected Preview Error: {e}", exc_info=True)
            resplit_preview_content.set(ui.p(f"An unexpected error occurred during preview.", class_="text-danger"))

    @reactive.effect
    @reactive.event(input.submit_resplit_data)
    async def _handle_resplit_data():
        logger.info(f"[RESPLIT] Submit button clicked.")
        file_info = input.uploaded_csv_for_resplit()
        if not file_info or len(file_info) == 0: ui.notification_show("No file for re-split.", type="error"); return
        user = current_user.get(); repo_id = selected_repo_id.get()
        if not (user and repo_id): ui.notification_show("Session invalid or repo not selected.", type="error"); return
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: ui.notification_show("Repo not found or access denied.", type="error"); return
        
        exclusive_id_col_resplit: str | None = None
        df_for_resplit = None
        try:
            ratio_str_hyphen = input.split_ratio_for_resplit() 
            if not ratio_str_hyphen: raise ValueError("Split ratio required.")
            ratio_tuple = tuple(map(float, ratio_str_hyphen.split("-")))
            if len(ratio_tuple) != 3 or not all(0 <= r <= 1 for r in ratio_tuple) or abs(sum(ratio_tuple) - 1.0) > 1e-9:
                raise ValueError("Split ratio must be three non-negative numbers that sum to 1.")

            selected_id_col_resplit_input = input.resplit_id_column() 
            if selected_id_col_resplit_input and selected_id_col_resplit_input.strip() != "" and selected_id_col_resplit_input.strip().lower() != "none (random split)":
                exclusive_id_col_resplit = selected_id_col_resplit_input.strip()
            
            temp_file_path = Path(file_info[0]["datapath"])
            df_for_resplit = read_dataframe(temp_file_path)
            if df_for_resplit is None or df_for_resplit.empty:
                raise ValueError("Could not read or process CSV for re-splitting, or it's empty.")
            if exclusive_id_col_resplit and exclusive_id_col_resplit not in df_for_resplit.columns:
                 raise ValueError(f"Selected ID column '{exclusive_id_col_resplit}' not in processed dataset columns.")
        except ValueError as ve: 
            logger.warning(f"[RESPLIT] Invalid input for re-split: {ve}", exc_info=True)
            ui.notification_show(f"Invalid input: {ve}", type="error", duration=7); return
        except Exception as e: 
            logger.error(f"[RESPLIT] Err processing inputs for re-split: {e}", exc_info=True)
            ui.notification_show(f"Err processing inputs for re-split: {e}", type="error", duration=7); return

        try:
            with ui.Progress(min=0, max=3) as p:
                p.set(message="Re-splitting dataset...", value=1); await asyncio.sleep(0.1)
                df_train, df_test, df_val = split_dataset(df_for_resplit.copy(), ratios=ratio_tuple, exclusive_id_column=exclusive_id_col_resplit)
                p.set(message="Saving files...", value=2)
                repo_path = Path(data_dir) / user.username / repo.repo_name; repo_path.mkdir(parents=True, exist_ok=True)
                train_fp, test_fp, val_fp = repo_path/"train.csv", repo_path/"test.csv", repo_path/"validation.csv"
                df_train.to_csv(train_fp, index=False); df_test.to_csv(test_fp, index=False); df_val.to_csv(val_fp, index=False); await asyncio.sleep(0.1)
                p.set(message="Updating database...", value=3)
                db.query(Dataset).filter(Dataset.repository_id == repo.id, Dataset.dataset_type.in_(["train", "test", "validation"])).delete(synchronize_session='evaluate')
                db.add_all([ Dataset(repository_id=repo.id, dataset_type=dt, location=str((repo_path/f"{dt}.csv").relative_to(data_dir)))
                             for dt in ["train", "test", "validation"] ])
                repo.split_column = exclusive_id_col_resplit 
                repo.split_ratio_selection = ratio_str_hyphen.replace("-",",") 
                db.commit(); await asyncio.sleep(0.1)
        except ValueError as ve: 
            logger.warning(f"[RESPLIT] Validation error during re-split: {ve}", exc_info=True)
            ui.notification_show(f"{ve}", type="error", duration=10); return 
        except Exception as e: 
            logger.error(f"[RESPLIT] Dataset re-split failed for repo {repo.id}: {e}", exc_info=True)
            ui.notification_show(f"Dataset re-split failed: {e}", type="error", duration=7); return

        ui.modal_remove()
        logger.info(f"[RESPLIT] Dataset re-split and saved for repo {repo.id}")
        btn_id_to_reset = f"upload_dataset_{repo.id}" 
        current_handled = handled_clicks.get().copy()
        if btn_id_to_reset in current_handled: current_handled.remove(btn_id_to_reset); handled_clicks.set(current_handled)
        ui.notification_show("Dataset re-split and saved.", type="message")
        repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)


# --- Upload Analysis, Edit Repo, Search, and Download Handlers ---

async def upload_analysis_handler(input, db, data_dir=PROJECT_ROOT_DATA_DIR):
    last_vals = {} 
    @reactive.effect
    def _watch_upload_clicks():
        _ = repo_refresh_trigger.get(); user = current_user.get()
        if not user: return
        user_repos = db.query(Repository).filter(Repository.user_id == user.id).all()
        for repo in user_repos:
            btn_id = f"upload_analysis_{repo.id}" 
            try:
                input_val = getattr(input, btn_id, None)
                if not callable(input_val): continue
                current_click_count = input_val(); previous_click_count = last_vals.get(btn_id, 0)
                if current_click_count > previous_click_count:
                    selected_repo_id.set(repo.id); last_vals[btn_id] = current_click_count
                    if db.query(Dataset).filter_by(repository_id=repo.id, dataset_type="analysis").first():
                        ui.notification_show(f"Analysis already uploaded for '{repo.repo_name}'. Re-upload will replace it.", type="warning", duration=5, close_button=True)
                    ui.modal_show(
                        ui.modal(
                            ui.input_file("analysis_file_to_upload", "Upload Analysis (PDF or Word)", accept=[".pdf", ".docx"]),
                            ui.input_action_button("submit_analysis_file_upload", "Submit Analysis File"),
                            title=f"Upload Analysis for '{repo.repo_name}'", easy_close=True ))
                    break 
                elif btn_id not in last_vals: last_vals[btn_id] = current_click_count
            except KeyError: continue
            except Exception as e: logger.error(f"Err in upload_analysis _watch for {btn_id}: {e}", exc_info=True)
    @reactive.effect
    @reactive.event(input.submit_analysis_file_upload)
    async def _handle_upload():
        user = current_user.get(); repo_id = selected_repo_id.get(); fileinfo = input.analysis_file_to_upload()
        if not user or not repo_id or not fileinfo or len(fileinfo) == 0:
            missing = [m for m, v in [("user session", user), ("repository context", repo_id), ("file to upload", fileinfo and len(fileinfo)>0)] if not v]
            ui.notification_show(f"Missing data: {', '.join(missing)}.", type="error", duration=7); return
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: ui.notification_show("Repo not found or access denied.", type="error", duration=7); return
        upload_path = Path(data_dir) / user.username / repo.repo_name; upload_path.mkdir(parents=True, exist_ok=True)
        orig_name = Path(fileinfo[0]["name"]); filename = f"analysis{orig_name.suffix.lower()}"
        full_path = upload_path / filename
        try:
            with ui.Progress(min=0, max=2) as p:
                p.set(message="Uploading analysis...", value=0); await asyncio.sleep(0.1)
                p.set(message="Saving file...", detail=f"{filename}", value=1)
                if full_path.exists(): logger.info(f"Replacing existing analysis file: {full_path}"); full_path.unlink()
                shutil.copy(fileinfo[0]["datapath"], full_path); await asyncio.sleep(0.1)
                p.set(message="Updating database record...", value=2)
                db.query(Dataset).filter_by(repository_id=repo.id, dataset_type="analysis").delete(synchronize_session='evaluate')
                db.commit() 
                new_ds = Dataset(repository_id=repo.id, dataset_type="analysis", location=str(full_path.relative_to(data_dir)))
                db.add(new_ds); db.commit(); await asyncio.sleep(0.1)
        except Exception as e: 
            logger.error(f"Err uploading analysis for repo {repo.id}: {e}", exc_info=True)
            ui.notification_show(f"Err uploading analysis: {e}", type="error", duration=7); return
        ui.modal_remove()
        if f"upload_analysis_{repo.id}" in last_vals: last_vals[f"upload_analysis_{repo.id}"] = 0 
        ui.notification_show(f"Analysis uploaded for '{repo.repo_name}'.", type="message")
        repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)

def watch_edit_repo(input, db): 
    last_vals = {}
    @reactive.effect
    def _():
        _ = repo_refresh_trigger.get(); user = current_user.get()
        if not user: return
        repos = db.query(Repository).filter_by(user_id=user.id).all()
        for repo in repos:
            btn_id = f"edit_repo_{repo.id}"
            try:
                input_val = getattr(input, btn_id, None)
                if not callable(input_val): continue
                current_click_count = input_val(); previous_click_count = last_vals.get(btn_id, 0)
                if current_click_count > previous_click_count:
                    selected_repo_id.set(repo.id); last_vals[btn_id] = current_click_count
                    split_info_ui = [ui.p(tags.strong("Split Method:"), f" Exclusive ID Column: {repo.split_column}" if repo.split_column else " Random / Default"),
                                     ui.p(tags.strong("Split Ratio:"), f" {repo.split_ratio_selection.replace(',',':')} (Train:Test:Val)" if repo.split_ratio_selection else "N/A")]
                    modal_content = [
                        ui.input_text("edit_repo_name_field", "Repository Name", value=repo.repo_name),
                        ui.input_text("edit_repo_description_field", "Description", value=repo.description or ""),
                        ui.input_select("edit_repo_visibility_field","Visibility", {vis.name: vis.value.capitalize() for vis in VisibilityEnum}, selected=repo.visibility.name),
                        ui.hr(), ui.h5("Current Split Configuration"), *split_info_ui, ui.hr(),
                        ui.h5("Download Datasets"),
                        ui.download_button("download_train_edit_modal", "Train Set", class_="btn-sm btn-info me-2"),
                        ui.download_button("download_test_edit_modal", "Test Set", class_="btn-sm btn-info me-2"),
                        ui.output_ui("conditional_validation_download_button_ui")]
                    if any(d.dataset_type == "analysis" for d in repo.datasets): 
                        modal_content.append(ui.download_button("download_analysis_edit_modal", "Analysis File", class_="btn-sm btn-warning me-2"))
                    modal_content.append(ui.download_button("download_combined_bundle", "Download All (ZIP)", class_="btn-sm btn-success mt-2"))
                    modal_content.extend([ui.hr(), ui.input_action_button("submit_repo_changes", "Save Changes")])
                    ui.modal_show(ui.modal(*modal_content, title=f"Edit: {repo.repo_name}", easy_close=True, size="l"))
                    break
                elif btn_id not in last_vals: last_vals[btn_id] = current_click_count
            except KeyError: continue
            except Exception as e: logger.error(f"Error in watch_edit_repo for {btn_id}: {e}", exc_info=True)

    @render.ui 
    def conditional_validation_download_button_ui():
        repo_id = selected_repo_id.get()
        if not repo_id: return None
        repo = db.query(Repository).filter_by(id=repo_id).first() 
        if not repo: return None
        has_analysis = any(d.dataset_type == "analysis" for d in repo.datasets)
        validation_ds_exists = any(d.dataset_type == "validation" for d in repo.datasets)
        if has_analysis and validation_ds_exists:
            return ui.download_button("download_validation_edit_modal", "Validation Set", class_="btn-sm btn-info me-2")
        elif validation_ds_exists: 
            return ui.span(" (Upload analysis to download validation set)", class_="small text-muted")
        else: 
            return ui.span(" (Validation set not available)", class_="small text-muted")

def handle_submit_repo_edit(input, db):
    @reactive.effect
    @reactive.event(input.submit_repo_changes)
    def _():
        user = current_user.get(); repo_id = selected_repo_id.get()
        if not user or not repo_id: ui.notification_show("User session or repo context missing.", type="error"); return
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: ui.notification_show("Repo not found or access denied.", type="error"); return
        new_name = input.edit_repo_name_field().strip()
        if not new_name: ui.notification_show("Repo name cannot be empty.", type="error"); return
        if new_name != repo.repo_name and db.query(Repository).filter(Repository.user_id == user.id, Repository.repo_name == new_name, Repository.id != repo_id).first():
            ui.notification_show(f"Another repo named '{new_name}' already exists.", type="error"); return
        repo.repo_name = new_name; repo.description = input.edit_repo_description_field(); repo.visibility = VisibilityEnum[input.edit_repo_visibility_field()]
        try: db.commit()
        except Exception as e: db.rollback(); logger.error(f"Err updating repo: {e}", exc_info=True); ui.notification_show(f"Err updating: {e}", type="error"); return
        ui.modal_remove(); ui.notification_show(f"Repo '{repo.repo_name}' updated.", type="message")
        repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)

def watch_repo_search(input):
    @reactive.effect
    @reactive.event(input.repo_search) 
    def _update_search(): search_query.set(input.repo_search() or "")

def _generate_error_response_dl(message: str): 
    if not message.lower().startswith("error:"): full_message = f"Error: {message}"
    else: full_message = message
    logger.error(full_message)
    return io.BytesIO(full_message.encode()).getvalue()

def _get_download_path(db_session, data_dir_path, current_user_obj, selected_repo_id_val, dataset_type_str, is_public=False):
    user = current_user_obj.get(); repo_id = selected_repo_id_val.get()
    
    if not repo_id: return f"Error: Repository not selected for {dataset_type_str}."
    if not user and not is_public: return f"Error: User session required for private {dataset_type_str} download."

    filters = {"id": repo_id}
    if is_public: filters["visibility"] = VisibilityEnum.PUBLIC
    elif user: filters["user_id"] = user.id 
    else: return f"Error: User context ambiguous or missing for non-public {dataset_type_str} download."

    repo = db_session.query(Repository).filter_by(**filters).first()
    if not repo: return f"Error: Repository {repo_id} not found or access denied for {dataset_type_str}."
    
    if is_public and dataset_type_str == "validation" and not any(d.dataset_type == "analysis" for d in repo.datasets):
        return f"Error: Validation set for public repo {repo.id} requires analysis."

    file_info = next((d for d in repo.datasets if d.dataset_type == dataset_type_str), None)
    if not file_info: return f"Error: {dataset_type_str.capitalize()} dataset not found in repo {repo.id}."
    
    file_path = Path(data_dir_path) / file_info.location
    if not file_path.exists(): return f"Error: {dataset_type_str.capitalize()} file not found at {file_path}."
    
    logger.debug(f"Download serving: {dataset_type_str} from {file_path}")
    return str(file_path)

def register_static_downloads(db, data_dir=PROJECT_ROOT_DATA_DIR):
    @render.download(filename=lambda: f"repo_{selected_repo_id.get() or 'unknown'}_train.csv")
    def download_train_edit_modal(): 
        path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, "train")
        return path_or_error if not path_or_error.startswith("Error:") else _generate_error_response_dl(path_or_error)

    @render.download(filename=lambda: f"repo_{selected_repo_id.get() or 'unknown'}_test.csv")
    def download_test_edit_modal():
        path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, "test")
        return path_or_error if not path_or_error.startswith("Error:") else _generate_error_response_dl(path_or_error)
    
    @render.download(filename=lambda: f"repo_{selected_repo_id.get() or 'unknown'}_validation.csv")
    def download_validation_edit_modal():
        path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, "validation")
        return path_or_error if not path_or_error.startswith("Error:") else _generate_error_response_dl(path_or_error)

    @render.download(filename=lambda: f"repo_{selected_repo_id.get() or 'unknown'}_bundle.zip")
    def download_combined_bundle():
        user = current_user.get(); repo_id = selected_repo_id.get()
        if not user or not repo_id: return _generate_error_response_dl("User or repo context missing for bundle.")
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: return _generate_error_response_dl("Repo not found or access denied for bundle.")
        zip_buffer = io.BytesIO(); files_added = False
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for dt in ["train", "test", "validation", "analysis"]: 
                path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, dt, is_public=False) 
                if not (isinstance(path_or_error, str) and path_or_error.startswith("Error:")):
                    file_path_obj = Path(path_or_error)
                    arcname = f"{dt}.csv" if dt not in ["analysis"] else file_path_obj.name 
                    zipf.write(file_path_obj, arcname=arcname); files_added = True
                elif dt != "analysis": 
                    logger.warning(f"Bundle: {dt} data not found or error: {path_or_error}")
        if not files_added: return _generate_error_response_dl("No files found to include in bundle.")
        zip_buffer.seek(0); return zip_buffer  
    
    @render.download(
        filename=lambda: Path(getattr(next((d for d in getattr((db.query(Repository).filter_by(id=selected_repo_id.get(), user_id=current_user.get().id).first() if current_user.get() and selected_repo_id.get() else None), 'datasets', []) if d.dataset_type == "analysis"), None), 'location', f"analysis_file_repo_{(selected_repo_id.get() or 'unknown')}_not_found.txt")).name if current_user.get() and selected_repo_id.get() else f"analysis_file_default_name.txt"
    )
    def download_analysis_edit_modal():
        path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, "analysis")
        return path_or_error if not path_or_error.startswith("Error:") else _generate_error_response_dl(path_or_error)

def register_public_downloads(db, data_dir=PROJECT_ROOT_DATA_DIR):
    @render.download(filename=lambda: f"public_repo_{selected_repo_id.get() or 'unknown'}_train.csv")
    def download_train_public(): 
        path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, "train", is_public=True)
        return path_or_error if not path_or_error.startswith("Error:") else _generate_error_response_dl(path_or_error)

    @render.download(filename=lambda: f"public_repo_{selected_repo_id.get() or 'unknown'}_test.csv")
    def download_test_public(): 
        path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, "test", is_public=True)
        return path_or_error if not path_or_error.startswith("Error:") else _generate_error_response_dl(path_or_error)
    
    @render.download(filename=lambda: f"public_repo_{selected_repo_id.get() or 'unknown'}_validation.csv")
    def download_validation_public(): 
        path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, "validation", is_public=True)
        return path_or_error if not path_or_error.startswith("Error:") else _generate_error_response_dl(path_or_error)
    
    @render.download(
        filename=lambda: Path(getattr(next((d for d in getattr((db.query(Repository).filter_by(id=selected_repo_id.get(), visibility=VisibilityEnum.PUBLIC).first() if selected_repo_id.get() else None), 'datasets', []) if d.dataset_type == "analysis"),None),'location',f"public_analysis_repo_{(selected_repo_id.get() or 'unknown')}_not_found.txt")).name if selected_repo_id.get() else f"public_analysis_default_name.txt"
    )
    def download_analysis_public():
        path_or_error = _get_download_path(db, data_dir, current_user, selected_repo_id, "analysis", is_public=True)
        return path_or_error if not path_or_error.startswith("Error:") else _generate_error_response_dl(path_or_error)
<<<<<<< Updated upstream
=======
    
   
#  <---------------------------------Delete Repo Logic-------------------------------->

def delete_repo(db, repo_id):
    repo = db.query(Repository).filter_by(id=repo_id).first()
    if not repo:
        raise ValueError(f"Repository with ID {repo_id} not found.")

    for dataset in repo.datasets:
        db.delete(dataset)
    
    db.delete(repo)
    db.commit()

def watch_delete_repo_buttons(user_input, db):
    @reactive.Effect
    def _():
        _ = repo_refresh_trigger.get()
        all_repos = db.query(Repository).all()
        for repo in all_repos:
            if repo.id not in handled_delete_clicks:
                make_delete_modal_effect(user_input, repo.id, repo.repo_name)
                make_confirm_delete_effect(user_input, repo.id, db)
                handled_delete_clicks.add(repo.id)

def make_delete_modal_effect(user_input, repo_id, repo_name):
    @reactive.Effect
    @reactive.event(user_input[f"delete_repo_{repo_id}"])
    def _show_modal():
        ui.modal_show(
            ui.modal(
                ui.p(f"Are you sure you want to delete '{repo_name}'? This cannot be undone."),
                title="Confirm Deletion",
                easy_close=False,
                fade=False,
                footer=(
                    ui.modal_button("Cancel"),
                    ui.input_action_button(
                        f"confirm_delete_repo_{repo_id}",
                        "Delete",
                        class_="btn btn-danger"
                    )
                )
            )
        )

def make_confirm_delete_effect(user_input, repo_id, db):
    @reactive.Effect
    @reactive.event(user_input[f"confirm_delete_repo_{repo_id}"])
    def _confirm_delete():
        delete_repo(db, repo_id)
        ui.modal_remove()
        repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)

>>>>>>> Stashed changes
