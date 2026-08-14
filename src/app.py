from fastapi import FastAPI

import api
import ui


app = FastAPI()
app.include_router(api.router)
app.include_router(ui.router)
