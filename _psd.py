"""Shared PSD I/O for Live2D: read layers as RGBA arrays and write a PSD that
Cubism Editor imports cleanly (no layer masks, every layer visible, groups = parts).

Layers live in memory in two forms:
  - cropped  (arr, top, left): only the opaque bounding box, like the PSD itself
  - full     H x W x 4 array : used for warping and mask arithmetic
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.join(HERE, "_vendor")
try:                                   # prefer an installed psd-tools (native wheel for this platform)
    import psd_tools  # noqa: F401
except ImportError:                    # fall back to the bundled copy (pure-Python RLE outside macOS arm64)
    if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
        sys.path.insert(0, _VENDOR)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from psd_tools import PSDImage  # noqa: E402
from psd_tools.api.layers import Group, PixelLayer  # noqa: E402
from psd_tools.constants import ChannelID  # noqa: E402


def load(path):
    """Return (W, H, layers, order).
    layers: name -> (arr, top, left); order: layer names bottom -> top.
    Names are stripped and lose a trailing '.png'. Groups are only traversed,
    not kept (the output groups come from the config)."""
    psd = PSDImage.open(path)
    W, H = psd.size
    layers, order = {}, []
    for l in psd.descendants():
        if l.is_group():
            continue
        name = clean_name(l.name)
        if name in layers:
            raise SystemExit(f"{path}: duplicate layer name {name!r}")
        layers[name] = (np.asarray(l.topil(apply_icc=False).convert("RGBA")), int(l.top), int(l.left))
        order.append(name)
    return W, H, layers, order


def clean_name(n):
    n = n.strip()
    if n.lower().endswith(".png"):
        n = n[:-4].strip()
    return n


def full(entry, W, H):
    """Cropped layer -> full-canvas H x W x 4 array."""
    arr, top, left = entry
    a = np.zeros((H, W, 4), np.uint8)
    h, w = arr.shape[:2]
    y0, x0 = max(top, 0), max(left, 0)
    y1, x1 = min(top + h, H), min(left + w, W)
    if y1 > y0 and x1 > x0:
        a[y0:y1, x0:x1] = arr[y0 - top:y1 - top, x0 - left:x1 - left]
    return a


def crop(a):
    """Full-canvas array -> (arr, top, left), cropped to alpha > 0."""
    ys, xs = np.where(a[..., 3] > 0)
    if len(ys) == 0:
        raise SystemExit("layer became fully transparent")
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return np.ascontiguousarray(a[y0:y1, x0:x1]), int(y0), int(x0)


def flat_names(groups):
    """All layer names in a groups spec, bottom -> top."""
    out = []

    def walk(items):
        for it in items:
            if isinstance(it, str):
                out.append(it)
            else:
                walk(it[1])
    for _, items in groups:
        walk(items)
    return out


def save(path, W, H, layers, groups, overwrite=False):
    """Write a Cubism-ready PSD.
    groups (bottom -> top): [[group_name, [layer_name | [subgroup_name, [...]], ...]], ...]
    PSD groups become Cubism parts. Every layer must appear in groups exactly once."""
    names = flat_names(groups)
    missing = set(layers) - set(names)
    extra = [n for n in names if n not in layers]
    dup = {n for n in names if names.count(n) > 1}
    if missing or extra or dup:
        raise SystemExit(f"groups do not match the layers: not in any group {sorted(missing)}, "
                         f"unknown {extra}, duplicated {sorted(dup)}")
    if os.path.exists(path) and not overwrite:
        raise SystemExit(f"{path} exists (pass --overwrite to replace it)")
    out = PSDImage.new("RGB", (W, H), depth=8)

    def build(parent, name, items):
        g = Group.new(parent, name)
        for it in items:
            if isinstance(it, str):
                arr, top, left = layers[it]
                lay = PixelLayer.fromarray(np.ascontiguousarray(arr), out, it, top=top, left=left)
                _no_mask(lay)
                lay.visible = True
                lay.opacity = 255
                lay.move_to_group(g)
            else:
                build(g, it[0], it[1])
        g.visible = True

    for name, items in groups:
        build(out, name, items)
    out.save(path)


def _no_mask(lay):
    """Cubism ignores layer masks. If psd-tools stored the alpha in a user mask,
    move it into the transparency channel and drop the mask."""
    ids = [c.id for c in lay._record.channel_info]
    if ChannelID.USER_LAYER_MASK not in ids:
        return
    ti, mi = ids.index(ChannelID.TRANSPARENCY_MASK), ids.index(ChannelID.USER_LAYER_MASK)
    lay._channels[ti] = lay._channels[mi]
    lay._record.channel_info[ti].length = lay._record.channel_info[mi].length
    keep = [i for i in range(len(ids)) if i != mi]
    lay._record.channel_info = [lay._record.channel_info[i] for i in keep]
    lay._channels[:] = [lay._channels[i] for i in keep]
    lay._record.mask_data = None


def composite(W, H, layers, order, hide=(), bg=(243, 227, 195)):
    """Alpha-correct composite for previews. (The PSD's embedded preview written by
    psd-tools has no alpha channel, so it shows white fringes; don't judge by it.)"""
    c = Image.new("RGBA", (W, H), tuple(bg) + (255,))
    for n in order:
        if n in hide:
            continue
        arr, top, left = layers[n]
        f = Image.new("RGBA", (W, H))
        f.paste(Image.fromarray(arr, "RGBA"), (left, top))
        c.alpha_composite(f)
    return c.convert("RGB")
