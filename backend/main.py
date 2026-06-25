from fastapi import FastAPI, UploadFile
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

load_dotenv()

app = FastAPI()

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
        "base_url": os.getenv("CLAUDE_BASE_URL"),  # 可选，默认官方地址
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
        with open(filepath, 'r', encoding='latin-1') as f:
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
        n_results = top_k
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
5. 不要标注引用来源，直接陈述事实

回答结构：
- 先给出核心总结（一句话结论）
- 再详细拆解（分点陈述）
- 最后补充建议（如果适用）

规则：
- 只基于提供的参考资料回答，不要编造信息
- 如果参考资料中没有相关信息，请直接说"根据现有资料，无法回答这个问题"

参考资料：
{context}

用户问题：{question}"""
    return prompt

@app.get("/history/")
async def get_history():
    db = SessionLocal()
    records = db.query(models.ChatHistory).order_by(models.ChatHistory.created_at.asc()).all()
    db.close()

    return [
        {
            "id": r.id,
            "question": r.question,
            "answer": r.answer,
            "created_at": r.created_at.isoformat()
        }
        for r in records
    ]

@app.post("/chat/", response_model=schemas.ChatResponse)
async def chat(request: schemas.ChatRequest):
    question = request.question
    model_name = request.model or "mimo"

    chunks = search(question, top_k=3)

    prompt = build_prompt(question, chunks)

    config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["mimo"])
    client = get_ai_client(model_name)
    response = client.messages.create(
        model=config["model_name"],
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = response.content[0].text

    db = SessionLocal()
    try:
        db.add(models.ChatHistory(question=question, answer=answer))
        db.commit()
    finally:
        db.close()

    return {
        "question": question,
        "answer": answer,
        "references": [c["text"] for c in chunks]
    }

@app.post("/chat/stream/")
async def chat_stream(request: schemas.ChatRequest):
    question = request.question
    model_name = request.model or "mimo"

    chunks = search(question, top_k=3)

    prompt = build_prompt(question, chunks)

    config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["mimo"])
    client = get_ai_client(model_name)

    async def generate():
        full_answer = ""
        with client.messages.stream(
            model=config["model_name"],
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                full_answer += text
                yield f"data: {json.dumps({'text': text, 'done': False})}\n\n"

        db = SessionLocal()
        try:
            db.add(models.ChatHistory(question=question, answer=full_answer))
            db.commit()
        finally:
            db.close()

        # 发送完成信号
        yield f"data: {json.dumps({'text': '', 'done': True, 'references': [c['text'] for c in chunks]})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.post("/upload/")
async def upload_file(file: UploadFile):
    content = await file.read()
    filepath = f"uploads/{file.filename}"
    with open(filepath, "wb") as f:
        f.write(content)

    text = extract_text(filepath)
    chunks = split_text(text)

    # 删除同一文件的旧数据（如果重新上传）
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

    # 把每块变成向量并存入 ChromaDB
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
    





