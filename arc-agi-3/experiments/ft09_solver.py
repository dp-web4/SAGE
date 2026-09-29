#!/usr/bin/env python3
"""
ft09 Color Puzzle Solver

Parses the ft09.py game source code and computes the click sequences
to solve each level.

Key mechanics:
- Grid of 3x3 tile sprites tagged "Hkx" (normal) or "NTi" (special)
- All tiles start at palette color index 0
- Clicking a tile cycles it to the next color in palette cwU
- elp pattern is always center-only [[0,0,0],[0,1,0],[0,0,0]] for all levels
- For NTi tiles: clicking also cycles neighbors at positions where
  the NTi sprite has magenta (color 6) pixels
- "bsT" goal sprites define constraints on neighboring tiles:
  - center pixel = target color nRq
  - surrounding pixel == 0 (black) → neighbor tile must be nRq
  - surrounding pixel != 0 → neighbor tile must NOT be nRq

Win condition: all bsT constraints satisfied simultaneously.

Display coordinate mapping:
  Camera is 16x16 rendering to 64x64 (4x upscale)
  scale = 16 / max(grid_w, grid_h)
  display_scale = scale * 4
  display_coord = (sprite_x + 1) * display_scale + offset
  where offset = (64 - grid_dim * display_scale) / 2

Usage:
    python ft09_solver.py [--level N] [--source PATH]
"""

import re
import ast
import sys
import argparse
from typing import Dict, List, Optional, Tuple, Set

GAME_SOURCE_DEFAULT = (
    "/Users/dennispalatov/repos/shared-context/environment_files/"
    "ft09/0d8bbf25/ft09.py"
)


# ---------------------------------------------------------------------------
# 1. Parse sprite definitions
# ---------------------------------------------------------------------------

