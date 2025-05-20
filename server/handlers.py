import logging
from pathlib import Path
import asyncio

log_path = Path(__file__).resolve().parent / "debug_modal_state.log"
logger = logging.getLogger("app_debug")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.debug("Logger initialized.")

from shiny import reactive, ui, render
from db.models import Repository, User, Dataset, VisibilityEnum
from .state import (
    current_user, selected_repo_id, search_query,
    repo_refresh_trigger, handled_clicks, reset_app_state
)
import pandas as pd
# Ensure these helpers are in your utils/split.py and are imported
from utils.split import split_dataset, get_stratification_series, is_stratifiable 
import pyreadr
import shutil

# --- LOGIN HANDLER (Assumed to be the version from previous successful steps) ---
def login_handler(input, db):
    @reactive.effect
    @reactive.event(input.login_main_btn)
    def _show_role_selection_modal():
        ui.modal_remove(); logger.debug("[LOGIN_HANDLER] login_main_btn clicked.")
        ui.modal_show(
            ui.modal(
                ui.h4("Login As"),
                ui.input_action_button("login_as_scholar_btn", "Login as Scholar", class_="btn-primary w-100 mb-2"),
                ui.input_action_button("login_as_peer_btn", "Login as Peer", class_="btn-secondary w-100"),
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

PROJECT_ROOT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROJECT_ROOT_DATA_DIR.mkdir(parents=True, exist_ok=True)

stratifiable_columns_for_creation = reactive.Value([]) # Stores only viable column names or info/error messages

async def repo_creation_handler(input, db, session):
    @reactive.effect
    def _filter_stratifiable_columns_on_upload():
        file_info = input.new_repo_dataset_file()
        if not file_info or len(file_info) == 0:
            stratifiable_columns_for_creation.set([]); return
        
        file_path = Path(file_info[0]["datapath"])
        df = None
        valid_cols_for_stratify = []
        error_message_for_ui = None # To store a single error/info message for UI
        try:
            logger.debug(f"[REPO_CREATION] Reading & filtering stratifiable columns from: {file_path.name}")
            if file_path.suffix.lower() == ".rds": result = pyreadr.read_r(str(file_path))
            elif file_path.suffix.lower() == ".rda": result = pyreadr.read_r(str(file_path))
            else:
                error_message_for_ui = f"Error: Unsupported file type ({file_path.suffix}). Please use .rda or .rds."
                logger.warning(error_message_for_ui); stratifiable_columns_for_creation.set([error_message_for_ui]); return
            
            if result: df = next(iter(result.values()))

            if df is not None and isinstance(df, pd.DataFrame):
                if df.empty:
                    error_message_for_ui = "Info: Uploaded dataset is empty."
                    logger.info(error_message_for_ui); stratifiable_columns_for_creation.set([error_message_for_ui]); return

                for col_name in df.columns:
                    try:
                        # Check if this single column is stratifiable
                        temp_stratify_series = get_stratification_series(df, col_name) # From utils/split.py
                        if temp_stratify_series is not None and is_stratifiable(temp_stratify_series, min_samples_per_group=2): # From utils/split.py
                            valid_cols_for_stratify.append(col_name)
                    except Exception as col_check_e: # Catch errors during individual column check
                        logger.debug(f"Column '{col_name}' not suitable for stratification or error during check: {col_check_e}")
                
                stratifiable_columns_for_creation.set(valid_cols_for_stratify)
                logger.debug(f"[REPO_CREATION] Stratifiable columns found: {valid_cols_for_stratify}")

                if not valid_cols_for_stratify and df.columns.any(): # If DF has columns but none are stratifiable as single columns
                     stratifiable_columns_for_creation.set(["Info: No single column found suitable for robust stratification. You may still select multiple columns if their combination is viable."])
                elif not df.columns.any() and not valid_cols_for_stratify: # DF has no columns
                    stratifiable_columns_for_creation.set(["Info: Uploaded dataset has no columns."])
            else:
                error_message_for_ui = "Error: Could not read data frame from file."
                logger.warning(error_message_for_ui); stratifiable_columns_for_creation.set([error_message_for_ui])
        except Exception as e:
            logger.error(f"Error reading/filtering columns: {e}", exc_info=True)
            stratifiable_columns_for_creation.set([f"Error processing file: {str(e)[:100]}"])


    @render.ui
    def dynamic_stratify_columns_input_ui(): 
        cols_or_message = stratifiable_columns_for_creation.get()
        
        if isinstance(cols_or_message, list) and len(cols_or_message) > 0:
            first_item = str(cols_or_message[0]) # Check if the list contains an error/info message
            if "Error:" in first_item:
                return ui.p(f"{first_item}", class_="text-danger small mt-2")
            elif "Info:" in first_item:
                 return ui.p(f"{first_item}", class_="text-info small mt-2")
            else: # It's a list of valid column names
                choices = {col: col for col in cols_or_message} 
                return ui.input_selectize( 
                    "new_repo_actual_split_columns", 
                    "Stratify By (select one or more; only individually viable columns shown):",
                    choices=choices, multiple=True 
                )
        else: # Default message or empty list after successful processing but no valid single columns
            return ui.p("Upload dataset to see stratification options. Only columns suitable for robust single-column stratification will be listed. You can still select multiple columns if their combination is viable.", class_="text-muted small mt-2")


    @reactive.effect
    @reactive.event(input.create_repo)
    def _show_create_repo_modal():
        logger.debug("[REPO_CREATION] create_repo button clicked.")
        stratifiable_columns_for_creation.set([]) 
        ui.modal_show(
            ui.modal(
                ui.input_text("new_repo_name", "Repository Name"),
                ui.input_text("new_repo_description", "Description (Optional)"),
                ui.input_select("new_repo_visibility", "Visibility", 
                                {vis.name: vis.value.capitalize() for vis in VisibilityEnum}, 
                                selected=VisibilityEnum.PRIVATE.name),
                ui.input_file("new_repo_dataset_file", "Upload Dataset (.rda or .rds)", accept=[".rds", ".rda"]),
                ui.output_ui("dynamic_stratify_columns_input_ui"), 
                ui.input_select("new_repo_split_ratio_str", "Split Ratio", 
                                {"0.7,0.15,0.15": "70/15/15", "0.6,0.2,0.2": "60/20/20", "0.8,0.1,0.1": "80/10/10"}, 
                                selected="0.7,0.15,0.15"),
                ui.input_action_button("submit_new_repo_creation", "Create Repository"),
                title="Create New Repository", easy_close=True, size="l" # Larger modal
            )
        )

    @reactive.effect
    @reactive.event(input.submit_new_repo_creation)
    async def _submit_new_repo_async():
        user = current_user.get()
        if not user: ui.notification_show("Login required.", type="error"); return
        file_info = input.new_repo_dataset_file()
        if not file_info or len(file_info) == 0: ui.notification_show("Dataset file required.", type="error"); return
        new_repo_name_val = input.new_repo_name().strip()
        if not new_repo_name_val: ui.notification_show("Repository name required.", type="error"); return
        
        split_cols_selected = input.new_repo_actual_split_columns() 
        split_cols_for_function = list(split_cols_selected) if split_cols_selected and len(split_cols_selected) > 0 else None
        split_cols_to_store_in_db = ",".join(split_cols_for_function) if split_cols_for_function else None

        ratio_str = input.new_repo_split_ratio_str() 
        if not ratio_str: ui.notification_show("Split ratio required.", type="error"); return
        ratio_tuple = tuple(map(float, ratio_str.split(",")))
        
        file_path = Path(file_info[0]["datapath"])
        repo_base_dir = PROJECT_ROOT_DATA_DIR

        with ui.Progress(min=0, max=5) as p:
            p.set(message="Initializing...", value=0)
            try:
                p.set(message="Reading dataset...", detail=f"Loading {file_path.name}", value=1); await asyncio.sleep(0.1)
                df = None
                if file_path.suffix.lower() == ".rds": result = pyreadr.read_r(str(file_path))
                elif file_path.suffix.lower() == ".rda": result = pyreadr.read_r(str(file_path))
                else: raise ValueError(f"Unsupported file type: {file_path.suffix}")
                if result: df = next(iter(result.values()))
                if df is None: raise ValueError("Could not read data frame from file.")

                p.set(message="Splitting dataset...", value=2); await asyncio.sleep(0.1)
                # The split_dataset function (from utils_split_py_stratify_check_v2)
                # will now raise a ValueError if the selected combination is not stratifiable.
                df_train, df_test, df_val = split_dataset(df, split_cols_for_function, ratio_tuple)

                p.set(message="Saving files...", value=3); await asyncio.sleep(0.1)
                repo_dir_path = repo_base_dir / user.username / new_repo_name_val
                repo_dir_path.mkdir(parents=True, exist_ok=True)
                train_fp, test_fp, val_fp = repo_dir_path/"train.csv", repo_dir_path/"test.csv", repo_dir_path/"validation.csv"
                df_train.to_csv(train_fp, index=False); df_test.to_csv(test_fp, index=False); df_val.to_csv(val_fp, index=False)

                p.set(message="Updating database...", value=4); await asyncio.sleep(0.1)
                if db.query(Repository).filter_by(user_id=user.id, repo_name=new_repo_name_val).first():
                    raise ValueError(f"Repository name '{new_repo_name_val}' already exists for this user.")
                new_repo = Repository(
                    user_id=user.id, repo_name=new_repo_name_val, description=input.new_repo_description(),
                    visibility=VisibilityEnum[input.new_repo_visibility()],
                    split_column=split_cols_to_store_in_db, 
                    split_ratio_selection=ratio_str 
                )
                db.add(new_repo); db.commit(); db.refresh(new_repo)
                db.add_all([
                    Dataset(repository_id=new_repo.id, dataset_type="train", location=str(train_fp.relative_to(repo_base_dir))),
                    Dataset(repository_id=new_repo.id, dataset_type="test", location=str(test_fp.relative_to(repo_base_dir))),
                    Dataset(repository_id=new_repo.id, dataset_type="validation", location=str(val_fp.relative_to(repo_base_dir))),
                ])
                db.commit()
                p.set(message="Completed!", value=5); await asyncio.sleep(0.2)
                ui.modal_remove()
                ui.notification_show("Repository created successfully.", type="message")
                repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)
            except ValueError as ve: 
                logger.warning(f"Validation error during repo creation: {ve}")
                ui.notification_show(f"{ve}", type="error", duration=10) 
                # Modal remains open for user to correct input
            except Exception as e:
                logger.error(f"Unexpected error during repo creation: {e}", exc_info=True)
                ui.modal_remove() # Close modal on unexpected errors
                ui.notification_show(f"An unexpected error occurred: {e}", type="error", duration=7)

# --- Other Handlers (logout_handler, upload_split_handler, etc. - Ensure they are async if using await) ---
def logout_handler(input):
    @reactive.effect
    @reactive.event(input.logout_btn)
    def _logout():
        logger.debug("[LOGOUT] Logout triggered by logout_btn")
        reset_app_state()
        ui.notification_show("You have been logged out.", type="message")

async def upload_split_handler(input, db, data_dir=PROJECT_ROOT_DATA_DIR):
    # This handler also needs to be updated for dynamic multi-column selection for re-split
    # For now, it uses a placeholder text input for comma-separated columns.
    stratifiable_columns_for_resplit = reactive.Value([]) 

    @reactive.effect 
    def _read_columns_for_resplit_modal():
        file_info = input.uploaded_csv_for_resplit() 
        if not file_info or len(file_info) == 0: stratifiable_columns_for_resplit.set([]); return
        file_path = Path(file_info[0]["datapath"])
        df = None
        valid_cols = []
        error_message_for_ui = None
        try:
            logger.debug(f"[RESPLIT_HANDLER] Reading & filtering columns from: {file_path.name}")
            if file_path.suffix.lower() == ".csv": 
                df = pd.read_csv(file_path)
            else: 
                error_message_for_ui = f"Error: Use CSV for re-split for now. ({file_path.suffix} unsupported)"
                logger.warning(error_message_for_ui); stratifiable_columns_for_resplit.set([error_message_for_ui]); return
            
            if df is not None:
                if df.empty:
                    error_message_for_ui = "Info: Uploaded CSV for re-split is empty."
                    logger.info(error_message_for_ui); stratifiable_columns_for_resplit.set([error_message_for_ui]); return
                for col_name in df.columns:
                    try:
                        temp_stratify_series = get_stratification_series(df, col_name)
                        if temp_stratify_series is not None and is_stratifiable(temp_stratify_series, min_samples_per_group=2):
                            valid_cols.append(col_name)
                    except: pass 
                stratifiable_columns_for_resplit.set(valid_cols)
                if not valid_cols and df.columns.any():
                    stratifiable_columns_for_resplit.set(["Info: No single column suitable for robust stratification in CSV."])
                elif not df.columns.any() and not valid_cols:
                     stratifiable_columns_for_resplit.set(["Info: Uploaded CSV has no columns."])
            else: 
                stratifiable_columns_for_resplit.set(["Error: Could not read data from CSV"])
        except Exception as e:
            logger.error(f"Error reading columns for resplit: {e}", exc_info=True)
            stratifiable_columns_for_resplit.set([f"Error reading CSV: {str(e)[:100]}"])

    @render.ui 
    def dynamic_stratify_columns_for_resplit_ui():
        cols_or_message = stratifiable_columns_for_resplit.get()
        if isinstance(cols_or_message, list) and len(cols_or_message) > 0:
            first_item = str(cols_or_message[0])
            if "Error:" in first_item: return ui.p(f"{first_item}", class_="text-danger small")
            elif "Info:" in first_item: return ui.p(f"{first_item} You can still proceed without stratification or select multiple columns.", class_="text-info small")
            else: return ui.input_selectize("resplit_actual_split_columns", "Stratify Re-Split By (select one or more, only viable single columns shown):", choices={col: col for col in cols_or_message}, multiple=True)
        else: return ui.p("Upload a CSV to see stratification options.", class_="text-muted small")


    @reactive.effect
    def _watch_upload_clicks():
        _ = repo_refresh_trigger.get() 
        user = current_user.get()
        if not user: return
        scholar_repos = db.query(Repository).filter(Repository.user_id == user.id).all()
        for repo in scholar_repos:
            btn_id = f"upload_dataset_{repo.id}" 
            try:
                if input[btn_id]() > 0 and btn_id not in handled_clicks.get():
                    logger.debug(f"[UPLOAD_SPLIT_HANDLER] Btn {btn_id} clicked for repo {repo.id}.")
                    selected_repo_id.set(repo.id)
                    stratifiable_columns_for_resplit.set([]) 
                    current_handled_set = handled_clicks.get().copy(); current_handled_set.add(btn_id); handled_clicks.set(current_handled_set)
                    ui.modal_show(
                        ui.modal(
                            ui.input_file("uploaded_csv_for_resplit", "Upload New CSV to Re-Split", accept=[".csv"]),
                            ui.output_ui("dynamic_stratify_columns_for_resplit_ui"), 
                            ui.input_select("split_ratio_for_resplit", "New Split Ratio", 
                                            {"0.7-0.15-0.15": "70/15/15", "0.6-0.2-0.2": "60/20/20", "0.8-0.1-0.1": "80/10/10"}, 
                                            selected="0.7-0.15-0.15"),
                            ui.input_action_button("submit_resplit_data", "Re-Split & Save"),
                            title=f"Upload and Re-Split for '{repo.repo_name}'", easy_close=True, size="l"
                        )
                    )
                    break 
            except KeyError: continue
            except Exception as e: logger.error(f"Err in upload_split _watch for {btn_id}: {e}", exc_info=True)

    @reactive.effect
    @reactive.event(input.submit_resplit_data)
    async def _handle_resplit_data():
        file_info = input.uploaded_csv_for_resplit()
        if not file_info or len(file_info) == 0: ui.notification_show("No file for re-split.", type="error"); return
        user = current_user.get(); repo_id = selected_repo_id.get()
        if not (user and repo_id): ui.notification_show("Session invalid or repo not selected.", type="error"); return
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: ui.notification_show("Repo not found or access denied.", type="error"); return
        try:
            ratio_str = input.split_ratio_for_resplit()
            split_cols_selected = input.resplit_actual_split_columns() 
            split_cols_for_function = list(split_cols_selected) if split_cols_selected and len(split_cols_selected) > 0 else None
            split_cols_to_store_in_db = ",".join(split_cols_for_function) if split_cols_for_function else None
            if not ratio_str: ui.notification_show("Split ratio required.", type="error"); return
            ratio_tuple = tuple(map(float, ratio_str.split("-"))) 
            df = pd.read_csv(file_info[0]["datapath"])
        except Exception as e: logger.error(f"Err processing inputs for re-split: {e}", exc_info=True); ui.notification_show(f"Err processing inputs: {e}", type="error", duration=7); return
        try:
            with ui.Progress(min=0, max=3) as p:
                p.set(message="Re-splitting...", value=0); await asyncio.sleep(0.1)
                p.set(message="Splitting dataset...", value=1)
                df_train, df_test, df_val = split_dataset(df, split_cols_for_function, ratio_tuple)
                await asyncio.sleep(0.1)
                p.set(message="Saving files...", value=2)
                repo_path = Path(data_dir) / user.username / repo.repo_name; repo_path.mkdir(parents=True, exist_ok=True)
                train_fp, test_fp, val_fp = repo_path/"train.csv", repo_path/"test.csv", repo_path/"validation.csv"
                df_train.to_csv(train_fp, index=False); df_test.to_csv(test_fp, index=False); df_val.to_csv(val_fp, index=False); await asyncio.sleep(0.1)
                p.set(message="Updating database...", value=3)
                db.query(Dataset).filter(Dataset.repository_id == repo.id, Dataset.dataset_type.in_(["train", "test", "validation"])).delete(synchronize_session='evaluate')
                db.add_all([
                    Dataset(repository_id=repo.id, dataset_type="train", location=str(train_fp.relative_to(data_dir))),
                    Dataset(repository_id=repo.id, dataset_type="test", location=str(test_fp.relative_to(data_dir))),
                    Dataset(repository_id=repo.id, dataset_type="validation", location=str(val_fp.relative_to(data_dir))),
                ])
                repo.split_column = split_cols_to_store_in_db 
                repo.split_ratio_selection = ratio_str.replace("-",",") 
                db.commit(); await asyncio.sleep(0.1)
        except ValueError as ve: logger.warning(f"Validation error during re-split: {ve}"); ui.notification_show(f"{ve}", type="error", duration=10); return 
        except Exception as e: logger.error(f"Dataset re-split failed for repo {repo.id}: {e}", exc_info=True); ui.notification_show(f"Dataset re-split failed: {e}", type="error", duration=7); ui.modal_remove(); return
        ui.modal_remove()
        btn_id_to_reset = f"upload_dataset_{repo.id}" 
        current_handled = handled_clicks.get().copy()
        if btn_id_to_reset in current_handled: current_handled.remove(btn_id_to_reset); handled_clicks.set(current_handled)
        ui.notification_show("Dataset re-split and saved.", type="message")
        repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)

