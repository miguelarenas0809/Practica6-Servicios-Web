# Sala de cine: lectores-escritores con servicios web

[![CI](https://github.com/USUARIO/REPOSITORIO/actions/workflows/ci.yml/badge.svg)](https://github.com/USUARIO/REPOSITORIO/actions/workflows/ci.yml)

Simulación de venta de boletos en una sala de cine mediante un servicio web en Flask.
Es una instancia del problema **lectores-escritores**:

- **Lectores**: clientes que consultan la sala (asientos restantes). Pueden ir en paralelo.
- **Escritores**: clientes que compran un boleto. Requieren acceso exclusivo.

La sala se representa con una **matriz** (`None` = libre, `cliente_id` = vendido).

## Problemas de concurrencia y cómo se evitan

| Problema | Estrategia |
|---|---|
| Doble venta (check-then-act) | Verificar y escribir el asiento dentro de la misma sección crítica (`Sala.comprar`) |
| Actualización perdida del contador | El contador solo se modifica con el lock de escritura tomado |
| Lecturas inconsistentes | `Sala.consultar` toma el lock de lectura y devuelve una copia (snapshot) |
| Inanición | `FairRWLock`: lock de lectores-escritores con turnos FIFO (`threading.Condition`) |
| Estado duplicado | Un solo proceso con varios hilos (el estado vive en memoria) |

## Estructura

```
rwlock.py            Lock de lectores-escritores justo (FIFO)
servidor.py          Servidor Flask (sala, endpoints, validaciones)
simulador.py         Simulador de clientes concurrentes + verificación de invariantes
cliente_manual.py    Cliente interactivo de consola
cliente_gui.py       Cliente gráfico (Tkinter)
scripts/resumen_md.py  Convierte resultados.json en tabla Markdown
tests/               Pruebas con pytest (lock, sala, API)
.github/workflows/ci.yml   Integración continua
```

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # para desarrollo: requirements-dev.txt
```

La GUI requiere Tkinter (incluido en Python para Windows y macOS; en Linux: `sudo apt install python3-tk`).

## Uso

```bash
# Terminal 1: servidor (un solo proceso)
python servidor.py --filas 10 --columnas 10 --puerto 5000

# Terminal 2: simulación
python simulador.py --clientes 50 --acciones 40

# Clientes manuales (puedes abrir varios con distinto --id)
python cliente_manual.py --id Ana
python cliente_gui.py --id Beto
```

### API

| Endpoint | Rol | Descripción |
|---|---|---|
| `GET /sala` | Lector | Asientos disponibles y matriz |
| `POST /comprar` | Escritor | Body `{fila, columna, cliente_id}`. 200 vendido, 409 ocupado, 400 inválido |
| `GET /stats` | Lector | Ventas, conflictos y chequeos de integridad |
| `POST /reset` | Escritor | Reinicia la sala. Body opcional `{filas, columnas}` |

### Simulador

Opciones principales: `--clientes`, `--acciones`, `--filas`, `--columnas`, `--p-consulta`
(proporción de consultas), `--zona` (asientos en disputa), `--semilla`, `--esperar SEG`
(espera a que el servidor responda) y `--salida resultados.json`.

Verifica siete invariantes (sin doble venta, ventas = ocupados, contador = matriz, etc.).
Códigos de salida: `0` todo correcto, `1` hay inconsistencias, `2` no se pudo preparar la simulación.

## Seguridad básica

- Límites: sala de hasta 100×100, `cliente_id` de hasta 64 caracteres, cuerpo de petición de hasta 1 KB.
- Si se define la variable de entorno `ADMIN_TOKEN`, `POST /reset` exige la cabecera `X-Admin-Token`.
  El simulador y el cliente manual la envían automáticamente si la variable está definida.
- El servidor escucha solo en `127.0.0.1` y no usa modo debug.

```bash
export ADMIN_TOKEN=un-valor-secreto
python servidor.py
```

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

## Integración continua (GitHub Actions)

En cada `push` a `main` y en cada `pull_request`:

1. **Pruebas**: estilo (`ruff`), compilación y `pytest` en Python 3.10 y 3.12.
2. **Simulación**: levanta el servidor y ejecuta el simulador con cuatro configuraciones
   (ligera, alta concurrencia, mayoría de compras, alta contención). Si una invariante falla,
   el trabajo falla. Los resultados quedan como artefactos y como tabla en el resumen del trabajo.

> Los runners de GitHub son máquinas compartidas: las latencias varían entre ejecuciones.
> El CI valida la **corrección**, no el rendimiento.

## Limitaciones

- El estado vive en memoria: se pierde al reiniciar y no escala a varios procesos o instancias.
- Sin autenticación de clientes: `cliente_id` es declarado por el propio cliente.
- Servidor de desarrollo de Flask y sin HTTPS: adecuado para práctica local, no para exponerlo a Internet.
