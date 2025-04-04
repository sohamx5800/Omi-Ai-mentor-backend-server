from pydantic import BaseModel
from typing import List, Dict, Optional

class TranscriptRequest(BaseModel):
    segments: List[Dict]
    user_id: str

class TaskRequest(BaseModel):
    task: str
    time: Optional[str] = None
    date: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    password: str
    omi_user_id: str

class UserLogin(BaseModel):
    email: str
    password: str