from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from backend.app.core.config import settings
from backend.app.api.v1.router import router as api_v1_router

app = FastAPI(title="AgentGuard Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(_, exc: SQLAlchemyError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable; request rejected without provider execution"},
    )

app.include_router(api_v1_router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status": "ok"}