async def upload_analysis_handler(input, db, data_dir=PROJECT_ROOT_DATA_DIR):
    last_vals = {} 
    @reactive.effect
    def _watch_upload_clicks():
        _ = repo_refresh_trigger.get() 
        user = current_user.get()
        if not user: return
        user_repos = db.query(Repository).filter(Repository.user_id == user.id).all()
        for repo in user_repos:
            btn_id = f"upload_analysis_{repo.id}" 
            try:
                current_click_count = input[btn_id](); previous_click_count = last_vals.get(btn_id, 0)
                if current_click_count > previous_click_count:
                    logger.debug(f"[MODAL TRIGGERED] Upload analysis for repo {repo.repo_name} (id={repo.id})")
                    selected_repo_id.set(repo.id); last_vals[btn_id] = current_click_count
                    ui.modal_show(
                        ui.modal(
                            ui.input_file("analysis_file_to_upload", "Upload Excel Analysis (.xlsx)", accept=[".xlsx"]),
                            ui.input_action_button("submit_analysis_file_upload", "Submit Analysis File"),
                            title=f"Upload Analysis for '{repo.repo_name}'", easy_close=True
                        )
                    )
                    break 
                elif btn_id not in last_vals: last_vals[btn_id] = current_click_count
            except KeyError: continue
            except Exception as e: logger.error(f"Err in upload_analysis _watch for {btn_id}: {e}", exc_info=True)

    @reactive.effect
    @reactive.event(input.submit_analysis_file_upload)
    async def _handle_upload():
        user = current_user.get(); repo_id = selected_repo_id.get(); fileinfo = input.analysis_file_to_upload()
        if not user or not repo_id or not fileinfo or len(fileinfo) == 0:
            missing = ["user session" if not user else None, "repository context" if not repo_id else None, "file to upload" if not fileinfo or len(fileinfo) == 0 else None]
            ui.notification_show(f"Missing data: {', '.join(filter(None, missing))}.", type="error", duration=7); return
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: ui.notification_show("Repo not found or access denied.", type="error", duration=7); return
        upload_path = Path(data_dir) / user.username / repo.repo_name; upload_path.mkdir(parents=True, exist_ok=True)
        filename = "analysis.xlsx"; full_path = upload_path / filename
        try:
            with ui.Progress(min=0, max=2) as p:
                p.set(message="Uploading analysis...", value=0); await asyncio.sleep(0.1)
                p.set(message="Saving file...", detail=f"{filename}", value=1)
                if full_path.exists(): full_path.unlink()
                shutil.copy(fileinfo[0]["datapath"], full_path); await asyncio.sleep(0.1)
                p.set(message="Updating database record...", value=2)
                db.query(Dataset).filter_by(repository_id=repo.id, dataset_type="analysis").delete(synchronize_session='evaluate')
                new_ds = Dataset(repository_id=repo.id, dataset_type="analysis", location=str(full_path.relative_to(data_dir)))
                db.add(new_ds); db.commit(); await asyncio.sleep(0.1)
        except Exception as e: logger.error(f"Err uploading analysis for repo {repo.id}: {e}", exc_info=True); ui.notification_show(f"Err uploading analysis: {e}", type="error", duration=7); ui.modal_remove(); return
        ui.modal_remove()
        btn_id_to_reset = f"upload_analysis_{repo.id}" 
        if btn_id_to_reset in last_vals: last_vals[btn_id_to_reset] = 0 
        ui.notification_show(f"Analysis uploaded for '{repo.repo_name}'.", type="message")
        repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)

