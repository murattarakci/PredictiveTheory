from shiny import reactive

current_user = reactive.Value(None)
selected_repo_id = reactive.Value(None)
search_query = reactive.Value("")

show_modal = reactive.Value(False)
selected_repo_files = reactive.Value([])
selected_repo_name = reactive.Value("")
repo_refresh_trigger = reactive.Value(0)
upload_success = reactive.Value("")
upload_analysis_success = reactive.Value("")
handled_clicks = reactive.Value(set())

def reset_app_state():
    current_user.set(None)
    selected_repo_id.set(None)
    search_query.set("")
    show_modal.set(False)
    selected_repo_files.set([])
    selected_repo_name.set("")
    repo_refresh_trigger.set(0)
    upload_success.set("")
    upload_analysis_success.set("")
    handled_clicks.set(set())

def clear_handled_click(btn_id):
    updated = set(handled_clicks.get())
    updated.discard(btn_id)
    handled_clicks.set(updated)