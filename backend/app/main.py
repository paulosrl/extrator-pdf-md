from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import auth, jobs, upload, ws

app = FastAPI(
    title="PDF Cleaner for LLM",
    description="Converte PDFs em Markdown otimizado para LLMs",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(ws.router)

FRONTEND_PATH = Path("/frontend/index.html")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    if FRONTEND_PATH.exists():
        return FileResponse(str(FRONTEND_PATH))
    return {"message": "PDF Cleaner API v1.0 — acesse /docs para a documentação"}


@app.get("/health")
async def health():
    return {"status": "ok"}
