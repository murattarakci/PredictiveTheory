from shiny import ui, render
from db.models import Repository, VisibilityEnum, Dataset
from server.state import search_query, repo_refresh_trigger, selected_repo_id # Ensure repo_refresh_trigger is imported
import logging



def homepage_ui(db, share_token=None):
    if share_token:
        repo = db.query(Repository).filter_by(permalink=share_token).first()
        if not repo or repo.visibility != VisibilityEnum.PUBLIC:
            return ui.div(
                ui.h3("Public Datasets"),
                ui.p("No matching public repository found.")
            )
        public_repos = [repo]
    else:
        public_repos = db.query(Repository).filter(
            Repository.visibility == VisibilityEnum.PUBLIC
        ).order_by(Repository.created_at.desc()).all()

    if not public_repos:
        return ui.div(
            ui.h3("Public Datasets"),
            ui.p("No public datasets available at the moment.")
        )

    return ui.div(
        ui.h3("Public Datasets"),
        *[
            ui.card(
                ui.h4(repo.repo_name),
                ui.p(repo.description or "No description."),
                ui.p(f"Uploaded: {repo.created_at.strftime('%Y-%m-%d')}"),
                ui.input_action_button(f"open_repo_{repo.id}", "Download Files")
            ) for repo in public_repos
        ]
    )



def scholar_dashboard_ui(db, user):
    # The main part of the scholar dashboard UI
    # The list of repositories will be rendered by the 'filtered_cards' output UI

    @render.ui
    def filtered_cards():
        # Take a dependency on the refresh trigger.
        # Any change to repo_refresh_trigger.get() will cause this function to re-run.
        _ = repo_refresh_trigger.get()
        
        # Also take a dependency on the search query.
        query = search_query.get().strip().lower()
        
        # Fetch scholar_repos INSIDE this reactive render function
        # so it re-queries the database when the function re-runs.
        scholar_repos = db.query(Repository).filter(
            Repository.user_id == user.id
        ).order_by(Repository.created_at.desc()).all()

        logger = logging.getLogger("app_debug") # Get logger instance
        logger.debug(f"[SCHOLAR_DASHBOARD] Refreshing filtered_cards. Trigger: {repo_refresh_trigger.get()}, Query: '{query}', Found repos: {len(scholar_repos)}")

        cards = []
        if not scholar_repos and not query: # No repos and no search query
            cards.append(ui.p("You haven't created any repositories yet. Click 'Create New Repository' to get started!"))
        
        repos_to_display = []
        if query:
            repos_to_display = [
                repo for repo in scholar_repos if query in repo.repo_name.lower()
            ]
            if not repos_to_display:
                 cards.append(ui.p(f"No repositories found matching '{query}'."))
        else:
            repos_to_display = scholar_repos


        for repo in repos_to_display:
            has_analysis = any(d.dataset_type == "analysis" for d in repo.datasets)
            visibility_badge_class = {
                VisibilityEnum.PRIVATE: "bg-dark text-white",
                VisibilityEnum.EMBARGOED: "bg-warning text-dark",
                VisibilityEnum.PUBLIC: "bg-success text-white",
            }.get(repo.visibility, "bg-secondary text-white") # Default badge

            visibility_badge = ui.span(repo.visibility.name.capitalize(), class_=f"badge rounded-pill {visibility_badge_class} me-1")

            card_content = [
                ui.div(
                    visibility_badge,
                    ui.span("Has Analysis", class_="badge rounded-pill bg-info text-white") if has_analysis else None,
                    class_="mb-2"
                ),
                ui.div(repo.description or "No description provided.", class_="mb-2 text-muted"),
                ui.div(f"Created: {repo.created_at.strftime('%Y-%m-%d %H:%M')}", class_="small text-muted mb-2"),
                ui.div(
                    # Button IDs here must match those watched in handlers.py (e.g., watch_edit_repo)
                    ui.input_action_button(f"edit_repo_{repo.id}", "Edit", class_="btn btn-sm btn-outline-primary me-2"),
                    ui.input_action_button(f"upload_analysis_{repo.id}", "Upload Analysis", class_="btn btn-sm btn-outline-secondary me-2"),
                    None if has_analysis else ui.input_action_button(
                        f"upload_dataset_{repo.id}", "Re-Split Dataset", class_="btn btn-sm btn-outline-info"
                    ),
                    class_="d-flex flex-wrap gap-2"
                )
            ]
            
            card = ui.div(
                ui.card(
                    ui.card_header(ui.h5(repo.repo_name)),
                    ui.card_body(*card_content),
                    class_="mb-3 shadow-sm h-100" # h-100 for equal height cards in a row
                ),
                class_="col-md-6 col-lg-4" # Responsive column sizing
            )
            cards.append(card)
        
        if not cards and query : # If search yielded no results but there are repos
             pass # message already handled by repos_to_display check
        elif not cards and not query and scholar_repos : # Should not happen if scholar_repos is not empty
             cards.append(ui.p("Error displaying repositories."))


        return ui.div(
            ui.div(*cards, class_="row g-3") if cards else ui.p("No repositories to display based on current filter.")
        )

    return ui.div(
        ui.h3(f"Welcome, {user.username}! Your Dashboard"),
        ui.div(
            ui.input_action_button("create_repo", "Create New Repository", class_="btn btn-success"),
            class_="mb-3"
        ),
        ui.div(
            ui.input_text("repo_search", "", placeholder="Search your repositories by name...", width="100%"),
            class_="mb-3"
        ),
        ui.hr(),
        ui.output_ui("filtered_cards") # This will render the cards reactively
    )