# ChatGPT-Sol-6.1-Free

Sol AI is a responsive bilingual Persian/Dari and English AI chat web app with PostgreSQL-backed conversation history.

## Features
- Responsive chat interface for mobile and desktop.
- Persian/Dari and English replies, with automatic language detection.
- Gemini API key stays on the server; it is never sent to the browser.
- PostgreSQL storage for conversations and messages.
- Per-browser session history, conversation list, and conversation loading/deletion API.
- Health endpoint at `/health` reports AI key and database readiness.
- If PostgreSQL is not configured yet, the app can start and answer AI requests, but chat history is not saved.

## Railway setup
Add these variables to the service when you are ready:
- `GEMINI_API_KEY`: your Google Gemini API key (keep it private).
- `DATABASE_URL`: the private or public connection URL from a PostgreSQL database.
- Optional `GEMINI_MODEL`: defaults to `gemini-flash-latest`.

Use a PostgreSQL database service and copy its connection URL into `DATABASE_URL`. The app creates the `sol_conversations` and `sol_messages` tables automatically on startup. Keep the database URL private and do not commit it to GitHub.

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
- `POST /api/chat` — generate an answer and save the newest user/assistant messages when the database is ready.
- `GET /api/conversations?session_id=<UUID>` — list this browser session's conversations.
- `GET /api/conversations/{conversation_id}?session_id=<UUID>` — load conversation messages.
- `DELETE /api/conversations/{conversation_id}?session_id=<UUID>` — delete a conversation and its messages.

Note: the current history ownership model uses an unguessable per-browser UUID, not a full user login system. Add authentication before storing sensitive personal conversations for multiple signed-in users.
