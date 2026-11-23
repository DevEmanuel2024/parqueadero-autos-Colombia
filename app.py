import os
import sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "clave_parqueadero"

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parqueadero.db")


def conectar():
    con = sqlite3.connect(RUTA)
    con.row_factory = sqlite3.Row
    return con


def crear_base():
    if os.path.exists(RUTA):
        agregar_tablas_pagos()
        return
    con = sqlite3.connect(RUTA)
    schema = os.path.join(os.path.dirname(RUTA), "schema.sql")
    con.executescript(open(schema, encoding="utf-8").read())
    con.execute("INSERT INTO usuario(nombre, username, password, rol, activo) VALUES (?,?,?,?,1)",
                ("Juan Perez", "operario", generate_password_hash("operario123"), "operario"))
    con.execute("INSERT INTO usuario(nombre, username, password, rol, activo) VALUES (?,?,?,?,1)",
                ("Ana Gomez", "admin", generate_password_hash("admin123"), "administrador"))
    con.execute("INSERT INTO usuario(nombre, username, password, rol, activo) VALUES (?,?,?,?,0)",
                ("Pedro Ruiz", "pruiz", generate_password_hash("pedro123"), "operario"))
    for i in range(1, 11):
        con.execute("INSERT INTO celda(codigo) VALUES (?)", ("A-%02d" % i,))
    con.execute("INSERT INTO vehiculo VALUES ('ABC123', 'carro')")
    con.execute("INSERT INTO vehiculo VALUES ('XYZ987', 'moto')")
    con.execute("INSERT INTO vehiculo VALUES ('VEN000', 'carro')")
    con.execute("INSERT INTO mensualidad(placa, fecha_inicio, fecha_fin) VALUES ('ABC123', '2026-10-01', '2026-12-31')")
    con.execute("INSERT INTO mensualidad(placa, fecha_inicio, fecha_fin) VALUES ('XYZ987', '2026-10-01', '2026-12-31')")
    con.execute("INSERT INTO mensualidad(placa, fecha_inicio, fecha_fin) VALUES ('VEN000', '2026-01-01', '2026-02-01')")
    con.commit()
    con.close()
    agregar_tablas_pagos()


def agregar_tablas_pagos():
    # por si la base ya existía de antes, crea las tablas nuevas sin borrar nada
    con = sqlite3.connect(RUTA)
    con.execute("CREATE TABLE IF NOT EXISTS tarifa (tipo TEXT PRIMARY KEY, valor INTEGER NOT NULL)")
    con.execute("""CREATE TABLE IF NOT EXISTS pago (
        id_pago INTEGER PRIMARY KEY AUTOINCREMENT,
        placa TEXT NOT NULL,
        id_usuario INTEGER NOT NULL,
        id_mensualidad INTEGER NOT NULL,
        valor INTEGER NOT NULL,
        medio TEXT NOT NULL,
        fecha_pago DATETIME NOT NULL,
        FOREIGN KEY (placa) REFERENCES vehiculo(placa),
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario),
        FOREIGN KEY (id_mensualidad) REFERENCES mensualidad(id_mensualidad))""")
    if con.execute("SELECT COUNT(*) FROM tarifa").fetchone()[0] == 0:
        con.execute("INSERT INTO tarifa VALUES ('carro', 120000)")
        con.execute("INSERT INTO tarifa VALUES ('moto', 80000)")
    con.commit()
    con.close()


@app.template_filter("pesos")
def pesos(valor):
    return "$" + "{:,.0f}".format(valor).replace(",", ".")


def hay_sesion():
    return "id_usuario" in session


def es_admin():
    return session.get("rol") == "administrador"


# ---------------- login ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        con = conectar()
        usuario = con.execute("SELECT * FROM usuario WHERE username = ?",
                              (request.form["username"],)).fetchone()
        con.close()
        if usuario is None or not check_password_hash(usuario["password"], request.form["password"]):
            error = "Usuario o contraseña incorrectos"
        elif usuario["activo"] == 0:
            error = "El usuario está desactivado"
        else:
            session["id_usuario"] = usuario["id_usuario"]
            session["nombre"] = usuario["nombre"]
            session["rol"] = usuario["rol"]
            return redirect("/")
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- entrada y salida (iteración 1) ----------------

