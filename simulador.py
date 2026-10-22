"""Simulador de clientes concurrentes contra el servidor de la sala.

    python simulador.py --clientes 50 --acciones 40 --filas 10 --columnas 10
    python simulador.py --esperar 30 --salida resultados.json

Codigos de salida: 0 = todas las invariantes correctas, 1 = hay inconsistencias,
2 = no se pudo preparar la simulacion (servidor inaccesible, reset rechazado).
Si el servidor usa ADMIN_TOKEN, definirlo como variable de entorno o con --token.
"""
import argparse
import json
import os
import random
import statistics
import sys
import threading
import time

import requests


def cliente(idx, args, resultados, lock_res):
    rng = random.Random(args.semilla + idx)
    cid = f"cliente-{idx}"
    s = requests.Session()
    local = {"consultas": 0, "compras_ok": [], "compras_409": 0, "errores": 0,
             "lat_consulta": [], "lat_compra": []}

    for _ in range(args.acciones):
        try:
            if rng.random() < args.p_consulta:
                t0 = time.perf_counter()
                r = s.get(f"{args.url}/sala", timeout=30)
                local["lat_consulta"].append(time.perf_counter() - t0)
                if r.status_code == 200:
                    d = r.json()
                    # Snapshot consistente: el contador debe coincidir con la matriz
                    libres = sum(1 for f in d["matriz"] for c in f if c is None)
                    if libres != d["disponibles"]:
                        local["errores"] += 1
                    local["consultas"] += 1
                else:
                    local["errores"] += 1
            else:
                # Zona "caliente" pequeña para forzar colisiones entre clientes
                zona = min(args.zona, args.filas * args.columnas)
                n = rng.randrange(zona)
                fila, col = divmod(n, args.columnas)
                t0 = time.perf_counter()
                r = s.post(f"{args.url}/comprar",
                           json={"fila": fila, "columna": col, "cliente_id": cid}, timeout=30)
                local["lat_compra"].append(time.perf_counter() - t0)
                if r.status_code == 200:
                    local["compras_ok"].append((fila, col, cid))
                elif r.status_code == 409:
                    local["compras_409"] += 1
                else:
                    local["errores"] += 1
        except (requests.RequestException, ValueError):
            local["errores"] += 1

    with lock_res:
        resultados.append(local)


def estadisticas_lat(datos):
    if not datos:
        return {"n": 0, "media_ms": None, "p95_ms": None, "max_ms": None}
    ms = sorted(x * 1000 for x in datos)
    p95 = ms[max(0, int(len(ms) * 0.95) - 1)]
    return {"n": len(ms), "media_ms": round(statistics.mean(ms), 2),
            "p95_ms": round(p95, 2), "max_ms": round(ms[-1], 2)}


def linea_lat(nombre, e):
    if e["n"] == 0:
        return f"{nombre}: sin datos"
    return f"{nombre}: n={e['n']} media={e['media_ms']:.1f}ms p95={e['p95_ms']:.1f}ms max={e['max_ms']:.1f}ms"