def watch_edit_repo(input, db): 
    last_vals = {} 
    @reactive.effect
    def _():
        _ = repo_refresh_trigger.get() 
        user = current_user.get()
        if not user: return
        repos = db.query(Repository).filter_by(user_id=user.id).all()
        for repo in repos:
            btn_id = f"edit_repo_{repo.id}" 
            try:
                current_click_count = input[btn_id](); previous_click_count = last_vals.get(btn_id, 0)
                if current_click_count > previous_click_count:
                    logger.debug(f"[MODAL TRIGGERED] Edit repo modal for {repo.repo_name} (id={repo.id})")
                    selected_repo_id.set(repo.id); last_vals[btn_id] = current_click_count
                    ui.modal_show(
                        ui.modal(
                            ui.input_text("edit_repo_name_field", "Repository Name", value=repo.repo_name),
                            ui.input_text("edit_repo_description_field", "Description", value=repo.description or ""),
                            ui.input_select("edit_repo_visibility_field", "Visibility", {vis.name: vis.value.capitalize() for vis in VisibilityEnum}, selected=repo.visibility.name),
                            ui.hr(),
                            ui.h5("Download Datasets"),
                            ui.download_button("download_train_edit_modal", "Train Set", class_="btn-sm btn-info me-1"),
                            ui.download_button("download_test_edit_modal", "Test Set", class_="btn-sm btn-info me-1"),
                            ui.output_ui("conditional_validation_download_button_ui"), 
                            ui.hr(),
                            ui.input_action_button("submit_repo_changes", "Save Changes"),
                            title=f"Edit / Download: {repo.repo_name}", easy_close=True
                        )
                    )
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
        if has_analysis:
            return ui.download_button("download_validation_edit_modal", "Validation Set", class_="btn-sm btn-success")
        else:
            return ui.span(" (Upload analysis to download validation set)", class_="small text-muted")

