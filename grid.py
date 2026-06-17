import pygame
import json
import os
import re
from collections import defaultdict

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
    15: ["LEDPanel",  (30, 30, 30)],
}

cell_scripts = {}

SCRIPTABLE      = {"Engine", "Switch", "Button", "AND", "OR", "NOT", "XOR", "Sensor", "Destroyer", "Generator", "LEDPanel"}
GLUE_ATTACHABLE = {"Block", "Engine", "Button", "Switch", "Sensor", "LEDPanel"}
DIRS            = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
ROT_CW          = {"up": "right", "right": "down", "down": "left",  "left": "up"}
ROT_CCW         = {"up": "left",  "left": "down",  "down": "right", "right": "up"}
TYPE_NAME_TO_ID = {v[0]: k for k, v in cell_map.items()}


def generate_label(x, y):
    return f"{x}_{y}"


def parse_script(script_text):
    attrs = {}
    for line in script_text.strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            attrs[key.strip().lower()] = val.strip()
        else:
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                attrs[parts[0].strip().lower()] = parts[1].strip()
    return attrs


def split_sigs(raw):
    return [s.strip() for s in raw.split(",") if s.strip()]


def parse_dim(raw):
    parts = raw.lower().replace("x", " ").split()
    if len(parts) == 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return 1, 1


def parse_bulbs(raw, total, cols=None):
    vals = re.findall(r'[01]', raw)
    if len(vals) < total:
        vals += ["0"] * (total - len(vals))
    return [int(v) for v in vals[:total]]


def serialize_bulbs(bulbs, cols):
    rows = []
    for i in range(0, len(bulbs), cols):
        row = bulbs[i:i + cols]
        rows.append("[" + " ".join(str(b) for b in row) + "]")
    return "".join(rows)


