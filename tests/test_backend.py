"""Pruebas sin base de datos real: un cursor simulado reemplaza a MySQL."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import db
from app.calculos import TASA_ISR, calcular_concepto, calcular_totales, tasa_isr_para
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
        self.tipo_persona = "F"

    def commit(self):
        self.commits += 1

    def execute(self, sql, params=()):
        self.ejecutado.append((" ".join(sql.split()), params))
        s = sql
        if "FROM clientes c JOIN regimenes_fiscales" in s:
            self._resultado = [{"id_cliente": 1, "activo": 1, "tipo_persona": self.tipo_persona}]
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
    importe, iva, isr = calcular_concepto(Decimal("3"), Decimal("349"), Decimal("0.16"))
    assert (importe, iva, isr) == (Decimal("1047.00"), Decimal("167.52"), Decimal("0.00"))
    sub, iva_t, isr_t, total = calcular_totales([{"importe": importe, "iva_importe": iva,
                                                  "isr_importe": isr}])
    assert total == Decimal("1214.52")


def test_calculo_con_retencion_de_isr():
    importe, iva, isr = calcular_concepto(Decimal("3"), Decimal("349"), Decimal("0.16"), TASA_ISR)
    assert isr == Decimal("104.70")
    sub, iva_t, isr_t, total = calcular_totales([{"importe": importe, "iva_importe": iva,
                                                  "isr_importe": isr}])
    assert (sub, iva_t, isr_t, total) == (Decimal("1047.00"), Decimal("167.52"),
                                          Decimal("104.70"), Decimal("1109.82"))


@pytest.mark.parametrize("tipo, tasa", [("M", Decimal("0.10")), ("F", Decimal("0")), ("FM", Decimal("0"))])
def test_isr_solo_para_personas_morales(tipo, tasa):
    assert tasa_isr_para(tipo) == tasa


def test_redondeo_mitad_hacia_arriba():
    _, iva, _ = calcular_concepto(Decimal("1"), Decimal("0.03"), Decimal("0.5"))
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
    assert insert[-4:] == (Decimal("698.00"), Decimal("111.68"), Decimal("0.00"), Decimal("809.68"))
    assert cursor.commits == 1


def test_factura_a_persona_moral_retiene_isr(cliente_api):
    c, cursor = cliente_api
    cursor.tipo_persona = "M"
    r = c.post("/facturas", headers=H, json={**FACTURA, "conceptos": [
        {"id_servicio": "SRV-001", "cantidad": 2}]})
    assert r.status_code == 201
    insert = next(p for s, p in cursor.ejecutado if s.startswith("INSERT INTO facturas"))
    # 698.00 + 111.68 de IVA - 69.80 de ISR
    assert insert[-4:] == (Decimal("698.00"), Decimal("111.68"), Decimal("69.80"), Decimal("739.88"))
    detalle = next(p for s, p in cursor.ejecutado if s.startswith("INSERT INTO detalle_factura"))
    assert detalle[0][-2:] == (Decimal("0.10"), Decimal("69.80"))


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


# ---------- login ----------
from app import contrasenas  # noqa: E402


def test_contrasena_se_cifra_y_verifica():
    h = contrasenas.cifrar("ClaveSegura2026")
    assert h.startswith("pbkdf2_sha256$600000$") and "ClaveSegura2026" not in h
    assert contrasenas.verificar("ClaveSegura2026", h)
    assert not contrasenas.verificar("otra", h)
    assert not contrasenas.verificar("x", "basura")


def test_contrasena_robusta():
    assert contrasenas.es_robusta("ClaveSegura2026")
    assert not contrasenas.es_robusta("corta1")
    assert not contrasenas.es_robusta("sololetraslargas")


class CursorLogin(CursorFalso):
    def __init__(self, usuario):
        super().__init__()
        self.usuario = usuario

    def execute(self, sql, params=()):
        self.ejecutado.append((" ".join(sql.split()), params))
        self._resultado = [self.usuario] if ("FROM usuarios WHERE email" in sql and self.usuario) else []


@pytest.fixture
def login_api(monkeypatch):
    monkeypatch.setattr(Config, "BACKEND_API_KEY", CLAVE)

    def crear(usuario):
        cursor = CursorLogin(usuario)
        app = crear_app(validar_config=False)

        def conexion_falsa():
            yield cursor

        app.dependency_overrides[db.obtener_conexion] = conexion_falsa
        return TestClient(app), cursor
    return crear


def _usuario(**extra):
    base = {"id_usuario": 1, "nombre": "Ana", "email": "ana@sifat.mx", "rol": "Administrador",
            "activo": 1, "password_hash": contrasenas.cifrar("ClaveSegura2026"),
            "intentos_fallidos": 0, "bloqueado": 0}
    return {**base, **extra}


def test_login_correcto(login_api):
    c, cursor = login_api(_usuario())
    r = c.post("/auth/login", headers=H, json={"email": "ana@sifat.mx", "password": "ClaveSegura2026"})
    assert r.status_code == 200
    assert r.json() == {"id_usuario": 1, "nombre": "Ana", "email": "ana@sifat.mx", "rol": "Administrador"}
    assert "password_hash" not in r.text


def test_login_incorrecto_suma_intento(login_api):
    c, cursor = login_api(_usuario(intentos_fallidos=1))
    r = c.post("/auth/login", headers=H, json={"email": "ana@sifat.mx", "password": "mala"})
    assert r.status_code == 401 and r.json()["mensaje"] == "Correo o contraseña incorrectos"
    assert any("intentos_fallidos = %s" in s and p == (2, 1) for s, p in cursor.ejecutado)


def test_quinto_intento_bloquea(login_api):
    c, cursor = login_api(_usuario(intentos_fallidos=4))
    c.post("/auth/login", headers=H, json={"email": "ana@sifat.mx", "password": "mala"})
    assert any("bloqueado_hasta = CURRENT_TIMESTAMP + INTERVAL" in s for s, _ in cursor.ejecutado)


def test_cuenta_bloqueada_no_entra_ni_con_contrasena_correcta(login_api):
    c, _ = login_api(_usuario(bloqueado=1))
    r = c.post("/auth/login", headers=H, json={"email": "ana@sifat.mx", "password": "ClaveSegura2026"})
    assert r.status_code == 423


def test_correo_inexistente_mismo_mensaje(login_api):
    c, _ = login_api(None)
    r = c.post("/auth/login", headers=H, json={"email": "nadie@sifat.mx", "password": "x"})
    assert r.status_code == 401 and r.json()["mensaje"] == "Correo o contraseña incorrectos"


def test_usuario_sin_contrasena_no_entra(login_api):
    c, _ = login_api(_usuario(password_hash=None))
    r = c.post("/auth/login", headers=H, json={"email": "ana@sifat.mx", "password": ""+"x"})
    assert r.status_code == 401


def test_login_requiere_clave_del_frontend(login_api):
    c, _ = login_api(_usuario())
    assert c.post("/auth/login", json={"email": "ana@sifat.mx", "password": "x"}).status_code == 401


# ---------------- Usuarios ----------------
class CursorUsuarios(CursorFalso):
    """Simula la tabla usuarios: guarda lo insertado y responde al SELECT."""

    def __init__(self, existentes=()):
        super().__init__()
        self.correos = set(existentes)
        self.insertado = None

    def execute(self, sql, params=()):
        self.ejecutado.append((" ".join(sql.split()), params))
        if "SELECT 1 FROM usuarios WHERE email" in sql:
            self._resultado = [{"1": 1}] if params[0] in self.correos else []
        elif "INSERT INTO usuarios" in sql:
            self.insertado = params
            self.lastrowid = 9
            self._resultado = []
        elif "FROM usuarios" in sql and "WHERE id_usuario" in sql:
            nombre, email, _, rol = self.insertado
            self._resultado = [{"id_usuario": 9, "nombre": nombre, "email": email, "rol": rol,
                                "activo": 1, "ultimo_acceso": None, "tiene_contrasena": 1}]
        else:
            self._resultado = []


@pytest.fixture
def usuarios_api(monkeypatch):
    monkeypatch.setattr(Config, "BACKEND_API_KEY", CLAVE)

    def crear(existentes=()):
        cursor = CursorUsuarios(existentes)
        app = crear_app(validar_config=False)

        def conexion_falsa():
            yield cursor

        app.dependency_overrides[db.obtener_conexion] = conexion_falsa
        return TestClient(app), cursor
    return crear


NUEVO = {"nombre": "María José", "apellidos": "Pérez López", "email": "MJ.Perez@Sifat.mx",
         "password": "Facturas2026xyz", "rol": "Facturista"}


def test_alta_de_usuario_cifra_la_contrasena(usuarios_api):
    c, cursor = usuarios_api()
    r = c.post("/usuarios", headers=H, json=NUEVO)
    assert r.status_code == 201
    nombre, email, hash_guardado, rol = cursor.insertado
    assert (nombre, email, rol) == ("María José Pérez López", "mj.perez@sifat.mx", "Facturista")
    # Se guarda el hash, nunca la contraseña, y el hash verifica
    assert "Facturas2026xyz" not in hash_guardado
    assert contrasenas.verificar("Facturas2026xyz", hash_guardado)
    assert "password" not in r.text and "Facturas2026xyz" not in r.text
    assert cursor.commits == 1


def test_el_nuevo_usuario_puede_iniciar_sesion(usuarios_api, login_api):
    c, cursor = usuarios_api()
    c.post("/usuarios", headers=H, json=NUEVO)
    nombre, email, hash_guardado, rol = cursor.insertado
    c2, _ = login_api(_usuario(id_usuario=9, nombre=nombre, email=email, rol=rol,
                               password_hash=hash_guardado))
    r = c2.post("/auth/login", headers=H, json={"email": email, "password": "Facturas2026xyz"})
    assert r.status_code == 200 and r.json()["rol"] == "Facturista"


def test_correo_repetido_responde_409(usuarios_api):
    c, cursor = usuarios_api(existentes={"mj.perez@sifat.mx"})
    r = c.post("/usuarios", headers=H, json=NUEVO)
    assert r.status_code == 409 and cursor.insertado is None


@pytest.mark.parametrize("cambio, codigo", [
    ({"password": "corta1"}, 422),                       # menos de 12
    ({"password": "solamenteletras"}, 422),              # sin números
    ({"password": "123456789012"}, 422),                 # sin letras
    ({"password": "mj.perez2026abc"}, 422),              # contiene el correo
    ({"password": "aaaa1111aaaa1111"}, 422),             # demasiado repetitiva
    ({"nombre": "Ana1"}, 400),                           # número en el nombre
    ({"nombre": "<script>"}, 400),
    ({"apellidos": "A"}, 400),                           # muy corto
    ({"nombre": "Ana  María"}, 400),                     # doble espacio
    ({"email": "no-es-correo"}, 400),
    ({"rol": "Gerente"}, 400),                           # rol no permitido
    ({"rol": "Root"}, 400),
    ({"activo": False}, 400),                            # campo no declarado
])
def test_alta_de_usuario_valida_todo(usuarios_api, cambio, codigo):
    c, cursor = usuarios_api()
    r = c.post("/usuarios", headers=H, json={**NUEVO, **cambio})
    assert r.status_code == codigo, r.json()
    assert cursor.insertado is None


def test_alta_de_usuario_pide_clave_del_frontend(usuarios_api):
    c, _ = usuarios_api()
    assert c.post("/usuarios", json=NUEVO).status_code == 401


def test_lista_de_usuarios_sin_hash(usuarios_api):
    c, cursor = usuarios_api()
    r = c.get("/usuarios", headers=H)
    assert r.status_code == 200 and r.json() == {"total": 0, "usuarios": []}
    assert "password_hash IS NOT NULL AS tiene_contrasena" in cursor.ejecutado[0][0]


# ---------------- Administración de usuarios y cambio de contraseña ----------------
class TablaUsuarios(CursorFalso):
    """Tabla usuarios en memoria que entiende las consultas de usuarios.py y auth.py."""

    def __init__(self, filas):
        super().__init__()
        self.filas = {f["id_usuario"]: dict(f) for f in filas}

    def _publica(self, u):
        return {"id_usuario": u["id_usuario"], "nombre": u["nombre"], "email": u["email"], "rol": u["rol"],
                "activo": u["activo"], "ultimo_acceso": None, "tiene_contrasena": u["password_hash"] is not None}

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        self.ejecutado.append((s, params))
        self._resultado = []
        if s.startswith("SELECT COUNT(*) AS n FROM usuarios"):
            n = sum(1 for u in self.filas.values() if u["rol"] == "Administrador" and u["activo"]
                    and u["id_usuario"] != params[0])
            self._resultado = [{"n": n}]
        elif "FROM usuarios WHERE id_usuario = %s" in s:
            u = self.filas.get(params[0])
            if u:
                self._resultado = [self._publica(u) if "tiene_contrasena" in s else {**u, "bloqueado": 0}]
        elif s.startswith("UPDATE usuarios SET password_hash"):
            self.filas[params[1]].update(password_hash=params[0], intentos_fallidos=0)
        elif s.startswith("UPDATE usuarios SET intentos_fallidos = %s"):
            self.filas[params[1]]["intentos_fallidos"] = params[0]
        elif s.startswith("UPDATE usuarios SET") and "WHERE id_usuario = %s" in s:
            columnas = [c.split(" = ")[0] for c in s.split("SET ")[1].split(" WHERE")[0].split(", ")]
            self.filas[params[-1]].update(dict(zip(columnas, params[:-1])))


def _fila(id_usuario, rol="Administrador", activo=True, password="ClaveSegura2026", **extra):
    return {"id_usuario": id_usuario, "nombre": f"Persona {id_usuario}", "email": f"p{id_usuario}@sifat.mx",
            "rol": rol, "activo": activo, "password_hash": contrasenas.cifrar(password),
            "intentos_fallidos": 0, **extra}


@pytest.fixture
def tabla_api(monkeypatch):
    monkeypatch.setattr(Config, "BACKEND_API_KEY", CLAVE)

    def crear(*filas):
        cursor = TablaUsuarios(filas)
        app = crear_app(validar_config=False)

        def conexion_falsa():
            yield cursor

        app.dependency_overrides[db.obtener_conexion] = conexion_falsa
        return TestClient(app), cursor
    return crear


def test_desactivar_usuario(tabla_api):
    c, t = tabla_api(_fila(1), _fila(2, rol="Facturista"))
    r = c.patch("/usuarios/2", headers=H, json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False
    assert t.filas[2]["activo"] is False


def test_no_se_desactiva_al_ultimo_administrador(tabla_api):
    c, t = tabla_api(_fila(1), _fila(2, rol="Facturista"))
    r = c.patch("/usuarios/1", headers=H, json={"activo": False})
    assert r.status_code == 409 and "al menos un Administrador" in r.json()["mensaje"]
    assert t.filas[1]["activo"] is True
    # Tampoco quitándole el rol
    assert c.patch("/usuarios/1", headers=H, json={"rol": "Facturista"}).status_code == 409


def test_con_otro_admin_si_se_puede_desactivar(tabla_api):
    c, _ = tabla_api(_fila(1), _fila(3))
    assert c.patch("/usuarios/1", headers=H, json={"activo": False}).status_code == 200


@pytest.mark.parametrize("cuerpo", [{}, {"activo": "no"}, {"rol": "Gerente"}, {"email": "x@y.mx"}])
def test_modificar_usuario_valida(tabla_api, cuerpo):
    c, _ = tabla_api(_fila(1), _fila(2, rol="Facturista"))
    assert c.patch("/usuarios/2", headers=H, json=cuerpo).status_code == 400


def test_modificar_usuario_inexistente(tabla_api):
    c, _ = tabla_api(_fila(1))
    assert c.patch("/usuarios/99", headers=H, json={"activo": False}).status_code == 404


def test_restablecer_contrasena_y_entrar(tabla_api, login_api):
    c, t = tabla_api(_fila(1), _fila(2, rol="Facturista", intentos_fallidos=3))
    r = c.post("/usuarios/2/contrasena", headers=H, json={"password": "OtraClave2027xy"})
    assert r.status_code == 200
    assert t.filas[2]["intentos_fallidos"] == 0  # se desbloquea
    assert contrasenas.verificar("OtraClave2027xy", t.filas[2]["password_hash"])
    assert not contrasenas.verificar("ClaveSegura2026", t.filas[2]["password_hash"])


@pytest.mark.parametrize("password", ["corta1", "Persona2026abcd", "p2p2p2p2p2p2"])
def test_restablecer_contrasena_valida_reglas(tabla_api, password):
    c, t = tabla_api(_fila(1), _fila(2, rol="Facturista"))
    antes = t.filas[2]["password_hash"]
    assert c.post("/usuarios/2/contrasena", headers=H, json={"password": password}).status_code == 422
    assert t.filas[2]["password_hash"] == antes


def test_cambiar_mi_contrasena(tabla_api):
    c, t = tabla_api(_fila(2, rol="Facturista"))
    r = c.post("/auth/cambiar-contrasena", headers=H,
               json={"id_usuario": 2, "actual": "ClaveSegura2026", "nueva": "MiNuevaClave2027"})
    assert r.status_code == 200
    assert contrasenas.verificar("MiNuevaClave2027", t.filas[2]["password_hash"])


def test_cambiar_mi_contrasena_con_la_actual_mal_suma_intento(tabla_api):
    c, t = tabla_api(_fila(2, rol="Facturista", intentos_fallidos=1))
    r = c.post("/auth/cambiar-contrasena", headers=H,
               json={"id_usuario": 2, "actual": "equivocada", "nueva": "MiNuevaClave2027"})
    assert r.status_code == 403 and r.json()["mensaje"] == "La contraseña actual no es correcta"
    assert t.filas[2]["intentos_fallidos"] == 2
    assert contrasenas.verificar("ClaveSegura2026", t.filas[2]["password_hash"])


def test_cambiar_mi_contrasena_quinto_error_bloquea(tabla_api):
    c, t = tabla_api(_fila(2, rol="Facturista", intentos_fallidos=4))
    c.post("/auth/cambiar-contrasena", headers=H,
           json={"id_usuario": 2, "actual": "equivocada", "nueva": "MiNuevaClave2027"})
    assert any("bloqueado_hasta = CURRENT_TIMESTAMP + INTERVAL" in s for s, _ in t.ejecutado)


@pytest.mark.parametrize("nueva, mensaje", [("ClaveSegura2026", "distinta"), ("corta1", "12 caracteres")])
def test_cambiar_mi_contrasena_valida_la_nueva(tabla_api, nueva, mensaje):
    c, _ = tabla_api(_fila(2, rol="Facturista"))
    r = c.post("/auth/cambiar-contrasena", headers=H,
               json={"id_usuario": 2, "actual": "ClaveSegura2026", "nueva": nueva})
    assert r.status_code == 422 and mensaje in r.json()["mensaje"]


def test_usuario_inactivo_no_cambia_contrasena(tabla_api):
    c, _ = tabla_api(_fila(2, rol="Facturista", activo=False))
    r = c.post("/auth/cambiar-contrasena", headers=H,
               json={"id_usuario": 2, "actual": "ClaveSegura2026", "nueva": "MiNuevaClave2027"})
    assert r.status_code == 404


def test_obtener_usuario(tabla_api):
    c, _ = tabla_api(_fila(2, rol="Facturista"))
    r = c.get("/usuarios/2", headers=H)
    assert r.status_code == 200 and r.json()["rol"] == "Facturista" and "password_hash" not in r.text
    assert c.get("/usuarios/99", headers=H).status_code == 404


def test_contrasena_con_el_nombre_sin_acento_se_rechaza(usuarios_api):
    c, cursor = usuarios_api()
    r = c.post("/usuarios", headers=H, json={**NUEVO, "password": "Perez2026clave"})  # nombre: Pérez
    assert r.status_code == 422 and "nombre" in r.json()["mensaje"] and cursor.insertado is None
