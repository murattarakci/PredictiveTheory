from shiny import Inputs, Outputs, Session, render, ui
from server.state import current_user, repo_refresh_trigger # Ensure repo_refresh_trigger is imported
from server.views import homepage_ui, scholar_dashboard_ui
from server.handlers import (
    login_handler,
    logout_handler,
    repo_creation_handler,
    upload_split_handler, # This is async
    upload_analysis_handler, # This is async
    watch_edit_repo,
    handle_submit_repo_edit,
    watch_repo_search,
    register_static_downloads,
    register_public_downloads
)
from server.modals import show_repo_modal
from db.models import SessionLocal, User # Ensure User is imported
from pathlib import Path
import asyncio
import logging # Import logging

# Define the data directory path.
# Assuming 'data' is at the project root (same level as app.py)
# and this main.py is inside a 'server' directory.
PROJECT_ROOT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
logger = logging.getLogger("app_debug") # Get logger instance for main server if needed

def server(input: Inputs, output: Outputs, session: Session):
    db = SessionLocal() # Create a new session for each user session/request
    
    # Ensure data directory exists at the start of the server function
    PROJECT_ROOT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Wire all handlers
    login_handler(input, db)
    logout_handler(input)
    
    # Schedule async handlers
    asyncio.create_task(repo_creation_handler(input, db, session))
    asyncio.create_task(upload_split_handler(input, db, data_dir=PROJECT_ROOT_DATA_DIR))
    asyncio.create_task(upload_analysis_handler(input, db, data_dir=PROJECT_ROOT_DATA_DIR))
    
    # Synchronous handlers (or handlers that manage their own async if needed)
    # Assuming show_repo_modal is synchronous. If it becomes async, it also needs asyncio.create_task
    show_repo_modal(input, db, PROJECT_ROOT_DATA_DIR) # Pass data_dir if modals.py uses it
    
    watch_edit_repo(input, db) # This contains a nested @render.ui, which is fine
    handle_submit_repo_edit(input, db)
    watch_repo_search(input)
    
    # Register download handlers. These functions are @render.download,
    # so calling their parent registration function makes them available.
    register_static_downloads(db, PROJECT_ROOT_DATA_DIR)
    register_public_downloads(db, PROJECT_ROOT_DATA_DIR)


    @render.ui
    def login_status_ui():
        """
        Renders the login/logout button in the navbar header.
        This is for the ui.output_ui("login_status_ui") in ui_layout.py
        """
        user = current_user.get()
        if user:
            # Display username and make logout button smaller and styled for navbar
            return ui.input_action_button("logout_btn", f"Logout ({user.username})", class_="btn-sm btn-outline-light")
        else:
            # This ID "login_main_btn" is what the modified handlers.py expects
            return ui.input_action_button("login_main_btn", "Login", class_="btn-sm btn-light")

    @render.ui
    def homepage_content_ui():
        """
        Renders the content for the 'Public Datasets' nav panel.
        This now depends on repo_refresh_trigger to update when repo visibility changes.
        """
        _ = repo_refresh_trigger.get() # Establish reactive dependency
        logger.debug(f"[HOMEPAGE_UI_REFRESH] Trigger value: {repo_refresh_trigger.get()}")
        return homepage_ui(db)

    @render.ui
    def dashboard_content_ui():
        """
        Renders the content for the 'My Dashboard' nav panel.
        This is for the ui.output_ui("dashboard_content_ui") in ui_layout.py
        Shows scholar dashboard if a scholar is logged in.
        Shows a peer-specific message if a peer is logged in.
        Shows a generic login prompt otherwise.
        """
        user = current_user.get()
        if user:
            if user.role == 'scholar':
                return scholar_dashboard_ui(db, user)
            elif user.role == 'peer':
                # You can customize this further if peers should have a different view
                return ui.div(
                    ui.h4(f"Welcome, {user.username} (Peer)"),
                    ui.p("You can browse public datasets. Scholars have access to additional repository management features."),
                    class_="container mt-4" # Basic styling for the message
                )
        # If no user, or user role is not explicitly handled for a special dashboard
        return ui.div(
            ui.p("Please log in to access personalized content or scholar features."),
            class_="container mt-4" # Basic styling for the message
        )