def handle_submit_repo_edit(input, db):
    @reactive.effect
    @reactive.event(input.submit_repo_changes)
    def _():
        user = current_user.get(); repo_id = selected_repo_id.get()
        if not user or not repo_id: ui.notification_show("User session or repo context missing for edit.", type="error", duration=7); return
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: ui.notification_show("Repo not found or access denied.", type="error", duration=7); return
        new_name = input.edit_repo_name_field().strip()
        if not new_name: ui.notification_show("Repo name cannot be empty.", type="error"); return
        if new_name != repo.repo_name: 
            if db.query(Repository).filter(Repository.user_id == user.id, Repository.repo_name == new_name, Repository.id != repo_id).first():
                ui.notification_show(f"Another repo named '{new_name}' already exists.", type="error", duration=7); return
        repo.repo_name = new_name; repo.description = input.edit_repo_description_field(); repo.visibility = VisibilityEnum[input.edit_repo_visibility_field()]
        try: db.commit()
        except Exception as e: db.rollback(); logger.error(f"Err updating repo in DB: {e}", exc_info=True); ui.notification_show(f"Err updating repo: {e}", type="error", duration=7); return
        ui.modal_remove()
        ui.notification_show(f"Repo '{repo.repo_name}' updated.", type="message")
        repo_refresh_trigger.set(repo_refresh_trigger.get() + 1)

