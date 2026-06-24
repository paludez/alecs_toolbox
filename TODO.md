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
