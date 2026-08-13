from fastapi import FastAPI
from workers import WorkerEntrypoint

import api
import ui

app = FastAPI()
app.include_router(api.router)
app.include_router(ui.router)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi

        return await asgi.fetch(app, request.js_object, self.env)
