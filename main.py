"""LLM News Intelligence Service - FastAPI Application"""

import os
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.extract import router as extract_router
from api.entities import router as entities_router
from api.health import router as health_router


def load_config() -> dict:
    """Load configuration from config.yaml"""
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


config = load_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    print(f"Starting LLM News Service on port {config['service']['port']}")
    yield
    # Shutdown
    print("Shutting down LLM News Service")


app = FastAPI(
    title="LLM News Intelligence Service",
    description="Structured news extraction and entity state tracking",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router, tags=["health"])
app.include_router(extract_router, prefix="/extract", tags=["extraction"])
app.include_router(entities_router, prefix="/entities", tags=["entities"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config["service"]["host"],
        port=config["service"]["port"],
        reload=True,
    )
