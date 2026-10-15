"""Errores de la aplicación y cómo se convierten en respuestas HTTP."""


class ErrorNegocio(Exception):
    """Regla de negocio no cumplida: se informa al cliente tal cual (422 o el status dado)."""

    def __init__(self, mensaje, status=422):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


class ErrorServicioExterno(Exception):
    """Falla al consultar el catálogo de servicios (API Gateway)."""
