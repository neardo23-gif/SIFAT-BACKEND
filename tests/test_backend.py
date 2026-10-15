"""Pruebas sin base de datos real: un cursor simulado reemplaza a MySQL."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import db
from app.calculos import calcular_concepto, calcular_totales
from app.config import Config
from app.main import crear_app
from app.routers import facturas

CLAVE = "clave-de-prueba-con-mas-de-24-caracteres"


class CursorFalso:
    """Responde según el texto del SQL y registra todo lo que se ejecuta."""

    def __init__(self):
        self.ejecutado = []
        self.lastrowid = 7
        self._resultado = []
        self.connection = self
        self.commits = 0
        self.pagos_previos = Decimal("0")

    def commit(self):
        self.commits += 1

    def execute(self, sql, params=()):
        self.ejecutado.append((" ".join(sql.split()), params))
        s = sql
        if "FROM clientes WHERE id_cliente" in s:
            self._resultado = [{"id_cliente": 1, "activo": 1}]
        elif "FROM usuarios WHERE" in s:
            self._resultado = [{"1": 1}]
        elif "FROM formas_pago WHERE clave" in s:
            self._resultado = [{"id": 2, "id_forma": 2}]
        elif "FROM metodos_pago WHERE clave" in s:
            self._resultado = [{"id": 1}]
        elif "FROM impuestos WHERE" in s:
            self._resultado = [{"id": 1}]
        elif "SELECT id_factura, total, estatus FROM facturas" in s:
            self._resultado = [{"id_factura": 7, "total": Decimal("404.84"), "estatus": "vigente"}]
        elif "COALESCE(SUM(monto)" in s:
            self._resultado = [{"pagado": self.pagos_previos}]
        elif "FROM facturas f" in s and "WHERE f.folio" in s:
            self._resultado = [{"id_factura": 7, "folio": "FAC-0007", "total": Decimal("404.84"),
                                "estatus": "vigente"}]
        elif "FROM pagos p" in s and "WHERE p.id_pago" in s:
            self._resultado = [{"id_pago": 1, "folio": "FAC-0007", "monto": Decimal("100.00")}]
        else:
            self._resultado = []

    def executemany(self, sql, filas):
        self.ejecutado.append((" ".join(sql.split()), list(filas)))

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)


@pytest.fixture
def cliente_api(monkeypatch):
    monkeypatch.setattr(Config, "BACKEND_API_KEY", CLAVE)
    cursor = CursorFalso()
    app = crear_app(validar_config=False)

    def conexion_falsa():
        yield cursor

    app.dependency_overrides[db.obtener_conexion] = conexion_falsa
    monkeypatch.setattr(facturas, "obtener_servicio", lambda sid: {
        "id_servicio": sid, "clave": "HOST-BAS", "nombre": "Hosting Basico",
        "precio_unitario": Decimal("349"), "impuesto_nombre": "IVA",
        "impuesto_tasa": Decimal("0.16"), "impuesto_tipo": "traslado",
    })
    return TestClient(app), cursor


H = {"X-API-Key": CLAVE}
FACTURA = {"id_cliente": 1, "id_usuario": 1, "clave_forma_pago": "03",
           "clave_metodo_pago": "PUE", "conceptos": [{"id_servicio": "SRV-001", "cantidad": 1}]}


# ---------- cálculos ----------
def test_calculo_concepto_y_totales():
    importe, iva = calcular_concepto(Decimal("3"), Decimal("349"), Decimal("0.16"))
    assert (importe, iva) == (Decimal("1047.00"), Decimal("167.52"))
    sub, iva_t, total = calcular_totales([{"importe": importe, "iva_importe": iva}])
    assert total == Decimal("1214.52")


def test_redondeo_mitad_hacia_arriba():
    _, iva = calcular_concepto(Decimal("1"), Decimal("0.03"), Decimal("0.5"))
    assert iva == Decimal("0.02")


# ---------- seguridad ----------
def test_sin_clave_responde_401(cliente_api):
    c, _ = cliente_api
    assert c.get("/clientes").status_code == 401
    assert c.get("/clientes", headers={"X-API-Key": "otra"}).status_code == 401


def test_salud_no_requiere_clave(cliente_api):
    c, _ = cliente_api
    assert c.get("/salud").json() == {"estado": "ok"}


def test_campo_inventado_se_rechaza(cliente_api):
    c, _ = cliente_api
    r = c.post("/facturas", headers=H, json={**FACTURA, "total": 1})
    assert r.status_code == 400


def test_rfc_invalido_se_rechaza(cliente_api):
    c, _ = cliente_api
    r = c.post("/clientes", headers=H, json={
        "rfc": "x' OR 1=1--", "razon_social": "A", "cp_fiscal": "62000",
        "clave_regimen": "601", "clave_uso": "G03"})
    assert r.status_code == 400


def test_cantidad_negativa_se_rechaza(cliente_api):
    c, _ = cliente_api
    malo = {**FACTURA, "conceptos": [{"id_servicio": "SRV-001", "cantidad": -1}]}
    assert c.post("/facturas", headers=H, json=malo).status_code == 400


def test_consultas_siempre_parametrizadas(cliente_api):
    c, cursor = cliente_api
    c.post("/facturas", headers=H, json=FACTURA)
    for sql, _ in cursor.ejecutado:
        assert "SRV-001" not in sql and "FAC-" not in sql


# ---------- reglas de negocio ----------
def test_factura_calcula_totales_en_servidor(cliente_api):
    c, cursor = cliente_api
    r = c.post("/facturas", headers=H, json={**FACTURA, "conceptos": [
        {"id_servicio": "SRV-001", "cantidad": 2}]})
    assert r.status_code == 201
    insert = next(p for s, p in cursor.ejecutado if s.startswith("INSERT INTO facturas"))
    assert insert[-3:] == (Decimal("698.00"), Decimal("111.68"), Decimal("809.68"))
    assert cursor.commits == 1


def test_pago_mayor_al_saldo_se_rechaza(cliente_api):
    c, cursor = cliente_api
    cursor.pagos_previos = Decimal("400.00")
    r = c.post("/pagos", headers=H, json={"folio": "FAC-0007", "clave_forma_pago": "03", "monto": 10})
    assert r.status_code == 422 and "saldo" in r.json()["mensaje"]
    assert cursor.commits == 0


def test_pago_que_liquida_marca_factura_pagada(cliente_api):
    c, cursor = cliente_api
    r = c.post("/pagos", headers=H, json={"folio": "FAC-0007", "clave_forma_pago": "03",
                                           "monto": "404.84"})
    assert r.status_code == 201 and r.json()["factura_pagada"] is True
    assert any("SET estatus = 'pagada'" in s for s, _ in cursor.ejecutado)


def test_error_interno_no_revela_detalles(cliente_api, monkeypatch):
    c, _ = cliente_api

    def explota(_):
        raise RuntimeError("password=secreta host=rds")

    monkeypatch.setattr(facturas, "obtener_servicio", explota)
    c2 = TestClient(c.app, raise_server_exceptions=False)
    r = c2.post("/facturas", headers=H, json=FACTURA)
    assert r.status_code == 500 and "secreta" not in r.text


# ---------- transacción real (sin servidor) ----------
def test_transaccion_hace_rollback_si_falla(monkeypatch):
    estado = {}

    class ConexionFalsa:
        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def commit(self):
            estado["commit"] = True

        def rollback(self):
            estado["rollback"] = True

        def close(self):
            estado["close"] = True

    monkeypatch.setattr(db, "conectar", lambda: ConexionFalsa())
    with pytest.raises(ValueError):
        with db.transaccion():
            raise ValueError("falla a la mitad")
    assert estado == {"rollback": True, "close": True}
