"""Lock de lectores-escritores JUSTO (FIFO) con threading.Condition.

- Varios lectores pueden entrar a la vez.
- Un escritor entra solo (sin lectores ni otros escritores).
- Cada solicitud toma un turno (ticket) y se atiende en orden de llegada,
  por lo que no hay inanicion ni de lectores ni de escritores.
"""
import threading
from contextlib import contextmanager


class FairRWLock:
    def __init__(self):
        self._cond = threading.Condition()
        self._readers = 0          # lectores activos
        self._writer = False       # hay un escritor activo
        self._next_ticket = 0      # siguiente turno a repartir
        self._now_serving = 0      # turno que puede ser admitido

    # ---------- lectura ----------
    def acquire_read(self):
        with self._cond:
            my = self._next_ticket
            self._next_ticket += 1
            # espera su turno y a que no haya escritor activo
            self._cond.wait_for(lambda: my == self._now_serving and not self._writer)
            self._readers += 1
            self._now_serving += 1   # deja pasar al siguiente (otro lector entra en paralelo)
            self._cond.notify_all()

    def release_read(self):
        with self._cond:
            self._readers -= 1
            self._cond.notify_all()

    # ---------- escritura ----------
    def acquire_write(self):
        with self._cond:
            my = self._next_ticket
            self._next_ticket += 1
            self._cond.wait_for(
                lambda: my == self._now_serving and not self._writer and self._readers == 0
            )
            self._writer = True
            self._now_serving += 1
            self._cond.notify_all()

    def release_write(self):
        with self._cond:
            self._writer = False
            self._cond.notify_all()

    # ---------- context managers ----------
    @contextmanager
    def read_lock(self):
        self.acquire_read()
        try:
            yield
        finally:
            self.release_read()

    @contextmanager
    def write_lock(self):
        self.acquire_write()
        try:
            yield
        finally:
            self.release_write()
