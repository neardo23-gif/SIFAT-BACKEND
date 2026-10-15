"""Clientes. No se borran: se desactivan (activo = FALSE)."""
from fastapi import APIRouter, Depends, Query

from ..db import obtener_conexion
from ..errores import ErrorNegocio
from ..esquemas import ClienteCambios, ClienteNuevo

router = APIRouter(prefix="/clientes", tags=["Clientes"])

SELECT_CLIENTE = """
    SELECT c.id_cliente, c.rfc, c.razon_social, c.cp_fiscal, c.email, c.telefono,
           c.activo, c.fecha_registro,
           r.clave AS clave_regimen, r.descripcion AS regimen,
           u.clave AS clave_uso, u.descripcion AS uso_cfdi
    FROM clientes c
    JOIN regimenes_fiscales r ON r.id_regimen = c.id_regimen
    JOIN usos_cfdi u ON u.id_uso = c.id_uso
"""


def _id_por_clave(cur, tabla_columna, clave, nombre):
    # tabla_columna viene de este archivo, nunca del usuario
    tabla, columna = tabla_columna
    cur.execute(f"SELECT {columna} AS id FROM {tabla} WHERE clave = %s", (clave,))
    fila = cur.fetchone()
    if not fila:
        raise ErrorNegocio(f'La clave de {nombre} "{clave}" no existe en el catálogo')
    return fila["id"]


REGIMEN = ("regimenes_fiscales", "id_regimen")
USO = ("usos_cfdi", "id_uso")


def _obtener(cur, id_cliente):
    cur.execute(SELECT_CLIENTE + " WHERE c.id_cliente = %s", (id_cliente,))
    fila = cur.fetchone()
    if not fila:
        raise ErrorNegocio("Cliente no encontrado", status=404)
    fila["activo"] = bool(fila["activo"])
    return fila


@router.get("")
def listar(incluir_inactivos: bool = False,
           limite: int = Query(default=50, ge=1, le=200),
           desde: int = Query(default=0, ge=0),
           cur=Depends(obtener_conexion)):
    filtro = "" if incluir_inactivos else " WHERE c.activo = TRUE"
    cur.execute(SELECT_CLIENTE + filtro + " ORDER BY c.razon_social LIMIT %s OFFSET %s",
                (limite, desde))
    filas = cur.fetchall()
    for f in filas:
        f["activo"] = bool(f["activo"])
    return {"total": len(filas), "clientes": filas}


@router.get("/{id_cliente}")
def obtener(id_cliente: int, cur=Depends(obtener_conexion)):
    return _obtener(cur, id_cliente)


@router.post("", status_code=201)
def crear(datos: ClienteNuevo, cur=Depends(obtener_conexion)):
    cur.execute("SELECT 1 FROM clientes WHERE rfc = %s", (datos.rfc,))
    if cur.fetchone():
        raise ErrorNegocio("Ya existe un cliente con ese RFC", status=409)
    id_regimen = _id_por_clave(cur, REGIMEN, datos.clave_regimen, "régimen")
    id_uso = _id_por_clave(cur, USO, datos.clave_uso, "uso de CFDI")
    cur.execute(
        """INSERT INTO clientes (id_regimen, id_uso, rfc, razon_social, cp_fiscal, email, telefono)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (id_regimen, id_uso, datos.rfc, datos.razon_social, datos.cp_fiscal,
         datos.email, datos.telefono),
    )
    cliente = _obtener(cur, cur.lastrowid)
    cur.connection.commit()
    return cliente


@router.patch("/{id_cliente}")
def modificar(id_cliente: int, datos: ClienteCambios, cur=Depends(obtener_conexion)):
    _obtener(cur, id_cliente)
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise ErrorNegocio("No se enviaron campos para modificar", status=400)

    columnas = {}
    if "clave_regimen" in cambios:
        columnas["id_regimen"] = _id_por_clave(cur, REGIMEN, cambios.pop("clave_regimen"), "régimen")
    if "clave_uso" in cambios:
        columnas["id_uso"] = _id_por_clave(cur, USO, cambios.pop("clave_uso"), "uso de CFDI")
    columnas.update(cambios)

    # Las columnas salen del esquema validado (lista blanca), los valores van como parámetros
    permitidas = {"id_regimen", "id_uso", "razon_social", "cp_fiscal", "email", "telefono", "activo"}
    if not set(columnas) <= permitidas:
        raise ErrorNegocio("Campos no permitidos", status=400)
    sets = ", ".join(f"{col} = %s" for col in columnas)
    cur.execute(f"UPDATE clientes SET {sets} WHERE id_cliente = %s",
                (*columnas.values(), id_cliente))
    cliente = _obtener(cur, id_cliente)
    cur.connection.commit()
    return cliente
