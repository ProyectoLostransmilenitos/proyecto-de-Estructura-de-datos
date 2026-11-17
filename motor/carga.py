"""Lectura de los tres CSV (solo modulo csv, sin dict ni set)."""
import csv

from .algoritmos import esta_ordenada, ordenar
from .estructuras import AVL


def _ruta_archivo(carpeta, nombre):
    carpeta = str(carpeta)
    if carpeta.endswith("/") or carpeta.endswith("\\"):
        return carpeta + nombre
    return carpeta + "/" + nombre


def _filas(carpeta, nombre):
    with open(_ruta_archivo(carpeta, nombre), newline="", encoding="utf-8-sig") as f:
        lector = csv.reader(f)
        next(lector, None)  # encabezado
        for fila in lector:
            if fila:
                yield fila


def minutos(hora):
    """'HH:MM' -> minutos desde el inicio del dia de servicio.
    Horas >= 24 (ej. '25:10') se conservan como 1510: sin envolver al dia siguiente."""
    partes = hora.strip().split(":")
    return int(partes[0]) * 60 + int(partes[1])


def formato(m):
    return str(m // 60).zfill(2) + ":" + str(m % 60).zfill(2)


def leer_estaciones(carpeta):
    vistas = AVL()
    resultado = []
    for fila in _filas(carpeta, "estaciones.csv"):
        nombre = fila[0].strip()
        if nombre != "" and vistas.buscar(nombre) is None:
            vistas.insertar(nombre, True)
            resultado.append(nombre)
    return resultado


def leer_rutas(carpeta):
    """-> AVL ruta -> [estaciones en orden]."""
    pares = AVL()
    for fila in _filas(carpeta, "rutas.csv"):
        try:
            orden = int(fila[1])
        except ValueError:
            continue
        r = fila[0].strip()
        lista = pares.buscar(r)
        if lista is None:
            lista = []
            pares.insertar(r, lista)
        lista.append((orden, fila[2].strip()))

    rutas = AVL()
    for r, lista in pares.recorrer_desde(None):
        if not esta_ordenada(lista):
            lista = ordenar(lista)
        rutas.insertar(r, [e for _, e in lista])
    return rutas


def leer_horarios(carpeta):
    """-> AVL (ruta, estacion) -> [minutos ordenados]."""
    h = AVL()
    for fila in _filas(carpeta, "horarios.csv"):
        try:
            m = minutos(fila[2])
        except (ValueError, IndexError):
            continue
        clave = (fila[0].strip(), fila[1].strip())
        lista = h.buscar(clave)
        if lista is None:
            h.insertar(clave, [m])
        else:
            lista.append(m)

    for clave, lista in h.recorrer_desde(None):
        if not esta_ordenada(lista):
            h.insertar(clave, ordenar(lista))
    return h
