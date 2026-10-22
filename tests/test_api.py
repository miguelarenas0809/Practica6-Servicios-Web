"""Pruebas de los endpoints con el cliente de pruebas de Flask."""
import pytest

import servidor


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(servidor, "ADMIN_TOKEN", None)
    servidor.sala.reiniciar(5, 5)
    return servidor.app.test_client()


def comprar(c, fila, columna, cid="ana"):
    return c.post("/comprar", json={"fila": fila, "columna": columna, "cliente_id": cid})


def test_get_sala(cliente):
    r = cliente.get("/sala")
    d = r.get_json()
    assert r.status_code == 200
    assert d["filas"] == 5 and d["columnas"] == 5 and d["disponibles"] == 25
    assert d["matriz"] == [[None] * 5 for _ in range(5)]


def test_compra_exitosa_y_conflicto(cliente):
    assert comprar(cliente, 1, 2).status_code == 200
    r = comprar(cliente, 1, 2, "beto")
    assert r.status_code == 409
    d = cliente.get("/sala").get_json()
    assert d["matriz"][1][2] == "ana" and d["disponibles"] == 24
    s = cliente.get("/stats").get_json()
    assert s["ventas"] == 1 and s["conflictos"] == 1 and all(s["integridad"].values())


@pytest.mark.parametrize("cuerpo", [
    {},
    {"fila": 0, "columna": 0},
    {"fila": "0", "columna": 0, "cliente_id": "a"},
    {"fila": True, "columna": 0, "cliente_id": "a"},
    {"fila": 0.5, "columna": 0, "cliente_id": "a"},
    {"fila": 0, "columna": 0, "cliente_id": ""},
    {"fila": 0, "columna": 0, "cliente_id": 7},
    {"fila": -1, "columna": 0, "cliente_id": "a"},
    {"fila": 0, "columna": 5, "cliente_id": "a"},
    {"fila": 5, "columna": 0, "cliente_id": "a"},
    {"fila": 0, "columna": 0, "cliente_id": "x" * (servidor.MAX_ID + 1)},
    [1, 2, 3],
])
def test_compra_invalida_devuelve_400(cliente, cuerpo):
    assert cliente.post("/comprar", json=cuerpo).status_code == 400
    assert cliente.get("/stats").get_json()["ventas"] == 0


def test_cuerpo_que_no_es_json_devuelve_400(cliente):
    assert cliente.post("/comprar", data="no es json").status_code == 400


def test_cuerpo_demasiado_grande_devuelve_413(cliente):
    r = cliente.post("/comprar", json={"fila": 0, "columna": 0, "cliente_id": "x" * (servidor.MAX_BODY + 10)})
    assert r.status_code == 413


def test_reset_sin_token_configurado(cliente):
    comprar(cliente, 0, 0)
    r = cliente.post("/reset", json={"filas": 3, "columnas": 4})
    assert r.status_code == 200
    d = cliente.get("/sala").get_json()
    assert (d["filas"], d["columnas"], d["disponibles"]) == (3, 4, 12)


@pytest.mark.parametrize("cuerpo", [
    {"filas": 0, "columnas": 5},
    {"filas": 5, "columnas": -1},
    {"filas": servidor.MAX_DIM + 1, "columnas": 5},
    {"filas": 100000, "columnas": 100000},
    {"filas": "5", "columnas": 5},
    {"filas": True, "columnas": 5},
])
def test_reset_con_dimensiones_invalidas(cliente, cuerpo):
    assert cliente.post("/reset", json=cuerpo).status_code == 400
    assert cliente.get("/sala").get_json()["filas"] == 5   # la sala no cambio


def test_reset_exige_token_si_esta_configurado(cliente, monkeypatch):
    monkeypatch.setattr(servidor, "ADMIN_TOKEN", "secreto")
    comprar(cliente, 0, 0)
    assert cliente.post("/reset", json={}).status_code == 403
    assert cliente.post("/reset", json={}, headers={"X-Admin-Token": "incorrecto"}).status_code == 403
    assert cliente.get("/stats").get_json()["ventas"] == 1       # nada se borro
    assert cliente.post("/reset", json={}, headers={"X-Admin-Token": "secreto"}).status_code == 200
    assert cliente.get("/stats").get_json()["ventas"] == 0
