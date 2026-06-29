from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PyPDF2 import PdfReader
from docx import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from anthropic import Anthropic
from database import engine, SessionLocal
import models
import schemas
import chromadb
import os
import json
import redis
import hashlib
import time

load_dotenv()

app = FastAPI()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(redis_url, decode_responses=True)

# 模型配置（都是 Anthropic 兼容 API）
MODEL_CONFIGS = {
    "mimo": {
        "model_name": "mimo-v2.5-pro",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "base_url": os.getenv("ANTHROPIC_BASE_URL"),
    },
    "claude": {
        "model_name": "claude-sonnet-4-20250514",
        "api_key": os.getenv("CLAUDE_API_KEY"),
        "base_url": os.getenv("CLAUDE_BASE_URL"),
    },
}

def get_ai_client(model_name: str):
    """根据模型名称返回对应的 AI 客户端"""
    config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["mimo"])
    return Anthropic(api_key=config["api_key"], base_url=config["base_url"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(bind=engine)

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="documents")

def get_embedding(text: str) -> list[float]:
    vector = model.encode(text)
    return vector.tolist()

def extract_text(filepath: str) -> str:
    if filepath.endswith((".txt", ".md")):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    elif filepath.endswith(".pdf"):
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    elif filepath.endswith(".docx"):
        doc = Document(filepath)
        return "\n".join([para.text for para in doc.paragraphs])
    return ""

def split_text(text: str) -> list[str]:
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    texts = text_splitter.split_text(text)
    return texts

def search(query: str, top_k: int = 3) -> list[dict]:
    vector = get_embedding(query)
    results = collection.query(
        query_embeddings = [vector],
        n_results = top_k,
    )

    documents = results["documents"][0] if results["documents"] else []
    metadatas = results["metadatas"][0] if results["metadatas"] else []

    return [
        {"text": doc, "filename": (meta or {}).get("filename", "未知")}
        for doc, meta in zip(documents, metadatas)
    ]

def build_prompt(question: str, chunks: list[dict]) -> str:
    context_parts = []
    for chunk in chunks:
        context_parts.append(f"{chunk['text']}")
    context = "\n\n---\n\n".join(context_parts)
    prompt = f"""你是一个专业的文档分析助手。请根据以下参考资料回答用户的问题。

回答格式要求：
1. 使用 Markdown 格式输出
2. 长段落使用项目符号拆解，禁止输出一大段文字
3. 多个要点使用加粗标题或数字列表
4. 直接给出结论，避免冗余废话

规则：
- 优先基于参考资料回答
- 如果参考资料与问题相关性不高，尽量从已有内容中提取有用信息回答，不要直接拒绝
- 只有当参考资料完全无关时，才说"未找到相关内容，建议换个方式提问"
- 对于日常问候(如 hello、你好),自然回应即可

参考资料:{context}
用户问题:{question}

"""
    return prompt


# ========== 对话管理接口 ==========

@app.post("/conversations/", response_model=schemas.ConversationResponse)
async def create_conversation(request: schemas.ConversationCreate):
    db = SessionLocal()
    try:
        title = request.title or "新对话"
        conv = models.Conversation(title=title)
        db.add(conv)
        db.commit()
        db.refresh(conv)

        redis_client.hset(
            f"conv:{conv.id}", mapping={
                "title": conv.title,
                "created_at": conv.created_at.isoformat()
            }
        )

        redis_client.sadd("conv:ids", conv.id)
        redis_client.zadd("conv:active", {conv.id: time.time()})
        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at
        }
    finally:
        db.close()

@app.get("/conversations/")
async def list_conversations():
    db = SessionLocal()
    try:
        convs = []
        try:
            ids = redis_client.zrevrange("conv:active", 0, -1)
            if ids:
                for id in ids:
                    try:
                        conv = redis_client.hgetall(f"conv:{id}")
                        if conv:
                            convs.append({
                                "id": int(id),
                                "title": conv["title"],
                                "created_at": conv["created_at"]
                            })
                    except Exception:
                        continue
        except Exception:
            pass
        if not convs:
            convs = db.query(models.Conversation).order_by(models.Conversation.created_at.desc()).all()
            return [
                {
                    "id": c.id,
                    "title": c.title,
                    "created_at": c.created_at.isoformat()
                }
                for c in convs
            ]
        return convs
    finally:
        db.close()

