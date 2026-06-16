import pygame
from collections import defaultdict
import json
import os

cell_map = {
    0:  ["Empty",     (20, 18, 18)],
    1:  ["Block",     (177, 175, 169)],
    2:  ["Engine",    (239, 159, 39)],
    3:  ["Button",    (29, 158, 117)],
    4:  ["Sensor",    (55, 138, 221)],
    5:  ["Switch",    (93, 202, 165)],
    6:  ["AND",       (127, 119, 221)],
    7:  ["OR",        (175, 169, 236)],
    8:  ["NOT",       (206, 203, 246)],
    9:  ["XOR",       (83, 74, 183)],
    10: ["Glue",      (216, 90, 48)],
    11: ["RotateCW",  (255, 200, 100)],
    12: ["RotateCCW", (100, 200, 255)],
    13: ["Destroyer", (220, 50, 50)],
    14: ["Generator", (50, 220, 120)],
}

GLUE_ATTACHABLE = {"Block", "Engine", "Button", "Switch", "Sensor"}

cell_scripts = {}

SCRIPTABLE      = {"Engine", "Switch", "Button", "AND", "OR", "NOT", "XOR", "Sensor", "Destroyer", "Generator"}
DIRS            = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
ROT_CW          = {"up": "right", "right": "down", "down": "left",  "left": "up"}
ROT_CCW         = {"up": "left",  "left": "down",  "down": "right", "right": "up"}
TYPE_NAME_TO_ID = {v[0]: k for k, v in cell_map.items()}


def generate_label(x, y):
    return f"{x}_{y}"


def parse_script(script_text):
    attrs = {}
    for line in script_text.strip().split("\n"):
        parts = line.strip().split(" ", 1)
        if len(parts) == 2:
            attrs[parts[0].lower()] = parts[1].strip()
    return attrs


def split_sigs(raw):
    return [s.strip() for s in raw.split(",") if s.strip()]


