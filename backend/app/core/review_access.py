"""Fail-closed, application-wide account separation for assigned CT readers.

This supplements existing RBAC; it neither creates credentials nor decodes JWTs
itself. Qualification/outside knowledge are not established by this restriction.
"""
import re

from fastapi import HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy import select, text

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.database.session import SessionLocal
from app.models import User
from app.models.review_assignment import ReviewAssignment
from app.models.review_adjudication import AdjudicationAssignment
from app.services.audit import record_event

UUID = r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"


def enforce_review_access(request: Request):
    path = request.scope.get("path", "").rstrip("/")
    root = request.scope.get("root_path", "")
    if root and path.startswith(root+"/"):path = path[len(root):]
    prefix = settings.API_V1_STR
    if not path.startswith(prefix+"/"):
        yield
        return
    relative = path[len(prefix):]
    safe_auth = {("POST", "/auth/login"), ("POST", "/auth/register"),
                 ("POST", "/auth/logout"), ("GET", "/auth/me"),
                 ("PATCH", "/auth/me"), ("POST", "/auth/password")}
    if (request.method, relative) in safe_auth:
        yield
        return
    # Preserve unauthenticated public registration/normal route error behavior.
    # Protected routes still use their existing mandatory authentication.
    if not request.headers.get("Authorization"):
        yield
        return
    scheme, token = get_authorization_scheme_param(request.headers.get("Authorization"))
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Invalid or expired access token")
    # A separate transaction holds the access lock through response completion,
    # even when the endpoint commits its own business transaction early.
    with SessionLocal() as db:
        actor = get_current_user(token, db)
        version = actor.token_version
        if db.bind.dialect.name == "postgresql":
            # Separate advisory namespace avoids self-deadlocks with endpoint
            # transactions that legitimately lock the same user's row.
            db.execute(text("SELECT pg_advisory_xact_lock_shared(1447121731, :actor)"), {"actor": actor.id})
        db.refresh(actor)
        if not actor.is_active or actor.token_version != version:
            raise HTTPException(401, "Invalid or expired access token")
        assigned = db.scalar(select(ReviewAssignment.id).where(ReviewAssignment.reviewer_id == actor.id).limit(1))
        adjudicator = db.scalar(select(AdjudicationAssignment.id).where(AdjudicationAssignment.reviewer_id == actor.id).limit(1))
        if assigned is None and adjudicator is None:
            # Persist exposure BEFORE executing the endpoint, on a separate
            # transaction while the access lock stays held. A failed business
            # commit or interrupted stream cannot erase evidence of access.
            if not relative.startswith(("/review-", "/auth/")):
                try:
                    with SessionLocal() as audit:
                        record_event(audit, "review.prior_workspace_access", actor.id)
                        audit.commit()
                except Exception:
                    raise HTTPException(503, "Review access auditing is unavailable; workspace access was not started") from None
            yield
            return
        allowed = request.method == "GET" and relative == "/review-assignments"
        allowed = allowed or request.method == "GET" and bool(re.fullmatch(r"/review-assignments/"+UUID+r"(?:/source|/draft|/annotation-draft|/annotation-history|/submission|/amendments)?", relative))
        allowed = allowed or request.method == "PUT" and bool(re.fullmatch(r"/review-assignments/"+UUID+r"/(?:draft|annotation-draft)", relative))
        allowed = allowed or request.method == "POST" and bool(re.fullmatch(r"/review-assignments/"+UUID+r"/submit",relative))
        allowed = allowed or request.method == "POST" and bool(re.fullmatch(r"/review-assignments/"+UUID+r"/amendments",relative))
        if adjudicator is not None:
            allowed = assigned is None and (
                request.method == 'GET' and (relative == '/review-adjudications' or bool(re.fullmatch(r'/review-adjudications/'+UUID+r'(?:/source|/versions/[1-9][0-9]{0,9})?', relative)))
                or request.method == 'PUT' and bool(re.fullmatch(r'/review-adjudications/'+UUID+r'/draft', relative))
                or request.method == 'POST' and bool(re.fullmatch(r'/review-adjudications/'+UUID+r'/submit', relative)))
        if not allowed:
            record_event(db, "review.blinded_access_denied", actor.id)
            db.commit()
            raise HTTPException(403, "This assigned account is restricted to its own original CT review. Use Assigned CT review; AI outputs and other reviews are unavailable.")
        yield
