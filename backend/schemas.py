from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    question: str
    model: Optional[str] = "mimo"  # 可选: mimo, claude

class ChatResponse(BaseModel):
    question: str
    answer: str
    references: list[str]


