from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db, init_db
from .routers import auth, repos


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="CodeAtlas API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(repos.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    version = db.execute(text("select sqlite_version()")).scalar()
    tables = db.execute(
        text("select name from sqlite_master where type='table' order by name")
    ).scalars().all()
    return {"status": "ok", "database": "sqlite", "sqlite_version": version, "tables": tables}