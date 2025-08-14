from shiny import Inputs, Outputs, Session, render, ui
from server.state import current_user, repo_refresh_trigger, selected_repo_id # Ensure repo_refresh_trigger is imported
from urllib.parse import parse_qs
from server.views import homepage_ui, scholar_dashboard_ui
from shiny import reactive, ui
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
    register_public_downloads,
    watch_delete_repo_buttons

)
from server.modals import show_repo_modal
from db.models import Repository, SessionLocal, User, VisibilityEnum # Ensure User is imported
from pathlib import Path
import asyncio
import logging # Import logging

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
    watch_delete_repo_buttons(input, db)
    
    # Register download handlers. These functions are @render.download,
    # so calling their parent registration function makes them available.
    register_static_downloads(db, PROJECT_ROOT_DATA_DIR)
    register_public_downloads(db, PROJECT_ROOT_DATA_DIR)
    watch_delete_repo_buttons(input, db)



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
        _ = repo_refresh_trigger.get()
        query_string = session.clientdata.url_search()
        params = parse_qs(query_string.lstrip('?'))
        share_token = params.get("share", [None])[0]

        return ui.page_fluid(
            # Bootstrap icons stylesheet
            ui.HTML('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">'),

            # Main content section
            ui.div(
                ui.h1("Welcome to the Repository for Predictive Theorizing", class_="display-4 fw-bold mb-4"),
                ui.p(
                    "A research data repository where scholars upload, analyze, and share datasets enabling precdictive theorizing.",
                    class_="lead text-muted"
                ),
                # Buttons Section: Get Started and Learn More
                ui.div(
                    ui.input_action_button(
                        "learn_more", 
                        ui.HTML('<i class="bi bi-info-circle me-2"></i>Learn More'), 
                        class_="btn btn-outline-secondary btn-lg hover-shadow"
                    ),
                    class_="mb-5 text-center"
                ),
                class_="text-center mt-4"
            ),

            # Column-based layout for additional features
            ui.layout_columns(
                # Upload Datasets Card
                ui.card(
                    ui.HTML('<h4 class="card-title"><i class="bi bi-upload me-2"></i>Upload Datasets</h4>'),
                    ui.p(
                        "Supports `.rda`, `.rds`, `.csv`, and `.xlsx` formats. Automatically checks for variables for cross-validation.",
                        class_="text-muted"
                    ),
                    class_="shadow-sm p-3 hover-shadow"
                ),
                # Analyze Securely Card
                ui.card(
                    ui.HTML('<h4 class="card-title"><i class="bi bi-bar-chart-line me-2"></i>Analyze Securely</h4>'),
                    ui.p(
                        "Split, validate, and inspect datasets in a controlled environment. Maintain audit trails for every step.",
                        class_="text-muted"
                    ),
                    class_="shadow-sm p-3 hover-shadow"
                ),
                # Share & Collaborate Card
                ui.card(
                    ui.HTML('<h4 class="card-title"><i class="bi bi-share me-2"></i>Share & Collaborate</h4>'),
                    ui.p(
                        "Set visibility to Private, Embargoed, or Public. Generate shareable links and collaborate with peers.",
                        class_="text-muted"
                    ),
                    class_="shadow-sm p-3 hover-shadow"
                ),
                col_widths=4,  # Equal width columns
                class_="mb-5"
            ),
            
            # Displaying shared content (from external function)
            homepage_ui(db, share_token=share_token)
        )


    @reactive.Effect
    def handle_learn_more():
        if input.learn_more():
            modal_content = ui.modal(
                ui.h4("Learn More"),
                ui.p("This repository allows researchers to securely upload, analyze, and share datasets."),
                ui.p("Key features include dataset upload, analysis tools, and flexible sharing options."),
                ui.p("Collaborate with peers by setting visibility levels to Private, Embargoed, or Public."),
                footer=ui.modal_button("Close"),
                size="m",  # Optional: specify modal size
                easy_close=True  # Optional: allow closing by clicking outside
            )
            ui.modal_show(modal_content)



    # Hover effect styles (add to custom CSS or in-line styles)
    css = """
    .hover-shadow:hover {
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1), 0 0 12px rgba(0, 0, 0, 0.1);
        transition: box-shadow 0.3s ease-in-out;
    }

    .hover-shadow {
        transition: box-shadow 0.3s ease-in-out;
    }
    """
    ui.HTML(f'<style>{css}</style>')





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