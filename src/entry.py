from workers import WorkerEntrypoint

from app import app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi

        return await asgi.fetch(app, request.js_object, self.env)

    async def email(self, message, env=None, ctx=None):
        from email_import import process_email

        await process_email(message, env if env is not None else self.env)
