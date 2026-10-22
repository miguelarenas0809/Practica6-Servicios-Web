"""Pruebas de concurrencia de la clase Sala (sin HTTP)."""
import random
import threading

from servidor import Sala


def test_un_solo_ganador_por_asiento():
    sala = Sala(5, 5)
    n = 50
    barrera = threading.Barrier(n)
    resultados = []

    def comprar(i):
        barrera.wait()
        resultados.append(sala.comprar(2, 3, f"c{i}"))

    hilos = [threading.Thread(target=comprar, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert resultados.count(True) == 1
    assert resultados.count(False) == n - 1
    s = sala.estadisticas()
    assert s["ventas"] == 1 and s["conflictos"] == n - 1 and s["disponibles"] == 24
    assert all(s["integridad"].values())


def test_compras_concurrentes_sobre_toda_la_sala_conservan_invariantes():
    filas, cols = 6, 6
    sala = Sala(filas, cols)
    ganadores = []
    m = threading.Lock()

    def cliente(i):
        rng = random.Random(i)
        for _ in range(80):
            f, c = rng.randrange(filas), rng.randrange(cols)
            if sala.comprar(f, c, f"c{i}"):
                with m:
                    ganadores.append((f, c, f"c{i}"))

    hilos = [threading.Thread(target=cliente, args=(i,)) for i in range(20)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len({(f, c) for f, c, _ in ganadores}) == len(ganadores)   # sin doble venta
    snap = sala.consultar()
    assert all(snap["matriz"][f][c] == cid for f, c, cid in ganadores)
    s = sala.estadisticas()
    assert s["ventas"] == s["ocupados"] == len(ganadores)
    assert s["ocupados"] + s["disponibles"] == filas * cols
    assert all(s["integridad"].values())


def test_lecturas_siempre_consistentes_durante_escrituras():
    sala = Sala(10, 10)
    terminado = threading.Event()
    inconsistencias = []

    def escritor(k):
        for n in range(25):
            sala.comprar((k * 25 + n) // 10, (k * 25 + n) % 10, f"w{k}")

    def lector():
        while not terminado.is_set():
            d = sala.consultar()
            libres = sum(1 for f in d["matriz"] for c in f if c is None)
            if libres != d["disponibles"]:
                inconsistencias.append((libres, d["disponibles"]))

    lectores = [threading.Thread(target=lector) for _ in range(4)]
    escritores = [threading.Thread(target=escritor, args=(k,)) for k in range(4)]
    for h in lectores + escritores:
        h.start()
    for h in escritores:
        h.join()
    terminado.set()
    for h in lectores:
        h.join()

    assert inconsistencias == []
    assert sala.estadisticas()["disponibles"] == 0


def test_consultar_devuelve_copia():
    sala = Sala(3, 3)
    d = sala.consultar()
    d["matriz"][0][0] = "intruso"
    d["disponibles"] = -1
    assert sala.consultar()["matriz"][0][0] is None
    assert sala.consultar()["disponibles"] == 9
