from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import api
import ui


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_origin_regex=r"^https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+azamines\.workers\.dev$",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api.router)
app.include_router(ui.router)
