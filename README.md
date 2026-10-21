# ChatGPT-Sol-6.1-Free

A lightweight bilingual Persian/Dari and English AI chat web app, designed to deploy on Railway.

## Features
- Responsive chat interface for mobile and desktop.
- Persian/Dari and English replies, with automatic language detection.
- Gemini API key stays on the server; it is never sent to the browser.
- Health endpoint at `/health`.
- Clear error messages for missing keys, quota limits, and provider failures.

## Deploy on Railway
1. Create a Railway project from this GitHub repository.
2. In the service's **Variables**, add:
   - `GEMINI_API_KEY` = your Gemini API key (keep it private).
   - Optional: `GEMINI_MODEL` = `gemini-flash-latest`.
3. Redeploy. Railway reads `requirements.txt` and starts the web process from `Procfile`.
4. Open the generated public domain. Check `/health` if needed.

Do not commit API keys to GitHub or paste them into source code. If a key has been exposed, revoke/rotate it in the provider console and add the replacement only to Railway Variables.

## Local run
```bash
python -m pip install -r requirements.txt
export GEMINI_API_KEY="your-key"
uvicorn main:app --host 0.0.0.0 --port 8000
```

On Windows PowerShell, set the key with:
```powershell
$env:GEMINI_API_KEY="your-key"
uvicorn main:app --host 0.0.0.0 --port 8000
```

This is a starting version; provider quotas and API availability still apply.
