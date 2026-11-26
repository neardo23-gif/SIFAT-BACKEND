-- ==============================================================================
-- Retención de ISR en facturas (10 % cuando el cliente es persona moral).
-- total = subtotal + iva - isr. Las facturas ya emitidas quedan con isr = 0.
-- Ejecútalo UNA vez en MySQL Workbench conectado como admin
-- (sifat_app no tiene permiso de ALTER).
-- ==============================================================================
USE sifat;

ALTER TABLE facturas
    ADD COLUMN isr DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (isr >= 0) AFTER iva;

ALTER TABLE detalle_factura
    ADD COLUMN tasa_isr DECIMAL(6,4) NOT NULL DEFAULT 0 CHECK (tasa_isr >= 0) AFTER iva_importe,
    ADD COLUMN isr_importe DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (isr_importe >= 0) AFTER tasa_isr;
