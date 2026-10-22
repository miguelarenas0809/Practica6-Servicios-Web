"""Pruebas de FairRWLock. Usan barreras y esperas activas, no dependen de tiempos fijos."""
import threading
import time

import pytest

from rwlock import FairRWLock

TIMEOUT = 5


def esperar(condicion, segundos=TIMEOUT):
    limite = time.time() + segundos
    while not condicion():
        if time.time() > limite:
            raise AssertionError("tiempo de espera agotado")
        time.sleep(0.005)


def test_varios_lectores_entran_a_la_vez():
    lock = FairRWLock()
    n = 5
    barrera = threading.Barrier(n, timeout=TIMEOUT)  # solo se cruza si los n estan dentro a la vez
    errores = []

    def lector():
        try:
            with lock.read_lock():
                barrera.wait()
        except threading.BrokenBarrierError:
            errores.append("lectores no concurrentes")

    hilos = [threading.Thread(daemon=True, target=lector) for _ in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert not errores


def test_escritor_es_exclusivo():
    lock = FairRWLock()
    estado = {"escritores": 0, "lectores": 0, "violaciones": 0}
    m = threading.Lock()

    def escritor():
        for _ in range(50):
            with lock.write_lock():
                with m:
                    if estado["escritores"] or estado["lectores"]:
                        estado["violaciones"] += 1
                    estado["escritores"] += 1
                time.sleep(0.0005)
                with m:
                    estado["escritores"] -= 1

    def lector():
        for _ in range(50):
            with lock.read_lock():
                with m:
                    if estado["escritores"]:
                        estado["violaciones"] += 1
                    estado["lectores"] += 1
                time.sleep(0.0005)
                with m:
                    estado["lectores"] -= 1

    hilos = [threading.Thread(daemon=True, target=escritor) for _ in range(4)] + \
            [threading.Thread(daemon=True, target=lector) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert estado["violaciones"] == 0


def test_escritor_en_espera_no_es_rebasado_por_lectores_nuevos():
    """FIFO: lector1 dentro -> escritor espera -> lector2 llega despues -> orden: escritor, lector2."""
    lock = FairRWLock()
    orden = []
    lock.acquire_read()  # lector1 mantiene el lock

    def escritor():
        with lock.write_lock():
            orden.append("escritor")

    def lector2():
        with lock.read_lock():
            orden.append("lector2")

    te = threading.Thread(daemon=True, target=escritor)
    te.start()
    esperar(lambda: lock._next_ticket == 2)       # turno 0 = lector1, turno 1 = escritor
    tl = threading.Thread(daemon=True, target=lector2)
    tl.start()
    esperar(lambda: lock._next_ticket == 3)       # turno 2 = lector2, detras del escritor
    assert orden == []                            # nadie avanza mientras lector1 sigue dentro
    lock.release_read()
    te.join(TIMEOUT)
    tl.join(TIMEOUT)
    assert orden == ["escritor", "lector2"]


def test_lector_en_espera_no_es_rebasado_por_escritores_nuevos():
    """FIFO simetrico: escritor1 dentro -> lector espera -> escritor2 despues -> orden: lector, escritor2."""
    lock = FairRWLock()
    orden = []
    lock.acquire_write()

    def lector():
        with lock.read_lock():
            orden.append("lector")

    def escritor2():
        with lock.write_lock():
            orden.append("escritor2")

    tl = threading.Thread(daemon=True, target=lector)
    tl.start()
    esperar(lambda: lock._next_ticket == 2)
    te = threading.Thread(daemon=True, target=escritor2)
    te.start()
    esperar(lambda: lock._next_ticket == 3)
    lock.release_write()
    tl.join(TIMEOUT)
    te.join(TIMEOUT)
    assert orden == ["lector", "escritor2"]


def test_se_libera_ante_excepcion():
    lock = FairRWLock()
    with pytest.raises(RuntimeError):
        with lock.write_lock():
            raise RuntimeError("fallo")
    # si no se hubiera liberado, esto se bloquearia
    hecho = threading.Event()

    def usar():
        with lock.write_lock():
            hecho.set()

    t = threading.Thread(daemon=True, target=usar)
    t.start()
    assert hecho.wait(TIMEOUT)
    t.join()
