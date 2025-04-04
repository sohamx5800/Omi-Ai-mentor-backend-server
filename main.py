from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import ssl
import http.client as http_client
from sqlalchemy.orm import Session
from database import SessionLocal, init_db, Task, Chat, User, Memory
from config import GROQ_API_KEY, OMI_API_KEY, OMI_APP_ID
from omi_client import OmiClient
from task_processor import detect_task
from models import TranscriptRequest, TaskRequest, UserCreate, UserLogin
from deep_translator import GoogleTranslator
from datetime import datetime
import bcrypt
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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

@app.post("/livetranscript")
async def live_transcription(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    segments = data.get("segments", [])
    user_id = request.query_params.get("uid") or data.get("user_id")
    if not user_id:
        logger.warning("No user_id provided in request")
        raise HTTPException(status_code=400, detail="user_id is required")
    
    transcript = " ".join(segment["text"] for segment in segments if "text" in segment).strip()
    logger.info(f"Received transcript from Omi for user {user_id}: {transcript}")
    if not transcript:
        logger.warning("No transcription received")
        return {"message": "No transcription received"}

    try:
        translated_text = translator.translate(transcript)
        logger.info(f"Translated text: {translated_text}")
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
        translated_text = transcript

    full_response = ask_groq(translated_text)
    logger.info(f"Full Grok response: {full_response}")
    notification_message = summarize_text(full_response)
    logger.info(f"Summarized notification: {notification_message}")

    task_data = detect_task(transcript)
    if task_data:
        logger.info(f"Task detected: {task_data}")
        date_str = task_data.get("date")
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        db_task = Task(
            user_id=user_id,
            task=task_data["task"],
            time=task_data.get("time") or None,
            date=date_obj
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        logger.info(f"Task saved with ID: {db_task.id}")
    else:
        logger.info("No task detected in transcript")

    db_memory = Memory(
        user_id=user_id,
        title=f"Chat on {datetime.now().date()}",
        transcript=transcript,
        response=full_response
    )
    db.add(db_memory)
    db.commit()
    db.refresh(db_memory)
    logger.info(f"Memory saved with ID: {db_memory.id}")

    memory_data = {
        "title": f"Chat on {datetime.now().date()}",
        "summary": notification_message
    }
    try:
        omi_result = omi_client.write_memory(user_id, memory_data)
        logger.info(f"Omi API memory sync result: {omi_result}")
    except Exception as e:
        logger.error(f"Omi API sync failed: {e}")

    return {"message": notification_message, "response": full_response}

@app.post("/webhook")
async def receive_transcription(request: Request):
    data = await request.json()
    transcript = data.get("transcript", "").strip()
    user_id = data.get("user_id", "unknown")
    if not transcript:
        logger.warning("No transcription received in webhook")
        return {"message": "No transcription received"}
    
    try:
        translated_text = translator.translate(transcript)
    except Exception as e:
        logger.warning(f"Translation failed in webhook: {e}")
        translated_text = transcript
    full_response = ask_groq(translated_text)
    notification_message = summarize_text(full_response)
    logger.info(f"Webhook processed for user {user_id}: {notification_message}")
    return {"message": "Webhook received", "response": full_response, "notification": notification_message}

@app.post("/signup")
async def signup(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = hash_password(user.password)
    db_user = User(email=user.email, password=hashed_password, omi_user_id=user.omi_user_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    logger.info(f"User signed up: {user.omi_user_id}")
    return {"message": "User created", "user_id": user.omi_user_id}

@app.post("/login")
async def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info(f"User logged in: {db_user.omi_user_id}")
    return {"message": "Login successful", "user_id": db_user.omi_user_id}

@app.get("/tasks/{user_id}")
def get_tasks(user_id: str, db: Session = Depends(get_db)):
    tasks = db.query(Task).filter(Task.user_id == user_id).all()
    tasks_data = [{"id": t.id, "task": t.task, "time": t.time or "", "date": t.date.isoformat() if t.date else ""} for t in tasks]
    logger.info(f"Retrieved tasks for {user_id}: {tasks_data}")
    return {"tasks": tasks_data}

@app.post("/tasks/{user_id}")
def add_task(user_id: str, task: TaskRequest, db: Session = Depends(get_db)):
    date_obj = datetime.strptime(task.date, "%Y-%m-%d").date() if task.date else None
    db_task = Task(user_id=user_id, task=task.task, time=task.time or None, date=date_obj)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    logger.info(f"Manual task added for {user_id} with ID: {db_task.id}")
    return {"message": "Task added"}

@app.get("/memories/{user_id}")
def get_memories(user_id: str, db: Session = Depends(get_db)):
    memories = db.query(Memory).filter(Memory.user_id == user_id).all()
    memories_data = [{"id": m.id, "title": m.title, "transcript": m.transcript, "response": m.response} for m in memories]
    logger.info(f"Retrieved memories for {user_id}: {memories_data}")
    return {"memories": memories_data}

@app.delete("/memories/{user_id}/{memory_id}")
def delete_memory(user_id: str, memory_id: str, db: Session = Depends(get_db)):
    memory = db.query(Memory).filter(Memory.user_id == user_id, Memory.id == memory_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.delete(memory)
    db.commit()
    try:
        omi_client.delete_memory(user_id, memory_id)
        logger.info(f"Memory {memory_id} deleted for {user_id} from Omi API")
    except Exception as e:
        logger.error(f"Omi API memory deletion failed: {e}")
    logger.info(f"Memory {memory_id} deleted for {user_id}")
    return {"message": "Memory deleted"}

@app.get("/chat/{user_id}")
def get_chat(user_id: str, db: Session = Depends(get_db)):
    chats = db.query(Chat).filter(Chat.user_id == user_id).all()
    chats_data = [{"user": c.user_message, "mentor": c.mentor_response, "timestamp": c.timestamp} for c in chats]
    logger.info(f"Retrieved chats for {user_id}: {chats_data}")
    return {"chats": chats_data}

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)