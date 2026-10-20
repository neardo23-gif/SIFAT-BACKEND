# SIFAT · Backend

API REST (FastAPI) para **clientes, facturas y pagos** sobre MySQL en Amazon RDS.
El catálogo de servicios vive en DynamoDB y se consulta por API Gateway.

```
Frontend (repo SIFAT) ──X-API-Key──► Backend (este repo) ──► MySQL (RDS)
                                          │
                                          └──x-api-key──► API Gateway ──► Lambda ──► DynamoDB (servicios)
```

## Arranque local
Requiere **Python 3.10 o más reciente**. En Mac, el `python3` del sistema (3.9 con LibreSSL)
no logra verificar el certificado de RDS: instala uno nuevo con `brew install python@3.12`.
```bash
/opt/homebrew/bin/python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # y llena los valores (ver abajo)
mkdir -p certs && curl -o certs/global-bundle.pem \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
python run.py                   # http://127.0.0.1:8000  (docs en /docs si ENABLE_DOCS=true)
pytest                          # pruebas sin base de datos real
```

## Preparar la base de datos (una sola vez, en MySQL Workbench como admin)
1. `sql/01_esquema.sql`: **solo si la base no existe**. Su primera línea borra `sifat`.
2. `sql/02_usuario_app.sql`: crea `sifat_app` con permisos mínimos. Cambia la
   contraseña en el script, ejecútalo y **no guardes el archivo con la contraseña**.
3. `sql/03_datos_iniciales.sql`: catálogos del SAT, usuarios y un cliente de prueba.
4. `sql/04_login.sql`: agrega a `usuarios` la contraseña cifrada y el bloqueo por intentos.

Después asigna la contraseña de cada usuario desde la terminal (no se muestra al escribirla):
```bash
python -m app.asignar_contrasena ana.lopez@sifat.mx
```

La IP pública de cada integrante debe estar en las reglas de entrada del grupo de
seguridad `sifat-rds-sg` (tipo MySQL/Aurora, origen `IP/32`).

## Variables de entorno (.env, nunca se sube al repo)
| Variable | Qué es |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME` | Endpoint de RDS, 3306, `sifat` |
| `DB_USER`, `DB_PASSWORD` | `sifat_app` y su contraseña. El backend se niega a arrancar con `admin` |
| `DB_SSL_CA` | `certs/global-bundle.pem` (conexión cifrada y verificada) |
| `SERVICIOS_API_URL`, `SERVICIOS_API_KEY` | API Gateway del catálogo y la clave `sifat-frontend` |
| `BACKEND_API_KEY` | Clave que el frontend manda en `X-API-Key` (mínimo 24 caracteres) |
| `ENABLE_DOCS` | `true` solo en desarrollo |

## Endpoints (todos piden `X-API-Key`, excepto `/salud`)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/salud` | Comprobación de vida |
| POST | `/auth/login` | Valida correo y contraseña (`email`, `password`); 5 fallos bloquean la cuenta 15 min |
| GET | `/catalogos` | Regímenes, usos de CFDI, formas y métodos de pago, impuestos, usuarios |
| GET | `/clientes?incluir_inactivos=&limite=&desde=` | Lista de clientes |
| GET | `/clientes/{id}` | Un cliente |
| POST | `/clientes` | Alta (`rfc`, `razon_social`, `cp_fiscal`, `clave_regimen`, `clave_uso`, `email?`, `telefono?`) |
| PATCH | `/clientes/{id}` | Cambios parciales; `activo: false` lo desactiva (no se borra) |
| GET | `/facturas?estatus=&id_cliente=&limite=&desde=` | Lista de facturas |
| GET | `/facturas/{folio}` | Factura con conceptos, pagos y saldo |
| POST | `/facturas` | Emite factura (`id_cliente`, `id_usuario`, `clave_forma_pago`, `clave_metodo_pago`, `conceptos[{id_servicio, cantidad}]`) |
| POST | `/facturas/{folio}/cancelar` | Cancela una factura vigente sin pagos (`motivo`) |
| GET | `/pagos?folio=` | Lista de pagos |
| POST | `/pagos` | Registra pago (`folio`, `clave_forma_pago`, `monto`, `referencia?`) |

## Reglas de negocio
- **Integración SQL/NoSQL:** al emitir una factura, cada `id_servicio` se consulta en
  DynamoDB; debe existir y estar activo. Su clave, nombre, precio y tasa se **copian** al
  detalle, así la factura conserva el precio al que se vendió.
- Factura, conceptos y totales se guardan en **una sola transacción** (ROLLBACK si algo falla).
- Los totales se calculan **en el servidor** con `Decimal` (redondeo a centavos, mitad hacia arriba).
- Un pago no puede superar el saldo; al liquidar, la factura pasa a `pagada`.
  La fila se bloquea (`SELECT ... FOR UPDATE`) para evitar pagos simultáneos.
- Las facturas no se borran: se **cancelan**. Los clientes no se borran: se **desactivan**.

## Seguridad
- Todas las consultas son parametrizadas; nombres de tablas y columnas salen de listas fijas.
- Entrada validada con Pydantic: campos no declarados se rechazan, RFC, CP, claves SAT,
  montos y longitudes con formato estricto.
- Conexión a MySQL cifrada (TLS) y con verificación del certificado de AWS.
- Usuario de base de datos sin `DELETE`, `DROP` ni `ALTER`.
- Contraseñas con PBKDF2-SHA256 (600 000 iteraciones y sal aleatoria); el login responde
  igual y tarda lo mismo si el correo no existe, y bloquea la cuenta tras 5 intentos.
- Errores internos responden solo con un `error_id`; el detalle queda en el log.
- El servidor escucha únicamente en `127.0.0.1`.
