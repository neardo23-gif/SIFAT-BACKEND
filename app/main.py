"""SIFAT - Backend (FastAPI): clientes, facturas y pagos sobre MySQL (RDS).

El catálogo de servicios vive en DynamoDB y se consulta por API Gateway.
"""
import logging
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Config
from .errores import ErrorNegocio, ErrorServicioExterno
from .routers import auth, catalogos, clientes, facturas, pagos
from .seguridad import requiere_api_key

log = logging.getLogger("sifat")
logging.basicConfig(level=logging.INFO)


def crear_app(validar_config=True):
    if validar_config:
        Config.validar()

    docs = "/docs" if Config.ENABLE_DOCS else None
    app = FastAPI(title="SIFAT Backend", version="1.0.0", docs_url=docs, redoc_url=None,
                  openapi_url="/openapi.json" if docs else None)

    protegido = [Depends(requiere_api_key)]
    for r in (auth.router, catalogos.router, clientes.router, facturas.router, pagos.router):
        app.include_router(r, dependencies=protegido)

    @app.get("/salud", tags=["Sistema"])
    def salud():
        return {"estado": "ok"}

    @app.middleware("http")
    async def cabeceras_seguras(request: Request, call_next):
        respuesta = await call_next(request)
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    @app.exception_handler(ErrorNegocio)
    async def _negocio(_, exc: ErrorNegocio):
        return JSONResponse(status_code=exc.status, content={"mensaje": exc.mensaje})

    @app.exception_handler(ErrorServicioExterno)
    async def _externo(_, exc: ErrorServicioExterno):
        log.warning("Catálogo de servicios: %s", exc)
        return JSONResponse(status_code=502, content={"mensaje": "El catálogo de servicios no está disponible"})

    @app.exception_handler(RequestValidationError)
    async def _validacion(_, exc: RequestValidationError):
        errores = [{"campo": ".".join(str(p) for p in e["loc"][1:]), "mensaje": e["msg"]}
                   for e in exc.errors()]
        return JSONResponse(status_code=400, content={"mensaje": "Datos inválidos", "errores": errores})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"mensaje": exc.detail})

    @app.exception_handler(Exception)
    async def _interno(_, exc: Exception):
        # El detalle solo va al log; el cliente recibe un id para rastrearlo
        error_id = uuid.uuid4().hex[:12]
        log.exception("Error %s", error_id)
        return JSONResponse(status_code=500, content={"mensaje": "Error interno", "error_id": error_id})

    return app
