CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    rol TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE vehiculo (
    placa TEXT PRIMARY KEY,
    tipo TEXT NOT NULL
);
CREATE TABLE mensualidad (
    id_mensualidad INTEGER PRIMARY KEY AUTOINCREMENT,
    placa TEXT NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    FOREIGN KEY (placa) REFERENCES vehiculo(placa)
);
CREATE TABLE celda (
    id_celda INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL DEFAULT 'disponible'
);
CREATE TABLE movimiento (
    id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
    placa TEXT NOT NULL,
    id_celda INTEGER NOT NULL,
    id_usuario INTEGER NOT NULL,
    fecha_entrada DATETIME NOT NULL,
    fecha_salida DATETIME,
    FOREIGN KEY (placa) REFERENCES vehiculo(placa),
    FOREIGN KEY (id_celda) REFERENCES celda(id_celda),
    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);
