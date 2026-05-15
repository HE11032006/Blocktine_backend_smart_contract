from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import auth, groups, payments, webhooks, admin

app = FastAPI(
    title="Tontine-Flow API",
    description="Backend pour la gestion de tontines sécurisées sur Polygon",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(groups.router, prefix="/groups", tags=["groups"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(webhooks.router, prefix="/webhook", tags=["webhooks"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "tontine-flow-api"}
