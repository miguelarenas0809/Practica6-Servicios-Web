"""Cliente manual (interactivo) para la sala de cine.

    python cliente_manual.py --url http://127.0.0.1:5000 --id Ana
"""
import argparse
import os
import sys

import requests


def mostrar_sala(d, mi_id):
    filas, cols = d["filas"], d["columnas"]
    print(f"\nAsientos disponibles: {d['disponibles']} de {filas * cols}")
    print("Leyenda: [ ] libre | [X] vendido | [*] comprado por ti\n")
    print("     " + " ".join(f"{c:>2}" for c in range(cols)))
    for i, fila in enumerate(d["matriz"]):
        celdas = []
        for dueno in fila:
            if dueno is None:
                celdas.append("[ ]")
            elif dueno == mi_id:
                celdas.append("[*]")
            else:
                celdas.append("[X]")
        print(f"{i:>3}  " + "".join(celdas))
    print()


def consultar(url, mi_id):
    r = requests.get(f"{url}/sala", timeout=10)
    r.raise_for_status()
    mostrar_sala(r.json(), mi_id)


def comprar(url, mi_id):
    try:
        fila = int(input("Fila: ").strip())
        columna = int(input("Columna: ").strip())
    except ValueError:
        print("Fila y columna deben ser numeros enteros.")
        return
    r = requests.post(f"{url}/comprar",
                      json={"fila": fila, "columna": columna, "cliente_id": mi_id}, timeout=10)
    if r.status_code == 200:
        print(f"Compra exitosa: asiento ({fila}, {columna}) a nombre de '{mi_id}'.")
    elif r.status_code == 409:
        print(f"El asiento ({fila}, {columna}) ya esta ocupado. Elige otro.")
    else:
        print(f"Solicitud invalida ({r.status_code}): {r.json().get('error')}")


def estadisticas(url):
    r = requests.get(f"{url}/stats", timeout=10)
    r.raise_for_status()
    s = r.json()
    print(f"\nCapacidad: {s['capacidad']} | Ocupados: {s['ocupados']} | "
          f"Disponibles: {s['disponibles']}")
    print(f"Ventas: {s['ventas']} | Conflictos (409): {s['conflictos']}")
    for nombre, ok in s["integridad"].items():
        print(f"  [{'OK' if ok else 'FALLO'}] {nombre}")
    print()


def reiniciar(url):
    if input("Esto borra todas las ventas. Escribe 'si' para confirmar: ").strip().lower() != "si":
        print("Cancelado.")
        return
    token = os.environ.get("ADMIN_TOKEN")
    cabeceras = {"X-Admin-Token": token} if token else {}
    r = requests.post(f"{url}/reset", json={}, headers=cabeceras, timeout=10)
    datos = r.json()
    print(datos.get("mensaje") or f"Error ({r.status_code}): {datos.get('error')}")


MENU = """--- Menu ({id}) ---
1. Consultar sala
2. Comprar boleto
3. Ver estadisticas del servidor
4. Cambiar mi id de cliente
5. Reiniciar sala
0. Salir"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5000")
    ap.add_argument("--id", default="cliente-manual", help="identificador del cliente")
    args = ap.parse_args()
    url, mi_id = args.url.rstrip("/"), args.id

    while True:
        print(MENU.format(id=mi_id))
        try:
            opcion = input("Opcion: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            return
        try:
            if opcion == "1":
                consultar(url, mi_id)
            elif opcion == "2":
                comprar(url, mi_id)
            elif opcion == "3":
                estadisticas(url)
            elif opcion == "4":
                nuevo = input("Nuevo id: ").strip()
                if nuevo:
                    mi_id = nuevo
            elif opcion == "5":
                reiniciar(url)
            elif opcion == "0":
                print("Hasta luego.")
                return
            else:
                print("Opcion no valida.")
        except requests.RequestException as e:
            print(f"No se pudo comunicar con el servidor: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
