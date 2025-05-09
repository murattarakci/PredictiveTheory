
from pathlib import Path
from shiny import App
from ui_components import main_ui
from handlers import server


data_dir = Path(__file__).parent / "data"
app = App(ui=main_ui(), server=server, static_assets=data_dir)