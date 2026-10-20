-- ==============================================================================
-- Login: columnas para contraseña cifrada y bloqueo por intentos fallidos.
-- Ejecútalo UNA vez en MySQL Workbench conectado como admin
-- (sifat_app no tiene permiso de ALTER).
-- ==============================================================================
USE sifat;

ALTER TABLE usuarios
    ADD COLUMN password_hash VARCHAR(255) NULL AFTER email,
    ADD COLUMN intentos_fallidos INT NOT NULL DEFAULT 0 AFTER activo,
    ADD COLUMN bloqueado_hasta DATETIME NULL AFTER intentos_fallidos,
    ADD COLUMN ultimo_acceso DATETIME NULL AFTER bloqueado_hasta;
