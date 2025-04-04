from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import ssl
import http.client as http_client
from sqlalchemy.orm import Session
from database import SessionLocal, init_db, Task, Chat, User
from config import GROQ_API_KEY, OMI_API_KEY, OMI_APP_ID
from omi_client import OmiClient
from task_processor import detect_task
from models import TranscriptRequest, TaskRequest, UserCreate, UserLogin
from deep_translator import GoogleTranslator
from datetime import datetime
import bcrypt

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://omi-ai-mentor-webmonitor.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
init_db()
omi_client = OmiClient()
translator = GoogleTranslator(source='auto', target='en')

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ask_groq(question):
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    conn = http_client.HTTPSConnection("api.groq.com", context=context)
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": question}]
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"}
    conn.request("POST", "/openai/v1/chat/completions", body=json.dumps(payload), headers=headers)
    res = conn.getresponse()
    data = res.read()
    return json.loads(data.decode("utf-8"))["choices"][0]["message"]["content"] if res.status == 200 else "Error"

def summarize_text(text, max_lines=3, max_length=150):
    lines = text.split(".")[:max_lines]
    return ". ".join(lines) + "." if len(text) > max_length else text

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

@app.post("//livetranscript")
async def live_transcription(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    segments = data.get("segments", [])
    user_id = data.get("user_id", "unknown")
    transcript = " ".join(segment["text"] for segment in segments if "text" in segment).strip()
    if not transcript:
        return {"message": "No transcription received"}

    translated_text = translator.translate(transcript)
    ai_response = ask_groq(translated_text)
    notification_message = summarize_text(ai_response)
    
    task_data = detect_task(transcript)
    if task_data:
        db.add(Task(user_id=user_id, **task_data))
        db.commit()

    db.add(Chat(user_id=user_id, user_message=transcript, mentor_response=ai_response, timestamp=str(datetime.now())))
    db.commit()

    return {"message": notification_message, "response": ai_response}

@app.post("/livetranscript")
async def live_transcription(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    segments = data.get("segments", [])
    user_id = data.get("user_id", "unknown")
    transcript = " ".join(segment["text"] for segment in segments if "text" in segment).strip()
    if not transcript:
        return {"message": "No transcription received"}

    translated_text = translator.translate(transcript)
    ai_response = ask_groq(translated_text)
    notification_message = summarize_text(ai_response)
    
    task_data = detect_task(transcript)
    if task_data:
        db.add(Task(user_id=user_id, **task_data))
        db.commit()

    db.add(Chat(user_id=user_id, user_message=transcript, mentor_response=ai_response, timestamp=str(datetime.now())))
    db.commit()

    return {"message": notification_message, "response": ai_response}

@app.post("/webhook")
async def receive_transcription(request: Request):
    data = await request.json()
    transcript = data.get("transcript", "").strip()
    user_id = data.get("user_id", "unknown")
    if not transcript:
        return {"message": "No transcription received"}
    
    translated_text = translator.translate(transcript)
    ai_response = ask_groq(translated_text)
    notification_message = summarize_text(ai_response)
    return {"message": "Webhook received", "response": ai_response, "notification": notification_message}

@app.post("//signup")
async def signup(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = hash_password(user.password)
    db_user = User(email=user.email, password=hashed_password, omi_user_id=user.omi_user_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"message": "User created", "user_id": user.omi_user_id}

@app.post("//login")
async def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Login successful", "user_id": db_user.omi_user_id}

@app.get("//tasks/{user_id}")
def get_tasks(user_id: str, db: Session = Depends(get_db)):
    today = datetime.now().date()
    tasks = db.query(Task).filter(Task.user_id == user_id, Task.date == today).all()
    return {"tasks": [{"id": t.id, "task": t.task, "time": t.time, "date": str(t.date)} for t in tasks]}

@app.post("//tasks/{user_id}")
def add_task(user_id: str, task: TaskRequest, db: Session = Depends(get_db)):
    db_task = Task(user_id=user_id, task=task.task, time=task.time, date=task.date)
    db.add(db_task)
    db.commit()
    return {"message": "Task added"}

@app.get("//memories/{user_id}")
def get_memories(user_id: str):
    return {"memories": omi_client.read_memories(user_id)}

@app.get("//chat/{user_id}")
def get_chat(user_id: str, db: Session = Depends(get_db)):
    chats = db.query(Chat).filter(Chat.user_id == user_id).all()
    return {"chats": [{"user": c.user_message, "mentor": c.mentor_response, "timestamp": c.timestamp} for c in chats]}


@app.delete("//memories/{user_id}/{memory_id}")
def delete_memory(user_id: str, memory_id: str):

    response = omi_client.delete_memory(user_id, memory_id)
    return {"message": "Memory deleted"} if response else {"message": "Failed to delete memory"}


def delete_memory(self, user_id, memory_id):
    response = requests.delete(f"{self.BASE_URL}/memories/{memory_id}?user_id={user_id}", headers=self.headers)
    return response.status_code == 204

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)