"""Read-only reference research display using existing authentication/RBAC."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.config import settings
from app.core.dependencies import require_roles
from app.core.roles import Role
from app.models import User
from app.services.reference_profiles import (
    GATE_ID, ReferenceDisplayUnavailable, load_reference_profiles,
)

router = APIRouter(prefix="/research", tags=["Reference research display"])
ReferenceReader = Annotated[User, Depends(require_roles(Role.ADMIN, Role.DATA_SCIENTIST, Role.RESEARCHER))]


@router.get("/reference-profiles", response_class=Response)
def reference_profiles(current_user: ReferenceReader):
    try:
        data = load_reference_profiles(settings.VASCULAI_REFERENCE_PROFILE_DIR)
    except (ReferenceDisplayUnavailable, OSError):
        raise HTTPException(503, "Approved reference profile evidence unavailable or identity check failed") from None
    return Response(data, media_type="application/json", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "X-Reference-Display-Gate": GATE_ID,
    })