def watch_repo_search(input):
    @reactive.effect
    @reactive.event(input.repo_search) 
    def _update_search():
        search_val = input.repo_search()
        search_query.set(search_val if search_val is not None else "")

# --- DOWNLOAD HANDLERS (Corrected to be synchronous) ---
def register_static_downloads(db, data_dir=PROJECT_ROOT_DATA_DIR):
    @render.download(filename=lambda: f"repo_{selected_repo_id.get() or 'unknown'}_train.csv")
    def download_train_edit_modal(): # Synchronous
        user = current_user.get(); repo_id = selected_repo_id.get()
        if not user or not repo_id: logger.error("[DOWNLOAD] train_edit: No user/repo."); return b"" 
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: logger.error(f"[DOWNLOAD] train_edit: Repo {repo_id} not found."); return b""
        file_info = next((d for d in repo.datasets if d.dataset_type == "train"), None)
        if not file_info: logger.error(f"[DOWNLOAD] train_edit: Train dataset not found in repo {repo.id}."); return b""
        file_path = Path(data_dir) / file_info.location 
        logger.debug(f"[DOWNLOAD] Serving train_edit file: {file_path}")
        if not file_path.exists(): logger.error(f"[DOWNLOAD] train_edit: File not at {file_path}."); return b""
        return str(file_path)

    @render.download(filename=lambda: f"repo_{selected_repo_id.get() or 'unknown'}_test.csv")
    def download_test_edit_modal(): # Synchronous
        user = current_user.get(); repo_id = selected_repo_id.get()
        if not user or not repo_id: logger.error("[DOWNLOAD] test_edit: No user/repo."); return b""
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: logger.error(f"[DOWNLOAD] test_edit: Repo {repo_id} not found."); return b""
        file_info = next((d for d in repo.datasets if d.dataset_type == "test"), None)
        if not file_info: logger.error(f"[DOWNLOAD] test_edit: Test dataset not found in repo {repo.id}."); return b""
        file_path = Path(data_dir) / file_info.location
        logger.debug(f"[DOWNLOAD] Serving test_edit file: {file_path}")
        if not file_path.exists(): logger.error(f"[DOWNLOAD] test_edit: File not at {file_path}."); return b""
        return str(file_path)
    
    @render.download(filename=lambda: f"repo_{selected_repo_id.get() or 'unknown'}_validation.csv")
    def download_validation_edit_modal(): # Synchronous
        user = current_user.get(); repo_id = selected_repo_id.get()
        if not user or not repo_id: logger.error("[DOWNLOAD] validation_edit: No user/repo."); return b""
        repo = db.query(Repository).filter_by(id=repo_id, user_id=user.id).first()
        if not repo: logger.error(f"[DOWNLOAD] validation_edit: Repo {repo_id} not found."); return b""
        has_analysis = any(d.dataset_type == "analysis" for d in repo.datasets)
        if not has_analysis:
            logger.warn(f"[DOWNLOAD] validation_edit: Access denied for repo {repo.id} - no analysis.")
            ui.notification_show("Validation set download requires analysis upload.", type="warning", duration=7); return b""
        file_info = next((d for d in repo.datasets if d.dataset_type == "validation"), None)
        if not file_info: logger.error(f"[DOWNLOAD] validation_edit: Validation dataset not found in repo {repo.id}."); return b""
        file_path = Path(data_dir) / file_info.location
        logger.debug(f"[DOWNLOAD] Serving validation_edit file: {file_path}")
        if not file_path.exists(): logger.error(f"[DOWNLOAD] validation_edit: File not at {file_path}."); return b""
        return str(file_path)

