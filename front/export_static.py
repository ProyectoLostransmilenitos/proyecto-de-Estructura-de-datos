"""Export the existing network for the dependency-free GitHub Pages adapter."""
import argparse
import json
from pathlib import Path

from app import DATOS, WRAPPED, red
from motor.carga import leer_horarios


def export_network(output):
    schedules = {}
    for (route, station), times in leer_horarios(DATOS).items():
        schedules.setdefault(route, {})[station] = times
    data = {
        "stations": WRAPPED["estaciones"],
        "routes": [[route, red.recorrido(route)] for route in WRAPPED["rutas"]],
        "schedules": schedules,
        "wrapped": WRAPPED,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Path to the generated network.json")
    export_network(parser.parse_args().output)
