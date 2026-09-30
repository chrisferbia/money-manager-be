from workers import WorkerEntrypoint

from app import app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi

        return await asgi.fetch(app, request.js_object, self.env)

    async def email(self, message, env=None, ctx=None):
        # Inbound mail is not tenant-addressed yet. Fail closed until routing and
        # sender verification are implemented for a specific workspace.
        raise RuntimeError("Email imports are disabled")
