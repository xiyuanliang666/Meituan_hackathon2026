from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import ai, chat, dataset, db, demo_state, evaluation, events, hand_standardize, operations, styles, taxonomy, templates, trends, tryon_history, tune
from app.config import get_settings


app = FastAPI(
    title="Nail AI Try-On and Smart Operations API",
    version="0.1.0",
    description="Demo backend for user try-on, style recommendation, and merchant operations.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(styles.router, prefix="/api", tags=["styles"])
app.include_router(taxonomy.router, prefix="/api", tags=["taxonomy"])
app.include_router(ai.router, prefix="/api", tags=["ai"])
app.include_router(operations.router, prefix="/api", tags=["operations"])
app.include_router(dataset.router, prefix="/api", tags=["dataset"])
app.include_router(db.router, prefix="/api", tags=["database"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(evaluation.router, prefix="/api", tags=["evaluation"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(hand_standardize.router, prefix="/api", tags=["hand-standardize"])
app.include_router(tryon_history.router, prefix="/api", tags=["tryon-history"])
app.include_router(templates.router, prefix="/api", tags=["templates"])
app.include_router(trends.router, prefix="/api", tags=["trends"])
app.include_router(tune.router, prefix="/api", tags=["tune"])
app.include_router(demo_state.router, prefix="/api", tags=["demo-state"])
app.mount("/static", StaticFiles(directory=get_settings().storage_dir), name="static")

# 挂载前端静态文件（联调模式：前端可通过 http://localhost:8000/app/ 访问）
import os
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/app", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