@app.route("/")
def inicio():
    if not hay_sesion():
        return redirect("/login")
    return render_template("operacion.html")


@app.route("/entrada", methods=["POST"])
def entrada():
    if not hay_sesion():
        return redirect("/login")
    placa = request.form["placa"].strip().upper()
    tipo = request.form["tipo"]
    hoy = date.today().isoformat()
    con = conectar()

    vehiculo = con.execute("SELECT * FROM vehiculo WHERE placa = ?", (placa,)).fetchone()
    mensualidad = con.execute(
        "SELECT * FROM mensualidad WHERE placa = ? AND fecha_inicio <= ? AND fecha_fin >= ?",
        (placa, hoy, hoy)).fetchone()
    dentro = con.execute("SELECT * FROM movimiento WHERE placa = ? AND fecha_salida IS NULL",
                         (placa,)).fetchone()
    celda = con.execute("SELECT * FROM celda WHERE estado = 'disponible' LIMIT 1").fetchone()

    if vehiculo is None:
        flash(("error", "La placa " + placa + " no está registrada"))
    elif vehiculo["tipo"] != tipo:
        flash(("error", "El tipo no coincide: la placa " + placa + " está registrada como " + vehiculo["tipo"]))
    elif mensualidad is None:
        flash(("error", "La placa " + placa + " no tiene mensualidad vigente"))
    elif dentro is not None:
        flash(("error", "El vehículo " + placa + " ya está dentro"))
    elif celda is None:
        flash(("error", "No hay celdas disponibles"))
    else:
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("UPDATE celda SET estado = 'ocupada' WHERE id_celda = ?", (celda["id_celda"],))
        con.execute("INSERT INTO movimiento(placa, id_celda, id_usuario, fecha_entrada) VALUES (?,?,?,?)",
                    (placa, celda["id_celda"], session["id_usuario"], ahora))
        con.commit()
        flash(("ok", "Entrada registrada. Celda asignada: " + celda["codigo"]))
    con.close()
    return redirect("/")


@app.route("/salida", methods=["POST"])
def salida():
    if not hay_sesion():
        return redirect("/login")
    placa = request.form["placa"].strip().upper()
    con = conectar()
    mov = con.execute("""SELECT movimiento.id_movimiento, movimiento.id_celda, celda.codigo
                         FROM movimiento JOIN celda ON celda.id_celda = movimiento.id_celda
                         WHERE movimiento.placa = ? AND movimiento.fecha_salida IS NULL""",
                      (placa,)).fetchone()
    if mov is None:
        flash(("error", "La placa " + placa + " no está dentro del parqueadero"))
    else:
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("UPDATE movimiento SET fecha_salida = ? WHERE id_movimiento = ?",
                    (ahora, mov["id_movimiento"]))
        con.execute("UPDATE celda SET estado = 'disponible' WHERE id_celda = ?", (mov["id_celda"],))
        con.commit()
        flash(("ok", "Salida registrada. Celda " + mov["codigo"] + " liberada"))
    con.close()
    return redirect("/")


@app.route("/consultas")
def consultas():
    if not hay_sesion():
        return redirect("/login")
    placa = request.args.get("placa", "").strip().upper()
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")
    con = conectar()
    dentro = con.execute("""SELECT movimiento.placa, celda.codigo, movimiento.fecha_entrada
                            FROM movimiento JOIN celda ON celda.id_celda = movimiento.id_celda
                            WHERE movimiento.fecha_salida IS NULL""").fetchall()
    consulta = """SELECT movimiento.placa, celda.codigo, movimiento.fecha_entrada, movimiento.fecha_salida
                  FROM movimiento JOIN celda ON celda.id_celda = movimiento.id_celda WHERE 1 = 1"""
    datos = []
    if placa != "":
        consulta += " AND movimiento.placa = ?"
        datos.append(placa)
    if desde != "":
        consulta += " AND date(movimiento.fecha_entrada) >= ?"
        datos.append(desde)
    if hasta != "":
        consulta += " AND date(movimiento.fecha_entrada) <= ?"
        datos.append(hasta)
    historial = con.execute(consulta + " ORDER BY movimiento.fecha_entrada DESC", datos).fetchall()
    con.close()
    return render_template("consultas.html", dentro=dentro, historial=historial,
                           placa=placa, desde=desde, hasta=hasta)


