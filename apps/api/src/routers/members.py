"""Board membership and permissions router placeholder for Phase 4."""

from fastapi import APIRouter

router = APIRouter(
    prefix="/boards/{board_id}/members",
    tags=["Board Members"],
)