def parse_source(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def extract_sprites(source: str) -> Dict[str, dict]:
    """Extract sprite name -> {pixels, tags} from sprites = {...} dict."""
    sprites = {}

    # Find the sprites section
    sprites_start = source.find('sprites = {')
    levels_start = source.find('\nlevels')
    sprites_section = source[sprites_start:levels_start]

    # Match each Sprite block - pixels use nested brackets
    pixel_pattern = re.compile(
        r'"(\w+)":\s*Sprite\(\s*pixels=(\[(?:\s*\[[^\]]*\],?\s*)*\]),',
        re.DOTALL,
    )

    # For each sprite, find its full block to extract tags
    for m in pixel_pattern.finditer(sprites_section):
        name = m.group(1)
        pixels_str = m.group(2)
        pixels = ast.literal_eval(pixels_str)

        # Find tags in the rest of this Sprite() block
        # Look from end of pixels match to next closing paren
        block_start = m.end()
        # Find the closing ),  of this Sprite
        paren_depth = 1
        pos = sprites_section.find('Sprite(', m.start()) + len('Sprite(')
        # Actually simpler: just search forward from the match for tags=
        block_end = sprites_section.find('\n    "', block_start)
        if block_end == -1:
            block_end = len(sprites_section)
        block_rest = sprites_section[block_start:block_end]

        tags_match = re.search(r'tags=(\[[^\]]*\])', block_rest)
        tags = ast.literal_eval(tags_match.group(1)) if tags_match else []

        sprites[name] = {"pixels": pixels, "tags": tags}

    return sprites


def extract_levels(source: str, sprites: Dict[str, dict]) -> List[dict]:
    """Extract level data: sprites with positions, grid_size, cwU, elp."""
    levels = []

    # Find level blocks
    level_pattern = re.compile(
        r'#\s*(\w+)\s*\n\s*Level\(\s*sprites=\[(.*?)\],\s*'
        r'grid_size=\((\d+),\s*(\d+)\),\s*'
        r'data=\{(.*?)\},\s*'
        r'name="(\w+)",?\s*\)',
        re.DOTALL,
    )

    for m in level_pattern.finditer(source):
        level_name = m.group(6)
        sprites_block = m.group(2)
        gw, gh = int(m.group(3)), int(m.group(4))
        data_block = m.group(5)

        # Parse data
        cwU_match = re.search(r'"cwU":\s*(\[[^\]]+\])', data_block)
        elp_match = re.search(r'"elp":\s*(\[\[.*?\]\])', data_block, re.DOTALL)
        cwU = ast.literal_eval(cwU_match.group(1)) if cwU_match else [9, 8]
        elp = ast.literal_eval(elp_match.group(1)) if elp_match else [[0, 0, 0], [0, 1, 0], [0, 0, 0]]

        # Parse sprite placements
        placement_pattern = re.compile(
            r'sprites\["(\w+)"\]\.clone\(\)\.set_position\((\d+),\s*(\d+)\)'
        )

        level_sprites = []
        for sp in placement_pattern.finditer(sprites_block):
            sname = sp.group(1)
            sx, sy = int(sp.group(2)), int(sp.group(3))
            level_sprites.append((sname, sx, sy))

        # Also handle sprites without set_position (just clone())
        no_pos_pattern = re.compile(
            r'sprites\["(\w+)"\]\.clone\(\)(?!\.set_position)'
        )
        for sp in no_pos_pattern.finditer(sprites_block):
            sname = sp.group(1)
            level_sprites.append((sname, 0, 0))

        levels.append({
            "name": level_name,
            "grid_size": (gw, gh),
            "cwU": cwU,
            "elp": elp,
            "sprites": level_sprites,
        })

    return levels


# ---------------------------------------------------------------------------
# 2. Solve each level
# ---------------------------------------------------------------------------

def solve_level(level: dict, sprite_defs: Dict[str, dict]) -> dict:
    """
    Solve a single level.

    Returns dict with level info and list of click display coordinates.
    """
    cwU = level["cwU"]
    gw, gh = level["grid_size"]

    # Classify sprites in this level
    hkx_tiles = []   # (x, y) - normal clickable tiles
    nti_tiles = []    # (sprite_name, x, y) - special NTi tiles
    bst_goals = []    # (sprite_name, x, y, pixels) - goal sprites

    for sname, sx, sy in level["sprites"]:
        sdef = sprite_defs.get(sname)
        if not sdef:
            continue
        tags = sdef["tags"]
        if "Hkx" in tags:
            hkx_tiles.append((sx, sy))
        elif "NTi" in tags:
            nti_tiles.append((sname, sx, sy))
        elif "bsT" in tags:
            bst_goals.append((sname, sx, sy, sdef["pixels"]))

    # Build tile lookup: position -> current color index
    # All Hkx tiles start at cwU[0]
    # NTi tiles also start at cwU[0] (non-magenta pixels remapped)
    tile_positions = {}  # (x, y) -> initial_color
    for (x, y) in hkx_tiles:
        tile_positions[(x, y)] = cwU[0]
    for (sname, x, y) in nti_tiles:
        tile_positions[(x, y)] = cwU[0]  # center pixel remapped to cwU[0]

    # Determine target color for each tile from bsT constraints
    # For each bsT goal, examine its 3x3 pixel pattern
    # Neighbor offsets mapping pixel position to world offset
    neighbor_offsets = [
        (0, 0, -4, -4),   # pixels[0][0] -> (x-4, y-4)
        (0, 1,  0, -4),   # pixels[0][1] -> (x,   y-4)
        (0, 2,  4, -4),   # pixels[0][2] -> (x+4, y-4)
        (1, 0, -4,  0),   # pixels[1][0] -> (x-4, y)
        # (1, 1) is the center = target color nRq
        (1, 2,  4,  0),   # pixels[1][2] -> (x+4, y)
        (2, 0, -4,  4),   # pixels[2][0] -> (x-4, y+4)
        (2, 1,  0,  4),   # pixels[2][1] -> (x,   y+4)
        (2, 2,  4,  4),   # pixels[2][2] -> (x+4, y+4)
    ]

    # Collect constraints per tile: positive ("must be X") and negative ("must not be X")
    tile_must = {}     # (x, y) -> set of required colors (from black pixels)
    tile_must_not = {} # (x, y) -> set of forbidden colors (from non-black pixels)

    for sname, gx, gy, pixels in bst_goals:
        nRq = pixels[1][1]  # target color (center pixel)

        for pr, pc, dx, dy in neighbor_offsets:
            tx, ty = gx + dx, gy + dy
            if (tx, ty) not in tile_positions:
                continue

            pixel_val = pixels[pr][pc]
            if pixel_val == 0:
                # Black pixel: neighbor MUST be nRq
                tile_must.setdefault((tx, ty), set()).add(nRq)
            else:
                # Non-black: neighbor must NOT be nRq
                tile_must_not.setdefault((tx, ty), set()).add(nRq)

    # Resolve constraints to a single target color per tile
    tile_targets = {}  # (x, y) -> target_color

    all_tile_positions = set(tile_positions.keys())
    constrained_tiles = set(tile_must.keys()) | set(tile_must_not.keys())

    for pos in constrained_tiles:
        must = tile_must.get(pos, set())
        must_not = tile_must_not.get(pos, set())

        if must:
            # Positive constraints pin the color exactly
            # (All "must" values should agree; if not, the puzzle is inconsistent)
            target = list(must)[0]
            tile_targets[pos] = target
        else:
            # Only negative constraints: pick a valid color
            candidates = [c for c in cwU if c not in must_not]
            if len(candidates) == 1:
                tile_targets[pos] = candidates[0]
            elif len(candidates) > 1:
                # Prefer the initial color if valid (fewest clicks = 0)
                if cwU[0] in candidates:
                    tile_targets[pos] = cwU[0]
                else:
                    # Pick the candidate requiring fewest clicks from initial
                    initial_idx = 0
                    best = None
                    best_clicks = len(cwU) + 1
                    for c in candidates:
                        c_idx = cwU.index(c)
                        n = (c_idx - initial_idx) % len(cwU)
                        if n < best_clicks:
                            best_clicks = n
                            best = c
                    tile_targets[pos] = best
            else:
                # No valid color - puzzle is inconsistent
                tile_targets[pos] = cwU[0]

    # For tiles with no constraints from any bsT goal, they should stay initial
    # (They must already satisfy all constraints, which they trivially do
    # since no bsT checks them)

    # Now determine clicks needed
    # For NTi tiles, clicking them also affects neighbors (positions with magenta pixels)
    # But since elp is center-only for ALL levels, clicking an Hkx tile only affects itself
    # For NTi tiles: clicking cycles self AND neighbors at magenta (6) positions

    # First, let's check if there are NTi tiles in this level
    # If so, we need to solve a system of equations (clicking NTi affects multiple tiles)
    if nti_tiles:
        return solve_with_nti(level, sprite_defs, cwU, tile_positions, tile_targets,
                              hkx_tiles, nti_tiles, bst_goals)

    # Simple case: no NTi tiles, each click only affects one tile
    clicks = []
    palette_size = len(cwU)

    for pos, target in tile_targets.items():
        initial = cwU[0]
        if target == initial:
            continue  # already correct

        initial_idx = cwU.index(initial)
        target_idx = cwU.index(target)
        num_clicks = (target_idx - initial_idx) % palette_size

        for _ in range(num_clicks):
            clicks.append(pos)

    # Compute display coordinates
    scale = 16.0 / max(gw, gh)
    display_scale = scale * 4
    offset_x = (64 - gw * display_scale) / 2
    offset_y = (64 - gh * display_scale) / 2

    display_clicks = []
    for (sx, sy) in clicks:
        # Click center of 3x3 sprite: pixel [1][1] is at (sx+1, sy+1)
        dx = int((sx + 1) * display_scale + offset_x)
        dy = int((sy + 1) * display_scale + offset_y)
        display_clicks.append((dx, dy))

    return {
        "name": level["name"],
        "num_clicks": len(display_clicks),
        "clicks": display_clicks,
        "cwU": cwU,
        "num_hkx": len(hkx_tiles),
        "num_nti": len(nti_tiles),
        "num_bst": len(bst_goals),
    }


def solve_with_nti(level, sprite_defs, cwU, tile_positions, tile_targets,
                   hkx_tiles, nti_tiles, bst_goals):
    """
    Solve a level that has NTi tiles.

    When an NTi tile is clicked:
    - The center (self) always cycles
    - Any position in the NTi sprite's 3x3 pixels that has color 6 (magenta)
      also cycles the tile at that offset (*4)

    When an Hkx tile is clicked: only self cycles (elp is center-only).

    We need to find click counts for each tile such that final colors match targets.
    This is a system of linear equations mod len(cwU).
    """
    gw, gh = level["grid_size"]
    palette_size = len(cwU)

    # Build the effect matrix: for each clickable tile, what tiles does it affect?
    # All positions (both Hkx and NTi)
    all_positions = list(tile_positions.keys())
    pos_index = {pos: i for i, pos in enumerate(all_positions)}
    n = len(all_positions)

    # NTi positions set for quick lookup
    nti_pos_set = {(x, y) for (_, x, y) in nti_tiles}
    nti_sprite_map = {(x, y): sname for (sname, x, y) in nti_tiles}

    # Effect matrix: effect[i][j] = 1 if clicking tile j affects tile i
    effect = [[0] * n for _ in range(n)]

    for j, pos in enumerate(all_positions):
        # Clicking any tile always affects itself
        effect[j][j] = 1

        # If it's an NTi tile, also affects neighbors at magenta positions
        if pos in nti_pos_set:
            sname = nti_sprite_map[pos]
            pixels = sprite_defs[sname]["pixels"]
            offsets = [
                (-1, -1), (0, -1), (1, -1),
                (-1,  0), (0,  0), (1,  0),
                (-1,  1), (0,  1), (1,  1),
            ]
            for row in range(3):
                for col in range(3):
                    if pixels[row][col] == 6:
                        dx = (col - 1) * 4
                        dy = (row - 1) * 4
                        target_pos = (pos[0] + dx, pos[1] + dy)
                        if target_pos in pos_index:
                            i = pos_index[target_pos]
                            effect[i][j] = 1

    # Target vector: how many clicks needed for each tile (mod palette_size)
    target_clicks = [0] * n
    for i, pos in enumerate(all_positions):
        if pos in tile_targets:
            target = tile_targets[pos]
            initial_idx = 0  # all start at cwU[0]
            target_idx = cwU.index(target)
            target_clicks[i] = (target_idx - initial_idx) % palette_size
        # else: target_clicks[i] = 0 (stay as-is)

    # Solve: effect * click_vector ≡ target_clicks (mod palette_size)
    # Use brute force for small palette sizes (2 or 3) since tiles are independent
    # except for NTi cross-effects

    # For palette_size=2 (binary), this is a system of linear equations over GF(2)
    # For palette_size=3, over Z/3Z
    # Use Gaussian elimination mod palette_size

    click_vector = gaussian_elimination_mod(effect, target_clicks, palette_size, n)

    if click_vector is None:
        # Fallback: try brute force for small cases
        print(f"  WARNING: Gaussian elimination failed, no solution found")
        click_vector = [0] * n

    # Generate click list
    clicks = []
    for j, pos in enumerate(all_positions):
        for _ in range(click_vector[j]):
            clicks.append(pos)

    # Compute display coordinates
    scale = 16.0 / max(gw, gh)
    display_scale = scale * 4
    offset_x = (64 - gw * display_scale) / 2
    offset_y = (64 - gh * display_scale) / 2

    display_clicks = []
    for (sx, sy) in clicks:
        dx = int((sx + 1) * display_scale + offset_x)
        dy = int((sy + 1) * display_scale + offset_y)
        display_clicks.append((dx, dy))

    return {
        "name": level["name"],
        "num_clicks": len(display_clicks),
        "clicks": display_clicks,
        "cwU": cwU,
        "num_hkx": len(hkx_tiles),
        "num_nti": len(nti_tiles),
        "num_bst": len(bst_goals),
    }


def gaussian_elimination_mod(A, b, mod, n):
    """
    Solve A * x ≡ b (mod `mod`) using Gaussian elimination.
    A is n x n, b is length n.
    Returns x as list of ints, or None if no solution.
    """
    # Augmented matrix
    aug = [row[:] + [b[i]] for i, row in enumerate(A)]

    pivot_col = 0
    for row in range(n):
        if pivot_col >= n:
            break
        # Find pivot
        found = False
        for i in range(row, n):
            if aug[i][pivot_col] % mod != 0:
                aug[row], aug[i] = aug[i], aug[row]
                found = True
                break
        if not found:
            pivot_col += 1
            # Try this row again with next column
            continue

        # Scale pivot row so pivot = 1
        inv = mod_inverse(aug[row][pivot_col], mod)
        if inv is None:
            pivot_col += 1
            continue
        for j in range(n + 1):
            aug[row][j] = (aug[row][j] * inv) % mod

        # Eliminate other rows
        for i in range(n):
            if i != row and aug[i][pivot_col] % mod != 0:
                factor = aug[i][pivot_col]
                for j in range(n + 1):
                    aug[i][j] = (aug[i][j] - factor * aug[row][j]) % mod

        pivot_col += 1

    # Extract solution
    x = [0] * n
    for i in range(n):
        # Find pivot column for this row
        pivot = -1
        for j in range(n):
            if aug[i][j] % mod != 0:
                pivot = j
                break
        if pivot >= 0:
            x[pivot] = aug[i][n] % mod

    # Verify solution
    for i in range(n):
        total = sum(A[i][j] * x[j] for j in range(n)) % mod
        if total != b[i] % mod:
            return None

    return x


def mod_inverse(a, mod):
    """Modular inverse of a mod `mod` using extended Euclidean algorithm."""
    a = a % mod
    if a == 0:
        return None
    for i in range(1, mod):
        if (a * i) % mod == 1:
            return i
    return None


# ---------------------------------------------------------------------------
# 3. Verification
# ---------------------------------------------------------------------------

def verify_solution(level: dict, sprite_defs: Dict[str, dict], world_clicks: List[Tuple[int, int]]) -> bool:
    """
    Simulate clicks and verify the win condition (cgj) is met.

    world_clicks: list of (sprite_x, sprite_y) positions to click.
    Returns True if solution is valid.
    """
    cwU = level["cwU"]
    palette_size = len(cwU)

    # Build tile state: (x, y) -> current color
    tile_state = {}
    tile_type = {}  # (x, y) -> "Hkx" or "NTi"
    nti_pixels = {}  # (x, y) -> original pixels (for magenta pattern)

    for sname, sx, sy in level["sprites"]:
        sdef = sprite_defs.get(sname)
        if not sdef:
            continue
        tags = sdef["tags"]
        if "Hkx" in tags:
            tile_state[(sx, sy)] = cwU[0]
            tile_type[(sx, sy)] = "Hkx"
        elif "NTi" in tags:
            tile_state[(sx, sy)] = cwU[0]
            tile_type[(sx, sy)] = "NTi"
            nti_pixels[(sx, sy)] = sdef["pixels"]

    # Simulate each click
    for cx, cy in world_clicks:
        if (cx, cy) not in tile_state:
            print(f"  VERIFY ERROR: click at ({cx},{cy}) is not a tile")
            return False

        # Determine effect pattern
        if tile_type[(cx, cy)] == "NTi":
            # Build effect from magenta pixels
            pixels = nti_pixels[(cx, cy)]
            eHl = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
            for j in range(3):
                for i in range(3):
                    if pixels[j][i] == 6:
                        eHl[j][i] = 1
        else:
            eHl = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]

        # Apply effect
        GBS = [
            [(-1, -1), (0, -1), (1, -1)],
            [(-1,  0), (0,  0), (1,  0)],
            [(-1,  1), (0,  1), (1,  1)],
        ]

        for i in range(3):
            for j in range(3):
                if eHl[j][i] == 1:
                    ybc, lga = GBS[j][i]
                    target_pos = (cx + ybc * 4, cy + lga * 4)
                    if target_pos in tile_state:
                        cur_idx = cwU.index(tile_state[target_pos])
                        new_idx = (cur_idx + 1) % palette_size
                        tile_state[target_pos] = cwU[new_idx]

    # Check win condition (cgj)
    neighbor_offsets = [
        (0, 0, -4, -4),
        (0, 1,  0, -4),
        (0, 2,  4, -4),
        (1, 0, -4,  0),
        (1, 2,  4,  0),
        (2, 0, -4,  4),
        (2, 1,  0,  4),
        (2, 2,  4,  4),
    ]

    for sname, gx, gy in level["sprites"]:
        sdef = sprite_defs.get(sname)
        if not sdef or "bsT" not in sdef["tags"]:
            continue
        pixels = sdef["pixels"]
        nRq = pixels[1][1]

        for pr, pc, dx, dy in neighbor_offsets:
            tx, ty = gx + dx, gy + dy
            if (tx, ty) not in tile_state:
                continue

            pixel_val = pixels[pr][pc]
            HJd = pixel_val == 0
            tile_color = tile_state[(tx, ty)]

            if HJd:
                if tile_color != nRq:
                    print(f"  VERIFY FAIL: bsT {sname} at ({gx},{gy}): "
                          f"tile ({tx},{ty})={tile_color} should be {nRq}")
                    return False
            else:
                if tile_color == nRq:
                    print(f"  VERIFY FAIL: bsT {sname} at ({gx},{gy}): "
                          f"tile ({tx},{ty})={tile_color} should NOT be {nRq}")
                    return False

    return True


