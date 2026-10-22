"""Cliente grafico (Tkinter) para la sala de cine.

    python cliente_gui.py --url http://127.0.0.1:5000 --id Ana

Las peticiones HTTP se hacen en hilos aparte y los resultados regresan al hilo
principal por una cola, para que la ventana nunca se congele.
"""
import argparse
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import requests

COLOR_LIBRE = "#4caf50"
COLOR_OTRO = "#b0b0b0"
COLOR_MIO = "#2196f3"
COLOR_SELEC = "#ffeb3b"
MARGEN = 26
REFRESCO_MS = 1500


class App:
    def __init__(self, root, url, cliente_id):
        self.root = root
        self.url = url.rstrip("/")
        self.cola = queue.Queue()
        self.estado = None          # ultimo snapshot de /sala
        self.seleccion = None       # (fila, columna) o None
        self.refrescando = False
        self.comprando = False
        self.celda = 36

        root.title("Sala de cine - Cliente")
        self.id_var = tk.StringVar(value=cliente_id)
        self.auto_var = tk.BooleanVar(value=True)
        self.disp_var = tk.StringVar(value="Disponibles: --")
        self.sel_var = tk.StringVar(value="Ningun asiento seleccionado")
        self.msg_var = tk.StringVar(value="")
        self.stats_vars = {k: tk.StringVar(value="--") for k in ("ventas", "conflictos", "integridad")}

        self._construir()
        self.refrescar()
        self.root.after(100, self._sondear_cola)
        self.root.after(REFRESCO_MS, self._auto_refresco)

    # ------------------------------------------------------------ interfaz
    def _construir(self):
        sup = ttk.Frame(self.root, padding=8)
        sup.pack(fill="x")
        ttk.Label(sup, text="Cliente:").pack(side="left")
        ttk.Entry(sup, textvariable=self.id_var, width=16).pack(side="left", padx=6)
        self.id_var.trace_add("write", lambda *_: self._dibujar())
        ttk.Label(sup, textvariable=self.disp_var, font=("TkDefaultFont", 14, "bold")).pack(side="right")

        self.barra = ttk.Progressbar(self.root, maximum=100)
        self.barra.pack(fill="x", padx=8)

        centro = ttk.Frame(self.root, padding=8)
        centro.pack(fill="both", expand=True)

        izq = ttk.Frame(centro)
        izq.pack(side="left")
        ttk.Label(izq, text="PANTALLA", anchor="center", background="#555", foreground="white").pack(fill="x")
        self.canvas = tk.Canvas(izq, width=420, height=420, highlightthickness=0)
        self.canvas.pack(pady=4)
        self.canvas.bind("<Button-1>", self._clic)
        self._leyenda(izq)

        der = ttk.Frame(centro, padding=(12, 0))
        der.pack(side="left", fill="y")
        ttk.Label(der, textvariable=self.sel_var, wraplength=190).pack(anchor="w", pady=(0, 6))
        self.btn_comprar = ttk.Button(der, text="Comprar", command=self.comprar, state="disabled")
        self.btn_comprar.pack(fill="x")
        ttk.Button(der, text="Actualizar", command=self.refrescar).pack(fill="x", pady=4)
        ttk.Checkbutton(der, text="Actualizar automaticamente", variable=self.auto_var).pack(anchor="w")
        self.lbl_msg = ttk.Label(der, textvariable=self.msg_var, wraplength=190)
        self.lbl_msg.pack(anchor="w", pady=10)

        est = ttk.LabelFrame(der, text="Estadisticas del servidor", padding=6)
        est.pack(fill="x", pady=6)
        for etiqueta, clave in (("Ventas:", "ventas"), ("Conflictos (409):", "conflictos"),
                                ("Integridad:", "integridad")):
            fila = ttk.Frame(est)
            fila.pack(fill="x")
            ttk.Label(fila, text=etiqueta).pack(side="left")
            ttk.Label(fila, textvariable=self.stats_vars[clave]).pack(side="right")

        bit = ttk.LabelFrame(self.root, text="Bitacora", padding=4)
        bit.pack(fill="both", padx=8, pady=(0, 8))
        self.log = tk.Text(bit, height=7, state="disabled", wrap="word")
        sb = ttk.Scrollbar(bit, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _leyenda(self, padre):
        f = ttk.Frame(padre)
        f.pack()
        for color, texto in ((COLOR_LIBRE, "Libre"), (COLOR_OTRO, "Vendido"),
                             (COLOR_MIO, "Tuyo"), (COLOR_SELEC, "Seleccionado")):
            tk.Label(f, bg=color, width=2).pack(side="left", padx=(8, 2))
            ttk.Label(f, text=texto).pack(side="left")

    # ------------------------------------------------------------- dibujo
    def _mi_id(self):
        return self.id_var.get().strip() or "cliente-gui"

    def _dibujar(self):
        c = self.canvas
        c.delete("all")
        if not self.estado:
            return
        filas, cols = self.estado["filas"], self.estado["columnas"]
        self.celda = max(16, min(40, 400 // max(filas, cols)))
        c.configure(width=MARGEN + cols * self.celda + 4, height=MARGEN + filas * self.celda + 4)
        mi = self._mi_id()

        for j in range(cols):
            c.create_text(MARGEN + j * self.celda + self.celda / 2, MARGEN / 2, text=str(j), font=("TkDefaultFont", 8))
        for i in range(filas):
            c.create_text(MARGEN / 2, MARGEN + i * self.celda + self.celda / 2, text=str(i), font=("TkDefaultFont", 8))
            for j in range(cols):
                dueno = self.estado["matriz"][i][j]
                if self.seleccion == (i, j):
                    color = COLOR_SELEC
                elif dueno is None:
                    color = COLOR_LIBRE
                elif dueno == mi:
                    color = COLOR_MIO
                else:
                    color = COLOR_OTRO
                x0, y0 = MARGEN + j * self.celda, MARGEN + i * self.celda
                c.create_rectangle(x0 + 1, y0 + 1, x0 + self.celda - 1, y0 + self.celda - 1,
                                   fill=color, outline="#333")

    # ------------------------------------------------------------ acciones
    def _clic(self, ev):
        if not self.estado or self.comprando:
            return
        j = (ev.x - MARGEN) // self.celda
        i = (ev.y - MARGEN) // self.celda
        if not (0 <= i < self.estado["filas"] and 0 <= j < self.estado["columnas"]):
            return
        if self.estado["matriz"][i][j] is not None:
            self._mensaje(f"El asiento ({i}, {j}) ya esta vendido.", error=True)
            return
        self.seleccion = (i, j)
        self.sel_var.set(f"Seleccionado: fila {i}, columna {j}")
        self.btn_comprar.state(["!disabled"])
        self._dibujar()

    def _limpiar_seleccion(self):
        self.seleccion = None
        self.sel_var.set("Ningun asiento seleccionado")
        self.btn_comprar.state(["disabled"])

    def refrescar(self):
        if self.refrescando:
            return
        self.refrescando = True
        self._en_hilo(self._tarea_refrescar)

    def comprar(self):
        if not self.seleccion or self.comprando:
            return
        fila, col = self.seleccion
        cid = self._mi_id()
        self.comprando = True
        self.btn_comprar.state(["disabled"])
        self._en_hilo(lambda: self._tarea_comprar(fila, col, cid))

    def _auto_refresco(self):
        if self.auto_var.get():
            self.refrescar()
        self.root.after(REFRESCO_MS, self._auto_refresco)

    # ------------------------------------- hilos de red (no tocan widgets)
    def _en_hilo(self, fn):
        threading.Thread(target=lambda: self.cola.put(fn()), daemon=True).start()

    def _tarea_refrescar(self):
        try:
            sala = requests.get(f"{self.url}/sala", timeout=10).json()
            stats = requests.get(f"{self.url}/stats", timeout=10).json()
            return ("estado", sala, stats)
        except (requests.RequestException, ValueError) as e:
            return ("error_red", f"Sin conexion con el servidor: {e}")

    def _tarea_comprar(self, fila, col, cid):
        try:
            r = requests.post(f"{self.url}/comprar",
                              json={"fila": fila, "columna": col, "cliente_id": cid}, timeout=10)
            return ("compra", fila, col, r.status_code, r.json().get("error", ""))
        except (requests.RequestException, ValueError) as e:
            return ("error_red", f"Sin conexion con el servidor: {e}")

    # ------------------------------ resultados (se ejecutan en hilo principal)
    def _sondear_cola(self):
        try:
            while True:
                self._procesar(self.cola.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._sondear_cola)

    def _procesar(self, res):
        tipo = res[0]
        if tipo == "estado":
            _, sala, stats = res
            self.refrescando = False
            self.estado = sala
            total = sala["filas"] * sala["columnas"]
            self.disp_var.set(f"Disponibles: {sala['disponibles']} de {total}")
            self.barra["value"] = 100 * (total - sala["disponibles"]) / total
            self.stats_vars["ventas"].set(str(stats["ventas"]))
            self.stats_vars["conflictos"].set(str(stats["conflictos"]))
            ok = all(stats["integridad"].values())
            self.stats_vars["integridad"].set("OK" if ok else "FALLO")
            # Si el asiento seleccionado ya lo vendio alguien mas, se deselecciona
            if self.seleccion:
                i, j = self.seleccion
                if (i >= sala["filas"] or j >= sala["columnas"]
                        or sala["matriz"][i][j] is not None):
                    self._mensaje(f"El asiento ({i}, {j}) acaba de ser vendido a otro cliente.", error=True)
                    self._limpiar_seleccion()
            self._dibujar()
        elif tipo == "compra":
            _, fila, col, codigo, error = res
            self.comprando = False
            if codigo == 200:
                self._mensaje(f"Compra exitosa: asiento ({fila}, {col}).")
            elif codigo == 409:
                self._mensaje(f"El asiento ({fila}, {col}) acaba de ser vendido a otro cliente.", error=True)
            else:
                self._mensaje(f"Solicitud invalida ({codigo}): {error}", error=True)
            self._limpiar_seleccion()
            self.refrescar()
        elif tipo == "error_red":
            self.refrescando = False
            self.comprando = False
            self._mensaje(res[1], error=True)
            if self.seleccion:
                self.btn_comprar.state(["!disabled"])

    def _mensaje(self, texto, error=False):
        self.msg_var.set(texto)
        self.lbl_msg.configure(foreground="#c62828" if error else "#2e7d32")
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {texto}\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5000")
    ap.add_argument("--id", default="cliente-gui")
    args = ap.parse_args()
    root = tk.Tk()
    App(root, args.url, args.id)
    root.mainloop()


if __name__ == "__main__":
    main()