class Grid:
    def __init__(self, width=800, height=600):
        self.cell_size   = 20
        self.width       = width
        self.height      = height
        self.screen      = pygame.display.set_mode((self.width, self.height))
        self.grid_width  = self.width  // self.cell_size
        self.grid_height = self.height // self.cell_size
        self.grid        = {}
        self.surface     = pygame.Surface((self.width, self.height))

        for y in range(self.grid_height):
            for x in range(self.grid_width):
                self.grid[(x, y)] = {
                    "type":  cell_map[0][0],
                    "color": cell_map[0][1],
                    "label": generate_label(x, y),
                }
                cell_scripts[(x, y)] = ""

        self._reset_sim_state()

    def save(self, name):
        data = {
            "grid": {},
            "scripts": {},
        }
        for pos, cell in self.grid.items():
            key = f"{pos[0]},{pos[1]}"
            data["grid"][key] = {
                "type":  cell["type"],
                "color": cell["color"],
            }
        for pos, script in cell_scripts.items():
            if script.strip():
                key = f"{pos[0]},{pos[1]}"
                data["scripts"][key] = script
        path = f"{name}.json"
        with open(path, "w") as f:
            json.dump(data, f)

    def load(self, name):
        path = f"{name}.json"
        if not os.path.exists(path):
            return False
        with open(path, "r") as f:
            data = json.load(f)
        for pos in self.grid:
            self.grid[pos]["type"]  = cell_map[0][0]
            self.grid[pos]["color"] = cell_map[0][1]
            cell_scripts[pos]       = ""
        for key, cell in data["grid"].items():
            x, y = map(int, key.split(","))
            if (x, y) in self.grid:
                self.grid[(x, y)]["type"]  = cell["type"]
                self.grid[(x, y)]["color"] = tuple(cell["color"])
        for key, script in data["scripts"].items():
            x, y = map(int, key.split(","))
            if (x, y) in self.grid:
                cell_scripts[(x, y)] = script
        self._reset_sim_state()
        self.draw_grid()
        return True

    def _reset_sim_state(self):
        self.signal_graph   = defaultdict(list)
        self.signal_state   = {}
        self.engine_data    = {}
        self.switch_data    = {}
        self.button_data    = {}
        self.gate_data      = {}
        self.sensor_data    = {}
        self.destroyer_data = {}
        self.generator_data = {}

    def draw_grid(self):
        self.surface.fill((0, 0, 0))
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                pygame.draw.rect(
                    self.surface,
                    self.grid[(x, y)]["color"],
                    (x * self.cell_size, y * self.cell_size, self.cell_size, self.cell_size),
                )

    def draw(self, screen):
        screen.blit(self.surface, (0, 0))

    def set_cell(self, x, y, cell_type):
        if (x, y) in self.grid:
            old_type = self.grid[(x, y)]["type"]
            new_type = cell_map[cell_type][0]

            if old_type in SCRIPTABLE:
                self.engine_data.pop((x, y), None)
                self.switch_data.pop((x, y), None)
                self.button_data.pop((x, y), None)
                self.gate_data.pop((x, y), None)
                self.sensor_data.pop((x, y), None)
                self.destroyer_data.pop((x, y), None)
                self.generator_data.pop((x, y), None)
                for sig, entries in self.signal_graph.items():
                    self.signal_graph[sig] = [e for e in entries if e[1] != (x, y)]

            if new_type not in SCRIPTABLE:
                cell_scripts.pop((x, y), None)
            else:
                cell_scripts[(x, y)] = ""

            self.grid[(x, y)]["type"]  = new_type
            self.grid[(x, y)]["color"] = cell_map[cell_type][1]
            self.draw_grid()

    def get_cell(self, x, y):
        c = self.grid.get((x, y))
        if c:
            return c["type"], c["label"]
        return "Empty", ""

    def set_script(self, x, y, script):
        cell_scripts[(x, y)] = script

    def get_script(self, x, y):
        return cell_scripts.get((x, y), "")

    def in_bounds(self, x, y):
        return 0 <= x < self.grid_width and 0 <= y < self.grid_height

    def cell_type(self, x, y):
        return self.grid.get((x, y), {}).get("type", "Empty")

    def is_empty(self, x, y):
        return self.cell_type(x, y) == "Empty"

    def neighbors4(self, x, y):
        for dx, dy in DIRS.values():
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                yield nx, ny

    def _build_clusters(self):
        glue_cells = set()
        non_glue   = set()

        for y in range(self.grid_height):
            for x in range(self.grid_width):
                t = self.cell_type(x, y)
                if t == "Empty":
                    continue
                if t == "Glue":
                    glue_cells.add((x, y))
                else:
                    non_glue.add((x, y))

        parent = {}

        def find(p):
            while parent.get(p, p) != p:
                parent[p] = parent.get(parent[p], parent[p])
                p = parent[p]
            return p

        def union(a, b):
            a, b = find(a), find(b)
            if a != b:
                parent[b] = a

        for gp in glue_cells:
            parent.setdefault(gp, gp)
            for nx, ny in self.neighbors4(gp[0], gp[1]):
                if (nx, ny) in glue_cells:
                    parent.setdefault((nx, ny), (nx, ny))
                    union(gp, (nx, ny))

        for np_ in non_glue:
            if self.cell_type(np_[0], np_[1]) not in GLUE_ATTACHABLE:
                continue
            touching = set()
            for nx, ny in self.neighbors4(np_[0], np_[1]):
                if (nx, ny) in glue_cells:
                    touching.add(find((nx, ny)))
            roots = list(touching)
            for i in range(1, len(roots)):
                union(roots[0], roots[i])

        glue_groups = defaultdict(set)
        for gp in glue_cells:
            glue_groups[find(gp)].add(gp)

        clusters = []
        absorbed = set()

        for root, group in glue_groups.items():
            cluster = set(group)
            for gp in group:
                for nx, ny in self.neighbors4(gp[0], gp[1]):
                    if (nx, ny) in non_glue and self.cell_type(nx, ny) in GLUE_ATTACHABLE:
                        cluster.add((nx, ny))
                        absorbed.add((nx, ny))
            clusters.append(cluster)

        for pos in non_glue:
            if pos not in absorbed:
                clusters.append({pos})

        return clusters

    def compile_scripts(self):
        self._reset_sim_state()

        for pos, script in cell_scripts.items():
            if not script.strip():
                continue
            x, y  = pos
            type_ = self.cell_type(x, y)
            attrs = parse_script(script)

            if type_ == "Engine":
                dir_name = attrs.get("dir", "right")
                inputs   = split_sigs(attrs.get("input", ""))
                speed    = max(1, min(int(attrs.get("speed", "1")), 4))
                self.engine_data[pos] = {
                    "dir_name": dir_name,
                    "vec":      DIRS.get(dir_name, (1, 0)),
                    "inputs":   inputs,
                    "speed":    speed,
                }
                for sig in inputs:
                    self.signal_graph[sig].append(("engine", pos))

            elif type_ == "Button":
                outputs = split_sigs(attrs.get("output", ""))
                self.button_data[pos] = {"outputs": outputs}

            elif type_ == "Switch":
                inputs  = split_sigs(attrs.get("input", ""))
                outputs = split_sigs(attrs.get("output", ""))
                self.switch_data[pos] = {
                    "inputs":  inputs,
                    "outputs": outputs,
                    "state":   0,
                    "last_in": 0,
                }
                for sig in inputs:
                    self.signal_graph[sig].append(("switch", pos))

            elif type_ == "Sensor":
                outputs    = split_sigs(attrs.get("output", ""))
                block_attr = attrs.get("block", "").strip()
                self.sensor_data[pos] = {
                    "outputs":    outputs,
                    "watch_type": block_attr if block_attr else None,
                }

            elif type_ in ("AND", "OR", "XOR"):
                inputs  = split_sigs(attrs.get("input", ""))
                outputs = split_sigs(attrs.get("output", ""))
                self.gate_data[pos] = {
                    "type":     type_,
                    "inputs":   inputs,
                    "outputs":  outputs,
                    "received": set(),
                }
                for sig in inputs:
                    self.signal_graph[sig].append(("gate", pos))

            elif type_ == "NOT":
                inputs  = split_sigs(attrs.get("input", ""))
                outputs = split_sigs(attrs.get("output", ""))
                self.gate_data[pos] = {
                    "type":     "NOT",
                    "inputs":   inputs,
                    "outputs":  outputs,
                    "received": set(),
                }
                for sig in inputs:
                    self.signal_graph[sig].append(("gate", pos))

            elif type_ == "Destroyer":
                inputs = split_sigs(attrs.get("input", ""))
                self.destroyer_data[pos] = {"inputs": inputs}
                for sig in inputs:
                    self.signal_graph[sig].append(("destroyer", pos))

            elif type_ == "Generator":
                inputs     = split_sigs(attrs.get("input", ""))
                block_name = attrs.get("block", "Block")
                dir_name   = attrs.get("dir", "right")
                blockscript = attrs.get("blockscript", "").replace("|", "\n")
                self.generator_data[pos] = {
                    "inputs":      inputs,
                    "block":       block_name,
                    "dir_name":    dir_name,
                    "blockscript": blockscript,
                }
                for sig in inputs:
                    self.signal_graph[sig].append(("generator", pos))

    def _do_destroy(self, pos):
        x, y = pos
        for nx, ny in self.neighbors4(x, y):
            t = self.cell_type(nx, ny)
            if t != "Empty" and t != "Destroyer":
                if t in SCRIPTABLE:
                    self.engine_data.pop((nx, ny), None)
                    self.switch_data.pop((nx, ny), None)
                    self.button_data.pop((nx, ny), None)
                    self.gate_data.pop((nx, ny), None)
                    self.sensor_data.pop((nx, ny), None)
                    self.destroyer_data.pop((nx, ny), None)
                    self.generator_data.pop((nx, ny), None)
                    for sig in list(self.signal_graph.keys()):
                        self.signal_graph[sig] = [e for e in self.signal_graph[sig] if e[1] != (nx, ny)]
                self.grid[(nx, ny)]["type"]  = cell_map[0][0]
                self.grid[(nx, ny)]["color"] = cell_map[0][1]
                cell_scripts[(nx, ny)]       = ""
        self.draw_grid()

    def _do_generate(self, pos):
        gd = self.generator_data.get(pos)
        if gd is None:
            return
        x, y   = pos
        dx, dy = DIRS.get(gd["dir_name"], (1, 0))
        tx, ty = x + dx, y + dy
        if self.in_bounds(tx, ty) and self.is_empty(tx, ty):
            block_id = TYPE_NAME_TO_ID.get(gd["block"], 1)
            new_type = cell_map[block_id][0]

            self.engine_data.pop((tx, ty), None)
            self.switch_data.pop((tx, ty), None)
            self.button_data.pop((tx, ty), None)
            self.gate_data.pop((tx, ty), None)
            self.sensor_data.pop((tx, ty), None)
            self.destroyer_data.pop((tx, ty), None)
            self.generator_data.pop((tx, ty), None)
            for sig in list(self.signal_graph.keys()):
                self.signal_graph[sig] = [e for e in self.signal_graph[sig] if e[1] != (tx, ty)]

            self.grid[(tx, ty)]["type"]  = new_type
            self.grid[(tx, ty)]["color"] = cell_map[block_id][1]

            if gd["blockscript"] and new_type in SCRIPTABLE:
                script = gd["blockscript"]
                cell_scripts[(tx, ty)] = script
                attrs = parse_script(script)
                if new_type == "Engine":
                    dir_name = attrs.get("dir", "right")
                    inputs   = split_sigs(attrs.get("input", ""))
                    speed    = max(1, min(int(attrs.get("speed", "1")), 4))
                    self.engine_data[(tx, ty)] = {
                        "dir_name": dir_name,
                        "vec":      DIRS.get(dir_name, (1, 0)),
                        "inputs":   inputs,
                        "speed":    speed,
                    }
                    for sig in inputs:
                        self.signal_graph[sig].append(("engine", (tx, ty)))
                elif new_type == "Switch":
                    inputs  = split_sigs(attrs.get("input", ""))
                    outputs = split_sigs(attrs.get("output", ""))
                    self.switch_data[(tx, ty)] = {
                        "inputs":  inputs,
                        "outputs": outputs,
                        "state":   0,
                        "last_in": 0,
                    }
                    for sig in inputs:
                        self.signal_graph[sig].append(("switch", (tx, ty)))
                elif new_type == "Sensor":
                    outputs    = split_sigs(attrs.get("output", ""))
                    block_attr = attrs.get("block", "").strip()
                    self.sensor_data[(tx, ty)] = {
                        "outputs":    outputs,
                        "watch_type": block_attr if block_attr else None,
                    }
                elif new_type in ("AND", "OR", "XOR", "NOT"):
                    inputs  = split_sigs(attrs.get("input", ""))
                    outputs = split_sigs(attrs.get("output", ""))
                    self.gate_data[(tx, ty)] = {
                        "type":     new_type,
                        "inputs":   inputs,
                        "outputs":  outputs,
                        "received": set(),
                    }
                    for sig in inputs:
                        self.signal_graph[sig].append(("gate", (tx, ty)))
                elif new_type == "Destroyer":
                    inputs = split_sigs(attrs.get("input", ""))
                    self.destroyer_data[(tx, ty)] = {"inputs": inputs}
                    for sig in inputs:
                        self.signal_graph[sig].append(("destroyer", (tx, ty)))
            else:
                cell_scripts[(tx, ty)] = ""

            self.draw_grid()

    def emit(self, sig, value, visited):
        if sig in visited:
            return
        visited.add(sig)
        self.signal_state[sig] = value

        for entry in self.signal_graph.get(sig, []):
            kind = entry[0]
            pos  = entry[1]

            if kind == "switch":
                sw = self.switch_data.get(pos)
                if sw is None:
                    continue
                prev = sw["last_in"]
                sw["last_in"] = value
                if value == 1 and prev == 0:
                    sw["state"] = 1 if sw["state"] == 0 else 0
                for out in sw["outputs"]:
                    self.emit(out, sw["state"], visited)

            elif kind == "gate":
                g = self.gate_data.get(pos)
                if g is None:
                    continue
                if value == 1:
                    g["received"].add(sig)
                else:
                    g["received"].discard(sig)
                result = self._eval_gate(g)
                for out in g["outputs"]:
                    self.emit(out, result, visited)

            elif kind == "destroyer":
                if value == 1:
                    self._do_destroy(pos)

            elif kind == "generator":
                if value == 1:
                    self._do_generate(pos)

    def _eval_gate(self, g):
        t        = g["type"]
        inputs   = g["inputs"]
        received = g["received"]
        if t == "AND":
            return 1 if all(i in received for i in inputs) else 0
        elif t == "OR":
            return 1 if any(i in received for i in inputs) else 0
        elif t == "XOR":
            return 1 if sum(1 for i in inputs if i in received) % 2 == 1 else 0
        elif t == "NOT":
            return 0 if any(i in received for i in inputs) else 1
        return 0

    def _tick_sensors(self, visited):
        sensor_signals = defaultdict(int)
        for pos, sd in self.sensor_data.items():
            x, y      = pos
            watch     = sd["watch_type"]
            triggered = False
            for nx, ny in self.neighbors4(x, y):
                t = self.cell_type(nx, ny)
                if t == "Empty":
                    continue
                if watch is None or t == watch:
                    triggered = True
                    break
            value = 1 if triggered else 0
            for out in sd["outputs"]:
                sensor_signals[out] = max(sensor_signals[out], value)
        for sig, value in sensor_signals.items():
            self.emit(sig, value, visited)

    def _tick_buttons(self, clicked, visited):
        button_signals = defaultdict(int)
        for pos in clicked:
            bd = self.button_data.get(pos)
            if bd is None:
                continue
            for out in bd["outputs"]:
                button_signals[out] = 1
        for sig, value in button_signals.items():
            self.emit(sig, value, visited)

    def _tick_switches_continuous(self, visited):
        switch_signals = defaultdict(int)
        for pos, sw in self.switch_data.items():
            for out in sw["outputs"]:
                switch_signals[out] = max(switch_signals[out], sw["state"])
        for sig, value in switch_signals.items():
            self.emit(sig, value, visited)

    def tick(self, clicked_buttons=None):
        for g in self.gate_data.values():
            g["received"] = set()
        self.signal_state = {}

        self._tick_sensors(set())
        self._tick_buttons(clicked_buttons or [], set())
        self._tick_switches_continuous(set())
        self._tick_engines()

    def _tick_engines(self):
        clusters   = self._build_clusters()
        cell_to_ci = {}
        for i, cl in enumerate(clusters):
            for pos in cl:
                cell_to_ci[pos] = i

        cluster_vecs = defaultdict(lambda: [0, 0])

        for pos, ed in self.engine_data.items():
            active = any(self.signal_state.get(sig, 0) == 1 for sig in ed["inputs"])
            if not active:
                continue
            ci = cell_to_ci.get(pos)
            if ci is None:
                continue
            dx, dy = ed["vec"]
            speed  = ed["speed"]
            cluster_vecs[ci][0] += dx * speed
            cluster_vecs[ci][1] += dy * speed

            ex, ey = pos
            nx, ny = ex + dx, ey + dy
            if self.in_bounds(nx, ny):
                t = self.cell_type(nx, ny)
                if t == "RotateCW":
                    new_dir        = ROT_CW[ed["dir_name"]]
                    ed["dir_name"] = new_dir
                    ed["vec"]      = DIRS[new_dir]
                elif t == "RotateCCW":
                    new_dir        = ROT_CCW[ed["dir_name"]]
                    ed["dir_name"] = new_dir
                    ed["vec"]      = DIRS[new_dir]

        for ci, (vx, vy) in cluster_vecs.items():
            if vx == 0 and vy == 0:
                continue
            cluster = list(clusters[ci])
            sdx     = 1 if vx > 0 else (-1 if vx < 0 else 0)
            sdy     = 1 if vy > 0 else (-1 if vy < 0 else 0)
            steps   = max(abs(vx), abs(vy))
            for _ in range(steps):
                if not self._try_move_cluster(cluster, sdx, sdy):
                    break

    def _try_move_cluster(self, cluster, dx, dy):
        cluster_set = set(cluster)
        for pos in cluster:
            x, y   = pos
            nx, ny = x + dx, y + dy
            if not self.in_bounds(nx, ny):
                return False
            if (nx, ny) not in cluster_set and not self.is_empty(nx, ny):
                return False

        data_maps = [
            self.engine_data,
            self.switch_data,
            self.button_data,
            self.gate_data,
            self.sensor_data,
            self.destroyer_data,
            self.generator_data,
        ]

        old_grid    = {pos: dict(self.grid[pos]) for pos in self.grid}
        old_scripts = dict(cell_scripts)
        old_data    = [dict(dm) for dm in data_maps]

        new_grid    = {pos: {"type": cell_map[0][0], "color": cell_map[0][1], "label": self.grid[pos]["label"]} for pos in self.grid}
        new_scripts = {pos: "" for pos in cell_scripts}
        new_data    = [{} for _ in data_maps]

        for pos in self.grid:
            if pos not in cluster_set:
                new_grid[pos]    = dict(old_grid[pos])
                new_scripts[pos] = old_scripts.get(pos, "")
                for i, dm in enumerate(old_data):
                    if pos in dm:
                        new_data[i][pos] = dm[pos]

        for pos in cluster_set:
            x, y   = pos
            nx, ny = x + dx, y + dy
            new_grid[(nx, ny)]          = dict(old_grid[pos])
            new_grid[(nx, ny)]["label"] = generate_label(nx, ny)
            new_scripts[(nx, ny)]       = old_scripts.get(pos, "")
            for i, dm in enumerate(old_data):
                if pos in dm:
                    new_data[i][(nx, ny)] = dm[pos]

        for pos in self.grid:
            self.grid[pos] = new_grid[pos]
        for pos in cell_scripts:
            cell_scripts[pos] = new_scripts[pos]
        for i, dm in enumerate(data_maps):
            dm.clear()
            dm.update(new_data[i])

        cluster[:] = [(p[0] + dx, p[1] + dy) for p in cluster]
        self.draw_grid()
        return True