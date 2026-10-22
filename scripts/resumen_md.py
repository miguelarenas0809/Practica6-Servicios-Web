"""Convierte uno o varios resultados.json del simulador en una tabla Markdown.

    python scripts/resumen_md.py resultados.json >> "$GITHUB_STEP_SUMMARY"
"""
import json
import sys


def main(rutas):
    print("### Resultados de la simulacion\n")
    print("| Clientes | Acciones | Sala | % consulta | Zona | Compras OK | 409 | Errores "
          "| Lat. consulta (media/p95 ms) | Lat. compra (media/p95 ms) | Resultado |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        c, t, lat = d["configuracion"], d["totales"], d["latencia"]

        def fmt(e):
            return "-" if e["n"] == 0 else f"{e['media_ms']} / {e['p95_ms']}"

        print(f"| {c['clientes']} | {c['acciones']} | {c['filas']}x{c['columnas']} | "
              f"{int(c['p_consulta'] * 100)}% | {c['zona']} | {t['compras_ok']} | {t['rechazos_409']} | "
              f"{t['errores']} | {fmt(lat['consulta'])} | {fmt(lat['compra'])} | "
              f"{'OK' if d['correcto'] else 'FALLO'} |")
    print("\n#### Invariantes verificadas\n")
    with open(rutas[0], encoding="utf-8") as f:
        for nombre, ok in json.load(f)["invariantes"].items():
            print(f"- {'✅' if ok else '❌'} {nombre}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("uso: resumen_md.py resultados.json [...]")
    main(sys.argv[1:])
