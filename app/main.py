import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401 — registra modelos no metadata do SQLAlchemy
from app.db.database import Base, engine
from app.routers import auth_router, predict_router, venda_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(name)s — %(message)s")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Visia Intelligence API",
    description="Previsão inteligente de vendas com sazonalidade e feriados brasileiros.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(venda_router.router)
app.include_router(predict_router.router)


@app.get("/health", tags=["Monitoramento"])
def health_check():
    return {"status": "healthy", "version": app.version}


_frontend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
