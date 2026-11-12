#!/usr/bin/env python3
"""Turn a flat, layered character PSD into a Cubism-ready PSD, driven by a JSON config.

Steps (each optional, applied in this order):
  reshape    - smooth head reshaping: lower/narrow the crown, slim the outer hair and the face.
               One warp field shared by every head layer, sampled once (body layers untouched).
  mouth      - scale the open-mouth layers about a fixed point (closed-mouth line untouched).
  back_fill  - fill the back-hair layer wherever face/front hair covers it, so turning the
               head never reveals the background behind the face.
  groups     - wrap layers in PSD groups (= Cubism parts) in the given draw order.

Usage:
  python3 make_psd.py CONFIG.json INPUT.psd OUTPUT.psd [--preview PREVIEW.png] [--overwrite]

See README.md for the config format and examples/mythbreaker.json for a full example.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as nd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _psd  # noqa: E402


def smoothstep(t):
    u = np.clip(t, 0, 1)
    return u * u * (3 - 2 * u)


# ── 1. reshape ────────────────────────────────────────────────────────────────

def reshape(layers, W, H, cfg):
    """cfg keys (pixels are canvas coordinates):
      center_x        face midline
      crown_bottom    rows below this are never moved vertically (keep it above hair clips etc.)
      crown_blend     height of the band above crown_bottom where vertical squash fades in
      hair_top        top of the hair (excluding ahoge); cut is measured here
      cut             pixels removed at hair_top (crown pushed down)
      crown_narrow    extra horizontal narrowing reached at the hair top (0..1)
      face_narrow     horizontal narrowing of the whole head (0..1)
      face_fade       [y0, y1]: face_narrow fades out between these rows (keeps the jaw/neck join)
      side_narrow     narrowing of the outer hair (0..1)
      side_blend      [d0, d1]: distance from center_x where side_narrow fades in
      skip            layer names left untouched (body, neck, collar, ...)
    """
    CX, Y1, B, TOP = cfg["center_x"], cfg["crown_bottom"], cfg["crown_blend"], cfg["hair_top"]
    FY0, FY1 = cfg["face_fade"]
    K0, K1 = cfg["side_blend"]
    cut, narrow, side, face = cfg["cut"], cfg["crown_narrow"], cfg["side_narrow"], cfg["face_narrow"]
    skip = set(cfg.get("skip", []))

    # vertical: forward map y -> y' (rows >= Y1 fixed); compression c(y) eases from 1 to kk
    ys = np.arange(H, dtype=np.float64)

    def fwd_y(kk):
        c = 1 - (1 - kk) * smoothstep((Y1 - ys) / B)
        c[ys >= Y1] = 1
        yp = ys.copy()
        above = ys < Y1
        cum = np.cumsum(c[::-1])[::-1]
        yp[above] = Y1 - (cum[above] - cum[int(Y1)])
        return yp

    lo, hi = 0.05, 1.0
    for _ in range(60):                       # find kk so that hair_top moves down by exactly `cut`
        mid = (lo + hi) / 2
        if fwd_y(mid)[TOP] - TOP > cut:
            lo = mid
        else:
            hi = mid
    YP = fwd_y((lo + hi) / 2)
    top_new = YP[TOP]

    def inv_y(yo):
        return np.interp(yo, YP, ys)

    # horizontal outer-hair narrowing: forward |d| -> |d'|
    ad = np.arange(0, max(3000, W), dtype=np.float64)
    cs = 1 - side * smoothstep((ad - K0) / (K1 - K0))
    adp = np.concatenate([[0], np.cumsum((cs[1:] + cs[:-1]) / 2)])

    def src_coords(x0, x1, y0, y1):
        yo, xo = np.mgrid[y0:y1, x0:x1].astype(np.float64)
        d = xo - CX
        d = d / (1 - narrow * smoothstep((Y1 - yo) / (Y1 - top_new)))      # crown narrowing (output y)
        ysrc = inv_y(yo)
        d = d / (1 - face * (1 - smoothstep((ysrc - FY0) / (FY1 - FY0))))  # face narrowing (source y)
        d = np.sign(d) * np.interp(np.abs(d), adp, ad)                      # outer-hair narrowing
        return ysrc, CX + d

    out = {}
    for name, (arr, top, left) in layers.items():
        if name in skip:
            out[name] = (arr, top, left)
            continue
        a = _psd.full((arr, top, left), W, H)
        bottom, right = top + arr.shape[0], left + arr.shape[1]
        # content moves down (crown) and toward the midline: grow the output box accordingly
        y0, x0, x1 = max(0, top - 5), max(0, min(left, CX) - 5), min(W, max(right, CX) + 5)
        y1 = min(H, max(bottom, Y1 if top < Y1 else 0) + 5)
        sy, sx = src_coords(x0, x1, y0, y1)
        f = a[y0:y1, x0:x1].astype(np.float32)
        f[..., :3] *= f[..., 3:4] / 255.0                                    # premultiply: no halos
        g = np.stack([nd.map_coordinates(f[..., c], [sy - y0, sx - x0], order=1, mode="constant", cval=0)
                      for c in range(4)], -1)
        al = g[..., 3:4]
        g[..., :3] = np.where(al > 0.5, g[..., :3] * 255.0 / np.maximum(al, 1e-3), 0)
        res = np.zeros_like(a)
        res[y0:y1, x0:x1] = np.clip(g + 0.5, 0, 255).astype(np.uint8)
        out[name] = _psd.crop(res)
    return out


# ── 2. mouth ──────────────────────────────────────────────────────────────────

def scale_mouth(layers, cfg):
    """cfg: layers (open-mouth layer names), center [x, y], scale."""
    MX, MY = cfg["center"]
    sc = cfg["scale"]
    out = dict(layers)
    for name in cfg["layers"]:
        arr, top, left = layers[name]
        h, w = arr.shape[:2]
        im = Image.fromarray(arr, "RGBA").resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.LANCZOS)
        a = np.asarray(im)
        t, l = round(MY + (top - MY) * sc), round(MX + (left - MX) * sc)
        ys, xs = np.where(a[..., 3] > 0)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        out[name] = (np.ascontiguousarray(a[y0:y1, x0:x1]), t + int(y0), l + int(x0))
    return out


# ── 3. back_fill ──────────────────────────────────────────────────────────────

def fill_back(layers, W, H, cfg):
    """cfg: layer (back hair), cover (layers in front of it), inset (px kept clear of the
    cover edges so nothing peeks out in the front view), interior (px eroded to sample the
    flat fill colour away from outlines)."""
    hb = _psd.full(layers[cfg["layer"]], W, H)
    cover = np.zeros((H, W), bool)
    for n in cfg["cover"]:
        cover |= _psd.full(layers[n], W, H)[..., 3] > 128
    cover = nd.binary_erosion(cover, iterations=cfg.get("inset", 6))
    need = cover & (hb[..., 3] < 250)
    known = hb[..., 3] >= 250
    inner = nd.binary_erosion(known, iterations=cfg.get("interior", 25))
    col = np.median(hb[inner][:, :3], axis=0).astype(np.uint8)
    new = hb.copy()
    new[need & ~known, :3] = col
    soft = np.clip(nd.gaussian_filter(need.astype(np.float32), 1.0) * 255, 0, 255).astype(np.uint8)
    new[..., 3] = np.maximum(hb[..., 3], soft)
    out = dict(layers)
    out[cfg["layer"]] = _psd.crop(new)
    return out, col


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--preview", help="write an alpha-correct composite PNG (open mouth and closed eyes hidden)")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))

    W, H, layers, order = _psd.load(a.input)
    print(f"{a.input}: {W}x{H}, {len(layers)} layers")
    if cfg.get("reshape"):
        layers = reshape(layers, W, H, cfg["reshape"])
        print("reshape: done")
    if cfg.get("mouth"):
        layers = scale_mouth(layers, cfg["mouth"])
        print(f"mouth: scaled {len(cfg['mouth']['layers'])} layers by {cfg['mouth']['scale']}")
    if cfg.get("back_fill"):
        layers, col = fill_back(layers, W, H, cfg["back_fill"])
        print(f"back_fill: fill colour {tuple(int(c) for c in col)}")
    groups = cfg.get("groups") or [["all", order]]
    _psd.save(a.output, W, H, layers, groups, overwrite=a.overwrite)
    print(f"saved {a.output}")
    if a.preview:
        hide = set(cfg.get("preview_hide", []))
        _psd.composite(W, H, layers, _psd.flat_names(groups), hide=hide).save(a.preview)
        print(f"preview {a.preview}")


if __name__ == "__main__":
    main()
