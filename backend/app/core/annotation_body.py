"""Bound JSON draft requests before FastAPI parses them, including streamed bodies."""
import re

from starlette.responses import JSONResponse

from app.schemas.annotation_draft import MAX_DRAFT_BYTES


class AnnotationBodyLimit:
    def __init__(self, app, *, prefix):
        self.app = app
        self.pattern = re.compile(re.escape(prefix) +
            r"(?:/cases/[^/]+/annotation-drafts(?:/[^/]+)?|/review-assignments/[^/]+/(?:draft|annotation-draft|submit|amendments)|/review-adjudications/[^/]+/(?:draft|submit)|/review-studies(?:/[^/]+/adjudicator)?)/?$")

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT"} or not self.pattern.fullmatch(path):
            return await self.app(scope, receive, send)

        async def reject(status, message):
            await JSONResponse({"detail": message}, status_code=status, headers={"Cache-Control": "no-store"})(scope, receive, send)

        lengths = [v for k, v in scope.get("headers", []) if k.lower() == b"content-length"]
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                return await reject(400, "Invalid Content-Length")
            declared = lengths[0].lstrip(b"0") or b"0"
            maximum = str(MAX_DRAFT_BYTES).encode()
            if len(declared) > len(maximum) or len(declared) == len(maximum) and declared > maximum:
                return await reject(413, "Annotation request exceeds 2 MiB")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_DRAFT_BYTES:
                return await reject(413, "Annotation request exceeds 2 MiB")
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        pending = iter([{"type": "http.request", "body": bytes(body), "more_body": False}])

        async def replay():
            value = next(pending, None)
            return value if value is not None else await receive()

        await self.app(scope, replay, send)
