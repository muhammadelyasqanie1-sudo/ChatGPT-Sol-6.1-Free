# AFG AI — هوش مصنوعی افغانستان

AFG AI (هوش مصنوعی افغانستان) is a responsive bilingual Persian/Dari and English AI chat web app with PostgreSQL-backed conversation history.

## Features
- Responsive chat interface for mobile and desktop.
- Persian/Dari and English replies, with automatic language detection.
- Gemini API key stays on the server; it is never sent to the browser.
- PostgreSQL storage for conversations and messages.
- Per-browser session history, conversation list, and conversation loading/deletion API.
- Health endpoint at `/health` reports AI key, database, file-analysis, and web-search readiness.
- Document analysis for TXT, Markdown, CSV, JSON, LOG, PDF, and DOCX files (8 MB upload limit; extracted text is capped).
- Optional web search through Tavily, with source URLs included for the assistant.
- Copy assistant replies and export the current conversation as a text file.
- If PostgreSQL is not configured yet, the app can start and answer AI requests, but chat history is not saved.

## Railway setup
Add these variables to the service when you are ready:
- `GEMINI_API_KEY`: your Google Gemini API key (keep it private).
- `DATABASE_URL`: the private or public connection URL from a PostgreSQL database.
- Optional `GEMINI_MODEL`: defaults to `gemini-flash-latest`.
- Optional `TAVILY_API_KEY`: enables the web-search checkbox. Without it, normal chat and file analysis remain available.

Use a PostgreSQL database service and copy its connection URL into `DATABASE_URL`. The app creates the `sol_conversations` and `sol_messages` tables automatically on startup. File analysis supports TXT, MD, CSV, JSON, LOG, PDF, and DOCX; scanned PDFs may require OCR and are not automatically OCR-processed. Keep the database URL private and do not commit it to GitHub.

The web process is started by `Procfile` using the platform's `PORT`. After deployment, open `/health` to view whether the database is configured and ready.

## Local run
```bash
python -m pip install -r requirements.txt
export GEMINI_API_KEY="your-key"
export DATABASE_URL="postgresql://user:password@localhost:5432/solai"
uvicorn main:app --host 0.0.0.0 --port 8000
```

On Windows PowerShell:
```powershell
$env:GEMINI_API_KEY="your-key"
$env:DATABASE_URL="postgresql://user:password@localhost:5432/solai"
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API overview
- `GET /health` — app, AI key, and database status.
- `POST /api/chat` — generate an answer; optionally add web search with `web_search: true` when `TAVILY_API_KEY` is configured.
- `POST /api/analyze-file` — analyze an uploaded supported document.
- `GET /api/conversations?session_id=<UUID>` — list this browser session's conversations.
- `GET /api/conversations/{conversation_id}?session_id=<UUID>` — load conversation messages.
- `DELETE /api/conversations/{conversation_id}?session_id=<UUID>` — delete a conversation and its messages.

Note: the current history ownership model uses an unguessable per-browser UUID, not a full user login system. Add authentication before storing sensitive personal conversations for multiple signed-in users.


## نام و هویت برند
- Brand name: **AFG AI**
- فارسی/دری: **AFG AI — هوش مصنوعی افغانستان**
- Tagline: **هوش مصنوعی افغانستان، برای همه | Afghanistan's AI, for everyone**


## Pro++ tools and configuration
- Add `GEMINI_API_KEY` to enable AI replies. The app does not embed keys in browser code.
- Add `DATABASE_URL` to persist conversation history.
- Add `TAVILY_API_KEY` only if you want the optional web-search tool. Search is not available until this key is configured.
- The UI includes file analysis, copy-to-clipboard for assistant replies, and plain-text conversation export.
- No authentication/login system is included yet; browser-session UUIDs are not a substitute for user accounts. Do not use this as a secure multi-user private workspace until authentication and authorization are implemented.
- These repository updates were made without running tests, as requested.
