"""Streaming request bound for the explicitly opted-in real-volume endpoint."""
from starlette.responses import JSONResponse

MAX_REAL_VOLUME_REQUEST_BYTES = 1024 * 1024 * 1024 + 2 * 1024 * 1024


class RealVolumeResearchBodyLimit:
    def __init__(self, app, *, path: str):
        self.app = app
        self.path = path

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        if scope.get("type") != "http" or scope.get("method") != "POST" or path.rstrip("/") != self.path:
            return await self.app(scope, receive, send)

        async def reject():
            response = JSONResponse({"detail": "Real-volume upload exceeds the configured request limit."}, status_code=413,
                                    headers={"Cache-Control": "no-store"})
            await response(scope, receive, send)

        lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit() or int(lengths[0]) > MAX_REAL_VOLUME_REQUEST_BYTES:
                return await reject()

        total = 0
        async def limited_receive():
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > MAX_REAL_VOLUME_REQUEST_BYTES:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            await reject()


class _RequestTooLarge(Exception):
    pass
