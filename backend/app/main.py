"""HTTP layer: routes, access control, dependency wiring and error responses."""

import time
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.access import COOKIE_NAME, AccessGate, LoginLocked, LoginRefused
from app.cases import CaseConflict, CaseNotFound, CaseService, SeatForbidden, TooManyCases, to_view
from app.config import Settings
from app.lawyer import BudgetedLawyer, ClaudeLawyer, Lawyer
from app.limits import SlidingWindowLimiter
from app.models import CaseView, Login, Person, SeatClaim, SeatGrant, SessionView, Submission

DAY_SECONDS = 24 * 60 * 60


def _cases(request: Request) -> CaseService:
    return request.app.state.cases


def _lawyer(request: Request) -> Lawyer:
    return request.app.state.lawyer


def _gate(request: Request) -> AccessGate:
    return request.app.state.gate


Cases = Annotated[CaseService, Depends(_cases)]
CaseLawyer = Annotated[Lawyer, Depends(_lawyer)]
Gate = Annotated[AccessGate, Depends(_gate)]
# The secret a device was given when it claimed its seat.
SeatToken = Annotated[str | None, Header(alias="X-Seat-Token")]


async def require_access(request: Request, gate: Gate) -> None:
    if not gate.is_valid(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Enter the passcode to continue.")


# Needs no passcode: the health check, and the calls that tell a device whether it needs one.
public = APIRouter(prefix="/api")
# Everything else, including the photos, needs the passcode cookie.
protected = APIRouter(prefix="/api", dependencies=[Depends(require_access)])


@public.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@public.get("/session")
async def read_session(request: Request, response: Response, gate: Gate) -> SessionView:
    response.headers["Cache-Control"] = "no-store"
    return SessionView(
        required=gate.required, authenticated=gate.is_valid(request.cookies.get(COOKIE_NAME))
    )


@public.post("/login")
async def login(body: Login, request: Request, response: Response, gate: Gate) -> SessionView:
    try:
        token = gate.login(body.passcode)
    except LoginLocked:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many wrong passcodes. Wait a few minutes and try again.",
        ) from None
    except LoginRefused:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That passcode isn't right.") from None
    if token:
        settings: Settings = request.app.state.settings
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=settings.session_lifetime_seconds,
            httponly=True,  # page scripts cannot read it
            samesite="lax",  # not sent with requests started by other sites
            secure=settings.cookie_secure,
            path="/",
        )
    return SessionView(required=gate.required, authenticated=True)


@protected.get("/photos/{person}.jpg")
async def read_photo(person: Person, request: Request) -> FileResponse:
    path = request.app.state.settings.photos_dir / f"{person}.jpg"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@protected.post("/cases", status_code=status.HTTP_201_CREATED)
async def create_case(cases: Cases) -> CaseView:
    return to_view(cases.create())


@protected.get("/cases/{case_id}")
async def read_case(case_id: UUID, response: Response, cases: Cases) -> CaseView:
    response.headers["Cache-Control"] = "no-store"
    return to_view(cases.get(case_id))


@protected.post("/cases/{case_id}/seats")
async def claim_seat(case_id: UUID, body: SeatClaim, cases: Cases) -> SeatGrant:
    return SeatGrant(person=body.person, token=cases.claim_seat(case_id, body.person))


@protected.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_id: UUID, cases: Cases, seat_token: SeatToken = None) -> None:
    cases.delete(case_id, seat_token)


@protected.post("/cases/{case_id}/statements")
async def submit_statement(
    case_id: UUID, body: Submission, cases: Cases, lawyer: CaseLawyer, seat_token: SeatToken = None
) -> CaseView:
    case = await cases.submit_statement(case_id, body.person, seat_token, body.text, lawyer)
    return to_view(case)


@protected.post("/cases/{case_id}/answers")
async def submit_answer(
    case_id: UUID, body: Submission, cases: Cases, lawyer: CaseLawyer, seat_token: SeatToken = None
) -> CaseView:
    case = await cases.submit_answer(case_id, body.person, seat_token, body.text, lawyer)
    return to_view(case)


@protected.post("/cases/{case_id}/retry")
async def retry_case(
    case_id: UUID, cases: Cases, lawyer: CaseLawyer, seat_token: SeatToken = None
) -> CaseView:
    return to_view(await cases.retry(case_id, seat_token, lawyer))


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message})


def create_app(
    settings: Settings | None = None,
    lawyer: Lawyer | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
) -> FastAPI:
    """Builds the app. Tests pass their own settings, lawyer and clocks."""
    settings = settings or Settings.from_env()
    settings.validate()

    # In production the API's own documentation would show strangers every route.
    hidden = {"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.production else {}
    app = FastAPI(title="Love on Trial API", **hidden)

    app.state.settings = settings
    app.state.gate = AccessGate(
        settings.access_passcode,
        settings.session_secret,
        settings.session_lifetime_seconds,
        SlidingWindowLimiter(settings.login_max_failures, settings.login_window_seconds, clock),
        wall_clock,
    )
    app.state.cases = CaseService(clock, settings.case_ttl_seconds, settings.max_live_cases)
    app.state.lawyer = BudgetedLawyer(
        lawyer or ClaudeLawyer(),
        SlidingWindowLimiter(settings.max_lawyer_calls_per_day, DAY_SECONDS, clock),
    )

    app.add_exception_handler(CaseNotFound, lambda *_: _error(404, "Case not found."))
    app.add_exception_handler(SeatForbidden, lambda _, exc: _error(403, str(exc)))
    app.add_exception_handler(CaseConflict, lambda _, exc: _error(409, str(exc)))
    app.add_exception_handler(
        TooManyCases, lambda *_: _error(429, "The court is full right now. Try again in a little while.")
    )

    app.include_router(public)
    app.include_router(protected)

    # Last, so it only answers paths no API route claimed.
    if settings.frontend_dist and settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app
