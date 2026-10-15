-- ==============================================================================
-- Usuario de la aplicación con permisos mínimos.
-- Ejecútalo en MySQL Workbench conectado como admin.
-- ANTES: reemplaza CAMBIA_ESTA_CONTRASENA por una contraseña larga y única
-- (mínimo 16 caracteres). No la guardes en este archivo ni la subas al repo:
-- solo va en el .env del backend.
-- ==============================================================================

CREATE USER IF NOT EXISTS 'sifat_app'@'%' IDENTIFIED BY 'CAMBIA_ESTA_CONTRASENA' REQUIRE SSL;

-- Sin DELETE, DROP ni ALTER: las facturas se cancelan, los clientes se desactivan.
GRANT SELECT, INSERT, UPDATE ON sifat.* TO 'sifat_app'@'%';

FLUSH PRIVILEGES;