# ---------------------------------------------------------------------------
# 4. Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ft09 Color Puzzle Solver")
    parser.add_argument("--level", type=int, default=None, help="Solve specific level (1-6)")
    parser.add_argument("--source", type=str, default=GAME_SOURCE_DEFAULT, help="Path to ft09.py")
    parser.add_argument("--verbose", action="store_true", help="Show detailed analysis")
    args = parser.parse_args()

    source = parse_source(args.source)
    sprite_defs = extract_sprites(source)
    levels = extract_levels(source, sprite_defs)

    if not levels:
        print("ERROR: No levels found in source")
        sys.exit(1)

    print(f"Parsed {len(sprite_defs)} sprites, {len(levels)} levels\n")

    if args.level is not None:
        if args.level < 1 or args.level > len(levels):
            print(f"ERROR: Level {args.level} not found (1-{len(levels)})")
            sys.exit(1)
        level_indices = [args.level - 1]
    else:
        level_indices = range(len(levels))

    all_pass = True
    for idx in level_indices:
        level = levels[idx]
        result = solve_level(level, sprite_defs)

        if args.verbose:
            print(f"Level {idx + 1} ({result['name']}): palette={result['cwU']}, "
                  f"tiles={result['num_hkx']} Hkx + {result['num_nti']} NTi, "
                  f"goals={result['num_bst']}")

        click_strs = [f"click({x},{y})" for x, y in result["clicks"]]
        print(f"Level {idx + 1}: {result['num_clicks']} clicks")
        if click_strs:
            print(f"  {' '.join(click_strs)}")

        # Verify by converting display clicks back to world clicks
        gw, gh = level["grid_size"]
        scale = 16.0 / max(gw, gh)
        display_scale = scale * 4
        offset_x = (64 - gw * display_scale) / 2
        offset_y = (64 - gh * display_scale) / 2

        world_clicks = []
        for dx, dy in result["clicks"]:
            # Reverse: world = (display - offset) / display_scale - 1
            wx = round((dx - offset_x) / display_scale - 1)
            wy = round((dy - offset_y) / display_scale - 1)
            world_clicks.append((wx, wy))

        ok = verify_solution(level, sprite_defs, world_clicks)
        if ok:
            print(f"  VERIFIED OK")
        else:
            print(f"  VERIFICATION FAILED")
            all_pass = False
        print()

    if all_pass:
        print("All levels verified successfully.")
    else:
        print("WARNING: Some levels failed verification.")
        sys.exit(1)


if __name__ == "__main__":
    main()
