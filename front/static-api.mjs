// GitHub Pages has no Python server. Keep this adapter separate from the Python motor.
const copy = value => JSON.parse(JSON.stringify(value));
const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const formatTime = minutes => String(Math.floor(minutes / 60)).padStart(2, '0') + ':' + String(minutes % 60).padStart(2, '0');

export async function loadStaticAPI() {
    const response = await fetch(new URL('./network.json', import.meta.url));
    if (!response.ok || !(response.headers.get('Content-Type') || '').includes('application/json')) {
        throw new Error('Faltan los datos de la red. Vuelve a publicar GitHub Pages con el workflow actualizado.');
    }
    return createStaticAPI(await response.json());
}

export function createStaticAPI(data) {
    const routes = new Map(data.routes.map(([route, stops]) => [route, [...stops]]));
    const routeNames = [...routes.keys()].sort(compare);
    const stations = new Map(data.stations.map(name => [name, {open: true, routes: new Set(), buses: 0}]));
    const schedules = new Map(Object.entries(data.schedules).map(([route, stops]) => [route, new Map(Object.entries(stops))]));
    const created = new Set(), undo = [], redo = [];
    const times = (route, station) => schedules.get(route)?.get(station) || [];
    const isOpen = name => stations.get(name)?.open === true;
    for (const [route, stops] of routes) {
        for (const name of stops) {
            const station = stations.get(name);
            station.routes.add(route);
            station.buses += times(route, name).length;
        }
    }
    const openNames = () => [...stations.keys()].filter(isOpen).sort(compare);
    const ranking = () => openNames().map(name => [name, stations.get(name).buses]).sort((a, b) => b[1] - a[1] || compare(a[0], b[0]));
    const departures = (route, station) => isOpen(station) ? [...new Set(times(route, station))].map(formatTime) : [];
    const record = change => { undo.push(change); redo.length = 0; };

    function addStop(route, name, after) {
        const stops = routes.get(route), station = stations.get(name);
        if (!stops || !station || stops.includes(name)) return false;
        const index = after == null ? -1 : stops.indexOf(after);
        if (after != null && index < 0) return false;
        stops.splice(index + 1, 0, name);
        station.routes.add(route);
        station.buses += times(route, name).length;
        return true;
    }

    function removeStop(route, name) {
        const stops = routes.get(route), index = stops ? stops.indexOf(name) : -1;
        if (index < 0) return false;
        stops.splice(index, 1);
        const station = stations.get(name);
        station.routes.delete(route);
        station.buses -= times(route, name).length;
        return true;
    }

    function setOpen(name, value) {
        const station = stations.get(name);
        if (!station || station.open === value) return false;
        station.open = value;
        return true;
    }

    function applyChange(change, reverse) {
        const [kind, a, b, previous] = change;
        if (kind === 'cerrar' || kind === 'reabrir') setOpen(a, (kind === 'reabrir') !== reverse);
        else if ((kind === 'agregar') !== reverse) addStop(a, b, previous);
        else removeStop(a, b);
    }

    function nextBus(station, route, hour) {
        if (!isOpen(station)) return null;
        const list = times(route, station);
        if (!list.length) return null;
        const parts = typeof hour === 'number' ? null : String(hour).split(':').map(Number);
        const minute = parts ? parts[0] * 60 + parts[1] : hour;
        if (!Number.isFinite(minute)) throw new Error('Escribe una hora válida.');
        let low = 0, high = list.length;
        while (low < high) {
            const middle = Math.floor((low + high) / 2);
            if (list[middle] < minute) low = middle + 1;
            else high = middle;
        }
        return low < list.length ? formatTime(list[low]) : null;
    }

    function trip(origin, destination) {
        if (!isOpen(origin) || !isOpen(destination)) return null;
        if (origin === destination) return {tipo: 'directo', tramos: [], paradas: 0, transbordo: null, transbordos: [], cruza_cerrada: false};
        const info = new Map(), visited = new Set();
        const key = (route, station) => JSON.stringify([route, station]);
        const better = (closed, stops, other) => !other || Number(closed) < Number(other.closed) || (closed === other.closed && stops < other.stops);
        let level = [];
        for (const route of stations.get(origin).routes) {
            const id = key(route, origin);
            info.set(id, {route, board: origin, closed: false, stops: 0, parent: null});
            visited.add(id);
            level.push(id);
        }
        while (level.length) {
            let finish = null;
            const next = [];
            for (const id of level) {
                const state = info.get(id), stops = routes.get(state.route);
                let closed = state.closed, count = state.stops;
                for (let i = stops.indexOf(state.board) + 1; i < stops.length; i++) {
                    const name = stops[i];
                    if (!isOpen(name)) { closed = true; continue; }
                    count++;
                    if (name === destination) {
                        if (better(closed, count, finish)) finish = {closed, stops: count, id};
                        break;
                    }
                    for (const route of stations.get(name).routes) {
                        if (route === state.route) continue;
                        const nextId = key(route, name);
                        if (visited.has(nextId)) continue;
                        const previous = info.get(nextId);
                        if (better(closed, count, previous)) {
                            if (!previous) next.push(nextId);
                            info.set(nextId, {route, board: name, closed, stops: count, parent: id});
                        }
                    }
                }
            }
            if (finish) {
                const chain = [];
                for (let id = finish.id; id !== null; id = info.get(id).parent) chain.push(info.get(id));
                chain.reverse();
                const transfers = chain.slice(1).map(state => state.board);
                return {
                    tipo: transfers.length ? 'transbordo' : 'directo',
                    tramos: chain.map((state, i) => [state.route, state.board, chain[i + 1]?.board || destination]),
                    paradas: finish.stops, transbordo: transfers[0] || null,
                    transbordos: transfers, cruza_cerrada: finish.closed,
                };
            }
            for (const id of next) visited.add(id);
            level = next;
        }
        return null;
    }

    function simulateQueue(q) {
        const count = Number(q.pasajeros), duration = Number(q.minutos);
        const frequency = Number(q.frecuencia), capacity = Number(q.capacidad);
        if (!Number.isInteger(count) || count < 0 || !Number.isFinite(duration) || duration < 0) throw new Error('Revisa la cantidad de pasajeros y los minutos.');
        if (count && (!Number.isFinite(frequency) || frequency <= 0 || !Number.isInteger(capacity) || capacity <= 0)) throw new Error('La frecuencia y la capacidad deben ser positivas.');
        const arrivals = Array.from({length: count}, () => Math.random() * duration).sort((a, b) => a - b);
        const first = [], series = [];
        let arrived = 0, boarded = 0, buses = 0, totalWait = 0, worstWait = 0, departure = 0;
        while (boarded < count) {
            departure = ++buses * frequency;
            while (arrived < count && arrivals[arrived] <= departure) arrived++;
            const passengers = Math.min(capacity, arrived - boarded);
            for (let i = 0; i < passengers; i++) {
                const wait = departure - arrivals[boarded++];
                totalWait += wait;
                worstWait = Math.max(worstWait, wait);
            }
            if (first.length < 12) first.push([departure, passengers]);
            if (series.length < 600) series.push([Math.round(departure * 100) / 100, passengers, arrived - boarded]);
        }
        return {buses, ultima_salida: departure, espera_media: count ? totalWait / count : 0, espera_max: worstWait, primeros: first, serie: series};
    }

    function dispatch(name, q, post) {
        if (post) {
            if (name === 'rendimiento' || name === 'rendimiento_uno') throw new Error('Las mediciones del motor de Python requieren ejecutar python front/app.py en tu equipo.');
            if (name === 'fila') return simulateQueue(q);
            if (name === 'crear') {
                if (!q.nombre || stations.has(q.nombre)) return false;
                stations.set(q.nombre, {open: true, routes: new Set(), buses: 0});
                created.add(q.nombre);
                return true;
            }
            if (name === 'eliminar_estacion') {
                if (!created.has(q.nombre)) return false;
                for (const route of [...stations.get(q.nombre).routes]) removeStop(route, q.nombre);
                stations.delete(q.nombre);
                created.delete(q.nombre);
                undo.length = redo.length = 0;
                return true;
            }
            if (name === 'agregar') {
                const after = q.despues || null;
                if (!addStop(q.ruta, q.nueva, after)) return false;
                record([name, q.ruta, q.nueva, after]);
                return true;
            }
            if (name === 'quitar') {
                const stops = routes.get(q.ruta), index = stops ? stops.indexOf(q.estacion) : -1;
                if (index < 0) return false;
                const previous = index ? stops[index - 1] : null;
                removeStop(q.ruta, q.estacion);
                record([name, q.ruta, q.estacion, previous]);
                return true;
            }
            if (name === 'cerrar' || name === 'reabrir') {
                if (!setOpen(q.nombre, name === 'reabrir')) return false;
                record([name, q.nombre]);
                return true;
            }
            if (name === 'deshacer' || name === 'rehacer') {
                const reverse = name === 'deshacer', source = reverse ? undo : redo, target = reverse ? redo : undo;
                const change = source.pop();
                if (!change) return false;
                applyChange(change, reverse);
                target.push(change);
                return true;
            }
        } else {
            switch (name) {
                case 'rutas': return routeNames;
                case 'wrapped': return data.wrapped;
                case 'estado': return stations.has(q.nombre) ? isOpen(q.nombre) ? 'abierta' : 'cerrada' : 'no existe';
                case 'autocompletar': return openNames().filter(station => station.startsWith(q.prefijo || '')).slice(0, Math.max(0, Number(q.k ?? 8)));
                case 'rango': return openNames().filter(station => station >= (q.desde || '') && station <= (q.hasta || ''));
                case 'recorrido': return q.reves === '1' ? [...(routes.get(q.ruta) || [])].reverse() : routes.get(q.ruta) || [];
                case 'proximo_bus': return nextBus(q.estacion, q.ruta, q.hora);
                case 'viaje': return trip(q.origen, q.destino);
                case 'ranking': return ranking().slice(0, Math.max(0, Number(q.k ?? 10)));
                case 'conteo': {
                    const station = stations.get(q.nombre);
                    if (!station) return null;
                    const list = ranking();
                    return {nombre: q.nombre, buses: station.buses, abierta: station.open, puesto: station.open ? list.findIndex(([name]) => name === q.nombre) + 1 : null, abiertas: list.length};
                }
                case 'horarios': return departures(q.ruta, q.estacion);
                case 'buses': return routeNames.filter(route => routes.get(route).length).map(route => {
                    const stops = routes.get(route);
                    let hours = [];
                    for (const station of stops) {
                        hours = departures(route, station);
                        if (hours.length) break;
                    }
                    return {ruta: route, origen: stops[0], destino: stops[stops.length - 1], paradas: stops.length, primero: hours[0] || null, ultimo: hours[hours.length - 1] || null, salidas: hours.length};
                });
            }
        }
        throw new Error('La operación solicitada no existe.');
    }

    // Match the API's JSON boundary so callers cannot mutate internal route arrays.
    return (name, params = {}, post = false) => copy(dispatch(name, params, post));
}
