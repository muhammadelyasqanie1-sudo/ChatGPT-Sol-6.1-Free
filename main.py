import os
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

APP_NAME = "Sol AI"
MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

app = FastAPI(title=APP_NAME, version="1.0.1")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    language: Literal["auto", "fa", "en"] = "auto"


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": APP_NAME,
        "model": MODEL,
        "api_key_configured": bool(API_KEY),
    }


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(PAGE)


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API key is not configured. Add GEMINI_API_KEY in Railway Variables.",
        )

    language_instruction = {
        "fa": "Answer in clear Persian (Dari/Farsi).",
        "en": "Answer in clear English.",
        "auto": "Reply in the same language as the user's latest message. Support Persian/Dari and English.",
    }[payload.language]

    contents = []
    for message in payload.messages:
        contents.append({
            "role": "user" if message.role == "user" else "model",
            "parts": [{"text": message.content}],
        })

    body = {
        "system_instruction": {
            "parts": [{
                "text": (
                    "You are Sol AI, a helpful, honest, safety-conscious assistant. "
                    "Be clear and practical. Never claim to have performed actions you did not perform. "
                    + language_instruction
                )
            }]
        },
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                url,
                params={"key": API_KEY},
                json=body,
                headers={"Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="The AI provider timed out. Please try again.")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not connect to the AI provider.")

    if response.status_code >= 400:
        if response.status_code in (401, 403):
            raise HTTPException(status_code=502, detail="The API key was rejected. Check Railway Variables.")
        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="The AI provider rate limit or quota was reached.")
        raise HTTPException(status_code=502, detail=f"AI provider returned HTTP {response.status_code}.")

    try:
        data = response.json()
        answer = data["candidates"][0]["content"]["parts"]
        text = "\\n".join(part.get("text", "") for part in answer).strip()
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="The AI provider returned an unexpected response.")

    if not text:
        raise HTTPException(status_code=502, detail="The AI provider returned an empty answer.")
    return {"reply": text, "model": MODEL}


PAGE = r"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#111827"><title>Sol AI</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#111a2e;--line:#26334d;--text:#eef2ff;--muted:#9aa9c4;--accent:#8b9cff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top,#182448,var(--bg) 60%);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text);min-height:100vh}
main{max-width:900px;margin:auto;padding:20px;display:flex;flex-direction:column;min-height:100vh}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 0 18px;border-bottom:1px solid var(--line)}
.brand{font-size:22px;font-weight:800;letter-spacing:.2px}.sub{font-size:12px;color:var(--muted);margin-top:3px}
select,button,textarea{font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px}
#chat{flex:1;display:flex;flex-direction:column;gap:14px;padding:22px 0;min-height:300px}
.msg{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;padding:14px 16px;border:1px solid var(--line);border-radius:16px;max-width:90%;background:var(--panel)}
.msg.user{align-self:flex-start;background:#202d50}.msg.assistant{align-self:flex-end}
.welcome{margin:auto;text-align:center;color:var(--muted);line-height:1.9}.welcome strong{font-size:22px;color:var(--text);display:block}
form{position:sticky;bottom:0;background:linear-gradient(transparent,var(--bg) 18%);padding:12px 0 6px}
.entry{display:flex;gap:10px;align-items:flex-end;border:1px solid var(--line);background:#0f172a;border-radius:16px;padding:8px}
textarea{resize:vertical;min-height:50px;max-height:180px;flex:1;border:0;background:transparent;outline:none}
button{cursor:pointer;background:var(--accent);color:#10162b;font-weight:750;border:0}button:disabled{opacity:.5;cursor:wait}
.foot{color:var(--muted);font-size:11px;text-align:center;padding-top:10px}
#error{color:#ffb4b4;white-space:pre-wrap;padding:8px 0}
@media(max-width:600px){main{padding:12px}.msg{max-width:96%}.brand{font-size:19px}}
</style></head>
<body><main>
<header><div><div class="brand">✦ Sol AI</div><div class="sub">دستیار هوشمند · AI assistant</div></div>
<select id="lang" aria-label="Language"><option value="auto">خودکار / Auto</option><option value="fa">فارسی / دری</option><option value="en">English</option></select></header>
<section id="chat" aria-live="polite"><div class="welcome" id="welcome"><strong>سلام کاربر عزیز! 👋</strong>من Sol AI هستم. برای آزمایش، پیامت را بنویس. / Hello! Send a message to test.</div></section>
<div id="error" role="status"></div>
<form id="form"><div class="entry"><textarea id="prompt" maxlength="12000" placeholder="پیامت را بنویس… / Type your message…" required></textarea><button id="send" type="submit">ارسال</button></div></form>
<div class="foot">پاسخ‌های هوش مصنوعی ممکن است اشتباه باشند؛ اطلاعات مهم را بررسی کن.</div>
</main>
<script>
const chat=document.getElementById('chat'), form=document.getElementById('form'), promptBox=document.getElementById('prompt'), send=document.getElementById('send'), err=document.getElementById('error'), welcome=document.getElementById('welcome');
const history=[];
function add(role,text){if(welcome)welcome.remove();const el=document.createElement('div');el.className='msg '+role;el.textContent=text;chat.appendChild(el);chat.scrollTop=chat.scrollHeight;return el;}
form.addEventListener('submit',async e=>{e.preventDefault();const text=promptBox.value.trim();if(!text)return;promptBox.value='';err.textContent='';add('user',text);history.push({role:'user',content:text});while(history.length>30)history.shift();send.disabled=true;send.textContent='…';const pending=add('assistant','در حال فکر کردن… / Thinking…');
try{const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:history,language:document.getElementById('lang').value})});const data=await res.json();if(!res.ok)throw new Error(data.detail||'درخواست ناموفق بود');pending.textContent=data.reply;history.push({role:'assistant',content:data.reply});while(history.length>30)history.shift();}
catch(ex){pending.remove();err.textContent=ex.message||'خطا رخ داد. دوباره تلاش کن.';history.pop();}
finally{send.disabled=false;send.textContent='ارسال';promptBox.focus();chat.scrollTop=chat.scrollHeight;}});
promptBox.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit();}});
</script></body></html>"""