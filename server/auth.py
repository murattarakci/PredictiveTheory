from shiny import ui, reactive
from db.models import User
from sqlalchemy.orm.exc import NoResultFound

current_user = reactive.Value(None)

def login_modals(input, db):
    @reactive.effect
    @reactive.event(input.login_btn)
    def show_login_modal():
        ui.modal_show(
            ui.modal(
                ui.input_text("username", "Username:"),
                ui.input_password("password", "Password:"),
                ui.input_action_button("submit_login", "Login"),
                title="Scholar Login",
                easy_close=True,
                footer=None
            )
        )

    @reactive.effect
    @reactive.event(input.submit_login)
    def process_login():
        username = input.username()
        password = input.password()
        try:
            user = db.query(User).filter_by(username=username, password_hash=password).one()
            if user.role == 'scholar':
                current_user.set(user)
                ui.modal_remove()
                ui.notification_show("Login successful.", type="message")
            else:
                ui.modal_remove()
                ui.notification_show("Access denied: Not a scholar.", type="error")
        except NoResultFound:
            ui.modal_remove()
            ui.notification_show("Invalid credentials.", type="error")

    return current_user
