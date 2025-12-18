# Mobile Caregiving Backend

Backend for the Mobile Caregiving and Monitoring System.

Overview:
- Framework: FastAPI
- Auth: Firebase Authentication (frontend handles login)
- Database: Firestore
- ML: Training code lives under `ml/`; backend only loads trained artifacts for inference.

Project layout follows clean architecture and keeps ML training code strictly separated from API code.

Quick start (development):

1. Create a virtual environment and install backend deps:

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

2. Set `FIREBASE_CREDENTIALS` in `.env` or environment to point to your service account JSON.

3. Run the API:

```bash
uvicorn app.main:app --reload
```

ML developers:
- Place training code under `ml/` and write artifacts to `ml/trained_models/`.
- Do NOT import training modules into the `app/` package.
