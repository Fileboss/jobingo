from typing import Annotated

from fastapi import APIRouter, Body, Response
from fastapi.responses import JSONResponse

from jobingo.domain.cv_document import CvLang
from jobingo.domain.cv_selection import CvPage, SelectionChoice
from jobingo.services import cv_page
from jobingo_api.deps import CurrentUser, DbConn
from jobingo_api.schemas import Refused

router = APIRouter(prefix="/cv", tags=["cv"])


@router.get("/{lang}/selection")
def get_cv_page(lang: CvLang, user: CurrentUser, conn: DbConn) -> CvPage:
    """The CV with what is on the page. Never chosen means everything is."""
    return cv_page.load_page(conn, user.id, lang)


@router.put(
    "/{lang}/selection",
    response_model=CvPage,
    responses={400: {"model": Refused, "description": "An option that cannot be on"}},
)
def save_cv_selection(
    lang: CvLang, choice: Annotated[SelectionChoice, Body()], user: CurrentUser, conn: DbConn
) -> CvPage | JSONResponse:
    try:
        return cv_page.save_choice(conn, user.id, lang, choice)
    except cv_page.OptionUnavailableError as refused:
        return JSONResponse(status_code=400, content=Refused(message=str(refused)).model_dump())


@router.get(
    "/{lang}/pdf",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            "headers": {
                "X-Page-Count": {"schema": {"type": "integer"}},
                "X-Missing-Items": {
                    "description": "Selected items cut from the PDF: a panel over its page",
                    "schema": {"type": "integer"},
                },
                "Content-Disposition": {"schema": {"type": "string"}},
            },
        },
        503: {"model": Refused, "description": "The PDF could not be produced"},
    },
)
def get_cv_pdf(lang: CvLang, user: CurrentUser, conn: DbConn) -> Response:
    """The PDF of the stored selection."""
    try:
        pdf = cv_page.render_page(conn, user.id, lang)
    except cv_page.CvRenderError as failed:
        return JSONResponse(status_code=503, content=Refused(message=str(failed)).model_dump())
    return Response(
        content=pdf.rendered.pdf,
        media_type="application/pdf",
        headers={
            "X-Page-Count": str(pdf.rendered.pages),
            "X-Missing-Items": str(pdf.missing_items),
            "Content-Disposition": f'inline; filename="{pdf.filename}"',
        },
    )
