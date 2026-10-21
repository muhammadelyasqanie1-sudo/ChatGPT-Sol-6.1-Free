import os
import uuid
from contextlib import asynccontextmanager
from typing import Literal

import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

APP_NAME = "Sol AI"
MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

DB_READY = False


async def db_connect():
    if not DATABASE_URL or not DB_READY:
        raise HTTPException(status_code=503, detail="Database is not ready. Add a PostgreSQL DATABASE_URL in your hosting environment.")
    return await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=8)


async def initialize_database():
    global DB_READY
    if not DATABASE_URL:
        print("DATABASE_URL is not configured; chat works without saved history.")
        return
    try:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=8) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sol_conversations (
                    id UUID PRIMARY KEY,
                    session_id UUID NOT NULL,
                    title TEXT NOT NULL DEFAULT 'گفتگوی تازه',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS sol_conversations_session_updated
                ON sol_conversations (session_id, updated_at DESC)
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sol_messages (
                    id BIGSERIAL PRIMARY KEY,
                    conversation_id UUID NOT NULL REFERENCES sol_conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS sol_messages_conversation_created
                ON sol_messages (conversation_id, created_at, id)
            """)
            await conn.commit()
        DB_READY = True
        print("PostgreSQL database schema is ready.")
    except Exception as exc:
        DB_READY = False
        print(f"Database initialization failed: {type(exc).__name__}: {str(exc)[:300]}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_database()
    yield


app = FastAPI(title=APP_NAME, version="2.0.0", lifespan=lifespan)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    language: Literal["auto", "fa", "en"] = "auto"
    session_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None


class HistoryRequest(BaseModel):
    session_id: uuid.UUID


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": APP_NAME,
        "model": MODEL,
        "api_key_configured": bool(API_KEY),
        "database_configured": bool(DATABASE_URL),
        "database_ready": DB_READY,
    }


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(PAGE)


@app.post("/api/conversations")
async def create_conversation(payload: HistoryRequest):
    async with await db_connect() as conn:
        row = await (await conn.execute(
            "INSERT INTO sol_conversations (id, session_id, title) VALUES (%s, %s, %s) RETURNING id, title, created_at, updated_at",
            (uuid.uuid4(), payload.session_id, "گفتگوی تازه"),
        )).fetchone()
        await conn.commit()
    return {"conversation": row}


@app.get("/api/conversations")
async def list_conversations(session_id: uuid.UUID):
    async with await db_connect() as conn:
        rows = await (await conn.execute(
            """SELECT id, title, created_at, updated_at FROM sol_conversations
               WHERE session_id = %s ORDER BY updated_at DESC LIMIT 100""",
            (session_id,),
        )).fetchall()
    return {"conversations": rows}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: uuid.UUID, session_id: uuid.UUID):
    async with await db_connect() as conn:
        conversation = await (await conn.execute(
            "SELECT id, title, created_at, updated_at FROM sol_conversations WHERE id = %s AND session_id = %s",
            (conversation_id, session_id),
        )).fetchone()
        if not conversation:
            raise HTTPException(status_code=404, detail="گفتگو پیدا نشد.")
        messages = await (await conn.execute(
            "SELECT role, content, created_at FROM sol_messages WHERE conversation_id = %s ORDER BY created_at, id",
            (conversation_id,),
        )).fetchall()
    return {"conversation": conversation, "messages": messages}


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: uuid.UUID, session_id: uuid.UUID):
    async with await db_connect() as conn:
        result = await conn.execute(
            "DELETE FROM sol_conversations WHERE id = %s AND session_id = %s",
            (conversation_id, session_id),
        )
        await conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="گفتگو پیدا نشد.")
    return {"deleted": True}


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="کلید هوش مصنوعی تنظیم نشده است. بعداً GEMINI_API_KEY را در Variables اضافه کن.",
        )

    language_instruction = {
        "fa": "Answer in clear Persian (Dari/Farsi).",
        "en": "Answer in clear English.",
        "auto": "Reply in the same language as the user's latest message. Support Persian/Dari and English.",
    }[payload.language]

    contents = [
        {"role": "user" if message.role == "user" else "model", "parts": [{"text": message.content}]}
        for message in payload.messages
    ]
    body = {
        "system_instruction": {"parts": [{"text": (
            "You are Sol AI, a helpful, honest, safety-conscious assistant. "
            "Be clear and practical. Never claim to have performed actions you did not perform. "
            + language_instruction
        )}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                url, json=body,
                headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="زمان پاسخ هوش مصنوعی تمام شد. دوباره تلاش کن.")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="اتصال به سرویس هوش مصنوعی برقرار نشد.")

    if response.status_code >= 400:
        try:
            provider_error = response.json().get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            provider_error = ""
        print(f"Gemini API error: HTTP {response.status_code}; {provider_error[:500]}")
        if response.status_code in (401, 403):
            raise HTTPException(status_code=502, detail="کلید Gemini یا مجوزهای آن پذیرفته نشد.")
        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="سهمیه یا محدودیت درخواست هوش مصنوعی تمام شده است.")
        raise HTTPException(status_code=502, detail=f"سرویس هوش مصنوعی خطای HTTP {response.status_code} داد.")

    try:
        data = response.json()
        answer = data["candidates"][0]["content"]["parts"]
        answer_text = "\n".join(part.get("text", "") for part in answer).strip()
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="پاسخ غیرمنتظره‌ای از سرویس هوش مصنوعی دریافت شد.")
    if not answer_text:
        raise HTTPException(status_code=502, detail="پاسخ هوش مصنوعی خالی بود.")

    conversation_id = payload.conversation_id
    saved = False
    if DB_READY and payload.session_id:
        try:
            async with await db_connect() as conn:
                if conversation_id:
                    conversation = await (await conn.execute(
                        "SELECT id FROM sol_conversations WHERE id = %s AND session_id = %s",
                        (conversation_id, payload.session_id),
                    )).fetchone()
                    if not conversation:
                        raise HTTPException(status_code=404, detail="گفتگو پیدا نشد یا متعلق به این نشست نیست.")
                else:
                    first_user_text = next((m.content for m in payload.messages if m.role == "user"), "گفتگوی تازه")
                    conversation_id = uuid.uuid4()
                    await conn.execute(
                        "INSERT INTO sol_conversations (id, session_id, title) VALUES (%s, %s, %s)",
                        (conversation_id, payload.session_id, first_user_text[:80]),
                    )
                latest_user = next((m.content for m in reversed(payload.messages) if m.role == "user"), "")
                if latest_user:
                    await conn.execute(
                        "INSERT INTO sol_messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
                        (conversation_id, latest_user),
                    )
                await conn.execute(
                    "INSERT INTO sol_messages (conversation_id, role, content) VALUES (%s, 'assistant', %s)",
                    (conversation_id, answer_text),
                )
                await conn.execute(
                    "UPDATE sol_conversations SET updated_at = NOW() WHERE id = %s",
                    (conversation_id,),
                )
                await conn.commit()
                saved = True
        except HTTPException:
            raise
        except Exception as exc:
            print(f"Could not save chat history: {type(exc).__name__}: {str(exc)[:250]}")

    return {
        "reply": answer_text,
        "model": MODEL,
        "conversation_id": str(conversation_id) if conversation_id else None,
        "saved": saved,
    }


PAGE = r"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b1020"><title>Sol AI</title>
<style>
:root{color-scheme:dark;--bg:#080d19;--panel:#101a2b;--line:#263650;--text:#eef4ff;--muted:#91a2bd;--accent:#a9b7ff;--teal:#61dfcb}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top,#172747,var(--bg) 62%);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text);min-height:100vh}
button,select,textarea{font:inherit}button{cursor:pointer}.app{min-height:100vh;display:grid;grid-template-columns:270px minmax(0,1fr);max-width:1500px;margin:auto}
aside{background:#0b1322d9;border-left:1px solid var(--line);padding:18px;display:flex;flex-direction:column;gap:16px}.brand{font-size:23px;font-weight:850;letter-spacing:.2px}.sub{font-size:12px;color:var(--muted);margin-top:3px}.new{background:var(--accent);color:#10172a;border:0;border-radius:12px;padding:12px;font-weight:800}.history-title{font-size:12px;color:var(--muted);margin-top:6px}.history{display:flex;flex-direction:column;gap:7px;overflow:auto;max-height:60vh}.history button{border:1px solid transparent;background:transparent;color:var(--text);padding:10px;text-align:right;border-radius:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.history button.active,.history button:hover{background:var(--panel);border-color:var(--line)}.db-note{margin-top:auto;font-size:11px;line-height:1.8;color:var(--muted)}
main{min-width:0;display:flex;flex-direction:column;min-height:100vh;padding:0 24px 16px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:18px 0;border-bottom:1px solid var(--line)}select{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:9px}.chat{flex:1;display:flex;flex-direction:column;gap:14px;padding:22px 0;min-height:300px}.welcome{margin:auto;text-align:center;color:var(--muted);line-height:2;max-width:520px}.welcome strong{font-size:26px;color:var(--text);display:block;margin-bottom:8px}.msg{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.9;padding:14px 17px;border:1px solid var(--line);border-radius:17px;max-width:min(85%,780px);background:var(--panel)}.msg.user{align-self:flex-start;background:#1b2b49}.msg.assistant{align-self:flex-end}.compose{position:sticky;bottom:0;background:linear-gradient(transparent,var(--bg) 18%);padding:12px 0 6px}.entry{display:flex;gap:10px;align-items:flex-end;border:1px solid var(--line);background:#0e1728;border-radius:18px;padding:9px}.entry textarea{resize:vertical;min-height:48px;max-height:190px;flex:1;border:0;background:transparent;color:var(--text);outline:none;padding:10px}.send{background:var(--accent);color:#10172a;border:0;border-radius:12px;padding:12px 18px;font-weight:800}.send:disabled{opacity:.55}.error{color:#ffb9bd;white-space:pre-wrap;padding:7px 0;font-size:13px}.foot{color:var(--muted);font-size:11px;text-align:center;padding-top:10px}.mobile-brand{display:none}
@media(max-width:760px){.app{display:block}aside{border-left:0;border-bottom:1px solid var(--line);padding:12px 14px;gap:10px}.aside-head{display:flex;align-items:center;justify-content:space-between}.brand{font-size:20px}.new{padding:9px 12px}.history-title,.db-note{display:none}.history{flex-direction:row;max-height:none}.history button{max-width:180px;flex:0 0 auto}main{min-height:70vh;padding:0 13px 12px}.top{padding:12px 0}.chat{padding:15px 0}.msg{max-width:96%}.welcome strong{font-size:22px}}
</style></head>
<body><div class="app">
<aside><div class="aside-head"><div><div class="brand">✦ Sol AI</div><div class="sub">دستیار هوشمند · AI assistant</div></div><button class="new" id="newChat">＋ گفتگوی تازه</button></div>
<div class="history-title">گفتگوهای قبلی / History</div><div class="history" id="history"></div>
<div class="db-note" id="dbNote">گفتگوها پس از تنظیم PostgreSQL ذخیره می‌شوند. / History is saved when PostgreSQL is configured.</div></aside>
<main><header class="top"><div><strong>Sol AI</strong><div class="sub">همراه هوشمند شما · Your AI companion</div></div><select id="lang" aria-label="Language"><option value="auto">خودکار / Auto</option><option value="fa">فارسی / دری</option><option value="en">English</option></select></header>
<section id="chat" class="chat" aria-live="polite"><div class="welcome" id="welcome"><strong>سلام کاربر عزیز! 👋</strong>من Sol AI هستم. چه کمکی از دستم برمی‌آید؟<br>Hello! I'm Sol AI. How can I help?</div></section>
<div id="error" class="error" role="status"></div>
<form id="form" class="compose"><div class="entry"><textarea id="prompt" maxlength="12000" placeholder="پیامت را بنویس… / Type your message…" required></textarea><button class="send" id="send" type="submit">ارسال</button></div></form>
<div class="foot">پاسخ‌های هوش مصنوعی ممکن است اشتباه باشند؛ اطلاعات مهم را بررسی کن.</div>
</main></div>
<script>
const chat=document.getElementById('chat'),form=document.getElementById('form'),promptBox=document.getElementById('prompt'),send=document.getElementById('send'),err=document.getElementById('error'),historyBox=document.getElementById('history'),dbNote=document.getElementById('dbNote');
const history=[],sessionKey='sol_ai_session_v2';
let sessionId=localStorage.getItem(sessionKey);if(!sessionId){sessionId=crypto.randomUUID();localStorage.setItem(sessionKey,sessionId);}
let conversationId=null;
function clearChat(){chat.replaceChildren();const welcome=document.createElement('div');welcome.className='welcome';welcome.innerHTML='<strong>سلام کاربر عزیز! 👋</strong>من Sol AI هستم. چه کمکی از دستم برمی‌آید؟<br>Hello! I\\'m Sol AI. How can I help?';chat.appendChild(welcome);history.length=0;}
function add(role,text){const el=document.createElement('div');el.className='msg '+role;el.textContent=text;chat.appendChild(el);chat.scrollTop=chat.scrollHeight;return el;}
async function loadHistory(){try{const r=await fetch('/api/conversations?session_id='+encodeURIComponent(sessionId));if(!r.ok)throw new Error();const data=await r.json();historyBox.replaceChildren();dbNote.textContent='ذخیره‌سازی فعال است · Database connected';for(const c of data.conversations){const b=document.createElement('button');b.textContent=c.title||'گفتگوی تازه';b.title=b.textContent;b.className=String(c.id)===conversationId?'active':'';b.onclick=()=>openConversation(c.id);historyBox.appendChild(b);}}catch{dbNote.textContent='پس از تنظیم DATABASE_URL در PostgreSQL، تاریخچه فعال می‌شود.';}}
async function openConversation(id){try{const r=await fetch('/api/conversations/'+encodeURIComponent(id)+'?session_id='+encodeURIComponent(sessionId));const data=await r.json();if(!r.ok)throw new Error(data.detail||'گفتگو باز نشد');conversationId=id;clearChat();chat.replaceChildren();for(const m of data.messages){history.push({role:m.role,content:m.content});add(m.role,m.content);}await loadHistory();}catch(e){err.textContent=e.message;}}
document.getElementById('newChat').addEventListener('click',()=>{conversationId=null;clearChat();err.textContent='';loadHistory();promptBox.focus();});
form.addEventListener('submit',async e=>{e.preventDefault();const text=promptBox.value.trim();if(!text)return;promptBox.value='';err.textContent='';add('user',text);history.push({role:'user',content:text});while(history.length>30)history.shift();send.disabled=true;send.textContent='…';const pending=add('assistant','در حال فکر کردن… / Thinking…');
try{const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:history,language:document.getElementById('lang').value,session_id:sessionId,conversation_id:conversationId})});const data=await res.json();if(!res.ok)throw new Error(data.detail||'درخواست ناموفق بود');pending.textContent=data.reply;history.push({role:'assistant',content:data.reply});while(history.length>30)history.shift();if(data.conversation_id)conversationId=data.conversation_id;if(data.saved)await loadHistory();}
catch(ex){pending.remove();err.textContent=ex.message||'خطا رخ داد. دوباره تلاش کن.';history.pop();}
finally{send.disabled=false;send.textContent='ارسال';promptBox.focus();chat.scrollTop=chat.scrollHeight;}});
promptBox.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit();}});
loadHistory();
</script></body></html>"""
