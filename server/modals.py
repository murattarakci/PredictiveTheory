from shiny import ui, reactive
from server.state import selected_repo_id, repo_refresh_trigger # Ensure repo_refresh_trigger is imported
from db.models import Repository, Dataset, VisibilityEnum
import logging # Import logging

logger = logging.getLogger("app_debug") # Get logger instance

def show_repo_modal(input, db, data_dir): # data_dir might not be needed here if paths are absolute or handled by download handlers

    @reactive.effect
    def _watch_public_repo_clicks():
        # Add dependency on the refresh trigger
        _ = repo_refresh_trigger.get()
        logger.debug(f"[SHOW_REPO_MODAL] Watching public repo clicks. Trigger: {repo_refresh_trigger.get()}")

        # Fetch the current list of public repositories
        # This query now re-runs when repo_refresh_trigger changes.
        public_repos = db.query(Repository).filter(
            Repository.visibility == VisibilityEnum.PUBLIC
        ).all()

        for repo in public_repos:
            btn_id = f"open_repo_{repo.id}" # This ID comes from views.py homepage_ui
            try:
                if input[btn_id]() > 0: # Check if button was clicked
                    # This simple check might lead to modal re-opening if not handled carefully.
                    # Using handled_clicks or last_vals pattern might be needed if re-opening is an issue.
                    # For now, assume simple click detection.
                    logger.debug(f"[SHOW_REPO_MODAL] Button {btn_id} for public repo {repo.id} clicked.")
                    selected_repo_id.set(repo.id) # Set for download handlers

                    datasets = db.query(Dataset).filter(
                        Dataset.repository_id == repo.id
                    ).all()

                    has_analysis = any(d.dataset_type == "analysis" for d in datasets)
                    has_train = any(d.dataset_type == "train" for d in datasets)
                    has_test = any(d.dataset_type == "test" for d in datasets)
                    has_validation = any(d.dataset_type == "validation" for d in datasets)

                    buttons = []
                    if has_train:
                        buttons.append(
                            ui.download_button("download_train_public", "Download Train CSV", class_="btn btn-sm btn-outline-success me-2")
                        )
                    if has_test:
                        buttons.append(
                            ui.download_button("download_test_public", "Download Test CSV", class_="btn btn-sm btn-outline-success me-2")
                        )
                    if has_validation and has_analysis: # Validation only if analysis exists
                        buttons.append(
                            ui.download_button("download_validation_public", "Download Validation CSV", class_="btn btn-sm btn-outline-success me-2")
                        )
                    if has_analysis:
                        buttons.append(
                            ui.download_button("download_analysis_public", "Download Analysis", class_="btn btn-sm btn-outline-success me-2")
                        )
                    
                    if not buttons:
                        buttons.append(ui.p("No downloadable files currently available for this public repository.", class_="text-muted"))

                    ui.modal_show(
                        ui.modal(
                            ui.h4(f"Download Files for '{repo.repo_name}'"),
                            ui.tags.hr(),
                            ui.div(*buttons, class_="d-flex flex-wrap justify-content-center gap-2 px-3"),
                            title="Available Public Files",
                            easy_close=True,
                            footer=ui.modal_button("Dismiss", class_="btn btn-secondary")
                        )
                    )
                    # Break after showing one modal to prevent multiple from opening if events fire rapidly
                    break 
            except KeyError: # Button might not exist if UI is still rendering
                # logger.debug(f"[SHOW_REPO_MODAL] Button {btn_id} not found in input for repo {repo.id}")
                continue
            except Exception as e:
                logger.error(f"[SHOW_REPO_MODAL] Error for repo {repo.id}, button {btn_id}: {e}", exc_info=True)
