import pygame
from grid import Grid, cell_scripts, cell_map, SCRIPTABLE
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

running         = True
open_editor     = False
sim_running     = False
show_panel      = False
t               = 0
mx, my          = 0, 0
sx, sy          = 0, 0
equipped        = 1
text_surface    = font_ui.render("", True, (255, 255, 255))
text_rect       = text_surface.get_rect()
clicked_buttons = []
file_mode       = None
file_input      = ""

select_mode     = False
copy_mode       = False
paste_mode      = False
selecting       = False
select_start    = None
select_end      = None
selected_cells  = set()
clipboard       = []

PANEL_W = 340


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
    y     = 8
    title = font_ui.render("signal flow  [P]", True, (180, 180, 180))
    panel.blit(title, (10, y))
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
        if not grid.is_empty(cx, cy):
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

    tick = (t == 0) and sim_running and not open_editor
    mp   = snap_to_grid(pygame.mouse.get_pos(), cell_size)
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

            if event.key == pygame.K_ESCAPE:
                if select_mode or copy_mode or paste_mode:
                    select_mode    = False
                    copy_mode      = False
                    paste_mode     = False
                    selecting      = False
                    select_start   = None
                    select_end     = None
                    selected_cells = set()
                else:
                    running = False

            elif event.key == pygame.K_x and not open_editor and not file_mode:
                select_mode    = True
                copy_mode      = False
                paste_mode     = False
                selecting      = False
                select_start   = None
                select_end     = None
                selected_cells = set()

            elif event.key == pygame.K_c and not open_editor and not file_mode:
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

            elif event.key == pygame.K_v and not open_editor and not file_mode and clipboard:
                paste_mode  = True
                copy_mode   = False
                select_mode = False

            elif event.key == pygame.K_BACKSPACE and select_mode and selected_cells:
                do_delete_selected()
                selected_cells = set()
                select_mode    = False

            elif event.key == pygame.K_p and not open_editor:
                show_panel = not show_panel

            elif event.key == pygame.K_s and not open_editor and not sim_running and not select_mode:
                file_mode  = "save"
                file_input = ""

            elif event.key == pygame.K_l and not open_editor and not sim_running and not select_mode:
                file_mode  = "load"
                file_input = ""

            elif event.key == pygame.K_SPACE and not open_editor:
                sim_running = not sim_running
                if sim_running:
                    grid.compile_scripts()

            elif event.key == pygame.K_LEFT and not select_mode and not copy_mode and not paste_mode:
                equipped = max(0, equipped - 1)
            elif event.key == pygame.K_RIGHT and not select_mode and not copy_mode and not paste_mode:
                equipped = min(len(cell_map) - 1, equipped + 1)

            elif event.key == pygame.K_TAB and not select_mode and not copy_mode and not paste_mode:
                cx, cy = mp[0] // cell_size, mp[1] // cell_size
                if not open_editor and grid.get_cell(cx, cy)[0] in SCRIPTABLE:
                    open_editor = True
                    sx, sy      = mp
                    mx, my      = sx + 20, sy
                    if mx > width - 210:
                        mx -= 230
                    if my > height - 210:
                        my -= 210
                else:
                    open_editor = False

            if open_editor:
                key  = pygame.key.get_pressed()
                pos  = (sx // cell_size, sy // cell_size)
                text = cell_scripts.get(pos, "")
                if key[pygame.K_BACKSPACE]:
                    text = text[:-1]
                elif key[pygame.K_RETURN]:
                    text += "\n"
                elif key[pygame.K_SPACE]:
                    text += " "
                elif event.key in (pygame.K_TAB, pygame.K_ESCAPE):
                    pass
                else:
                    text += event.unicode
                cell_scripts[pos] = text
                label        = f"{grid.get_cell(pos[0], pos[1])[0]} [{grid.get_cell(pos[0], pos[1])[1]}]\n{text}"
                text_surface = font_ui.render(label, True, (255, 255, 255))
                text_rect    = text_surface.get_rect()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if not open_editor and not file_mode:
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
                        else:
                            cell_scripts[(cx, cy)] = ""
                            grid.set_cell(cx, cy, equipped)
                    elif event.button == 3:
                        cell_scripts[(cx, cy)] = ""
                        grid.set_cell(cx, cy, 0)

        elif event.type == pygame.MOUSEBUTTONUP:
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

    if tick:
        grid.tick(clicked_buttons if clicked_buttons else None)
        clicked_buttons = []

    grid.draw(screen)

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

    if (select_mode or copy_mode) and select_start and select_end:
        x0 = min(select_start[0], select_end[0]) * cell_size
        y0 = min(select_start[1], select_end[1]) * cell_size
        x1 = (max(select_start[0], select_end[0]) + 1) * cell_size
        y1 = (max(select_start[1], select_end[1]) + 1) * cell_size
        col      = (100, 180, 255) if copy_mode else (255, 200, 80)
        sel_surf = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
        sel_surf.fill((*col, 50))
        screen.blit(sel_surf, (x0, y0))
        pygame.draw.rect(screen, col, (x0, y0, x1 - x0, y1 - y0), 1)

    if selected_cells and select_mode:
        for cx, cy in selected_cells:
            px, py   = cx * cell_size, cy * cell_size
            sel_surf = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
            sel_surf.fill((255, 200, 80, 60))
            screen.blit(sel_surf, (px, py))
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
            border_color = (0, 220, 0) if valid else (220, 60, 60)
            pygame.draw.rect(screen, border_color, (px, py, cell_size, cell_size), 1)

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
    elif open_editor:
        pygame.draw.rect(screen, (60, 60, 60), (mx, my, 200, 200))
        pygame.draw.rect(screen, (200, 200, 200), (sx, sy, cell_size, cell_size), 2)
        screen.blit(text_surface, (mx + 8, my + 8), text_rect)
    elif select_mode:
        if selected_cells:
            msg = font_ui.render(f"select mode — {len(selected_cells)} cells  [C] copy  [DEL] delete  [ESC] cancel", True, (255, 200, 80))
        else:
            msg = font_ui.render("select mode — click and drag to select  [ESC] cancel", True, (255, 200, 80))
        screen.blit(msg, (8, height - 24))
    elif copy_mode:
        screen.blit(font_ui.render("copy mode — click and drag to select region  [ESC] cancel", True, (100, 180, 255)), (8, height - 24))
    elif paste_mode:
        color = (0, 220, 0) if can_paste(mcx, mcy) else (220, 60, 60)
        screen.blit(font_ui.render("paste mode — click to place  right click to cancel", True, color), (8, height - 24))
    else:
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