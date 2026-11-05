from pydantic import BaseModel


class Refused(BaseModel):
    """A request refused for a reason the user can read, in French."""

    message: str
