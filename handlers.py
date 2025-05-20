import asyncio
import os
import pandas as pd
import pyreadr
from pathlib import Path
from shiny import reactive, render, ui
from db import get_db
from db.models import User, Repository, Dataset, AccessLog
from sklearn.model_selection import train_test_split
from ui_components import login_ui, scholar_dashboard, peer_dashboard

current_user = reactive.Value(None)
login_error_msg = reactive.Value("")
upload_success = reactive.Value("")
upload_analysis_success = reactive.Value("")
uploaded_files = reactive.Value([])
selected_repo_id = reactive.Value(None)
show_modal = reactive.Value(False)
selected_repo_files = reactive.Value([])
selected_repo_name = reactive.Value("")
repo_refresh_trigger = reactive.Value(0)
show_login_ui = reactive.Value(False)


data_dir = Path(__file__).parent / "data"


def server(input, output, session):

    @reactive.Effect
    def login_handler():
        if input.login_btn() > 0:
            username = input.username().strip()
            password = input.password().strip()

            if not username or not password:
                login_error_msg.set("Username and password are required.")
                return

            db = next(get_db())
            user = db.query(User).filter_by(username=username).first()

            if user:
                if user.password_hash != password:
                    login_error_msg.set("Incorrect password.")
                    return

                # Login based on role
                current_user.set({
                    "id": user.id,
                    "username": user.username,
                    "role": user.role
                })
                login_error_msg.set("")
            else:
                # User not found — create new peer
                new_user = User(
                    username=username,
                    password_hash=password,
                    role="peer"
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)

                current_user.set({
                    "id": new_user.id,
                    "username": new_user.username,
                    "role": new_user.role
                })
            show_login_ui.set(False)

            login_error_msg.set("")


    @reactive.Effect
    def logout_handler():
        if input.logout_btn() > 0:
            current_user.set(None)

    @output
    @render.text
    def render_login_error():
        return login_error_msg()

    @output
    @render.text
    def upload_status():
        return upload_success()

    @reactive.Effect
    @reactive.event(input.process_btn)
    async def process_dataset():
        user = current_user()
        files = input.dataset_upload()
        repo_name = input.repo_name()
        is_public = input.make_public()
        description = input.repo_description()

        if not files or len(files) == 0 or not repo_name:
            upload_success.set("Please upload a dataset and enter a repository name.")
            return

        file = files[0]
        ext = Path(file["name"]).suffix.lower()
        temp_path = file["datapath"]

        try:
            with ui.Progress(min=0, max=100) as p:
                p.set(10, message="Reading dataset")
                await asyncio.sleep(0.1)

                if ext == ".dta":
                    df = pd.read_stata(temp_path)
                elif ext == ".rds":
                    result = pyreadr.read_r(temp_path)
                    df = result[None]
                else:
                    upload_success.set("Unsupported file format.")
                    return

                if df.empty:
                    upload_success.set("The uploaded dataset is empty.")
                    return

                preset = input.split_preset()
                preset_map = {
                    "60% Train / 20% Test / 20% Validation": (0.6, 0.2),
                    "70% Train / 15% Test / 15% Validation": (0.7, 0.15),
                    "80% Train / 10% Test / 10% Validation": (0.8, 0.1)
                }
                train_pct, test_pct = preset_map.get(preset, (0.6, 0.2))
                valid_pct = 1.0 - train_pct - test_pct

                p.set(30, message="Splitting dataset")
                await asyncio.sleep(0.1)

                train, temp = train_test_split(df, train_size=train_pct, random_state=42)
                test, valid = train_test_split(temp, test_size=test_pct / (test_pct + valid_pct), random_state=42)

                p.set(50, message="Saving dataset")
                await asyncio.sleep(0.1)

                save_dir = Path("data") / user["username"] / repo_name
                save_dir.mkdir(parents=True, exist_ok=True)
                train.to_csv(save_dir / "train.csv", index=False)
                test.to_csv(save_dir / "test.csv", index=False)
                valid.to_csv(save_dir / "validation.csv", index=False)

                p.set(70, message="Saving metadata to database")
                await asyncio.sleep(0.1)

                db = next(get_db())
                repo = Repository(user_id=user["id"], repo_name=repo_name, description=description, is_public=is_public)
                db.add(repo)
                db.commit()
                db.refresh(repo)

                for dtype, fname in [("train", "train.csv"), ("test", "test.csv"), ("validation", "validation.csv")]:
                    db.add(Dataset(repository_id=repo.id, dataset_type=dtype, location=str(save_dir / fname)))

                db.add(AccessLog(user_id=user["id"], repository_id=repo.id, action="upload"))
                db.commit()

                p.set(100, message="Complete")
                upload_success.set("Dataset processed and saved successfully.")
                repo_refresh_trigger.set(repo_refresh_trigger() + 1)

        except Exception as e:
            upload_success.set(f"Error during processing: {e}")

    @output
    @render.ui
    def file_list_display():
        files = uploaded_files()
        if not files:
            return ui.p("No files yet.")
        return ui.panel_well(
            ui.h4(""),
            ui.tags.ul([ui.tags.li(f) for f in files])
        )

    @output
    @render.ui
    def main_ui_render():
        user = current_user()
        if user and user["role"] == "scholar":
            return scholar_dashboard(user["username"])
        elif show_login_ui():
            return login_ui()
        else:
            return ui.div(
                ui.h3("Public Repositories"),
                ui.output_ui("peer_repo_list"),
                ui.hr(),
                ui.input_action_button("show_login_btn", "Login as Scholar", class_="btn btn-primary")
        )
        
    @reactive.Effect
    def handle_show_login():
     if input.show_login_btn() > 0:
        show_login_ui.set(True)

    @output
    @render.ui
    def scholar_repo_list():
        _ = repo_refresh_trigger()
        user = current_user()
        if not user:
            return None

        db = next(get_db())
        repos = db.query(Repository).filter_by(user_id=user["id"]).order_by(Repository.created_at.desc()).all()

        for repo in repos:
            create_repo_select_effect(repo.id)

        return ui.panel_well(
            ui.h4(""),
            *[ui.input_action_button(f"select_repo_{repo.id}", f"{repo.repo_name} {'- Public Repository' if repo.is_public else ''}") for repo in repos]
        )

    def create_repo_select_effect(repo_id):
        @reactive.Effect
        def _():
            if input[f"select_repo_{repo_id}"]() > 0:
                db = next(get_db())
                repo = db.query(Repository).filter_by(id=repo_id).first()
                if repo:
                    repo_dir = Path("data") / repo.owner.username / repo.repo_name
                    file_list = []
                    if repo_dir.exists():
                        for f in repo_dir.glob("*.csv"):
                            try:
                                rel_path = f.resolve().relative_to(data_dir.resolve())
                                file_list.append(str(rel_path))
                            except ValueError:
                                file_list.append(f.name)

                    has_analysis = any(d.dataset_type == "analysis" for d in repo.datasets)
                    selected_repo_files.set((file_list, has_analysis, repo.user_id, repo.description))
                    session.send_input_message("public_toggle_modal", {"value": repo.is_public})
                    selected_repo_name.set(repo.repo_name)
                    show_modal.set(True)



    @output
    @render.ui
    def selected_repo_detail():
        repo_id = selected_repo_id()
        if not repo_id:
            return None

        db = next(get_db())
        repo = db.query(Repository).filter_by(id=repo_id).first()
        if not repo:
            return ui.p("Repository not found.")

        has_analysis = any(d.dataset_type == "analysis" for d in repo.datasets)

        repo_dir = Path("data") / repo.owner.username / repo.repo_name
        file_list = list(repo_dir.glob("*.csv")) if repo_dir.exists() else []

        def download_link(file):
            try:
                rel_path = file.resolve().relative_to(data_dir.resolve())
            except ValueError:
                rel_path = file.name

            if not has_analysis and file.name == "validation.csv":
                return ui.tags.li(f"{file.name} (locked until analysis uploaded)")
            return ui.tags.li(ui.tags.a(file.name, href=f"/{rel_path}", download=file.name))

        controls = []
        user = current_user()
        if user and user["id"] == repo.user_id:
            controls.extend([
                ui.hr(),
                ui.input_checkbox("public_toggle", "Make Repository Public", value=repo.is_public),
                ui.input_action_button("save_public_toggle", "Save Changes"),
                ui.input_file("analysis_upload", "Upload Analysis File", accept=[".csv", ".xlsx"]),
                ui.input_action_button("upload_analysis_btn", "Upload Analysis")
            ])

        return ui.panel_well(
            ui.h4(f"Repository: {repo.repo_name}"),
            ui.p(repo.description or "No description provided.", class_="text-muted fst-italic"),
            ui.tags.ul([download_link(f) for f in file_list]),
            *controls
        )

    @reactive.Effect
    @reactive.event(input.save_public_toggle)
    def update_repo_visibility():
        repo_id = selected_repo_id()
        if not repo_id:
            return

        db = next(get_db())
        repo = db.query(Repository).filter_by(id=repo_id).first()
        if repo:
            repo.is_public = input.public_toggle()
            db.commit()

    @reactive.Effect
    @reactive.event(input.upload_analysis_btn)
    def handle_analysis_upload():
        repo_id = selected_repo_id()
        user = current_user()
        files = input.analysis_upload()

        if not repo_id or not user or not files:
            upload_analysis_success.set("Missing required data.")
            return

        db = next(get_db())
        repo = db.query(Repository).filter_by(id=repo_id).first()

        if not repo:
            upload_analysis_success.set("Repository not found.")
            return

        file = files[0]
        ext = Path(file["name"]).suffix.lower()
        save_dir = Path("data") / user["username"] / repo.repo_name
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"analysis{ext}"
        os.rename(file["datapath"], save_path)

        db.add(Dataset(repository_id=repo_id, dataset_type="analysis", location=str(save_path)))
        db.commit()

        upload_analysis_success.set("Analysis uploaded successfully. Validation set unlocked.")

    @output
    @render.ui
    def peer_repo_list():
        db = next(get_db())
        repos = db.query(Repository).filter_by(is_public=True).order_by(Repository.created_at.desc()).all()

        if not repos:
            return ui.p("No public repositories available.")

        for repo in repos:
            create_peer_repo_select_effect(repo.id)

        return ui.panel_well(
            ui.h4(""),
            *[
                ui.input_action_button(
                    f"peer_select_repo_{repo.id}",
                    f"{repo.repo_name} — by {repo.owner.username}"
                ) for repo in repos
            ]
        )
    def create_peer_repo_select_effect(repo_id):
        @reactive.Effect
        def _():
            if input[f"peer_select_repo_{repo_id}"]() > 0:
                db = next(get_db())
                repo = db.query(Repository).filter_by(id=repo_id).first()
                if repo:
                    repo_dir = Path("data") / repo.owner.username / repo.repo_name
                    file_list = []
                    if repo_dir.exists():
                        for f in repo_dir.glob("*.csv"):
                            try:
                                rel_path = f.resolve().relative_to(data_dir.resolve())
                                file_list.append(str(rel_path))
                            except ValueError:
                                file_list.append(f.name)

                    has_analysis = any(d.dataset_type == "analysis" for d in repo.datasets)
                    selected_repo_files.set((file_list, has_analysis, repo.user_id, repo.description))
                    selected_repo_name.set(repo.repo_name)
                    show_modal.set(True)



    @output
    @render.ui
    def file_modal():
        if not show_modal():
            return None

        user = current_user()
        repo_name = selected_repo_name()

        try:
            files, has_analysis, owner_id, description = selected_repo_files()
        except ValueError:
            return ui.div("Error: File modal data malformed.")

        def render_file(f):
            fname = Path(f).name
            is_owner = user and user["id"] == owner_id

            if fname == "validation.csv" and not has_analysis:
                return ui.tags.li(f"{fname} (locked until analysis uploaded)")
            if fname == "validation.csv" and not is_owner:
                return ui.tags.li(f"{fname} (only available after analysis)")
            return ui.tags.li(ui.tags.a(fname, href=f"/{f}", download=fname))

        return ui.div(
            {"style": "position:fixed; top:10%; left:10%; width:80%; height:60%; background:white; z-index:9999; padding:20px; border:2px solid #ccc; box-shadow:0 4px 8px rgba(0,0,0,0.2); overflow:auto"},
            ui.h4(f"Files in {repo_name}"),
            ui.p(description or "No description provided.", class_="text-muted fst-italic"),
            ui.tags.ul([render_file(f) for f in files]),
            *([
                ui.hr(),
                *((
                    ui.input_checkbox("public_toggle_modal", "Make Repository Public", value=False),
                    ui.input_action_button("save_public_toggle_modal", "Save Changes"),
                    ui.hr()
                ) if has_analysis else ()),
                ui.input_file("analysis_upload_modal", "Upload Analysis File", accept=[".csv", ".xlsx"]),
                ui.input_action_button("upload_analysis_modal_btn", "Upload Analysis"),
                ui.output_text("upload_analysis_modal")
            ] if user and user["id"] == owner_id else []),
                        ui.input_action_button("close_modal_btn", "Close", class_="btn btn-secondary mt-3")


                    )
    @output
    @render.text
    def upload_analysis_modal():
        return upload_analysis_success()
    @reactive.Effect
    @reactive.event(input.close_modal_btn)
    def close_modal():
        show_modal.set(False)

    @reactive.Effect
    @reactive.event(input.upload_analysis_modal_btn)
    def upload_analysis_from_modal():
        user = current_user()
        try:
            files, _, owner_id, _ = selected_repo_files()
            repo_name = selected_repo_name()
        except Exception:
            upload_analysis_success.set("Upload failed: context missing.")
            return

        if not user or user["id"] != owner_id:
            upload_analysis_success.set("Unauthorized.")
            return

        files_uploaded = input.analysis_upload_modal()
        if not files_uploaded:
            upload_analysis_success.set("No file uploaded.")
            return

        file = files_uploaded[0]
        ext = Path(file["name"]).suffix.lower()
        save_dir = Path("data") / user["username"] / repo_name
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"analysis{ext}"

        os.rename(file["datapath"], save_path)

        db = next(get_db())
        repo = db.query(Repository).filter_by(user_id=user["id"], repo_name=repo_name).first()
        if not repo:
            upload_analysis_success.set("Repository not found.")
            return

        db.add(Dataset(repository_id=repo.id, dataset_type="analysis", location=str(save_path)))
        db.commit()

        upload_analysis_success.set("Analysis uploaded successfully.")

    @reactive.Effect
    @reactive.event(input.save_public_toggle_modal)
    def save_repo_public_flag():
        user = current_user()
        repo_name = selected_repo_name()

        if not user or not repo_name:
            return

        db = next(get_db())
        repo = db.query(Repository).filter_by(user_id=user["id"], repo_name=repo_name).first()
        if not repo:
            return

        repo.is_public = input.public_toggle_modal()
        db.commit()