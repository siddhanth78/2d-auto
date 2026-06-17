import pygame
from grid import Grid, cell_scripts, cell_map, SCRIPTABLE, parse_script, serialize_bulbs, parse_dim, parse_bulbs, default_script, generate_label
from collections import defaultdict

pygame.init()
pygame.key.set_repeat(200, 50)


def snap_to_grid(pos, cell_size):
    x, y = pos
    return (x // cell_size) * cell_size, (y // cell_size) * cell_size


cell_size     = 20
width, height = pygame.display.Info().current_w, pygame.display.Info().current_h - 120
screen        = pygame.display.set_mode((width, height))
grid          = Grid(width, height)
grid.draw_grid()
clock         = pygame.Clock()
font          = pygame.font.Font(None, 18)
font_ui       = pygame.font.Font(None, 24)
font_editor   = pygame.font.SysFont("monospace", 15)
font_label    = pygame.font.SysFont("monospace", 14)

running         = True
open_editor     = False
sim_running     = False
show_panel      = False
t               = 0
equipped        = 1
clicked_buttons = []
file_mode       = None
file_input      = ""

select_mode    = False
copy_mode      = False
paste_mode     = False
selecting      = False
select_start   = None
select_end     = None
selected_cells = set()
clipboard      = []

led_dragging   = False
led_drag_start = None
led_drag_end   = None

editor_pos          = None
editor_fields       = []
editor_values       = {}
editor_active_field = 0
editor_cur_col      = 0
editor_mx           = 0
editor_my           = 0
editor_blink        = 0

PANEL_W      = 340
ED_PAD       = 10
ED_HEADER_H  = 30
ED_ROW_H     = 26
BULB_SIZE    = 14   # px per bulb square
BULB_GAP     = 2    # gap between bulbs

# ratio-based editor width — 30% of screen, clamped
ED_TOTAL_W   = max(280, min(int(width * 0.30), 480))
FIELD_COL_W  = max(70, int(ED_TOTAL_W * 0.30))
VALUE_COL_W  = ED_TOTAL_W - FIELD_COL_W - ED_PAD * 3
CHAR_W       = 9
MAX_CHARS    = max(8, (VALUE_COL_W - 8) // CHAR_W)
ED_ROW_H2    = ED_ROW_H + 18  # 2-line text row height


def snap_cell(pos):
    x, y = pos
    return x // cell_size, y // cell_size


def get_select_rect():
    if select_start is None or select_end is None:
        return None
    x0 = min(select_start[0], select_end[0])
    y0 = min(select_start[1], select_end[1])
    x1 = max(select_start[0], select_end[0])
    y1 = max(select_start[1], select_end[1])
    return x0, y0, x1, y1


def get_label(pos):
    return f"{pos[0]}_{pos[1]}"


# ── bulb helpers ──────────────────────────────────────────────────────────────

def bulbs_str_to_list(s):
    """Parse bulbs string in any format — space-separated or bracketed rows."""
    import re
    vals = re.findall(r'[01]', s)
    return [int(v) for v in vals]


def bulbs_list_to_str(lst):
    return " ".join(str(v) for v in lst)


def get_bulb_dims(editor_values):
    dim_str = editor_values.get("dim", "")
    cols, rows = parse_dim(dim_str)
    return max(1, min(cols, 32)), max(1, min(rows, 32))












def resize_bulbs(old_list, old_cols, old_rows, new_cols, new_rows):
    """Resize bulb list preserving existing values, trimming or zero-padding."""
    new_list = []
    for r in range(new_rows):
        for c in range(new_cols):
            old_idx = r * old_cols + c
            if r < old_rows and c < old_cols and old_idx < len(old_list):
                new_list.append(old_list[old_idx])
            else:
                new_list.append(0)
    return new_list


def bulb_grid_height(cols, rows):
    """Pixel height of the bulb grid widget — label row + grid rows + padding."""
    return ED_ROW_H + ED_PAD + rows * (BULB_SIZE + BULB_GAP) + ED_PAD


# ── wrap helpers ──────────────────────────────────────────────────────────────

def wrap_value(val):
    if not val:
        return [""]
    lines = []
    while len(val) > MAX_CHARS:
        lines.append(val[:MAX_CHARS])
        val = val[MAX_CHARS:]
    lines.append(val)
    return lines


def cursor_to_wrap(val, flat_col):
    lines     = wrap_value(val)
    remaining = flat_col
    for i, line in enumerate(lines):
        if remaining <= len(line):
            return i, remaining
        remaining -= len(line)
    return len(lines) - 1, len(lines[-1])


def wrap_to_cursor(val, wrap_idx, col_in_line):
    lines = wrap_value(val)
    flat  = 0
    for i, line in enumerate(lines):
        if i == wrap_idx:
            flat += min(col_in_line, len(line))
            break
        flat += len(line)
    return flat


def field_row_height(field, val, editor_values):
    if field == "bulbs":
        cols, rows = get_bulb_dims(editor_values)
        return bulb_grid_height(cols, rows)
    lines = wrap_value(val)
    return ED_ROW_H2 if len(lines) > 1 else ED_ROW_H


def editor_total_h(fields, values):
    h = ED_HEADER_H + ED_PAD
    for f in fields:
        h += field_row_height(f, values.get(f, ""), values)
    h += ED_PAD + 20
    return h


# ── editor functions ──────────────────────────────────────────────────────────

def get_editor_fields(type_name, existing_script):
    attrs = parse_script(existing_script) if existing_script.strip() else {}
    if type_name == "Engine":
        fields = ["input", "dir", "speed"]
    elif type_name == "Button":
        fields = ["output"]
    elif type_name == "Switch":
        fields = ["input", "output"]
    elif type_name == "Sensor":
        fields = ["output", "block"]
    elif type_name in ("AND", "OR", "XOR", "NOT"):
        fields = ["input", "output"]
    elif type_name == "Destroyer":
        fields = ["input"]
    elif type_name == "Generator":
        fields = ["input", "dir", "block", "blockscript"]
    elif type_name == "LEDPanel":
        fields = ["dim", "bulbs", "input"]
    else:
        fields = []
    return fields, {f: attrs.get(f, "") for f in fields}


def editor_to_script():
    lines = []
    for f in editor_fields:
        val = editor_values.get(f, "")
        if f == "bulbs":
            cols, rows  = get_bulb_dims(editor_values)
            bulb_list   = bulbs_str_to_list(val)
            total       = cols * rows
            if len(bulb_list) < total:
                bulb_list += [0] * (total - len(bulb_list))
            else:
                bulb_list = bulb_list[:total]
            lines.append(f"bulbs {serialize_bulbs(bulb_list, cols)}")
        elif f == "dim":
            lines.append(f"dim {val}" if val else "dim 1x1")
        else:
            lines.append(f"{f}: {val}")
    return "\n".join(lines)


def open_editor_at(cx, cy, gx, gy):
    global open_editor, editor_pos, editor_fields, editor_values
    global editor_active_field, editor_cur_col, editor_mx, editor_my, editor_blink

    editor_pos   = (cx, cy)
    type_name    = grid.cell_type(cx, cy)
    existing     = cell_scripts.get((cx, cy), "")
    fields, vals = get_editor_fields(type_name, existing)

    editor_fields       = fields
    editor_values       = vals
    editor_active_field = 0
    editor_cur_col      = len(vals.get(fields[0], "")) if fields else 0
    editor_blink        = 0

    total_h = editor_total_h(fields, vals)

    editor_mx = gx * cell_size + cell_size + 4
    editor_my = gy * cell_size
    if editor_mx + ED_TOTAL_W > width:
        editor_mx = gx * cell_size - ED_TOTAL_W - 4
    if editor_my + total_h > height - 30:
        editor_my = height - 30 - total_h

    open_editor = True


def close_editor():
    global open_editor, editor_pos
    if editor_pos is None:
        open_editor = False
        return
    script    = editor_to_script()
    cx, cy    = editor_pos
    type_name = grid.cell_type(cx, cy)
    cell_scripts[editor_pos] = script
    if type_name == "LEDPanel":
        origin = grid.find_led_origin(cx, cy)
        if origin:
            grid.update_led_script(origin, script)
    elif type_name in SCRIPTABLE and sim_running:
        grid.register_cell(cx, cy, type_name, script)
    open_editor = False
    editor_pos  = None


def draw_bulb_field(surface, row_y, is_active, editor_values):
    """Draw the bulb grid full-width inside the editor panel."""
    cols, rows  = get_bulb_dims(editor_values)
    bulb_list   = bulbs_str_to_list(editor_values.get("bulbs", ""))
    total_bulbs = cols * rows
    if len(bulb_list) < total_bulbs:
        bulb_list += [0] * (total_bulbs - len(bulb_list))
    else:
        bulb_list = bulb_list[:total_bulbs]

    gh  = bulb_grid_height(cols, rows)
    fw  = ED_TOTAL_W - ED_PAD * 2          # full inner width
    fx  = editor_mx + ED_PAD
    fy  = row_y

    bg  = (45, 45, 55) if is_active else (38, 38, 42)
    bd  = (140, 140, 200) if is_active else (70, 70, 70)
    pygame.draw.rect(surface, bg, (fx, fy, fw, gh - 2))
    pygame.draw.rect(surface, bd, (fx, fy, fw, gh - 2), 1)

    # "bulbs" label left, active highlight
    lbl = font_label.render("bulbs", True, (220, 220, 220) if is_active else (160, 160, 160))
    surface.blit(lbl, (fx + ED_PAD, fy + (ED_ROW_H - lbl.get_height()) // 2))

    # grid starts below the label row
    ox = fx + ED_PAD
    oy = fy + ED_ROW_H + ED_PAD // 2
    for r in range(rows):
        for c in range(cols):
            idx  = r * cols + c
            bx   = ox + c * (BULB_SIZE + BULB_GAP)
            by   = oy + r * (BULB_SIZE + BULB_GAP)
            on   = bulb_list[idx] == 1
            col  = (240, 220, 80) if on else (55, 55, 55)
            bcol = (200, 180, 60) if on else (85, 85, 85)
            pygame.draw.rect(surface, col,  (bx, by, BULB_SIZE, BULB_SIZE))
            pygame.draw.rect(surface, bcol, (bx, by, BULB_SIZE, BULB_SIZE), 1)


def handle_bulb_click(mx, my, row_top, editor_values):
    """Toggle bulb at mouse pos. Returns updated bulbs string or None."""
    cols, rows = get_bulb_dims(editor_values)
    ox = editor_mx + ED_PAD + ED_PAD          # fx + ED_PAD
    oy = row_top + ED_ROW_H + ED_PAD // 2
    c  = (mx - ox) // (BULB_SIZE + BULB_GAP)
    r  = (my - oy) // (BULB_SIZE + BULB_GAP)
    if 0 <= c < cols and 0 <= r < rows:
        bulb_list   = bulbs_str_to_list(editor_values.get("bulbs", ""))
        total_bulbs = cols * rows
        if len(bulb_list) < total_bulbs:
            bulb_list += [0] * (total_bulbs - len(bulb_list))
        else:
            bulb_list = bulb_list[:total_bulbs]
        idx              = r * cols + c
        bulb_list[idx]   = 1 if bulb_list[idx] == 0 else 0
        return bulbs_list_to_str(bulb_list)
    return None


def draw_editor(surface):
    global editor_blink
    editor_blink = (editor_blink + 1) % 60

    if not editor_fields:
        return

    type_name = grid.cell_type(editor_pos[0], editor_pos[1]) if editor_pos else ""
    lbl       = f"{type_name} [{get_label(editor_pos)}]" if editor_pos else ""

    total_h = editor_total_h(editor_fields, editor_values)

    pygame.draw.rect(surface, (35, 35, 35), (editor_mx, editor_my, ED_TOTAL_W, total_h))
    pygame.draw.rect(surface, (110, 110, 110), (editor_mx, editor_my, ED_TOTAL_W, total_h), 1)

    header = font_label.render(lbl, True, (160, 160, 160))
    surface.blit(header, (editor_mx + ED_PAD, editor_my + 8))
    pygame.draw.line(surface, (60, 60, 60),
                     (editor_mx, editor_my + ED_HEADER_H),
                     (editor_mx + ED_TOTAL_W, editor_my + ED_HEADER_H), 1)

    row_y = editor_my + ED_HEADER_H + ED_PAD

    for i, field in enumerate(editor_fields):
        is_active = (i == editor_active_field)
        val       = editor_values.get(field, "")
        rh        = field_row_height(field, val, editor_values)

        if field == "bulbs":
            draw_bulb_field(surface, row_y, is_active, editor_values)
        else:
            label_surf = font_label.render(field, True,
                                           (220, 220, 220) if is_active else (160, 160, 160))
            surface.blit(label_surf, (editor_mx + ED_PAD,
                                      row_y + (rh - label_surf.get_height()) // 2))

            vx = editor_mx + ED_PAD + FIELD_COL_W
            vy = row_y
            vw = VALUE_COL_W
            lines = wrap_value(val)
            vh    = rh - 2

            bg_col = (55, 55, 55) if is_active else (42, 42, 42)
            bd_col = (140, 140, 200) if is_active else (70, 70, 70)
            pygame.draw.rect(surface, bg_col, (vx, vy, vw, vh))
            pygame.draw.rect(surface, bd_col, (vx, vy, vw, vh), 1)

            clip_rect = pygame.Rect(vx + 1, vy + 1, vw - 2, vh - 2)
            old_clip  = surface.get_clip()
            surface.set_clip(clip_rect)

            if len(lines) == 1:
                txt_surf = font_editor.render(lines[0], True, (230, 230, 230))
                surface.blit(txt_surf, (vx + 4, vy + 5))
                if is_active and editor_blink < 30:
                    cur_x = vx + 4 + font_editor.size(lines[0][:editor_cur_col])[0]
                    pygame.draw.line(surface, (230, 230, 230),
                                     (cur_x, vy + 3), (cur_x, vy + vh - 3), 1)
            else:
                wi, wc = cursor_to_wrap(val, editor_cur_col)
                if wi == 0:
                    view_start = 0
                elif wi >= len(lines) - 1:
                    view_start = max(0, len(lines) - 2)
                else:
                    view_start = wi - 1
                view_start = min(view_start, max(0, len(lines) - 2))

                line_h = ED_ROW_H - 6
                for draw_i, li in enumerate(range(view_start, view_start + 2)):
                    if li >= len(lines):
                        break
                    ly       = vy + 3 + draw_i * line_h
                    txt_surf = font_editor.render(lines[li], True, (230, 230, 230))
                    surface.blit(txt_surf, (vx + 4, ly))
                    if is_active and editor_blink < 30 and li == wi:
                        cx_px = vx + 4 + font_editor.size(lines[li][:wc])[0]
                        pygame.draw.line(surface, (230, 230, 230),
                                         (cx_px, ly + 1), (cx_px, ly + line_h - 2), 1)

                surface.set_clip(old_clip)
                if view_start > 0:
                    pygame.draw.circle(surface, (120, 120, 180), (vx + vw - 6, vy + 5), 2)
                if view_start + 2 < len(lines):
                    pygame.draw.circle(surface, (120, 120, 180), (vx + vw - 6, vy + vh - 5), 2)

            surface.set_clip(old_clip)

        row_y += rh

    hint_y = editor_my + total_h - 18
    surface.blit(font.render("TAB / ESC  close", True, (70, 70, 70)),
                 (editor_mx + ED_PAD, hint_y))

    hx = editor_pos[0] * cell_size
    hy = editor_pos[1] * cell_size
    pygame.draw.rect(surface, (200, 200, 200), (hx, hy, cell_size, cell_size), 2)


def editor_handle_key(event):
    global editor_active_field, editor_cur_col, editor_values

    if not editor_fields:
        return

    field = editor_fields[editor_active_field]
    val   = editor_values.get(field, "")

    # bulbs field is mouse-only, keys just navigate fields
    if field == "bulbs":
        if event.key in (pygame.K_TAB, pygame.K_ESCAPE):
            close_editor()
        elif event.key == pygame.K_UP:
            editor_active_field = max(0, editor_active_field - 1)
            f = editor_fields[editor_active_field]
            editor_cur_col = len(editor_values.get(f, ""))
        elif event.key == pygame.K_DOWN:
            editor_active_field = min(len(editor_fields) - 1, editor_active_field + 1)
            f = editor_fields[editor_active_field]
            editor_cur_col = len(editor_values.get(f, ""))
        return

    if event.key in (pygame.K_TAB, pygame.K_ESCAPE):
        close_editor()
        return

    if event.key == pygame.K_UP:
        wi, wc = cursor_to_wrap(val, editor_cur_col)
        if wi > 0:
            editor_cur_col = wrap_to_cursor(val, wi - 1, wc)
        else:
            editor_active_field = max(0, editor_active_field - 1)
            f = editor_fields[editor_active_field]
            editor_cur_col = len(editor_values.get(f, ""))
        return

    if event.key == pygame.K_DOWN:
        lines  = wrap_value(val)
        wi, wc = cursor_to_wrap(val, editor_cur_col)
        if wi < len(lines) - 1:
            editor_cur_col = wrap_to_cursor(val, wi + 1, wc)
        else:
            editor_active_field = min(len(editor_fields) - 1, editor_active_field + 1)
            f = editor_fields[editor_active_field]
            editor_cur_col = len(editor_values.get(f, ""))
        return

    if event.key == pygame.K_LEFT:
        editor_cur_col = max(0, editor_cur_col - 1)
        return

    if event.key == pygame.K_RIGHT:
        editor_cur_col = min(len(val), editor_cur_col + 1)
        return

    if event.key == pygame.K_HOME:
        wi, _          = cursor_to_wrap(val, editor_cur_col)
        editor_cur_col = wrap_to_cursor(val, wi, 0)
        return

    if event.key == pygame.K_END:
        wi, _          = cursor_to_wrap(val, editor_cur_col)
        lines          = wrap_value(val)
        editor_cur_col = wrap_to_cursor(val, wi, len(lines[wi]))
        return

    if event.key == pygame.K_BACKSPACE:
        if editor_cur_col > 0:
            # when dim changes, resize bulbs to preserve values
            old_val = val
            val     = val[:editor_cur_col - 1] + val[editor_cur_col:]
            editor_values[field] = val
            editor_cur_col -= 1
            if field == "dim":
                _sync_bulbs_to_dim(old_val, val)

    elif event.key == pygame.K_DELETE:
        if editor_cur_col < len(val):
            old_val = val
            val     = val[:editor_cur_col] + val[editor_cur_col + 1:]
            editor_values[field] = val
            if field == "dim":
                _sync_bulbs_to_dim(old_val, val)

    elif event.key == pygame.K_SPACE:
        old_val = val
        val     = val[:editor_cur_col] + " " + val[editor_cur_col:]
        editor_values[field] = val
        editor_cur_col      += 1
        if field == "dim":
            _sync_bulbs_to_dim(old_val, val)

    elif event.unicode and event.unicode.isprintable() and event.key not in (pygame.K_TAB, pygame.K_ESCAPE):
        old_val = val
        val     = val[:editor_cur_col] + event.unicode + val[editor_cur_col:]
        editor_values[field] = val
        editor_cur_col      += 1
        if field == "dim":
            _sync_bulbs_to_dim(old_val, val)


def _sync_bulbs_to_dim(old_dim_str, new_dim_str):
    """Resize bulbs list when dim field changes."""
    old_cols, old_rows = parse_dim(old_dim_str)
    new_cols, new_rows = parse_dim(new_dim_str)
    old_list = bulbs_str_to_list(editor_values.get("bulbs", ""))
    new_list = resize_bulbs(old_list, old_cols, old_rows, new_cols, new_rows)
    editor_values["bulbs"] = bulbs_list_to_str(new_list)


def get_cell_state(pos, type_):
    if type_ == "Switch":
        sw = grid.switch_data.get(pos)
        return sw["state"] if sw else 0
    elif type_ == "Sensor":
        sd = grid.sensor_data.get(pos)
        if sd and sd["outputs"]:
            return grid.signal_state.get(sd["outputs"][0], 0)
        return 0
    elif type_ in ("AND", "OR", "NOT", "XOR"):
        gd = grid.gate_data.get(pos)
        if gd and gd["outputs"]:
            return grid.signal_state.get(gd["outputs"][0], 0)
        return 0
    elif type_ == "Engine":
        ed = grid.engine_data.get(pos)
        if ed:
            return 1 if any(grid.signal_state.get(s, 0) == 1 for s in ed["inputs"]) else 0
        return 0
    elif type_ == "Button":
        bd = grid.button_data.get(pos)
        if bd and bd["outputs"]:
            return grid.signal_state.get(bd["outputs"][0], 0)
        return 0
    elif type_ == "Destroyer":
        dd = grid.destroyer_data.get(pos)
        if dd and dd["inputs"]:
            return grid.signal_state.get(dd["inputs"][0], 0)
        return 0
    elif type_ == "Generator":
        gd = grid.generator_data.get(pos)
        if gd and gd["inputs"]:
            return grid.signal_state.get(gd["inputs"][0], 0)
        return 0
    elif type_ == "LEDPanel":
        ld = grid.led_data.get(pos)
        if ld and ld["inputs"]:
            return grid.signal_state.get(ld["inputs"][0], 0)
        return 0
    return 0


def build_flow_chains():
    sig_to_receivers = defaultdict(list)
    for pos, sw in grid.switch_data.items():
        for sig in sw["inputs"]:
            sig_to_receivers[sig].append(("Switch", pos))
    for pos, ed in grid.engine_data.items():
        for sig in ed["inputs"]:
            sig_to_receivers[sig].append(("Engine", pos))
    for pos, gd in grid.gate_data.items():
        for sig in gd["inputs"]:
            sig_to_receivers[sig].append((gd["type"], pos))
    for pos, dd in grid.destroyer_data.items():
        for sig in dd["inputs"]:
            sig_to_receivers[sig].append(("Destroyer", pos))
    for pos, gd in grid.generator_data.items():
        for sig in gd["inputs"]:
            sig_to_receivers[sig].append(("Generator", pos))
    for pos, ld in grid.led_data.items():
        for sig in ld["inputs"]:
            sig_to_receivers[sig].append(("LEDPanel", pos))

    chains      = []
    seen_chains = set()
    emitters    = []
    for pos, bd in grid.button_data.items():
        emitters.append(("Button", pos, bd["outputs"]))
    for pos, sd in grid.sensor_data.items():
        emitters.append(("Sensor", pos, sd["outputs"]))
    for pos, sw in grid.switch_data.items():
        emitters.append(("Switch", pos, sw["outputs"]))
    for pos, gd in grid.gate_data.items():
        emitters.append((gd["type"], pos, gd["outputs"]))

    for etype, epos, eouts in emitters:
        for sig in eouts:
            for rtype, rpos in sig_to_receivers.get(sig, []):
                key = (epos, sig, rpos)
                if key in seen_chains:
                    continue
                seen_chains.add(key)
                chains.append((etype, epos, sig, rtype, rpos))
    return chains


def draw_panel(surface, chains):
    pw    = PANEL_W
    ph    = height
    panel = pygame.Surface((pw, ph))
    panel.fill((30, 30, 30))
    pygame.draw.line(panel, (80, 80, 80), (0, 0), (0, ph), 1)
    y = 8
    panel.blit(font_ui.render("signal flow  [P]", True, (180, 180, 180)), (10, y))
    y += 28
    pygame.draw.line(panel, (60, 60, 60), (0, y), (pw, y), 1)
    y += 8
    if not sim_running:
        panel.blit(font.render("start sim to see live state", True, (100, 100, 100)), (10, y))
    else:
        if not chains:
            panel.blit(font.render("no signal connections found", True, (100, 100, 100)), (10, y))
        else:
            prev_sig = None
            for etype, epos, sig, rtype, rpos in chains:
                if sig != prev_sig:
                    if prev_sig is not None:
                        y += 4
                        pygame.draw.line(panel, (50, 50, 50), (0, y), (pw, y), 1)
                        y += 6
                    panel.blit(font.render(f"signal: {sig}", True, (120, 120, 180)), (10, y))
                    y += 16
                    prev_sig = sig
                estate = get_cell_state(epos, etype)
                rstate = get_cell_state(rpos, rtype)
                ec     = (0, 220, 0) if estate == 1 else (180, 60, 60)
                rc     = (0, 220, 0) if rstate == 1 else (180, 60, 60)
                e_surf = font.render(f"  {etype} [{get_label(epos)}]", True, ec)
                arrow  = font.render("  -->  ", True, (100, 100, 100))
                r_surf = font.render(f"{rtype} [{get_label(rpos)}]", True, rc)
                ex = 10
                panel.blit(e_surf, (ex, y))
                ex += e_surf.get_width()
                panel.blit(arrow, (ex, y))
                ex += arrow.get_width()
                panel.blit(r_surf, (ex, y))
                y += 18
                if y > ph - 20:
                    break
    surface.blit(panel, (width - pw, 0))


def do_copy_selected():
    global clipboard, paste_mode, copy_mode, select_mode
    if not selected_cells:
        return
    x0 = min(p[0] for p in selected_cells)
    y0 = min(p[1] for p in selected_cells)
    clipboard = []
    for cx, cy in selected_cells:
        t = grid.cell_type(cx, cy)
        if t != "Empty":
            clipboard.append({
                "rel":       (cx - x0, cy - y0),
                "type_name": t,
                "color":     grid.grid[(cx, cy)]["color"],
                "script":    cell_scripts.get((cx, cy), ""),
            })
    paste_mode  = True
    copy_mode   = False
    select_mode = False


def do_delete_selected():
    for cx, cy in selected_cells:
        t = grid.cell_type(cx, cy)
        if t == "LEDPanel":
            origin = grid.find_led_origin(cx, cy)
            if origin:
                grid.remove_led_panel(origin)
        elif not grid.is_empty(cx, cy):
            cell_scripts[(cx, cy)] = ""
            grid.set_cell(cx, cy, 0)


def can_paste(origin_cx, origin_cy):
    for item in clipboard:
        dx, dy = item["rel"]
        tx, ty = origin_cx + dx, origin_cy + dy
        if not grid.in_bounds(tx, ty):
            return False
        if not grid.is_empty(tx, ty):
            return False
    return True


def do_paste(origin_cx, origin_cy):
    if not can_paste(origin_cx, origin_cy):
        return
    for item in clipboard:
        dx, dy    = item["rel"]
        tx, ty    = origin_cx + dx, origin_cy + dy
        type_name = item["type_name"]
        grid.grid[(tx, ty)]["type"]  = type_name
        grid.grid[(tx, ty)]["color"] = item["color"]
        if type_name in SCRIPTABLE:
            cell_scripts[(tx, ty)] = item["script"]
            grid.register_cell(tx, ty, type_name, item["script"])
        else:
            cell_scripts.pop((tx, ty), None)
    grid.draw_grid()


while running:
    screen.fill((0, 0, 0))

    if sim_running and not open_editor:
        t = (t + 1) % 10
    else:
        t = 0

    tick     = (t == 0) and sim_running and not open_editor
    mp       = snap_to_grid(pygame.mouse.get_pos(), cell_size)
    mcx, mcy = snap_cell(pygame.mouse.get_pos())

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:

            if file_mode:
                if event.key == pygame.K_RETURN:
                    if file_input.strip():
                        if file_mode == "save":
                            grid.save(file_input.strip())
                        elif file_mode == "load":
                            grid.load(file_input.strip())
                    file_mode  = None
                    file_input = ""
                elif event.key == pygame.K_ESCAPE:
                    file_mode  = None
                    file_input = ""
                elif event.key == pygame.K_BACKSPACE:
                    file_input = file_input[:-1]
                else:
                    if event.unicode and event.unicode.isprintable():
                        file_input += event.unicode
                continue

            if open_editor:
                editor_handle_key(event)
                continue

            if event.key == pygame.K_ESCAPE:
                if select_mode or copy_mode or paste_mode:
                    select_mode    = False
                    copy_mode      = False
                    paste_mode     = False
                    selecting      = False
                    select_start   = None
                    select_end     = None
                    selected_cells = set()
                elif led_dragging:
                    led_dragging   = False
                    led_drag_start = None
                    led_drag_end   = None
                else:
                    running = False

            elif event.key == pygame.K_x and not file_mode:
                select_mode    = True
                copy_mode      = False
                paste_mode     = False
                selecting      = False
                select_start   = None
                select_end     = None
                selected_cells = set()

            elif event.key == pygame.K_c and not file_mode:
                if select_mode and selected_cells:
                    do_copy_selected()
                elif not select_mode:
                    copy_mode      = True
                    paste_mode     = False
                    select_mode    = False
                    selecting      = False
                    select_start   = None
                    select_end     = None
                    selected_cells = set()
                    clipboard      = []

            elif event.key == pygame.K_v and not file_mode and clipboard:
                paste_mode  = True
                copy_mode   = False
                select_mode = False

            elif event.key == pygame.K_BACKSPACE and select_mode and selected_cells:
                do_delete_selected()
                selected_cells = set()
                select_mode    = False

            elif event.key == pygame.K_p:
                show_panel = not show_panel

            elif event.key == pygame.K_s and not sim_running and not select_mode:
                file_mode  = "save"
                file_input = ""

            elif event.key == pygame.K_l and not sim_running and not select_mode:
                file_mode  = "load"
                file_input = ""

            elif event.key == pygame.K_SPACE:
                sim_running = not sim_running
                if sim_running:
                    grid.compile_scripts()

            elif event.key == pygame.K_LEFT and not select_mode and not copy_mode and not paste_mode:
                equipped = max(0, equipped - 1)
            elif event.key == pygame.K_RIGHT and not select_mode and not copy_mode and not paste_mode:
                equipped = min(len(cell_map) - 1, equipped + 1)

            elif event.key == pygame.K_TAB and not select_mode and not copy_mode and not paste_mode:
                cx, cy    = mcx, mcy
                cell_type = grid.cell_type(cx, cy)
                if cell_type == "LEDPanel":
                    origin = grid.find_led_origin(cx, cy)
                    if origin:
                        open_editor_at(origin[0], origin[1], origin[0], origin[1])
                elif cell_type in SCRIPTABLE:
                    open_editor_at(cx, cy, cx, cy)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if open_editor:
                total_h    = editor_total_h(editor_fields, editor_values)
                mx_m, my_m = pygame.mouse.get_pos()
                if not (editor_mx <= mx_m <= editor_mx + ED_TOTAL_W and
                        editor_my <= my_m <= editor_my + total_h):
                    close_editor()
                else:
                    row_y = editor_my + ED_HEADER_H + ED_PAD
                    for idx, f in enumerate(editor_fields):
                        rh = field_row_height(f, editor_values.get(f, ""), editor_values)
                        if row_y <= my_m <= row_y + rh:
                            editor_active_field = idx
                            if f == "bulbs" and event.button == 1:
                                result = handle_bulb_click(mx_m, my_m, row_y, editor_values)
                                if result is not None:
                                    editor_values["bulbs"] = result
                            else:
                                editor_cur_col = len(editor_values.get(f, ""))
                            break
                        row_y += rh
                continue

            if not file_mode:
                if select_mode or copy_mode:
                    if event.button == 1:
                        selecting    = True
                        select_start = (mcx, mcy)
                        select_end   = (mcx, mcy)
                elif paste_mode:
                    if event.button == 1:
                        do_paste(mcx, mcy)
                        paste_mode = False
                    elif event.button == 3:
                        paste_mode = False
                else:
                    cx, cy = mcx, mcy
                    if event.button == 1:
                        t_name = grid.get_cell(cx, cy)[0]
                        if t_name == "Button" and sim_running:
                            if (cx, cy) not in clicked_buttons:
                                clicked_buttons.append((cx, cy))
                        elif t_name == "Switch" and sim_running:
                            sw = grid.switch_data.get((cx, cy))
                            if sw is not None:
                                sw["state"] = 1 if sw["state"] == 0 else 0
                        elif t_name == "LEDPanel":
                            pass
                        elif cell_map[equipped][0] == "LEDPanel":
                            led_dragging   = True
                            led_drag_start = (cx, cy)
                            led_drag_end   = (cx, cy)
                        else:
                            grid.set_cell(cx, cy, equipped)
                    elif event.button == 3:
                        t_name = grid.get_cell(cx, cy)[0]
                        if t_name == "LEDPanel":
                            origin = grid.find_led_origin(cx, cy)
                            if origin:
                                grid.remove_led_panel(origin)
                        else:
                            grid.set_cell(cx, cy, 0)

        elif event.type == pygame.MOUSEBUTTONUP:
            if led_dragging and event.button == 1:
                led_dragging = False
                if led_drag_start and led_drag_end:
                    x0   = min(led_drag_start[0], led_drag_end[0])
                    y0   = min(led_drag_start[1], led_drag_end[1])
                    x1   = max(led_drag_start[0], led_drag_end[0])
                    y1   = max(led_drag_start[1], led_drag_end[1])
                    cols = min(x1 - x0 + 1, 16)
                    rows = min(y1 - y0 + 1, 16)
                    ok   = all(grid.is_empty(x0 + c, y0 + r) for r in range(rows) for c in range(cols))
                    if ok:
                        script = grid.place_led_panel(x0, y0, cols, rows)
                        grid.register_cell(x0, y0, "LEDPanel", script)
                led_drag_start = None
                led_drag_end   = None

            if selecting and event.button == 1:
                selecting = False
                rect = get_select_rect()
                if rect:
                    x0, y0, x1, y1 = rect
                    if copy_mode:
                        clipboard = []
                        for cy in range(y0, y1 + 1):
                            for cx in range(x0, x1 + 1):
                                t = grid.cell_type(cx, cy)
                                if t != "Empty":
                                    clipboard.append({
                                        "rel":       (cx - x0, cy - y0),
                                        "type_name": t,
                                        "color":     grid.grid[(cx, cy)]["color"],
                                        "script":    cell_scripts.get((cx, cy), ""),
                                    })
                        copy_mode  = False
                        paste_mode = True
                    elif select_mode:
                        selected_cells = set()
                        for cy in range(y0, y1 + 1):
                            for cx in range(x0, x1 + 1):
                                selected_cells.add((cx, cy))

        elif event.type == pygame.MOUSEMOTION:
            if selecting:
                select_end = (mcx, mcy)
            if led_dragging:
                led_drag_end = (mcx, mcy)

    if tick:
        grid.tick(clicked_buttons if clicked_buttons else None)
        clicked_buttons = []

    grid.draw(screen, sim_running)

    if sim_running:
        for pos, sw in grid.switch_data.items():
            x, y  = pos
            color = (0, 220, 0) if sw["state"] == 1 else (180, 60, 60)
            pygame.draw.circle(screen, color, (x * cell_size + cell_size // 2, y * cell_size + cell_size // 2), 3)
        for pos, sd in grid.sensor_data.items():
            x, y  = pos
            sig   = sd["outputs"][0] if sd["outputs"] else None
            value = grid.signal_state.get(sig, 0) if sig else 0
            color = (0, 220, 0) if value == 1 else (180, 60, 60)
            pygame.draw.circle(screen, color, (x * cell_size + cell_size // 2, y * cell_size + cell_size // 2), 3)
        for pos, gd in grid.gate_data.items():
            x, y  = pos
            sig   = gd["outputs"][0] if gd["outputs"] else None
            value = grid.signal_state.get(sig, 0) if sig else 0
            color = (0, 220, 0) if value == 1 else (180, 60, 60)
            pygame.draw.circle(screen, color, (x * cell_size + cell_size // 2, y * cell_size + cell_size // 2), 3)
        for pos, ed in grid.engine_data.items():
            x, y   = pos
            active = any(grid.signal_state.get(sig, 0) == 1 for sig in ed["inputs"])
            color  = (0, 220, 0) if active else (180, 60, 60)
            pygame.draw.circle(screen, color, (x * cell_size + cell_size // 2, y * cell_size + cell_size // 2), 3)
        for pos, bd in grid.button_data.items():
            x, y  = pos
            sig   = bd["outputs"][0] if bd["outputs"] else None
            value = grid.signal_state.get(sig, 0) if sig else 0
            color = (0, 220, 0) if value == 1 else (180, 60, 60)
            pygame.draw.circle(screen, color, (x * cell_size + cell_size // 2, y * cell_size + cell_size // 2), 3)
        for pos, dd in grid.destroyer_data.items():
            x, y  = pos
            value = grid.signal_state.get(dd["inputs"][0], 0) if dd["inputs"] else 0
            color = (0, 220, 0) if value == 1 else (180, 60, 60)
            pygame.draw.circle(screen, color, (x * cell_size + cell_size // 2, y * cell_size + cell_size // 2), 3)
        for pos, gd in grid.generator_data.items():
            x, y  = pos
            value = grid.signal_state.get(gd["inputs"][0], 0) if gd["inputs"] else 0
            color = (0, 220, 0) if value == 1 else (180, 60, 60)
            pygame.draw.circle(screen, color, (x * cell_size + cell_size // 2, y * cell_size + cell_size // 2), 3)
        for pos, ld in grid.led_data.items():
            x, y  = pos
            value = grid.signal_state.get(ld["inputs"][0], 0) if ld["inputs"] else 0
            color = (0, 220, 0) if value == 1 else (180, 60, 60)
            pygame.draw.circle(screen, color, (x * cell_size + cell_size // 2, y * cell_size + cell_size // 2), 3)

    if led_dragging and led_drag_start and led_drag_end:
        x0   = min(led_drag_start[0], led_drag_end[0]) * cell_size
        y0   = min(led_drag_start[1], led_drag_end[1]) * cell_size
        cols = min(abs(led_drag_end[0] - led_drag_start[0]) + 1, 16)
        rows = min(abs(led_drag_end[1] - led_drag_start[1]) + 1, 16)
        x1   = x0 + cols * cell_size
        y1   = y0 + rows * cell_size
        ghost = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
        ghost.fill((30, 30, 30, 160))
        screen.blit(ghost, (x0, y0))
        pygame.draw.rect(screen, (200, 180, 255), (x0, y0, x1 - x0, y1 - y0), 1)
        screen.blit(font.render(f"{cols}x{rows}", True, (200, 180, 255)), (x0 + 4, y0 + 4))

    if (select_mode or copy_mode) and select_start and select_end:
        x0   = min(select_start[0], select_end[0]) * cell_size
        y0   = min(select_start[1], select_end[1]) * cell_size
        x1   = (max(select_start[0], select_end[0]) + 1) * cell_size
        y1   = (max(select_start[1], select_end[1]) + 1) * cell_size
        col  = (100, 180, 255) if copy_mode else (255, 200, 80)
        surf = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
        surf.fill((*col, 50))
        screen.blit(surf, (x0, y0))
        pygame.draw.rect(screen, col, (x0, y0, x1 - x0, y1 - y0), 1)

    if selected_cells and select_mode:
        for cx, cy in selected_cells:
            px, py = cx * cell_size, cy * cell_size
            surf   = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
            surf.fill((255, 200, 80, 60))
            screen.blit(surf, (px, py))
            pygame.draw.rect(screen, (255, 200, 80), (px, py, cell_size, cell_size), 1)

    if paste_mode and clipboard:
        valid = can_paste(mcx, mcy)
        for item in clipboard:
            dx, dy = item["rel"]
            tx, ty = mcx + dx, mcy + dy
            px, py = tx * cell_size, ty * cell_size
            color  = item["color"]
            ghost  = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
            ghost.fill((*color, 140))
            screen.blit(ghost, (px, py))
            pygame.draw.rect(screen, (0, 220, 0) if valid else (220, 60, 60), (px, py, cell_size, cell_size), 1)

    if open_editor:
        draw_editor(screen)

    if show_panel:
        chains = build_flow_chains()
        draw_panel(screen, chains)

    if file_mode:
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))
        box_w, box_h = 400, 100
        bx = width  // 2 - box_w // 2
        by = height // 2 - box_h // 2
        pygame.draw.rect(screen, (60, 60, 60), (bx, by, box_w, box_h))
        pygame.draw.rect(screen, (200, 200, 200), (bx, by, box_w, box_h), 1)
        label = "save as:" if file_mode == "save" else "load file:"
        screen.blit(font_ui.render(label, True, (200, 200, 200)), (bx + 16, by + 12))
        screen.blit(font_ui.render(file_input + "|", True, (255, 255, 255)), (bx + 16, by + 52))
    elif select_mode:
        if selected_cells:
            msg = font_ui.render(f"select — {len(selected_cells)} cells  [C] copy  [DEL] delete  [ESC] cancel", True, (255, 200, 80))
        elif selecting:
            msg = font_ui.render("select — drag to select  [ESC] cancel", True, (255, 200, 80))
        else:
            msg = font_ui.render("select — click and drag  [ESC] cancel", True, (255, 200, 80))
        screen.blit(msg, (8, height - 24))
    elif copy_mode:
        screen.blit(font_ui.render("copy — drag to select region  [ESC] cancel", True, (100, 180, 255)), (8, height - 24))
    elif paste_mode:
        color = (0, 220, 0) if can_paste(mcx, mcy) else (220, 60, 60)
        screen.blit(font_ui.render("paste — click to place  right click cancel", True, color), (8, height - 24))
    elif led_dragging:
        screen.blit(font_ui.render("LED panel — drag to set size  max 16x16", True, (200, 180, 255)), (8, height - 24))
    elif not open_editor:
        pygame.draw.rect(screen, cell_map[equipped][1], (mp[0], mp[1], cell_size, cell_size), 2)
        status = (
            f"[SPACE] {'STOP' if sim_running else 'START'}  |  "
            f"equipped: [{equipped}] {cell_map[equipped][0]}  |  "
            f"[</> arrows] select  |  [TAB] script  |  "
            f"[X] select  [C] copy  [V] paste  |  [S] save  [L] load  |  [P] panel"
        )
        screen.blit(font_ui.render(status, True, (200, 200, 200)), (8, height - 24))

    pygame.display.update()
    clock.tick(60)

pygame.quit()
quit()