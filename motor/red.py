"""Clase Red: contrato del motor (R1-R9) sin dict ni set internos."""
from .estructuras import AVL, ListaDoble, Pila
from .algoritmos import primero_mayor_o_igual
from . import carga


class _Ruta:
    __slots__ = ("id", "lista", "nodos")

    def __init__(self, id_):
        self.id = id_
        self.lista = ListaDoble()       # paradas en orden (R7)
        self.nodos = AVL()              # estacion -> nodo de la lista


class Red:
    def __init__(self, carpeta):
        nombres = carga.leer_estaciones(carpeta)
        rutas = carga.leer_rutas(carpeta)
        self._horarios = carga.leer_horarios(carpeta)

        self._abierta = AVL()           # R1: nombre -> bool
        self._buses = AVL()             # nombre -> buses al dia
        self._rutas_de = AVL()          # estacion -> AVL(ruta -> True)
        self._arbol_nombres = AVL()     # R2/R3: estaciones abiertas por nombre
        self._arbol_ranking = AVL()     # R6: estaciones abiertas por (-buses, nombre)
        self._rutas = AVL()             # id_ -> _Ruta
        self._deshacer = Pila()         # R9
        self._rehacer = Pila()
        self._nuevas = AVL()            # estaciones añadidas en runtime

        for nombre in nombres:
            self._abierta.insertar(nombre, True)
            self._buses.insertar(nombre, 0)
            self._rutas_de.insertar(nombre, AVL())

        for id_, lista_estaciones in rutas.recorrer_desde(None):
            ruta = _Ruta(id_)
            for est in lista_estaciones:
                if self._abierta.buscar(est) is None or ruta.nodos.buscar(est) is not None:
                    continue  # estacion desconocida o repetida en la ruta
                ruta.nodos.insertar(est, ruta.lista.agregar_al_final(est))
                self._rutas_de.buscar(est).insertar(id_, True)
                buses_actual = self._buses.buscar(est)
                self._buses.insertar(est, buses_actual + self._pasan(id_, est))
            self._rutas.insertar(id_, ruta)

        for nombre in nombres:
            self._arbol_nombres.insertar(nombre, True)
            self._arbol_ranking.insertar((-self._buses.buscar(nombre), nombre), True)

    # ------------------------------------------------------------ auxiliares
    def _pasan(self, ruta, estacion):
        h = self._horarios.buscar((ruta, estacion))
        return len(h) if h is not None else 0

    def _ajustar_buses(self, estacion, delta):
        antes = self._buses.buscar(estacion)
        nuevo = antes + delta
        self._buses.insertar(estacion, nuevo)
        if self._abierta.buscar(estacion) is True:
            self._arbol_ranking.eliminar((-antes, estacion))
            self._arbol_ranking.insertar((-nuevo, estacion), True)

    def crear_estacion(self, nombre):
        """Extra (fuera del contrato): registra una estacion nueva, abierta y sin rutas."""
        if nombre == "" or self._abierta.buscar(nombre) is not None:
            return False
        self._abierta.insertar(nombre, True)
        self._buses.insertar(nombre, 0)
        self._rutas_de.insertar(nombre, AVL())
        self._arbol_nombres.insertar(nombre, True)
        self._arbol_ranking.insertar((0, nombre), True)
        self._nuevas.insertar(nombre, True)
        return True

    def eliminar_estacion(self, nombre):
        """Extra: elimina SOLO una estacion creada con crear_estacion."""
        if self._nuevas.buscar(nombre) is None:
            return False
        rutas_est = [r for r, _ in self._rutas_de.buscar(nombre).recorrer_desde(None)]
        for ruta in rutas_est:
            self._quitar(ruta, nombre)
        if self._abierta.buscar(nombre) is True:
            self._arbol_nombres.eliminar(nombre)
            self._arbol_ranking.eliminar((-self._buses.buscar(nombre), nombre))
        self._abierta.eliminar(nombre)
        self._buses.eliminar(nombre)
        self._rutas_de.eliminar(nombre)
        self._nuevas.eliminar(nombre)
        self._deshacer.vaciar()
        self._rehacer.vaciar()
        return True

    # ------------------------------------------------------------ R1
    def estado(self, nombre):
        """'abierta', 'cerrada' o 'no existe'."""
        a = self._abierta.buscar(nombre)
        if a is None:
            return "no existe"
        return "abierta" if a else "cerrada"

    # ------------------------------------------------------------ R2
    def autocompletar(self, prefijo, k):
        """Hasta k estaciones abiertas que empiezan por prefijo, en orden."""
        res = []
        if k <= 0:
            return res
        for nombre, _ in self._arbol_nombres.recorrer_desde(prefijo):
            if not nombre.startswith(prefijo):
                break
            res.append(nombre)
            if len(res) >= k:
                break
        return res

    # ------------------------------------------------------------ R3
    def rango(self, desde, hasta):
        """Abiertas con desde <= nombre <= hasta, en orden."""
        res = []
        if hasta < desde:
            return res
        for nombre, _ in self._arbol_nombres.recorrer_desde(desde):
            if hasta < nombre:
                break
            res.append(nombre)
        return res

    # ------------------------------------------------------------ R4
    def proximo_bus(self, estacion, ruta, hora):
        """Primera hora de paso >= hora ('HH:MM'), como 'HH:MM', o None."""
        if self._abierta.buscar(estacion) is not True:
            return None
        r = self._rutas.buscar(ruta)
        if r is None or r.nodos.buscar(estacion) is None:
            return None
        horas = self._horarios.buscar((ruta, estacion))
        if horas is None:
            return None
        m = hora if isinstance(hora, int) else carga.minutos(hora)
        i = primero_mayor_o_igual(horas, m)
        if i >= len(horas):
            return None
        return carga.formato(horas[i])

    # ------------------------------------------------------------ R5
    def viaje(self, origen, destino):
        """Ruta con cualquier cantidad de transbordos."""
        if self._abierta.buscar(origen) is not True or self._abierta.buscar(destino) is not True:
            return None
        if origen == destino:
            return {"tipo": "directo", "tramos": [], "paradas": 0, "transbordo": None,
                    "transbordos": [], "cruza_cerrada": False}

        info = AVL()     # (ruta, estacion_subida) -> [cruza, paradas, clave_padre, estacion_subida]
        visto = AVL()
        nivel = []

        for ra, _ in self._rutas_de.buscar(origen).recorrer_desde(None):
            k = (ra, origen)
            info.insertar(k, [False, 0, None, origen])
            visto.insertar(k, True)
            nivel.append(k)

        while nivel:
            fin = None
            sig = []
            for k in nivel:
                ruta, sube = k
                datos_k = info.buscar(k)
                cruza, paradas = datos_k[0], datos_k[1]
                nodo = self._rutas.buscar(ruta).nodos.buscar(sube).sig
                while nodo is not None:
                    est = nodo.valor
                    nodo = nodo.sig
                    if self._abierta.buscar(est) is not True:
                        cruza = True
                        continue
                    paradas += 1
                    if est == destino:
                        if fin is None or (cruza, paradas) < (fin[0], fin[1]):
                            fin = (cruza, paradas, k)
                        break
                    for rb, _ in self._rutas_de.buscar(est).recorrer_desde(None):
                        if rb == ruta:
                            continue
                        nk = (rb, est)
                        if visto.buscar(nk) is not None:
                            continue
                        previo = info.buscar(nk)
                        if previo is None or (cruza, paradas) < (previo[0], previo[1]):
                            if previo is None:
                                sig.append(nk)
                            info.insertar(nk, [cruza, paradas, k, est])

            if fin is not None:
                cruza, paradas, k = fin
                cadena = []
                while k is not None:
                    cadena.append(k)
                    k = info.buscar(k)[2]
                cadena.reverse()
                tramos = []
                for n, (ruta, sube) in enumerate(cadena):
                    hasta = cadena[n + 1][1] if n + 1 < len(cadena) else destino
                    tramos.append((ruta, sube, hasta))
                trans = [sube for _, sube in cadena[1:]]
                return {"tipo": "directo" if not trans else "transbordo", "tramos": tramos,
                        "paradas": paradas, "transbordo": trans[0] if trans else None,
                        "transbordos": trans, "cruza_cerrada": cruza}

            for nk in sig:
                visto.insertar(nk, True)
            nivel = sig
        return None

    # ------------------------------------------------------------ R6
    def ranking(self, k):
        """k estaciones abiertas con mas buses al dia: [(nombre, buses)]."""
        res = []
        if k <= 0:
            return res
        for (neg, nombre), _ in self._arbol_ranking.recorrer_desde(None):
            res.append((nombre, -neg))
            if len(res) >= k:
                break
        return res

    def conteo(self, nombre):
        """Buses al dia de una estacion y su puesto entre las abiertas."""
        buses_est = self._buses.buscar(nombre)
        if buses_est is None:
            return None
        if self._abierta.buscar(nombre) is not True:
            return {"nombre": nombre, "buses": buses_est, "abierta": False,
                    "puesto": None, "abiertas": len(self._arbol_nombres)}
        puesto = 0
        for (neg, otra), _ in self._arbol_ranking.recorrer_desde(None):
            puesto += 1
            if otra == nombre:
                break
        return {"nombre": nombre, "buses": buses_est, "abierta": True,
                "puesto": puesto, "abiertas": len(self._arbol_nombres)}

    # ------------------------------------------------------------ R7
    def recorrido(self, ruta, al_reves=False):
        """Paradas de la ruta (incluye cerradas), en un sentido o en el otro."""
        r = self._rutas.buscar(ruta)
        if r is None:
            return []
        return list(r.lista.atras() if al_reves else r.lista.adelante())

    def _agregar(self, ruta, nueva, despues_de):
        r = self._rutas.buscar(ruta)
        if r is None or self._abierta.buscar(nueva) is None or r.nodos.buscar(nueva) is not None:
            return False
        ref = None
        if despues_de is not None:
            ref = r.nodos.buscar(despues_de)
            if ref is None:
                return False
        r.nodos.insertar(nueva, r.lista.insertar_despues(ref, nueva))
        self._rutas_de.buscar(nueva).insertar(ruta, True)
        self._ajustar_buses(nueva, self._pasan(ruta, nueva))
        return True

    def _quitar(self, ruta, estacion):
        """-> (ok, estacion anterior en la ruta o None)."""
        r = self._rutas.buscar(ruta)
        if r is None:
            return False, None
        nodo = r.nodos.buscar(estacion)
        if nodo is None:
            return False, None
        anterior = nodo.ant.valor if nodo.ant is not None else None
        r.lista.quitar(nodo)
        r.nodos.eliminar(estacion)
        self._rutas_de.buscar(estacion).eliminar(ruta)
        self._ajustar_buses(estacion, -self._pasan(ruta, estacion))
        return True, anterior

    def agregar_parada(self, ruta, nueva, despues_de):
        """Inserta `nueva` justo despues de `despues_de` (None = al inicio)."""
        if self._agregar(ruta, nueva, despues_de):
            self._registrar(("agregar", ruta, nueva, despues_de))
            return True
        return False

    def quitar_parada(self, ruta, estacion):
        ok, anterior = self._quitar(ruta, estacion)
        if ok:
            self._registrar(("quitar", ruta, estacion, anterior))
        return ok

    # ------------------------------------------------------------ R8
    def _cerrar(self, nombre):
        if self._abierta.buscar(nombre) is not True:
            return False
        self._abierta.insertar(nombre, False)
        self._arbol_nombres.eliminar(nombre)
        self._arbol_ranking.eliminar((-self._buses.buscar(nombre), nombre))
        return True

    def _reabrir(self, nombre):
        if self._abierta.buscar(nombre) is not False:
            return False
        self._abierta.insertar(nombre, True)
        self._arbol_nombres.insertar(nombre, True)
        self._arbol_ranking.insertar((-self._buses.buscar(nombre), nombre), True)
        return True

    def cerrar(self, nombre):
        if self._cerrar(nombre):
            self._registrar(("cerrar", nombre))
            return True
        return False

    def reabrir(self, nombre):
        if self._reabrir(nombre):
            self._registrar(("reabrir", nombre))
            return True
        return False

    # ------------------------------------------------------------ R9
    def _registrar(self, cambio):
        self._deshacer.apilar(cambio)
        self._rehacer.vaciar()

    def deshacer(self):
        c = self._deshacer.desapilar()
        if c is None:
            return False
        tipo = c[0]
        if tipo == "cerrar":
            self._reabrir(c[1])
        elif tipo == "reabrir":
            self._cerrar(c[1])
        elif tipo == "agregar":
            self._quitar(c[1], c[2])
        else:  # quitar
            self._agregar(c[1], c[2], c[3])
        self._rehacer.apilar(c)
        return True

    def rehacer(self):
        c = self._rehacer.desapilar()
        if c is None:
            return False
        tipo = c[0]
        if tipo == "cerrar":
            self._cerrar(c[1])
        elif tipo == "reabrir":
            self._reabrir(c[1])
        elif tipo == "agregar":
            self._agregar(c[1], c[2], c[3])
        else:  # quitar
            self._quitar(c[1], c[2])
        self._deshacer.apilar(c)
        return True
