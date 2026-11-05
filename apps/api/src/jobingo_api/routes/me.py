from fastapi import APIRouter

from jobingo.domain.users import User
from jobingo_api.deps import CurrentUser

router = APIRouter(tags=["account"])


@router.get("/me")
def get_me(user: CurrentUser) -> User:
    return user
