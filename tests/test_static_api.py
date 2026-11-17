"""Compare the GitHub Pages adapter with the original Python API, using only Node built-ins."""
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "front"))
import app
from export_static import export_network
from motor import Red

RUNNER = """
const {createStaticAPI} = await import(process.argv[1]);
let input = '';
for await (const chunk of process.stdin) input += chunk;
const {data, calls} = JSON.parse(input);
const api = createStaticAPI(data);
Math.random = () => 0.5;
const results = calls.map(([name, params, post]) => {
    try { return {value: api(name, params, post)}; }
    catch (error) { return {error: error.message}; }
});
process.stdout.write(JSON.stringify(results));
"""


@unittest.skipUnless(shutil.which("node"), "Node is needed to verify the browser adapter")
class StaticAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "network.json"
            export_network(target)
            cls.data = json.loads(target.read_text(encoding="utf-8"))

    def compare_calls(self, calls):
        result = subprocess.run(
            ["node", "--input-type=module", "-e", RUNNER, str(ROOT / "front/static-api.mjs")],
            input=json.dumps({"data": self.data, "calls": calls}),
            capture_output=True, text=True, check=True,
        )
        actual = json.loads(result.stdout)
        with patch.object(app, "red", Red(app.DATOS)), patch.object(app.random, "uniform", lambda a, b: a + (b - a) * 0.5):
            for call, response in zip(calls, actual):
                name, params, post = call
                with self.subTest(name=name, params=params):
                    if post:
                        expected = app.POST[name](params)
                    else:
                        expected = app.GET[name]({key: [str(value)] for key, value in params.items()})
                    expected = json.loads(json.dumps(expected))
                    self.assertEqual(response, {"value": expected})
        self.assertEqual(len(actual), len(calls))

    def test_queries_and_trips_match_python(self):
        calls = [
            ["rutas", {}, False], ["wrapped", {}, False], ["buses", {}, False],
            ["estado", {"nombre": "UNIVERSIDADES"}, False],
            ["estado", {"nombre": "DOES NOT EXIST"}, False],
            ["autocompletar", {"prefijo": "PORTAL", "k": 8}, False],
            ["autocompletar", {"prefijo": "", "k": 0}, False],
            ["rango", {"desde": "CALLE 22", "hasta": "CALLE 76"}, False],
            ["ranking", {"k": 1000}, False],
            ["conteo", {"nombre": "UNIVERSIDADES"}, False],
            ["conteo", {"nombre": "DOES NOT EXIST"}, False],
            ["recorrido", {"ruta": "1-1", "reves": "1"}, False],
            ["recorrido", {"ruta": "DOES NOT EXIST"}, False],
            ["horarios", {"ruta": "1-1", "estacion": "UNIVERSIDADES"}, False],
        ]
        for hour in ("00:00", "08:00", "23:59", "25:10"):
            calls.append(["proximo_bus", {"ruta": "1-1", "estacion": "UNIVERSIDADES", "hora": hour}, False])
        calls.append(["viaje", {"origen": "UNIVERSIDADES", "destino": "PORTAL ELDORADO"}, False])
        rng = random.Random(23)
        for _ in range(80):
            origin, destination = rng.choices(self.data["stations"], k=2)
            calls.append(["viaje", {"origen": origin, "destino": destination}, False])
        self.compare_calls(calls)

    def test_edits_history_and_closed_stations_match_python(self):
        calls = []

        def call(name, post=False, **params):
            calls.append([name, params, post])

        def snapshot():
            call("ranking", k=1000)
            call("autocompletar", prefijo="", k=1000)
            call("recorrido", ruta="1-1")
            call("viaje", origen="UNIVERSIDADES", destino="PORTAL ELDORADO")
            call("viaje", origen="PORTAL NORTE", destino="PORTAL SUR")

        call("crear", True, nombre="STATIC NEW")
        call("crear", True, nombre="STATIC NEW")
        call("agregar", True, ruta="1-1", nueva="STATIC NEW", despues="UNIVERSIDADES")
        call("viaje", origen="STATIC NEW", destino="PORTAL ELDORADO")
        snapshot()
        for name in ("MODELIA", "UNIVERSIDADES", "PORTAL NORTE"):
            call("cerrar", True, nombre=name)
            call("estado", nombre=name)
            call("conteo", nombre=name)
            call("proximo_bus", estacion=name, ruta="1-1", hora="08:00")
            snapshot()
        for _ in range(4):
            call("deshacer", True)
            snapshot()
        for _ in range(4):
            call("rehacer", True)
            snapshot()
        call("reabrir", True, nombre="UNIVERSIDADES")
        call("rehacer", True)
        call("quitar", True, ruta="1-1", estacion="MODELIA")
        snapshot()
        call("deshacer", True)
        snapshot()
        call("eliminar_estacion", True, nombre="UNIVERSIDADES")
        call("eliminar_estacion", True, nombre="STATIC NEW")
        call("deshacer", True)
        call("rehacer", True)
        snapshot()
        self.compare_calls(calls)

    def test_queue_matches_python(self):
        self.compare_calls([
            ["fila", {"pasajeros": 11, "minutos": 10, "frecuencia": 3, "capacidad": 4}, True],
            ["fila", {"pasajeros": 0, "minutos": 10, "frecuencia": 3, "capacidad": 4}, True],
        ])


if __name__ == "__main__":
    unittest.main()