# ---------------- gestión de usuarios (iteración 2) ----------------

def revisar_admin():
    # devuelve una redirección si no hay sesión o no es administrador
    if not hay_sesion():
        return redirect("/login")
    if not es_admin():
        flash(("error", "No tienes permiso para entrar a esta sección"))
        return redirect("/")
    return None


@app.route("/usuarios")
def usuarios():
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    con = conectar()
    lista = con.execute("SELECT * FROM usuario ORDER BY nombre").fetchall()
    con.close()
    return render_template("usuarios.html", usuarios=lista)


@app.route("/usuarios/nuevo", methods=["POST"])
def usuario_nuevo():
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    nombre = request.form["nombre"].strip()
    username = request.form["username"].strip()
    password = request.form["password"]
    rol = request.form["rol"]
    con = conectar()
    existe = con.execute("SELECT * FROM usuario WHERE username = ?", (username,)).fetchone()
    if nombre == "" or username == "" or password == "":
        flash(("error", "Todos los campos son obligatorios"))
    elif existe:
        flash(("error", "El nombre de usuario ya existe"))
    else:
        con.execute("INSERT INTO usuario(nombre, username, password, rol, activo) VALUES (?,?,?,?,1)",
                    (nombre, username, generate_password_hash(password), rol))
        con.commit()
        flash(("ok", "Usuario registrado correctamente"))
    con.close()
    return redirect("/usuarios")


@app.route("/usuarios/editar/<int:id>", methods=["GET", "POST"])
def usuario_editar(id):
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    con = conectar()
    usuario = con.execute("SELECT * FROM usuario WHERE id_usuario = ?", (id,)).fetchone()
    if usuario is None:
        con.close()
        return redirect("/usuarios")
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        username = request.form["username"].strip()
        password = request.form["password"]
        rol = request.form["rol"]
        otro = con.execute("SELECT * FROM usuario WHERE username = ? AND id_usuario != ?",
                           (username, id)).fetchone()
        if nombre == "" or username == "":
            flash(("error", "El nombre y el usuario son obligatorios"))
        elif otro:
            flash(("error", "El nombre de usuario ya existe"))
        else:
            con.execute("UPDATE usuario SET nombre = ?, username = ?, rol = ? WHERE id_usuario = ?",
                        (nombre, username, rol, id))
            if password != "":
                con.execute("UPDATE usuario SET password = ? WHERE id_usuario = ?",
                            (generate_password_hash(password), id))
            con.commit()
            con.close()
            flash(("ok", "Usuario actualizado"))
            return redirect("/usuarios")
    con.close()
    return render_template("editar_usuario.html", usuario=usuario)


@app.route("/usuarios/estado/<int:id>", methods=["POST"])
def usuario_estado(id):
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    con = conectar()
    usuario = con.execute("SELECT * FROM usuario WHERE id_usuario = ?", (id,)).fetchone()
    if usuario is None:
        flash(("error", "El usuario no existe"))
    elif usuario["id_usuario"] == session["id_usuario"]:
        flash(("error", "No puedes desactivar tu propio usuario"))
    else:
        nuevo = 0 if usuario["activo"] == 1 else 1
        con.execute("UPDATE usuario SET activo = ? WHERE id_usuario = ?", (nuevo, id))
        con.commit()
        flash(("ok", "Usuario " + ("activado" if nuevo == 1 else "desactivado")))
    con.close()
    return redirect("/usuarios")


# ---------------- gestión de celdas (iteración 2) ----------------

