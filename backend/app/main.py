from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.documents import router as documents_router


class HealthResponse(BaseModel):
    status: Literal["ok"]


app = FastAPI(title="NEXUS ACADEMY")
app.include_router(documents_router)


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")