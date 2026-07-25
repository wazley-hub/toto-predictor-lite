TOTO PREDICTOR LITE
===================

App ini berasingan daripada Rumah A Predictor.

Kandungan:
- Keputusan terbaru (read-only)
- Input Top 3 dan butang Generate
- Bridge V1
- Bridge Pair Shortlist (Bridge V1 sahaja)

Keselamatan:
- Tiada upload fail
- History Manager hanya menulis ke wazley-hub/toto-predictor-lite
- Kemas kini dilindungi kata laluan
- Token GitHub disimpan dalam Streamlit Secrets, bukan dalam kod
- Tiada akses tulis kepada repo Rumah A Predictor

STREAMLIT SECRETS
=================

Di Streamlit: Manage app > Settings > Secrets

LITE_GITHUB_TOKEN = "token fine-grained untuk repo toto-predictor-lite"
LITE_UPDATE_PASSWORD = "kata laluan yang diberikan kepada pengguna"

Deploy sebagai projek Streamlit yang berasingan menggunakan app.py.
