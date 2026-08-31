from workers import WorkerEntrypoint

from app import app
from email_import import process_email


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi

        return await asgi.fetch(app, request.js_object, self.env)

    async def email(self, message, env=None, ctx=None):
        await process_email(message, env or self.env)