@app.route("/celdas")
def celdas():
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    con = conectar()
    lista = con.execute("SELECT * FROM celda ORDER BY codigo").fetchall()
    con.close()
    return render_template("celdas.html", celdas=lista)


@app.route("/celdas/nueva", methods=["POST"])
def celda_nueva():
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    codigo = request.form["codigo"].strip().upper()
    con = conectar()
    existe = con.execute("SELECT * FROM celda WHERE codigo = ?", (codigo,)).fetchone()
    if codigo == "":
        flash(("error", "Escribe un código para la celda"))
    elif existe:
        flash(("error", "El código ya existe"))
    else:
        con.execute("INSERT INTO celda(codigo, estado) VALUES (?, 'disponible')", (codigo,))
        con.commit()
        flash(("ok", "Celda registrada"))
    con.close()
    return redirect("/celdas")


@app.route("/celdas/editar/<int:id>", methods=["GET", "POST"])
def celda_editar(id):
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    con = conectar()
    celda = con.execute("SELECT * FROM celda WHERE id_celda = ?", (id,)).fetchone()
    if celda is None:
        con.close()
        return redirect("/celdas")
    if celda["estado"] == "ocupada":
        con.close()
        flash(("error", "No se puede editar una celda ocupada"))
        return redirect("/celdas")
    if request.method == "POST":
        codigo = request.form["codigo"].strip().upper()
        otra = con.execute("SELECT * FROM celda WHERE codigo = ? AND id_celda != ?", (codigo, id)).fetchone()
        if codigo == "":
            flash(("error", "Escribe un código para la celda"))
        elif otra:
            flash(("error", "El código ya existe"))
        else:
            con.execute("UPDATE celda SET codigo = ? WHERE id_celda = ?", (codigo, id))
            con.commit()
            con.close()
            flash(("ok", "Celda actualizada"))
            return redirect("/celdas")
    con.close()
    return render_template("editar_celda.html", celda=celda)


@app.route("/celdas/estado/<int:id>", methods=["POST"])
def celda_estado(id):
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    con = conectar()
    celda = con.execute("SELECT * FROM celda WHERE id_celda = ?", (id,)).fetchone()
    if celda is None:
        flash(("error", "La celda no existe"))
    elif celda["estado"] == "ocupada":
        flash(("error", "No se puede inhabilitar una celda ocupada"))
    else:
        nuevo = "inhabilitada" if celda["estado"] == "disponible" else "disponible"
        con.execute("UPDATE celda SET estado = ? WHERE id_celda = ?", (nuevo, id))
        con.commit()
        flash(("ok", "La celda " + celda["codigo"] + " quedó " + nuevo))
    con.close()
    return redirect("/celdas")


# ---------------- vehículos y tarifas (iteración 3) ----------------

@app.route("/vehiculos")
def vehiculos():
    if not hay_sesion():
        return redirect("/login")
    con = conectar()
    lista = con.execute("SELECT * FROM vehiculo ORDER BY placa").fetchall()
    con.close()
    return render_template("vehiculos.html", vehiculos=lista)


@app.route("/vehiculos/nuevo", methods=["POST"])
def vehiculo_nuevo():
    if not hay_sesion():
        return redirect("/login")
    placa = request.form["placa"].strip().upper()
    tipo = request.form["tipo"]
    con = conectar()
    existe = con.execute("SELECT * FROM vehiculo WHERE placa = ?", (placa,)).fetchone()
    if placa == "":
        flash(("error", "Escribe la placa del vehículo"))
    elif tipo not in ("carro", "moto"):
        flash(("error", "El tipo debe ser carro o moto"))
    elif existe:
        flash(("error", "La placa " + placa + " ya existe"))
    else:
        con.execute("INSERT INTO vehiculo(placa, tipo) VALUES (?, ?)", (placa, tipo))
        con.commit()
        flash(("ok", "Vehículo registrado correctamente"))
    con.close()
    return redirect("/vehiculos")


@app.route("/tarifas")
def tarifas():
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    con = conectar()
    lista = con.execute("SELECT * FROM tarifa ORDER BY tipo").fetchall()
    con.close()
    return render_template("tarifas.html", tarifas=lista)


