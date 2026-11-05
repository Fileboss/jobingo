from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from jobingo.db import Pool
from jobingo_api.deps import get_pool

router = APIRouter(tags=["system"])


class Health(BaseModel):
    database: Literal["ok", "unavailable"]


@router.get(
    "/health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Health}},
)
def get_health(pool: Annotated[Pool, Depends(get_pool)], response: Response) -> Health:
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(database="unavailable")
    return Health(database="ok")
