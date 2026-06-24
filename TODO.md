# TODO

## Equalize Edge Lengths

- **Revisit loop redistribution** — current implementation redistributes vertices
  along the original polyline (`perimeter / N`), preserving path shape but
  targeting an average length, not the active edge's length. Consider whether
  a "To Circle"-style projection (regular polygon fit) would be more useful for
  loops in practice.

## Feature gaps

- **Distribute Vertices** (`alec.distribute_vertices`) only handles open chains.
  Closed loops and branching selections abort with a warning. Could be extended
  to match the loop-detection logic now used in Equalize.

- **Set Edge Angle** — `flip_side` is documented as ignored in modal mode
  (non-modal only). Either implement it or remove the property from the modal path.

## Silent failures / missing reports

- `extract_and_solidify`: returns `FINISHED` when the duplicate+separate step
  produces no new object; should report a WARNING.

- `distribute.py` `cancel()` is never called — dead cancel path that never
  restores the snapshot.

- `fillet_chamfer.py` `_apply_fillet_if_ready` / `_apply_arc` return `False`
  on failure with no `report()`; pressing Enter/LMB can silently do nothing.

## Code quality

- Multiple `except Exception: pass` in `trim_extend.py`, `draw_mesh_edges.py`,
  `camera_tools.py`, and `fillet_chamfer.py` swallow status-bar and bmesh
  errors. At minimum add a `print` so failures are visible in the System Console.

- `modules/edit_mesh_helpers.py` line ~358: bare `except:` in
  `poll_two_edges_in_select_history` hides all poll failures.