def register_public_downloads(db, data_dir=PROJECT_ROOT_DATA_DIR):
    @render.download(filename=lambda: f"public_repo_{selected_repo_id.get() or 'unknown'}_train.csv")
    def download_train_public(): # Synchronous, matches ID in modals.py
        repo_id = selected_repo_id.get()
        if not repo_id: 
            logger.error("[PUBLIC_DOWNLOAD] train: No repo_id selected."); 
            return b"" 
        
        repo = db.query(Repository).filter_by(id=repo_id, visibility=VisibilityEnum.PUBLIC).first()
        if not repo: 
            logger.error(f"[PUBLIC_DOWNLOAD] train: Public repo {repo_id} not found."); 
            return b""

        file_info = next((d for d in repo.datasets if d.dataset_type == "train"), None)
        if not file_info: 
            logger.error(f"[PUBLIC_DOWNLOAD] train: Train dataset not found in public repo {repo.id}."); 
            return b""
        
        file_path = Path(data_dir) / file_info.location 
        logger.debug(f"[PUBLIC_DOWNLOAD] Serving train file: {file_path}")
        if not file_path.exists(): 
            logger.error(f"[PUBLIC_DOWNLOAD] train: File not at {file_path}."); 
            return b""
        return str(file_path) 

    @render.download(filename=lambda: f"public_repo_{selected_repo_id.get() or 'unknown'}_test.csv")
    def download_test_public(): # Synchronous
        repo_id = selected_repo_id.get()
        if not repo_id: logger.error("[PUBLIC_DOWNLOAD] test: No repo_id."); return b""
        repo = db.query(Repository).filter_by(id=repo_id, visibility=VisibilityEnum.PUBLIC).first()
        if not repo: logger.error(f"[PUBLIC_DOWNLOAD] test: Public repo {repo_id} not found."); return b""
        file_info = next((d for d in repo.datasets if d.dataset_type == "test"), None)
        if not file_info: logger.error(f"[PUBLIC_DOWNLOAD] test: Test dataset not found in public repo {repo.id}."); return b""
        file_path = Path(data_dir) / file_info.location
        logger.debug(f"[PUBLIC_DOWNLOAD] Serving test file: {file_path}")
        if not file_path.exists(): logger.error(f"[PUBLIC_DOWNLOAD] test: File not at {file_path}."); return b""
        return str(file_path)
    
    @render.download(filename=lambda: f"public_repo_{selected_repo_id.get() or 'unknown'}_validation.csv")
    def download_validation_public(): # Synchronous
        repo_id = selected_repo_id.get()
        if not repo_id: logger.error("[PUBLIC_DOWNLOAD] validation: No repo_id."); return b""
        repo = db.query(Repository).filter_by(id=repo_id, visibility=VisibilityEnum.PUBLIC).first()
        if not repo: logger.error(f"[PUBLIC_DOWNLOAD] validation: Public repo {repo_id} not found."); return b""
        
        has_analysis = any(d.dataset_type == "analysis" for d in repo.datasets)
        if not has_analysis: 
            logger.warn(f"[PUBLIC_DOWNLOAD] validation: Access denied for public repo {repo.id} - no analysis.")
            ui.notification_show("Validation set for this public repository requires analysis results to be present.", type="info", duration=7); return b""
        
        file_info = next((d for d in repo.datasets if d.dataset_type == "validation"), None)
        if not file_info: logger.error(f"[PUBLIC_DOWNLOAD] validation: Validation dataset not found in public repo {repo.id}."); return b""
        file_path = Path(data_dir) / file_info.location
        logger.debug(f"[PUBLIC_DOWNLOAD] Serving validation file: {file_path}")
        if not file_path.exists(): logger.error(f"[PUBLIC_DOWNLOAD] validation: File not at {file_path}."); return b""
        return str(file_path)
