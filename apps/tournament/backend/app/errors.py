import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException


class AppError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


def install_errors(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, error: Exception):
        logging.getLogger("tournament").error("Unexpected Tournament error", exc_info=error)
        return JSONResponse({"error": "Ocorreu um erro inesperado. Tente novamente."}, status_code=500)

    @app.exception_handler(AppError)
    async def domain_error(_request: Request, error: AppError):
        return JSONResponse({"error": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError):
        if any(item["type"] == "json_invalid" for item in _error.errors()):
            # The legacy Fastify error handler treats malformed JSON as an unexpected error.
            return JSONResponse({"error": "Ocorreu um erro inesperado. Tente novamente."}, status_code=500)
        return JSONResponse({"error": "Os dados enviados não são válidos."}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException):
        return JSONResponse({"error": "O recurso pedido não existe."}, status_code=404 if error.status_code in (404, 405) else error.status_code)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request: Request, error: IntegrityError):
        message = str(error.orig)
        if "UNIQUE constraint failed: league_groups.name" in message:
            return JSONResponse({"error": "Já existe um grupo com esse nome."}, status_code=409)
        if "UNIQUE constraint failed: teams.number" in message:
            return JSONResponse({"error": "Já existe uma equipa com esse número."}, status_code=409)
        return JSONResponse({"error": "Ocorreu um erro inesperado. Tente novamente."}, status_code=500)
