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

PANEL_W = 340


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


def get_outputs(pos, type_):
    if type_ == "Switch":
        sw = grid.switch_data.get(pos)
        return sw["outputs"] if sw else []
    elif type_ == "Sensor":
        sd = grid.sensor_data.get(pos)
        return sd["outputs"] if sd else []
    elif type_ in ("AND", "OR", "NOT", "XOR"):
        gd = grid.gate_data.get(pos)
        return gd["outputs"] if gd else []
    elif type_ == "Button":
        bd = grid.button_data.get(pos)
        return bd["outputs"] if bd else []
    elif type_ == "Generator":
        gd = grid.generator_data.get(pos)
        return gd["inputs"] if gd else []
    elif type_ == "Destroyer":
        dd = grid.destroyer_data.get(pos)
        return dd["inputs"] if dd else []
    return []


def get_inputs(pos, type_):
    if type_ == "Switch":
        sw = grid.switch_data.get(pos)
        return sw["inputs"] if sw else []
    elif type_ in ("AND", "OR", "NOT", "XOR"):
        gd = grid.gate_data.get(pos)
        return gd["inputs"] if gd else []
    elif type_ == "Engine":
        ed = grid.engine_data.get(pos)
        return ed["inputs"] if ed else []
    elif type_ == "Destroyer":
        dd = grid.destroyer_data.get(pos)
        return dd["inputs"] if dd else []
    elif type_ == "Generator":
        gd = grid.generator_data.get(pos)
        return gd["inputs"] if gd else []
    return []


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

    chains = []

    emitters = []
    for pos, bd in grid.button_data.items():
        emitters.append(("Button", pos, bd["outputs"]))
    for pos, sd in grid.sensor_data.items():
        emitters.append(("Sensor", pos, sd["outputs"]))
    for pos, sw in grid.switch_data.items():
        emitters.append(("Switch", pos, sw["outputs"]))
    for pos, gd in grid.gate_data.items():
        emitters.append((gd["type"], pos, gd["outputs"]))

    seen_chains = set()

    for etype, epos, eouts in emitters:
        for sig in eouts:
            receivers = sig_to_receivers.get(sig, [])
            for rtype, rpos in receivers:
                key = (epos, sig, rpos)
                if key in seen_chains:
                    continue
                seen_chains.add(key)
                chains.append((etype, epos, sig, rtype, rpos))

    return chains


def draw_panel(surface, chains):
    pw = PANEL_W
    ph = height
    panel = pygame.Surface((pw, ph))
    panel.fill((30, 30, 30))
    pygame.draw.line(panel, (80, 80, 80), (0, 0), (0, ph), 1)

    y = 8
    title = font_ui.render("signal flow  [P]", True, (180, 180, 180))
    panel.blit(title, (10, y))
    y += 28
    pygame.draw.line(panel, (60, 60, 60), (0, y), (pw, y), 1)
    y += 8

    if not sim_running:
        msg = font.render("start sim to see live state", True, (100, 100, 100))
        panel.blit(msg, (10, y))
    else:
        if not chains:
            msg = font.render("no signal connections found", True, (100, 100, 100))
            panel.blit(msg, (10, y))
        else:
            prev_sig = None
            for etype, epos, sig, rtype, rpos in chains:
                if sig != prev_sig:
                    if prev_sig is not None:
                        y += 4
                        pygame.draw.line(panel, (50, 50, 50), (0, y), (pw, y), 1)
                        y += 6
                    sig_surf = font.render(f"signal: {sig}", True, (120, 120, 180))
                    panel.blit(sig_surf, (10, y))
                    y += 16
                    prev_sig = sig

                estate = get_cell_state(epos, etype)
                rstate = get_cell_state(rpos, rtype)

                ec = (0, 220, 0) if estate == 1 else (180, 60, 60)
                rc = (0, 220, 0) if rstate == 1 else (180, 60, 60)

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


while running:
    effective_width = width - PANEL_W if show_panel else width
    screen.fill((0, 0, 0))

    if sim_running and not open_editor:
        t = (t + 1) % 10
    else:
        t = 0

    tick = (t == 0) and sim_running and not open_editor

    mp = snap_to_grid(pygame.mouse.get_pos(), cell_size)

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
                running = False

            elif event.key == pygame.K_p and not open_editor and not file_mode:
                show_panel = not show_panel

            elif event.key == pygame.K_s and not open_editor and not sim_running:
                file_mode  = "save"
                file_input = ""

            elif event.key == pygame.K_l and not open_editor and not sim_running:
                file_mode  = "load"
                file_input = ""

            elif event.key == pygame.K_SPACE and not open_editor:
                sim_running = not sim_running
                if sim_running:
                    grid.compile_scripts()

            elif event.key == pygame.K_LEFT:
                equipped = max(0, equipped - 1)
            elif event.key == pygame.K_RIGHT:
                equipped = min(len(cell_map) - 1, equipped + 1)

            elif event.key == pygame.K_TAB:
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
                cx, cy = mp[0] // cell_size, mp[1] // cell_size
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
    else:
        pygame.draw.rect(screen, cell_map[equipped][1], (mp[0], mp[1], cell_size, cell_size), 2)

    status = (
        f"[SPACE] {'STOP' if sim_running else 'START'}  |  "
        f"equipped: [{equipped}] {cell_map[equipped][0]}  |  "
        f"[</> arrows] select  |  [TAB] script  |  "
        f"[S] save  [L] load  |  [P] panel"
    )
    screen.blit(font_ui.render(status, True, (200, 200, 200)), (8, height - 24))

    pygame.display.update()
    clock.tick(60)

pygame.quit()
quit()