def esperar_servidor(url, segundos):
    """Reintenta hasta que /stats responda. Devuelve True si el servidor esta listo."""
    limite = time.time() + segundos
    while True:
        try:
            if requests.get(f"{url}/stats", timeout=2).status_code == 200:
                return True
        except requests.RequestException:
            pass
        if time.time() >= limite:
            return False
        time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5000")
    ap.add_argument("--clientes", type=int, default=50)
    ap.add_argument("--acciones", type=int, default=40)
    ap.add_argument("--filas", type=int, default=10)
    ap.add_argument("--columnas", type=int, default=10)
    ap.add_argument("--p-consulta", type=float, default=0.8)
    ap.add_argument("--zona", type=int, default=60, help="asientos en disputa (primeros N)")
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--esperar", type=float, default=0, help="segundos a esperar a que el servidor responda")
    ap.add_argument("--salida", help="archivo JSON donde guardar los resultados")
    ap.add_argument("--token", default=os.environ.get("ADMIN_TOKEN"),
                    help="token de administrador para /reset (por defecto, variable ADMIN_TOKEN)")
    args = ap.parse_args()
    args.url = args.url.rstrip("/")

    # ---------- preparacion ----------
    if not esperar_servidor(args.url, args.esperar):
        print(f"ERROR: el servidor {args.url} no responde.", file=sys.stderr)
        sys.exit(2)
    cabeceras = {"X-Admin-Token": args.token} if args.token else {}
    try:
        r = requests.post(f"{args.url}/reset", headers=cabeceras,
                          json={"filas": args.filas, "columnas": args.columnas}, timeout=10)
    except requests.RequestException as e:
        print(f"ERROR: no se pudo reiniciar la sala: {e}", file=sys.stderr)
        sys.exit(2)
    if r.status_code != 200:
        print(f"ERROR: /reset respondio {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(2)

    # ---------- ejecucion ----------
    resultados, lock_res = [], threading.Lock()
    hilos = [threading.Thread(target=cliente, args=(i, args, resultados, lock_res))
             for i in range(args.clientes)]
    t0 = time.perf_counter()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    dur = time.perf_counter() - t0

    # ---------- agregacion ----------
    consultas = sum(r["consultas"] for r in resultados)
    ok = [x for r in resultados for x in r["compras_ok"]]
    c409 = sum(r["compras_409"] for r in resultados)
    errores = sum(r["errores"] for r in resultados)
    lat_c = estadisticas_lat([x for r in resultados for x in r["lat_consulta"]])
    lat_b = estadisticas_lat([x for r in resultados for x in r["lat_compra"]])

    try:
        estado = requests.get(f"{args.url}/sala", timeout=10).json()
        stats = requests.get(f"{args.url}/stats", timeout=10).json()
    except (requests.RequestException, ValueError) as e:
        print(f"ERROR: no se pudo leer el estado final: {e}", file=sys.stderr)
        sys.exit(2)
    matriz = estado["matriz"]

    # ---------- verificacion de invariantes ----------
    asientos_ok = [(f, c) for f, c, _ in ok]
    ocupados = sum(1 for fila in matriz for x in fila if x is not None)
    checks = {
        "Ningun asiento vendido dos veces": len(asientos_ok) == len(set(asientos_ok)),
        "Cada venta exitosa figura a nombre de su cliente": all(matriz[f][c] == cid for f, c, cid in ok),
        "Ventas de clientes == asientos ocupados == ventas del servidor":
            len(ok) == ocupados == stats["ventas"],
        "Rechazos de clientes == conflictos del servidor": c409 == stats["conflictos"],
        "ocupados + disponibles == capacidad": ocupados + estado["disponibles"] == args.filas * args.columnas,
        "Consultas siempre consistentes (contador == matriz)": errores == 0,
        "Integridad interna del servidor": all(stats["integridad"].values()),
    }
    correcto = all(checks.values())

    print(f"\n=== Simulacion: {args.clientes} clientes x {args.acciones} acciones ({dur:.2f}s) ===")
    print(f"Consultas: {consultas} | Compras exitosas: {len(ok)} | Rechazos 409: {c409} | Errores: {errores}")
    print(linea_lat("Latencia consulta", lat_c))
    print(linea_lat("Latencia compra  ", lat_b))
    print("\n--- Invariantes ---")
    for nombre, valor in checks.items():
        print(f"[{'OK' if valor else 'FALLO'}] {nombre}")
    print("\nRESULTADO:", "TODO CORRECTO" if correcto else "HAY INCONSISTENCIAS")

    if args.salida:
        config = {k: v for k, v in vars(args).items() if k != "token"}
        with open(args.salida, "w", encoding="utf-8") as f:
            json.dump({
                "configuracion": config,
                "duracion_s": round(dur, 3),
                "totales": {"consultas": consultas, "compras_ok": len(ok),
                            "rechazos_409": c409, "errores": errores},
                "latencia": {"consulta": lat_c, "compra": lat_b},
                "invariantes": checks,
                "correcto": correcto,
            }, f, indent=2, ensure_ascii=False)
        print(f"Resultados guardados en {args.salida}")

    sys.exit(0 if correcto else 1)


if __name__ == "__main__":
    main()