@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: int):
    db = SessionLocal()
    try:
        try:
            redis_client.zadd("conv:active", {conversation_id:time.time()})
        except Exception:
            pass

        try:
            cached = redis_client.lrange(f'conv:{conversation_id}:messages', 0, -1)
            if cached:
                messages = [json.loads(msg) for msg in cached]
                messages.reverse()
                return messages
        except Exception:
            pass

        conv = db.query(models.Conversation).filter(models.Conversation.id == conversation_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        messages = db.query(models.ChatHistory).filter(
            models.ChatHistory.conversation_id == conversation_id
        ).order_by(models.ChatHistory.created_at.asc()).all()
        return [
            {
                "id": m.id,
                "question": m.question,
                "answer": m.answer,
                "created_at": m.created_at.isoformat()
            }
            for m in messages
        ]
    finally:
        db.close()

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int):
    db = SessionLocal()
    try:
        conv = db.query(models.Conversation).filter(models.Conversation.id == conversation_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        db.delete(conv)
        db.commit()

        redis_client.delete(f"conv:{conversation_id}")
        redis_client.srem("conv:ids", conversation_id)
        redis_client.delete(f"conv:{conversation_id}:messages")
        redis_client.zrem("conv:active", conversation_id)
        return {"message": "已删除"}
    finally:
        db.close()

@app.patch("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: int, request: schemas.ConversationCreate):
    db = SessionLocal()
    try:
        conv = db.query(models.Conversation).filter(models.Conversation.id == conversation_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        conv.title = request.title
        db.commit()
        redis_client.hset(f"conv:{conversation_id}", "title", request.title)
        return {"id": conv.id, "title": conv.title, "created_at": conv.created_at.isoformat()}
    finally:
        db.close()


# ========== 聊天接口 ==========

@app.get("/history/")
async def get_history(conversation_id: int = None):
    db = SessionLocal()
    try:
        query = db.query(models.ChatHistory)
        if conversation_id:
            query = query.filter(models.ChatHistory.conversation_id == conversation_id)
        records = query.order_by(models.ChatHistory.created_at.asc()).all()
        return [
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "created_at": r.created_at.isoformat()
            }
            for r in records
        ]
    finally:
        db.close()

@app.post("/chat/", response_model=schemas.ChatResponse)
async def chat(request: schemas.ChatRequest):
    question = request.question
    model_name = request.model or "mimo"
    conversation_id = request.conversation_id

    db = SessionLocal()
    try:
        # 如果没有 conversation_id，自动创建新对话
        if not conversation_id:
            title = question[:20] + ("..." if len(question) > 20 else "")
            conv = models.Conversation(title=title)
            db.add(conv)
            db.commit()
            db.refresh(conv)
            conversation_id = conv.id

        chunks = search(question, top_k=3)
        prompt = build_prompt(question, chunks)

        config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["mimo"])
        ai_client = get_ai_client(model_name)
        response = ai_client.messages.create(
            model=config["model_name"],
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.content[0].text

        db.add(models.ChatHistory(
            question=question,
            answer=answer,
            conversation_id=conversation_id
        ))
        db.commit()

        return {
            "question": question,
            "answer": answer,
            "references": [c["text"] for c in chunks],
            "conversation_id": conversation_id
        }
    finally:
        db.close()

@app.post("/chat/stream/")
async def chat_stream(body: schemas.ChatRequest, request: Request):
    question = body.question
    model_name = body.model or "mimo"
    conversation_id = body.conversation_id

    db = SessionLocal()

    # 如果没有 conversation_id，自动创建新对话
    if not conversation_id:
        title = question[:20] + ("..." if len(question) > 20 else "")
        conv = models.Conversation(title=title)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conversation_id = conv.id

        redis_client.hset(
            f"conv:{conv.id}", mapping={
                "title": conv.title,
                "created_at": conv.created_at.isoformat()
            }
        )
        redis_client.sadd("conv:ids", conv.id)
        redis_client.zadd("conv:active", {conv.id: time.time()})

    db.close()

    ip = request.client.host
    rate_key = "rate:" + ip
    try:
        count = redis_client.incr(rate_key)
        if count == 1:
            redis_client.expire(rate_key, 60)
        if count > 10:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    except HTTPException:
        raise
    except Exception:
        pass

    cache_key = "chat:" + hashlib.md5(question.encode()).hexdigest()

    try:
        cached = redis_client.get(cache_key)
    except Exception:
        cached = None

    if cached:
        import asyncio
        async def return_cached():
            text = cached
            # 每次发 5 个字，模拟流式
            for i in range(0, len(text), 5):
                chunk = json.dumps({"text": text[i:i+5], "done": False})
                yield f"data: {chunk}\n\n"
                await asyncio.sleep(0.03)
            done = json.dumps({"text": "", "done": True, "conversation_id": conversation_id})
            yield f"data: {done}\n\n"
        return StreamingResponse(
            return_cached(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

    chunks = search(question, top_k=3)
    prompt = build_prompt(question, chunks)

    config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["mimo"])
    ai_client = get_ai_client(model_name)

    async def generate():
        import queue
        q = queue.Queue()

        def stream_worker():
            full = ""
            with ai_client.messages.stream(
                model=config["model_name"],
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    full += text
                    q.put(text)
            q.put(None)  # 结束标记
            return full

        import asyncio
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, stream_worker)

        full_answer = ""
        while True:
            chunk = await loop.run_in_executor(None, q.get)
            if chunk is None:
                break
            full_answer += chunk
            yield f"data: {json.dumps({'text': chunk, 'done': False})}\n\n"

        # 等待线程完成，获取完整回答
        await future

        try:
            redis_client.set(cache_key, full_answer, ex=60)
        except Exception:
            pass

        db = SessionLocal()
        try:
            db.add(models.ChatHistory(
                question=question,
                answer=full_answer,
                conversation_id=conversation_id
            ))
            db.commit()

            redis_client.lpush(f"conv:{conversation_id}:messages", json.dumps({'role': 'user', 'content': question}))
            redis_client.lpush(f"conv:{conversation_id}:messages", json.dumps({'role': 'assistant', 'content': full_answer}))
            redis_client.ltrim(f"conv:{conversation_id}:messages", 0, 49)

        except Exception:
            pass

        finally:
            db.close()

        yield f"data: {json.dumps({'text': '', 'done': True, 'conversation_id': conversation_id, 'references': [c['text'] for c in chunks]})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# ========== 文档上传接口 ==========

@app.post("/upload/")
async def upload_file(file: UploadFile):
    content = await file.read()
    filepath = f"uploads/{file.filename}"
    with open(filepath, "wb") as f:
        f.write(content)

    text = extract_text(filepath)
    chunks = split_text(text)

    try:
        ids_to_delete = []
        for i in range(100):
            doc_id = f"{file.filename}_{i}"
            try:
                collection.get(ids=[doc_id])
                ids_to_delete.append(doc_id)
            except Exception:
                break
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
    except Exception:
        pass

    for i, chunk in enumerate(chunks):
        vector = get_embedding(chunk)
        collection.add(
            ids = [f"{file.filename}_{i}"],
            documents = [chunk],
            embeddings = [vector],
            metadatas = [{"filename": file.filename}]
        )

    return {
        "filename": file.filename,
        "chunks_count": len(chunks),
        "message": "已存入向量数据库"
    }

@app.post("/search/")
async def search_data(question: str):
    results = search(question)
    return {
        "question": question,
        "results": results
    }
