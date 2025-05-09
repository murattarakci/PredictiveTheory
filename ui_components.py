from shiny import ui

def page_layout(title: str, content_ui):
    return ui.page_fluid(
        ui.div(
            {"class": "d-flex flex-column bg-light", "style": "min-height: 100vh; font-family: 'Segoe UI', sans-serif;"},
            # Header
            ui.div(
                    {"class": "bg-dark text-white py-3 px-4 d-flex justify-content-between align-items-center shadow-sm"},
                    ui.h4(title, class_="mb-0"),
                    ui.input_action_button("logout_btn", "Logout", class_="btn btn-outline-light btn-sm")
                ),


            # Content area
            ui.div(
                {"class": "container flex-grow-1 py-4"},
                content_ui
            ),

            # Footer
            ui.div(
                {"class": "text-center text-muted small py-3 border-top mt-auto"},
                "© 2025 Your Organization. All rights reserved."
            )

        )
    )


def login_ui():
    return ui.page_fluid(
        ui.div(
            {"class": "d-flex justify-content-center align-items-center bg-light", "style": "height: 100vh"},
            ui.div(
                {"class": "card shadow-sm p-4 border-0", "style": "width: 400px;"},
                ui.h4("Secure Login", class_="text-center mb-4 text-primary"),
                ui.input_text("username", "Username", placeholder="Enter your username"),
                ui.input_password("password", "Password", placeholder="Enter your password"),
                ui.div(
                    ui.output_text("render_login_error"),
                    class_="text-danger small mt-2"
                ),
                ui.input_action_button("login_btn", "Login", class_="btn btn-primary w-100 mt-3")
            )
        )
    )


def scholar_dashboard(username):
    return page_layout(
        title=f"Welcome, {username} (Scholar)",
        content_ui=ui.div(
            {"class": "row g-4"},
            
            # Upload Section
            ui.div(
                {"class": "col-12"},
                ui.card(
                    ui.div(
                        {"class": "p-4"},
                        ui.h5("Upload Dataset", class_="mb-4 text-center text-primary fw-semibold"),

                        # Repository Name
                        ui.div({"class": "mb-3 row"},
                            ui.tags.label("Repository Name", {"class": "col-5 col-form-label text-end fw-semibold"}),
                            ui.div({"class": "col-7"}, ui.input_text("repo_name", "", placeholder="e.g. my_study"))
                        ),

                        # Description textarea
                        ui.div({"class": "mb-3 row"},
                            ui.tags.label("Description", {"class": "col-5 col-form-label text-end fw-semibold"}),
                            ui.div({"class": "col-7"},
                                ui.input_text_area("repo_description", "", rows=3, placeholder="Write a short description about this repository")
                            )
                        ),
                        # # Public checkbox
                        # ui.div({"class": "mb-3 row"},
                        #     ui.tags.label("Make Public?", {"class": "col-5 col-form-label text-end fw-semibold"}),
                        #     ui.div({"class": "col-7 d-flex align-items-center"}, ui.input_checkbox("make_public", ""))
                        # ),
                        ui.div(
                            {"style": "display: none;"},
                            ui.input_checkbox("make_public", "", value=False)
                        ),

                        # File Upload
                        ui.div({"class": "mb-3 row"},
                            ui.tags.label("Upload File", {"class": "col-5 col-form-label text-end fw-semibold"}),
                            ui.div({"class": "col-7"}, ui.input_file("dataset_upload", "", accept=[".dta", ".rds"]))
                        ),

                        # Data Split
                        ui.div({"class": "mb-3 row"},
                            ui.tags.label("Data Split", {"class": "col-5 col-form-label text-end fw-semibold"}),
                            ui.div({"class": "col-7"},
                                ui.input_radio_buttons(
                                    "split_preset",
                                    "",
                                    choices=["60/20/20", "70/15/15", "80/10/10"],
                                    selected="60/20/20"
                                ),
                                ui.div({"class": "form-text"}, "Train / Test / Validation %")
                            )
                        ),

                        # Process Button
                        ui.div({"class": "mt-4 d-flex justify-content-center"},
                            ui.input_action_button("process_btn", "Process Dataset", class_="btn btn-primary w-50")
                        ),

                        # Status Message
                        ui.div({"class": "text-success mt-3 text-center fw-semibold"}, ui.output_text("upload_status"))
                    )
                )
            ),

            # Repositories Section
            ui.div(
                {"class": "col-12"},
                ui.card(
                    ui.div(
                        {"class": "p-4"},
                        ui.h5("Your Repositories", class_="mb-3 text-primary"),
                        ui.output_ui("scholar_repo_list")
                    )
                )
            )
        )
    )


def peer_dashboard(username):
    return page_layout(
        title=f"Welcome, {username} (Peer)",
        content_ui=ui.div(
            ui.card(
                ui.div(
                    {"class": "p-4"},
                    ui.h5("Public Repositories", class_="mb-3 text-primary"),
                    ui.output_ui("peer_repo_list")
                )
            )
        )
    )


def main_ui():
    return ui.page_fluid(
        ui.output_ui("main_ui_render"),
        ui.output_ui("file_modal")
    )
