-- ==============================================================================
-- Datos iniciales: catálogos del SAT, usuarios y un cliente de prueba.
-- Se puede ejecutar varias veces: INSERT IGNORE no duplica registros.
-- ==============================================================================
USE sifat;

INSERT IGNORE INTO regimenes_fiscales (clave, descripcion, tipo_persona) VALUES
  ('601', 'General de Ley Personas Morales', 'M'),
  ('603', 'Personas Morales con Fines no Lucrativos', 'M'),
  ('605', 'Sueldos y Salarios e Ingresos Asimilados a Salarios', 'F'),
  ('612', 'Personas Fisicas con Actividades Empresariales y Profesionales', 'F'),
  ('626', 'Regimen Simplificado de Confianza', 'FM');

INSERT IGNORE INTO usos_cfdi (clave, descripcion) VALUES
  ('G01', 'Adquisicion de mercancias'),
  ('G03', 'Gastos en general'),
  ('I04', 'Equipo de computo y accesorios'),
  ('S01', 'Sin efectos fiscales');

INSERT IGNORE INTO formas_pago (clave, descripcion) VALUES
  ('01', 'Efectivo'),
  ('03', 'Transferencia electronica de fondos'),
  ('04', 'Tarjeta de credito'),
  ('28', 'Tarjeta de debito'),
  ('99', 'Por definir');

INSERT IGNORE INTO metodos_pago (clave, descripcion) VALUES
  ('PUE', 'Pago en una sola exhibicion'),
  ('PPD', 'Pago en parcialidades o diferido');

-- impuestos no tiene llave única: se inserta solo si no existe
INSERT INTO impuestos (nombre, tasa, tipo)
SELECT 'IVA', 0.1600, 'traslado' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM impuestos WHERE nombre = 'IVA' AND tasa = 0.1600 AND tipo = 'traslado');

INSERT IGNORE INTO usuarios (nombre, email, rol) VALUES
  ('Ana Lopez', 'ana.lopez@sifat.mx', 'Administrador'),
  ('Luis Perez', 'luis.perez@sifat.mx', 'Facturista');

INSERT IGNORE INTO clientes (id_regimen, id_uso, rfc, razon_social, cp_fiscal, email, telefono)
SELECT r.id_regimen, u.id_uso, 'CSU210315AB1', 'Comercializadora del Sur SA de CV', '62000',
       'contacto@comsur.mx', '7771234567'
FROM regimenes_fiscales r, usos_cfdi u
WHERE r.clave = '601' AND u.clave = 'G03';
