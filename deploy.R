# ============================================================
# Deploy PredictiveTheorizing (Python Shiny) to shinyapps.io
# ============================================================
# This is a Python Shiny app, so we use rsconnect-python (CLI),
# NOT the R rsconnect package.
#
# PREREQUISITES (one-time setup):
#   pip install rsconnect-python
#
# HOW TO DEPLOY:
#   Open a terminal, cd into this project folder, then run:
#
#   Step 1 — Register credentials (only needed once per machine):
#
#     rsconnect add \
#       --account academic \
#       --name academic \
#       --token D800569686F93FD621126CE392EC5074 \
#       --secret dEIIRMOfNU7s0ASIDQ8q3SWEdBwA9QSvgntJlaav
#
#   Step 2 — Deploy the app:
#
#     rsconnect deploy shiny \
#       --name academic \
#       --title "PredictiveTheorizing" \
#       --entrypoint app:app \
#       --exclude venv \
#       --exclude .git \
#       --exclude .Rproj.user \
#       --exclude docker \
#       --exclude .DS_Store \
#       --exclude .RData \
#       --exclude .Rhistory \
#       --exclude rsconnect-python \
#       .
#
# LIVE URL:
#   https://academic.shinyapps.io/predictivetheorizing/
#
# NOTES:
#   - The --name flag refers to your shinyapps.io account name
#   - The --title flag sets the app name on shinyapps.io
#   - The --entrypoint flag points to the app object in app.py
#   - Subsequent deploys to the same title will update in place
#   - Set Dropbox env vars in the shinyapps.io dashboard if needed
# ============================================================