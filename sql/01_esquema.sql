-- ==============================================================================
-- SIFAT - DDL Script
-- Responsable: Santiago Acosta
-- (Copia del script ejecutado en RDS. ADVERTENCIA: la primera línea BORRA la base)
-- ==============================================================================

DROP DATABASE IF EXISTS sifat;
CREATE DATABASE IF NOT EXISTS sifat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE sifat;

-- BLOQUE 1: CATÁLOGOS (Sin dependencias)
CREATE TABLE regimenes_fiscales (
    id_regimen INT AUTO_INCREMENT PRIMARY KEY,
    clave CHAR(3) NOT NULL UNIQUE,
    descripcion VARCHAR(150) NOT NULL,
    tipo_persona ENUM('F', 'M', 'FM') NOT NULL
) ENGINE=InnoDB;

CREATE TABLE usos_cfdi (
    id_uso INT AUTO_INCREMENT PRIMARY KEY,
    clave VARCHAR(4) NOT NULL UNIQUE,
    descripcion VARCHAR(150) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE formas_pago (
    id_forma INT AUTO_INCREMENT PRIMARY KEY,
    clave CHAR(2) NOT NULL UNIQUE,
    descripcion VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE metodos_pago (
    id_metodo INT AUTO_INCREMENT PRIMARY KEY,
    clave CHAR(3) NOT NULL UNIQUE,
    descripcion VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE impuestos (
    id_impuesto INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(20) NOT NULL,
    tasa DECIMAL(6,4) NOT NULL CHECK (tasa >= 0),
    tipo ENUM('traslado', 'retencion') NOT NULL
) ENGINE=InnoDB;

-- BLOQUE 2: ACTORES
CREATE TABLE usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    rol ENUM('Administrador', 'Facturista', 'Gerente') NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

CREATE TABLE clientes (
    id_cliente INT AUTO_INCREMENT PRIMARY KEY,
    id_regimen INT NOT NULL,
    id_uso INT NOT NULL,
    rfc VARCHAR(13) NOT NULL UNIQUE,
    razon_social VARCHAR(200) NOT NULL,
    cp_fiscal CHAR(5) NOT NULL,
    email VARCHAR(120),
    telefono VARCHAR(15),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cliente_regimen FOREIGN KEY (id_regimen)
        REFERENCES regimenes_fiscales(id_regimen) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_cliente_uso FOREIGN KEY (id_uso)
        REFERENCES usos_cfdi(id_uso) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- BLOQUE 3: TRANSACCIONES
CREATE TABLE facturas (
    id_factura INT AUTO_INCREMENT PRIMARY KEY,
    folio VARCHAR(20) NOT NULL UNIQUE,
    id_cliente INT NOT NULL,
    id_usuario INT NOT NULL,
    id_forma INT NOT NULL,
    id_metodo INT NOT NULL,
    fecha_emision DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subtotal DECIMAL(12,2) NOT NULL CHECK (subtotal >= 0),
    iva DECIMAL(12,2) NOT NULL CHECK (iva >= 0),
    total DECIMAL(12,2) NOT NULL CHECK (total >= 0),
    estatus ENUM('vigente', 'pagada', 'cancelada') NOT NULL DEFAULT 'vigente',
    motivo_cancelacion VARCHAR(255) NULL,
    fecha_cancelacion DATETIME NULL,
    CONSTRAINT fk_factura_cliente FOREIGN KEY (id_cliente)
        REFERENCES clientes(id_cliente) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_factura_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_factura_forma FOREIGN KEY (id_forma)
        REFERENCES formas_pago(id_forma) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_factura_metodo FOREIGN KEY (id_metodo)
        REFERENCES metodos_pago(id_metodo) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE detalle_factura (
    id_detalle INT AUTO_INCREMENT PRIMARY KEY,
    id_factura INT NOT NULL,
    -- id_servicio es la Partition Key de DynamoDB (sin Foreign Key relacional)
    id_servicio VARCHAR(20) NOT NULL,
    clave_servicio VARCHAR(20) NOT NULL,
    nombre_servicio VARCHAR(120) NOT NULL,
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    precio_unitario DECIMAL(12,2) NOT NULL CHECK (precio_unitario >= 0),
    importe DECIMAL(12,2) NOT NULL CHECK (importe >= 0),
    id_impuesto INT NOT NULL,
    tasa_aplicada DECIMAL(6,4) NOT NULL CHECK (tasa_aplicada >= 0),
    iva_importe DECIMAL(12,2) NOT NULL CHECK (iva_importe >= 0),
    CONSTRAINT fk_detalle_factura FOREIGN KEY (id_factura)
        REFERENCES facturas(id_factura) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_detalle_impuesto FOREIGN KEY (id_impuesto)
        REFERENCES impuestos(id_impuesto) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE pagos (
    id_pago INT AUTO_INCREMENT PRIMARY KEY,
    id_factura INT NOT NULL,
    id_forma INT NOT NULL,
    fecha_pago DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    monto DECIMAL(12,2) NOT NULL CHECK (monto > 0),
    referencia VARCHAR(100),
    CONSTRAINT fk_pago_factura FOREIGN KEY (id_factura)
        REFERENCES facturas(id_factura) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_pago_forma FOREIGN KEY (id_forma)
        REFERENCES formas_pago(id_forma) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;
