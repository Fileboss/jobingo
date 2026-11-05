from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class SpaFiles(StaticFiles):
    """Serve the built client: a path that is no file is a client-side route."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            is_api = path == "api" or path.startswith("api/")
            if error.status_code != 404 or is_api:
                raise
            return await super().get_response("index.html", scope)
