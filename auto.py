import pygame
from grid import Grid, cell_scripts, cell_map, SCRIPTABLE

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
font          = pygame.font.Font(None, 24)
font_large    = pygame.font.Font(None, 32)

running         = True
open_editor     = False
sim_running     = False
t               = 0
mx, my          = 0, 0
sx, sy          = 0, 0
equipped        = 1
text_surface    = font.render("", True, (255, 255, 255))
text_rect       = text_surface.get_rect()
clicked_buttons = []

file_mode   = None
file_input  = ""

while running:
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
                text_surface = font.render(label, True, (255, 255, 255))
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
        screen.blit(font_large.render(label, True, (200, 200, 200)), (bx + 16, by + 12))
        screen.blit(font_large.render(file_input + "|", True, (255, 255, 255)), (bx + 16, by + 52))

    elif open_editor:
        pygame.draw.rect(screen, (60, 60, 60), (mx, my, 200, 200))
        pygame.draw.rect(screen, (200, 200, 200), (sx, sy, cell_size, cell_size), 2)
        screen.blit(text_surface, (mx + 8, my + 8), text_rect)
    else:
        pygame.draw.rect(screen, cell_map[equipped][1], (mp[0], mp[1], cell_size, cell_size), 2)

    status = (
        f"[SPACE] {'STOP' if sim_running else 'START'}  |  "
        f"equipped: [{equipped}] {cell_map[equipped][0]}  |  "
        f"[</> arrows] select  |  [TAB] edit script  |  "
        f"[S] save  [L] load"
    )
    screen.blit(font.render(status, True, (200, 200, 200)), (8, height - 24))

    pygame.display.update()
    clock.tick(60)

pygame.quit()
quit()