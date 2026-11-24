"""Collaboration token issuance router placeholder for Phase 7."""

from fastapi import APIRouter

router = APIRouter(
    prefix="/boards/{board_id}/collaboration-token",
    tags=["Collaboration"],
)
