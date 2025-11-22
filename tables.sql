CREATE DATABASE ICC;

USE ICC;

-- Tabla para almacenar información de los usuarios
CREATE TABLE usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    correo VARCHAR(150) UNIQUE NOT NULL,
    contrasena VARCHAR(255) NOT NULL,
    tipo_usuario ENUM('admin', 'usuario') NOT NULL DEFAULT 'usuario',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para almacenar información de los aspersores
CREATE TABLE aspersores (
    id_aspersor INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    ubicacion VARCHAR(255),
    estado ENUM('activo', 'inactivo') NOT NULL DEFAULT 'inactivo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE
);

-- Tabla para almacenar la programación de riegos
CREATE TABLE programaciones_riego (
    id_programacion INT AUTO_INCREMENT PRIMARY KEY,
    id_aspersor INT NOT NULL,
    hora_inicio DATETIME NOT NULL, 
    duracion_minutos INT NOT NULL,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_aspersor) REFERENCES aspersores(id_aspersor) ON DELETE CASCADE
);



-- Tabla para almacenar datos de los sensores
CREATE TABLE datos_sensores (
    id_dato INT AUTO_INCREMENT PRIMARY KEY,
    id_aspersor INT NOT NULL,
    tipo_sensor ENUM('humedad', 'temperatura', 'luz', 'otros') NOT NULL,
    valor_sensor FLOAT NOT NULL,
    fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_aspersor) REFERENCES aspersores(id_aspersor) ON DELETE CASCADE
);

INSERT INTO usuarios (nombre, correo, contrasena) VALUES ('Jaime Farfan','jfarfan@utec.edu.pe','123');