from shiny import ui
from shinyswatch import theme

app_ui = ui.page_navbar(
    # --- Start of Positional Arguments (*args) for page_navbar ---
    # These are the main content items for the navbar: tabs, spacers, controls.

    ui.nav_panel("Public Datasets", ui.output_ui("homepage_content_ui")),
    ui.nav_panel("My Dashboard", ui.output_ui("dashboard_content_ui")),

    # ui.nav_spacer() is a positional argument. It attempts to push subsequent items.
    ui.nav_spacer(),

    # ui.nav_control() is a positional argument. It's for adding individual controls.
    # The content of the nav_control is your login button UI.
    ui.nav_control(
        ui.output_ui("login_status_ui")
        # Note: We cannot directly add class_="ms-auto" to ui.nav_control itself.
        # If this doesn't align right, we'll need to wrap ui.output_ui inside it
        # with a div that has ms-auto, or use CSS.
    ),
    # --- End of Positional Arguments (*args) ---

    # --- Start of Keyword Arguments for page_navbar ---
    # All keyword arguments MUST come after ALL positional arguments.
    title="Predictive Theorizing",    # Keyword argument for the main title/brand
    theme=theme.flatly,         # Keyword argument for the theme
    # position="fixed-top",     # Optional keyword argument
    # id="main_navbar"          # Optional keyword argument
    # --- End of Keyword Arguments ---
)
