import os
import sqlite3
from datetime import datetime, date
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
        return
    con = sqlite3.connect(RUTA)
    schema = os.path.join(os.path.dirname(RUTA), "schema.sql")
    con.executescript(open(schema, encoding="utf-8").read())
    con.execute("INSERT INTO usuario(nombre, username, password, rol) VALUES (?,?,?,?)",
                ("Juan Perez", "operario", generate_password_hash("operario123"), "operario"))
    con.execute("INSERT INTO usuario(nombre, username, password, rol) VALUES (?,?,?,?)",
                ("Ana Gomez", "admin", generate_password_hash("admin123"), "administrador"))
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


def hay_sesion():
    return "id_usuario" in session


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        con = conectar()
        usuario = con.execute("SELECT * FROM usuario WHERE username = ?",
                              (request.form["username"],)).fetchone()
        con.close()
        if usuario and check_password_hash(usuario["password"], request.form["password"]):
            session["id_usuario"] = usuario["id_usuario"]
            session["nombre"] = usuario["nombre"]
            session["rol"] = usuario["rol"]
            return redirect("/")
        error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


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


if __name__ == "__main__":
    crear_base()
    app.run(debug=True)
