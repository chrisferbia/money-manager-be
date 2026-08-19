from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import api
import ui


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://money-manager-fe.azamines.workers.dev",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api.router)
app.include_router(ui.router)