def default_script(type_name, cols=1, rows=1):
    if type_name == "Engine":
        return "input:\ndir:\nspeed:"
    elif type_name == "Button":
        return "output:"
    elif type_name == "Switch":
        return "input:\noutput:"
    elif type_name == "Sensor":
        return "output:\nblock:"
    elif type_name in ("AND", "OR", "XOR", "NOT"):
        return "input:\noutput:"
    elif type_name == "Destroyer":
        return "input:"
    elif type_name == "Generator":
        return "input:\ndir:\nblock:\nblockscript:"
    elif type_name == "LEDPanel":
        total = cols * rows
        return f"dim {cols}x{rows}\nbulbs {serialize_bulbs([0] * total, cols)}\ninput:"
    return ""


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
        self.led_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        for y in range(self.grid_height):
            for x in range(self.grid_width):
                self.grid[(x, y)] = {
                    "type":  cell_map[0][0],
                    "color": cell_map[0][1],
                    "label": generate_label(x, y),
                }
                cell_scripts[(x, y)] = ""

        self._reset_sim_state()

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
        self.led_data       = {}

    def draw_grid(self):
        self.surface.fill((0, 0, 0))
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                pygame.draw.rect(
                    self.surface,
                    self.grid[(x, y)]["color"],
                    (x * self.cell_size, y * self.cell_size, self.cell_size, self.cell_size),
                )

    def draw_leds(self, sim_running):
        self.led_surface.fill((0, 0, 0, 0))
        for origin, ld in self.led_data.items():
            ox, oy     = origin
            cols, rows = ld["dim"]
            active     = sim_running and (
                self.signal_state.get(ld["inputs"][0], 0) == 1 if ld["inputs"] else False
            )
            bulbs = ld["bulbs"]
            for row in range(rows):
                for col in range(cols):
                    idx   = row * cols + col
                    bval  = bulbs[idx] if idx < len(bulbs) else 0
                    px    = (ox + col) * self.cell_size
                    py    = (oy + row) * self.cell_size
                    color = (255, 255, 255, 255) if (active and bval == 1) else (60, 60, 60, 180)
                    cx_   = px + self.cell_size // 2
                    cy_   = py + self.cell_size // 2
                    r     = max(2, self.cell_size // 2 - 3)
                    pygame.draw.circle(self.led_surface, color, (cx_, cy_), r)

    def draw(self, screen, sim_running=False):
        screen.blit(self.surface, (0, 0))
        self.draw_leds(sim_running)
        screen.blit(self.led_surface, (0, 0))

    def place_led_panel(self, ox, oy, cols, rows):
        for row in range(rows):
            for col in range(cols):
                tx, ty = ox + col, oy + row
                if not self.in_bounds(tx, ty):
                    continue
                self.grid[(tx, ty)]["type"]  = cell_map[15][0]
                self.grid[(tx, ty)]["color"] = cell_map[15][1]
        total  = cols * rows
        script = f"dim {cols}x{rows}\nbulbs {serialize_bulbs([0] * total, cols)}\ninput:"
        cell_scripts[(ox, oy)] = script
        self.draw_grid()
        return script

    def remove_led_panel(self, origin):
        ox, oy = origin
        ld     = self.led_data.get(origin)
        if ld is None:
            script     = cell_scripts.get(origin, "")
            attrs      = parse_script(script)
            cols, rows = parse_dim(attrs.get("dim", "1x1"))
        else:
            cols, rows = ld["dim"]
        for row in range(rows):
            for col in range(cols):
                tx, ty = ox + col, oy + row
                if self.in_bounds(tx, ty):
                    self.grid[(tx, ty)]["type"]  = cell_map[0][0]
                    self.grid[(tx, ty)]["color"] = cell_map[0][1]
                    cell_scripts[(tx, ty)]       = ""
        self.led_data.pop(origin, None)
        for sig in list(self.signal_graph.keys()):
            self.signal_graph[sig] = [e for e in self.signal_graph[sig] if e[1] != origin]
        self.draw_grid()

    def find_led_origin(self, x, y):
        if self.cell_type(x, y) != "LEDPanel":
            return None
        for origin, ld in self.led_data.items():
            ox, oy     = origin
            cols, rows = ld["dim"]
            if ox <= x < ox + cols and oy <= y < oy + rows:
                return origin
        for pos, script in cell_scripts.items():
            if self.cell_type(pos[0], pos[1]) != "LEDPanel":
                continue
            attrs      = parse_script(script)
            dim_raw    = attrs.get("dim", "")
            if not dim_raw:
                continue
            cols, rows = parse_dim(dim_raw)
            ox, oy     = pos
            if ox <= x < ox + cols and oy <= y < oy + rows:
                return pos
        return None

    def update_led_script(self, origin, new_script):
        ox, oy             = origin
        attrs              = parse_script(new_script)
        old_ld             = self.led_data.get(origin)
        old_cols, old_rows = old_ld["dim"] if old_ld else (1, 1)
        old_bulbs          = old_ld["bulbs"] if old_ld else []

        new_cols, new_rows = parse_dim(attrs.get("dim", f"{old_cols}x{old_rows}"))
        new_cols = max(1, min(new_cols, 16))
        new_rows = max(1, min(new_rows, 16))
        total    = new_cols * new_rows

        if attrs.get("bulbs", ""):
            new_bulbs = parse_bulbs(attrs["bulbs"], total, new_cols)
        else:
            new_bulbs = (old_bulbs + [0] * total)[:total]

        if new_cols != old_cols or new_rows != old_rows:
            for row in range(max(old_rows, new_rows)):
                for col in range(max(old_cols, new_cols)):
                    tx, ty = ox + col, oy + row
                    if not self.in_bounds(tx, ty):
                        continue
                    in_old = col < old_cols and row < old_rows
                    in_new = col < new_cols and row < new_rows
                    if in_new:
                        self.grid[(tx, ty)]["type"]  = cell_map[15][0]
                        self.grid[(tx, ty)]["color"] = cell_map[15][1]
                    elif in_old and not in_new:
                        self.grid[(tx, ty)]["type"]  = cell_map[0][0]
                        self.grid[(tx, ty)]["color"] = cell_map[0][1]
                        cell_scripts[(tx, ty)]       = ""

        inp_val        = attrs.get("input", "")
        updated_script = (
            f"dim {new_cols}x{new_rows}\n"
            f"bulbs {serialize_bulbs(new_bulbs, new_cols)}\n"
            f"input: {inp_val}"
        )
        cell_scripts[(ox, oy)] = updated_script

        inputs = split_sigs(inp_val)
        for sig in list(self.signal_graph.keys()):
            self.signal_graph[sig] = [e for e in self.signal_graph[sig] if e[1] != origin]

        self.led_data[origin] = {
            "dim":    (new_cols, new_rows),
            "bulbs":  new_bulbs,
            "inputs": inputs,
        }
        for sig in inputs:
            self.signal_graph[sig].append(("led", origin))

        self.draw_grid()
        return updated_script

    def set_cell(self, x, y, cell_type):
        if (x, y) in self.grid:
            old_type = self.grid[(x, y)]["type"]
            new_type = cell_map[cell_type][0]

            if old_type == "LEDPanel":
                origin = self.find_led_origin(x, y)
                if origin:
                    self.remove_led_panel(origin)
                return

            if old_type in SCRIPTABLE:
                self._remove_from_sim((x, y))

            if new_type in SCRIPTABLE:
                cell_scripts[(x, y)] = default_script(new_type)
            else:
                cell_scripts.pop((x, y), None)

            self.grid[(x, y)]["type"]  = new_type
            self.grid[(x, y)]["color"] = cell_map[cell_type][1]
            self.draw_grid()

    def _remove_from_sim(self, pos):
        self.engine_data.pop(pos, None)
        self.switch_data.pop(pos, None)
        self.button_data.pop(pos, None)
        self.gate_data.pop(pos, None)
        self.sensor_data.pop(pos, None)
        self.destroyer_data.pop(pos, None)
        self.generator_data.pop(pos, None)
        self.led_data.pop(pos, None)
        for sig in list(self.signal_graph.keys()):
            self.signal_graph[sig] = [e for e in self.signal_graph[sig] if e[1] != pos]

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
            if type_ not in SCRIPTABLE:
                continue
            self._register_from_script(pos, type_, script)

    def _register_from_script(self, pos, type_, script):
        attrs = parse_script(script)

        if type_ == "Engine":
            dir_name = attrs.get("dir", "right")
            inputs   = split_sigs(attrs.get("input", ""))
            spd_raw  = attrs.get("speed", "1")
            speed    = max(1, min(int(spd_raw) if spd_raw.isdigit() else 1, 4))
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
            inputs      = split_sigs(attrs.get("input", ""))
            block_name  = attrs.get("block", "Block")
            dir_name    = attrs.get("dir", "right")
            blockscript = attrs.get("blockscript", "").replace("|", "\n")
            self.generator_data[pos] = {
                "inputs":      inputs,
                "block":       block_name,
                "dir_name":    dir_name,
                "blockscript": blockscript,
            }
            for sig in inputs:
                self.signal_graph[sig].append(("generator", pos))

        elif type_ == "LEDPanel":
            cols, rows = parse_dim(attrs.get("dim", "1x1"))
            cols       = max(1, min(cols, 16))
            rows       = max(1, min(rows, 16))
            total      = cols * rows
            bulbs      = parse_bulbs(attrs.get("bulbs", ""), total, cols)
            inputs     = split_sigs(attrs.get("input", ""))
            self.led_data[pos] = {
                "dim":    (cols, rows),
                "bulbs":  bulbs,
                "inputs": inputs,
            }
            for sig in inputs:
                self.signal_graph[sig].append(("led", pos))

    def register_cell(self, x, y, type_name, script):
        pos = (x, y)
        self._remove_from_sim(pos)
        if type_name in SCRIPTABLE:
            self._register_from_script(pos, type_name, script)

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
                prev          = sw["last_in"]
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

            elif kind == "led":
                pass

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

    def _do_destroy(self, pos):
        x, y = pos
        for nx, ny in self.neighbors4(x, y):
            t = self.cell_type(nx, ny)
            if t != "Empty" and t != "Destroyer":
                if t == "LEDPanel":
                    origin = self.find_led_origin(nx, ny)
                    if origin:
                        self.remove_led_panel(origin)
                    continue
                self._remove_from_sim((nx, ny))
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
            self._remove_from_sim((tx, ty))
            self.grid[(tx, ty)]["type"]  = new_type
            self.grid[(tx, ty)]["color"] = cell_map[block_id][1]
            if gd["blockscript"] and new_type in SCRIPTABLE:
                script = gd["blockscript"]
                cell_scripts[(tx, ty)] = script
                self.register_cell(tx, ty, new_type, script)
            else:
                cell_scripts[(tx, ty)] = default_script(new_type) if new_type in SCRIPTABLE else ""
            self.draw_grid()

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

        led_origins_in_cluster = {}
        for pos in cluster_set:
            if self.cell_type(pos[0], pos[1]) == "LEDPanel":
                origin = self.find_led_origin(pos[0], pos[1])
                if origin and origin not in led_origins_in_cluster:
                    led_origins_in_cluster[origin] = self.led_data.get(origin)

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

        for old_origin, ld in led_origins_in_cluster.items():
            if ld is None:
                continue
            new_origin = (old_origin[0] + dx, old_origin[1] + dy)
            self.led_data.pop(old_origin, None)
            self.led_data[new_origin] = ld
            for sig in list(self.signal_graph.keys()):
                self.signal_graph[sig] = [
                    (e[0], new_origin) if e[1] == old_origin else e
                    for e in self.signal_graph[sig]
                ]

        cluster[:] = [(p[0] + dx, p[1] + dy) for p in cluster]
        self.draw_grid()
        return True

    def tick(self, clicked_buttons=None):
        for g in self.gate_data.values():
            g["received"] = set()
        self.signal_state = {}

        self._tick_sensors(set())
        self._tick_buttons(clicked_buttons or [], set())
        self._tick_switches_continuous(set())
        self._tick_engines()

    def save(self, name):
        data = {"grid": {}, "scripts": {}}
        for pos, cell in self.grid.items():
            key = f"{pos[0]},{pos[1]}"
            data["grid"][key] = {"type": cell["type"], "color": list(cell["color"])}
        for pos, script in cell_scripts.items():
            if script.strip():
                key = f"{pos[0]},{pos[1]}"
                data["scripts"][key] = script
        with open(f"{name}.json", "w") as f:
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