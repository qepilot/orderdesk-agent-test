"""REST API conventions shared by every /api/v1 endpoint."""

from fastapi import APIRouter

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
