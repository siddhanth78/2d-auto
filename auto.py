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
FIELD_COL_W  = 100
VALUE_COL_W  = 160
ED_ROW_H     = 26
ED_PAD       = 10
ED_HEADER_H  = 30


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
        if f in ("dim", "bulbs"):
            lines.append(f"{f} {val}" if val else f"{f}")
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

    total_h  = ED_HEADER_H + ED_PAD + len(fields) * ED_ROW_H + ED_PAD + 20
    ed_w     = FIELD_COL_W + VALUE_COL_W + ED_PAD * 3

    editor_mx = gx * cell_size + cell_size + 4
    editor_my = gy * cell_size
    if editor_mx + ed_w > width:
        editor_mx = gx * cell_size - ed_w - 4
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


def draw_editor(surface):
    global editor_blink
    editor_blink = (editor_blink + 1) % 60

    if not editor_fields:
        return

    type_name = grid.cell_type(editor_pos[0], editor_pos[1]) if editor_pos else ""
    lbl       = f"{type_name} [{get_label(editor_pos)}]" if editor_pos else ""

    total_h = ED_HEADER_H + ED_PAD + len(editor_fields) * ED_ROW_H + ED_PAD + 20
    ed_w    = FIELD_COL_W + VALUE_COL_W + ED_PAD * 3

    pygame.draw.rect(surface, (35, 35, 35), (editor_mx, editor_my, ed_w, total_h))
    pygame.draw.rect(surface, (110, 110, 110), (editor_mx, editor_my, ed_w, total_h), 1)

    header = font_label.render(lbl, True, (160, 160, 160))
    surface.blit(header, (editor_mx + ED_PAD, editor_my + 8))
    pygame.draw.line(surface, (60, 60, 60),
                     (editor_mx, editor_my + ED_HEADER_H),
                     (editor_mx + ed_w, editor_my + ED_HEADER_H), 1)

    for i, field in enumerate(editor_fields):
        row_y    = editor_my + ED_HEADER_H + ED_PAD + i * ED_ROW_H
        is_active = (i == editor_active_field)

        label_surf = font_label.render(field, True, (160, 160, 160) if not is_active else (220, 220, 220))
        surface.blit(label_surf, (editor_mx + ED_PAD, row_y + 5))

        vx = editor_mx + ED_PAD + FIELD_COL_W
        vy = row_y + 2
        vw = VALUE_COL_W
        vh = ED_ROW_H - 4

        bg_col = (55, 55, 55) if is_active else (42, 42, 42)
        bd_col = (140, 140, 200) if is_active else (70, 70, 70)
        pygame.draw.rect(surface, bg_col, (vx, vy, vw, vh))
        pygame.draw.rect(surface, bd_col, (vx, vy, vw, vh), 1)

        val       = editor_values.get(field, "")
        val_surf  = font_editor.render(val, True, (230, 230, 230))
        surface.blit(val_surf, (vx + 4, vy + 4))

        if is_active and editor_blink < 30:
            cur_x = vx + 4 + font_editor.size(val[:editor_cur_col])[0]
            pygame.draw.line(surface, (230, 230, 230),
                             (cur_x, vy + 3),
                             (cur_x, vy + vh - 3), 1)

    hint_y = editor_my + total_h - 18
    surface.blit(font.render("TAB next field   ESC close", True, (70, 70, 70)),
                 (editor_mx + ED_PAD, hint_y))

    hx = editor_pos[0] * cell_size
    hy = editor_pos[1] * cell_size
    pygame.draw.rect(surface, (200, 200, 200), (hx, hy, cell_size, cell_size), 2)


def editor_handle_key(event):
    global editor_active_field, editor_cur_col, editor_values, open_editor

    if not editor_fields:
        return

    if event.key == pygame.K_TAB:
        editor_active_field = (editor_active_field + 1) % len(editor_fields)
        field               = editor_fields[editor_active_field]
        editor_cur_col      = len(editor_values.get(field, ""))
        return

    if event.key == pygame.K_ESCAPE:
        close_editor()
        return

    if event.key == pygame.K_UP:
        editor_active_field = max(0, editor_active_field - 1)
        field               = editor_fields[editor_active_field]
        editor_cur_col      = len(editor_values.get(field, ""))
        return

    if event.key == pygame.K_DOWN:
        editor_active_field = min(len(editor_fields) - 1, editor_active_field + 1)
        field               = editor_fields[editor_active_field]
        editor_cur_col      = len(editor_values.get(field, ""))
        return

    field = editor_fields[editor_active_field]
    val   = editor_values.get(field, "")

    if event.key == pygame.K_LEFT:
        editor_cur_col = max(0, editor_cur_col - 1)

    elif event.key == pygame.K_RIGHT:
        editor_cur_col = min(len(val), editor_cur_col + 1)

    elif event.key == pygame.K_HOME:
        editor_cur_col = 0

    elif event.key == pygame.K_END:
        editor_cur_col = len(val)

    elif event.key == pygame.K_BACKSPACE:
        if editor_cur_col > 0:
            val                       = val[:editor_cur_col - 1] + val[editor_cur_col:]
            editor_values[field]      = val
            editor_cur_col           -= 1

    elif event.key == pygame.K_DELETE:
        if editor_cur_col < len(val):
            val                  = val[:editor_cur_col] + val[editor_cur_col + 1:]
            editor_values[field] = val

    elif event.key == pygame.K_SPACE:
        val                  = val[:editor_cur_col] + " " + val[editor_cur_col:]
        editor_values[field] = val
        editor_cur_col      += 1

    elif event.unicode and event.unicode.isprintable() and event.key not in (pygame.K_TAB, pygame.K_ESCAPE):
        val                  = val[:editor_cur_col] + event.unicode + val[editor_cur_col:]
        editor_values[field] = val
        editor_cur_col      += 1


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
                ed_w    = FIELD_COL_W + VALUE_COL_W + ED_PAD * 3
                total_h = ED_HEADER_H + ED_PAD + len(editor_fields) * ED_ROW_H + ED_PAD + 20
                mx_m, my_m = pygame.mouse.get_pos()
                if not (editor_mx <= mx_m <= editor_mx + ed_w and editor_my <= my_m <= editor_my + total_h):
                    close_editor()
                else:
                    rel_y = my_m - (editor_my + ED_HEADER_H + ED_PAD)
                    if rel_y >= 0:
                        clicked_row = rel_y // ED_ROW_H
                        if 0 <= clicked_row < len(editor_fields):
                            editor_active_field = clicked_row
                            field               = editor_fields[editor_active_field]
                            editor_cur_col      = len(editor_values.get(field, ""))
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