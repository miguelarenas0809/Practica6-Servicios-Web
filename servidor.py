"""Servidor Flask: venta de boletos de cine con control de concurrencia.

Ejecutar con UN solo proceso (el estado vive en memoria):
    python servidor.py --filas 10 --columnas 10 --puerto 5000

Variable de entorno opcional:
    ADMIN_TOKEN  si esta definida, POST /reset exige la cabecera X-Admin-Token.
"""
import argparse
import hmac
import os

from flask import Flask, jsonify, request

from rwlock import FairRWLock

MAX_DIM = 100          # tope de filas y de columnas
MAX_ID = 64            # longitud maxima de cliente_id
MAX_BODY = 1024        # bytes maximos del cuerpo de una peticion


class Sala:
    """Sala representada como matriz: None = libre, str = cliente_id dueño."""

    def __init__(self, filas, columnas):
        self.lock = FairRWLock()
        self.reiniciar(filas, columnas)

    def reiniciar(self, filas, columnas):
        self.filas = filas
        self.columnas = columnas
        self.matriz = [[None] * columnas for _ in range(filas)]
        self.disponibles = filas * columnas
        self.ventas = 0
        self.conflictos = 0

    # --- LECTOR: devuelve una copia consistente (snapshot) ---
    def consultar(self):
        with self.lock.read_lock():
            return {
                "filas": self.filas,
                "columnas": self.columnas,
                "disponibles": self.disponibles,
                "matriz": [fila[:] for fila in self.matriz],  # copia, no referencia
            }

    # --- ESCRITOR: verificar y escribir en la MISMA seccion critica ---
    def comprar(self, fila, columna, cliente_id):
        with self.lock.write_lock():
            if self.matriz[fila][columna] is not None:
                self.conflictos += 1
                return False
            self.matriz[fila][columna] = cliente_id
            self.disponibles -= 1
            self.ventas += 1
            return True

    def estadisticas(self):
        with self.lock.read_lock():
            ocupados = sum(1 for f in self.matriz for c in f if c is not None)
            total = self.filas * self.columnas
            return {
                "capacidad": total,
                "ocupados": ocupados,
                "disponibles": self.disponibles,
                "ventas": self.ventas,
                "conflictos": self.conflictos,
                "integridad": {
                    "disponibles_coincide_con_matriz": self.disponibles == total - ocupados,
                    "ventas_coincide_con_matriz": self.ventas == ocupados,
                    "ocupados_mas_disponibles_es_capacidad": ocupados + self.disponibles == total,
                },
            }


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY
sala = Sala(10, 10)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")


def _entero(valor):
    # bool es subclase de int en Python; lo rechazamos explicitamente
    return isinstance(valor, int) and not isinstance(valor, bool)


def _autorizado():
    if not ADMIN_TOKEN:
        return True
    recibido = request.headers.get("X-Admin-Token", "")
    return hmac.compare_digest(recibido.encode(), ADMIN_TOKEN.encode())


@app.errorhandler(413)
def cuerpo_demasiado_grande(_e):
    return jsonify(error=f"Cuerpo de la peticion mayor a {MAX_BODY} bytes"), 413


@app.get("/sala")
def get_sala():
    return jsonify(sala.consultar())


@app.post("/comprar")
def post_comprar():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        datos = {}
    fila, columna, cliente = datos.get("fila"), datos.get("columna"), datos.get("cliente_id")

    if not (_entero(fila) and _entero(columna)) or not isinstance(cliente, str) or not cliente:
        return jsonify(error="Se requiere fila (int), columna (int) y cliente_id (str)"), 400
    if len(cliente) > MAX_ID:
        return jsonify(error=f"cliente_id mayor a {MAX_ID} caracteres"), 400
    if not (0 <= fila < sala.filas and 0 <= columna < sala.columnas):
        return jsonify(error="Asiento fuera de rango"), 400

    if sala.comprar(fila, columna, cliente):
        return jsonify(mensaje="Boleto vendido", fila=fila, columna=columna, cliente_id=cliente), 200
    return jsonify(error="Asiento ya ocupado", fila=fila, columna=columna), 409


@app.get("/stats")
def get_stats():
    return jsonify(sala.estadisticas())


@app.post("/reset")
def post_reset():
    if not _autorizado():
        return jsonify(error="No autorizado"), 403
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        datos = {}
    filas = datos.get("filas", sala.filas)
    columnas = datos.get("columnas", sala.columnas)
    if not (_entero(filas) and _entero(columnas)) or not (1 <= filas <= MAX_DIM and 1 <= columnas <= MAX_DIM):
        return jsonify(error=f"filas y columnas deben ser enteros entre 1 y {MAX_DIM}"), 400
    with sala.lock.write_lock():
        sala.reiniciar(filas, columnas)
    return jsonify(mensaje="Sala reiniciada", filas=filas, columnas=columnas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--filas", type=int, default=10)
    ap.add_argument("--columnas", type=int, default=10)
    ap.add_argument("--puerto", type=int, default=5000)
    args = ap.parse_args()
    if not (1 <= args.filas <= MAX_DIM and 1 <= args.columnas <= MAX_DIM):
        ap.error(f"filas y columnas deben estar entre 1 y {MAX_DIM}")
    sala.reiniciar(args.filas, args.columnas)
    if not ADMIN_TOKEN:
        print("AVISO: ADMIN_TOKEN no definido; /reset es de acceso libre.")
    # threaded=True: un hilo por peticion; un solo proceso (sin reloader)
    app.run(host="127.0.0.1", port=args.puerto, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
