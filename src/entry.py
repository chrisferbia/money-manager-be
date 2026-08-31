from workers import WorkerEntrypoint

from app import app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi

        return await asgi.fetch(app, request.js_object, self.env)

    async def email(self, message):
        headers = message.headers
        print(
            "Incoming email:",
            {
                "from": getattr(message, "from", None),
                "to": getattr(message, "to", None),
                "subject": headers.get("subject"),
                "message_id": headers.get("message-id"),
                "date": headers.get("date"),
                "raw_size": getattr(message, "rawSize", None),
            },
        )