@app.route("/tarifas/guardar", methods=["POST"])
def tarifa_guardar():
    bloqueo = revisar_admin()
    if bloqueo:
        return bloqueo
    tipo = request.form["tipo"]
    try:
        valor = int(request.form["valor"])
    except ValueError:
        valor = 0
    if valor <= 0:
        flash(("error", "El valor debe ser un número mayor que cero"))
    else:
        con = conectar()
        con.execute("UPDATE tarifa SET valor = ? WHERE tipo = ?", (valor, tipo))
        con.commit()
        con.close()
        flash(("ok", "Tarifa de " + tipo + " actualizada"))
    return redirect("/tarifas")


# ---------------- pagos (iteración 3) ----------------

@app.route("/pagos")
def pagos():
    if not hay_sesion():
        return redirect("/login")
    con = conectar()
    lista_tarifas = con.execute("SELECT * FROM tarifa").fetchall()
    lista_vehiculos = con.execute("SELECT * FROM vehiculo").fetchall()
    con.close()
    return render_template("pagos.html", tarifas=lista_tarifas, vehiculos=lista_vehiculos)


@app.route("/pagos/nuevo", methods=["POST"])
def pago_nuevo():
    if not hay_sesion():
        return redirect("/login")
    placa = request.form["placa"].strip().upper()
    medio = request.form["medio"]
    con = conectar()
    vehiculo = con.execute("SELECT * FROM vehiculo WHERE placa = ?", (placa,)).fetchone()
    if vehiculo is None:
        con.close()
        flash(("error", "La placa " + placa + " no está registrada"))
        return redirect("/pagos")
    if medio not in ("efectivo", "transferencia"):
        con.close()
        flash(("error", "Elige un medio de pago válido"))
        return redirect("/pagos")
    tarifa = con.execute("SELECT * FROM tarifa WHERE tipo = ?", (vehiculo["tipo"],)).fetchone()
    if tarifa is None:
        con.close()
        flash(("error", "El tipo " + vehiculo["tipo"] + " no tiene tarifa"))
        return redirect("/pagos")

    # si ya tiene mensualidad vigente, la nueva empieza el día siguiente a que termine
    hoy = date.today()
    ultima = con.execute("SELECT MAX(fecha_fin) FROM mensualidad WHERE placa = ?", (placa,)).fetchone()[0]
    if ultima is not None and ultima >= hoy.isoformat():
        inicio = date.fromisoformat(ultima) + timedelta(days=1)
    else:
        inicio = hoy
    fin = inicio + timedelta(days=29)

    cursor = con.execute("INSERT INTO mensualidad(placa, fecha_inicio, fecha_fin) VALUES (?,?,?)",
                         (placa, inicio.isoformat(), fin.isoformat()))
    id_mensualidad = cursor.lastrowid
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = con.execute("""INSERT INTO pago(placa, id_usuario, id_mensualidad, valor, medio, fecha_pago)
                            VALUES (?,?,?,?,?,?)""",
                         (placa, session["id_usuario"], id_mensualidad, tarifa["valor"], medio, ahora))
    id_pago = cursor.lastrowid
    con.commit()
    con.close()
    return redirect("/comprobante/" + str(id_pago))


@app.route("/comprobante/<int:id>")
def comprobante(id):
    if not hay_sesion():
        return redirect("/login")
    con = conectar()
    pago = con.execute("""SELECT pago.*, usuario.nombre AS cajero, mensualidad.fecha_inicio, mensualidad.fecha_fin
                          FROM pago JOIN usuario ON usuario.id_usuario = pago.id_usuario
                          JOIN mensualidad ON mensualidad.id_mensualidad = pago.id_mensualidad
                          WHERE pago.id_pago = ?""", (id,)).fetchone()
    con.close()
    if pago is None:
        return redirect("/pagos")
    return render_template("comprobante.html", pago=pago)


if __name__ == "__main__":
    crear_base()
    app.run(debug=True)
