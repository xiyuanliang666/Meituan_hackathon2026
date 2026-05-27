from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import ai, chat, dataset, db, evaluation, events, hand_standardize, operations, styles, taxonomy, tryon_history
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
app.mount("/static", StaticFiles(directory=get_settings().storage_dir), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
