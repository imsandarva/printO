"""Build the web app. This file wires routes and safety checks; it does not decide how printing works."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from printo.errors import UserError
from printo.http import admin, customer
from printo.http.guard import blocked
from printo.http.respond import fail
from printo.messages import hidden, try_again, unexpected, validation
from printo.runtime import start, stop
from printo.wiring import Context

log = logging.getLogger("printo.http")


def create_app(ctx: Context) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await start(ctx)
        try:
            yield
        finally:
            await stop(ctx)

    app = FastAPI(title="printO", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.ctx = ctx
    app.middleware("http")(_guard)
    app.add_exception_handler(UserError, _user_error)
    app.add_exception_handler(RequestValidationError, _bad_request)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected)
    app.include_router(customer.router)
    app.include_router(admin.router)
    return app


async def _guard(request: Request, call_next):
    response = blocked(request, request.app.state.ctx.settings)
    if response is not None:
        return response
    return await call_next(request)


async def _user_error(_request: Request, exc: UserError):
    return fail(exc.message, exc.status)


async def _bad_request(_request: Request, _exc: RequestValidationError):
    return fail(validation(), 400)


async def _http_error(_request: Request, exc: HTTPException):
    if exc.status_code == 404:
        return fail(hidden(), 404)
    if exc.status_code == 405:
        return fail(try_again(), 405)
    return fail(unexpected(), exc.status_code)


async def _unexpected(request: Request, _exc: Exception):
    log.exception("unexpected failure on %s", request.url.path)
    return fail(unexpected(), 500)
