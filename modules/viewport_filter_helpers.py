"""Shared constants for viewport object-type visibility/selectability filters."""

VIEWPORT_TYPE_FILTERS = (
    ("mesh",   'MESH_DATA'),
    ("curves", 'OUTLINER_OB_CURVE'),
    ("empty",  'EMPTY_DATA'),
    ("light",  'LIGHT_DATA'),
    ("camera", 'CAMERA_DATA'),
)

VIEWPORT_TYPE_FILTER_NAMES = tuple(name for name, _ in VIEWPORT_TYPE_FILTERS)
