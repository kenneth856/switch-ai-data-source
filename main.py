import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.routes import router

os.makedirs("logs", exist_ok=True)

_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")

_file_handler = logging.FileHandler("logs/app.log")
_file_handler.setFormatter(_fmt)

_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _stream_handler])
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Switch AI Freight Module starting up")
    # Load ingredient density factors from Monday.com at startup
    try:
        from freight.cbm_calculator import load_density_from_monday
        cache = load_density_from_monday()
        logger.info("Monday.com ingredient density cache loaded: %d ingredients", len(cache))
    except Exception as e:
        logger.warning("Monday.com density cache load failed (using fallback): %s", e)
    yield
    logger.info("Switch AI Freight Module shutting down")


app = FastAPI(
    title="Switch AI - Freight Cost Module",
    description="AI-powered freight cost prediction using NetSuite data",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api")


@app.get("/")
def health_check():
    return {"status": "ok", "service": "Switch AI Freight Module"}
