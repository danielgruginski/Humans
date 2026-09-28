"""A hooded cloak, worn over clothes, a gambeson or mail - never over pauldrons, gorgets or plate (the Cloak
excludes them: bulky) - the outermost layer.

Cloak      a cape: wool, from a collar around the neck over the tops of the shoulders, then hanging *behind*
           the arms down to mid-calf; fastened at the throat by an iron clasp. The arms stay free in front of
           and beside it. Rings are the convex support of torso, legs and a proxy of the arms hanging and
           swinging back (the rest pose has them out), so the cape clears the arms' back-swing when walking.
           On the spine only (a cape doesn't follow the thighs; they swing in front of it).
CloakHood  worn with the cloak (a companion garment): a close hood (small point at the back), the face open
           from the hairline to the chin, closed around the throat, a short collar over the shoulders. Bound
           to the head keys like hair. Hair under it is cut by the HoodCut UV (hood_cut); the fringe and
           face-framing strands in the opening, and long hair below the collar in front, stay.
"""
import math

import numpy as np

import hum_cloth as C
import hum_armor as A

ss = C.ss
CLOAK_SPAN_TOP = math.pi                 # closed around the neck at the clasp
CLOAK_SPAN_SHOULDER = math.radians(118)  # over the tops of the shoulders
CLOAK_SPAN = math.radians(78)            # below the armpits: behind the arms


def _hull(Q):
    """2D convex hull (monotone chain), counter-clockwise."""
    Q = np.unique(np.round(Q, 5), axis=0)
    if len(Q) < 3:
        return Q
    Q = Q[np.lexsort((Q[:, 1], Q[:, 0]))]

    def half(pts):
        h = []
        for p in pts:
            while len(h) >= 2 and np.cross(h[-1] - h[-2], p - h[-2]) <= 0:
                h.pop()
            h.append(p)
        return h
    lo, up = half(Q), half(Q[::-1])
    return np.array(lo[:-1] + up[:-1])


def _ray_hull(H, c, d):
    """Distance from c along unit d to the boundary of the convex polygon H (c inside)."""
    best = 0.0
    for a, b in zip(H, np.roll(H, -1, 0)):
        e = b - a
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            continue
        w = a - c
        t = (w[0] * e[1] - w[1] * e[0]) / den
        u = (w[0] * d[1] - w[1] * d[0]) / den
        if t > 0 and -1e-9 <= u <= 1 + 1e-9:
            best = max(best, t)
    return best


def _support_rings(P, cx, cy, Z, th, band=0.03):
    """R[k, j]: distance from (cx, cy) in direction th[j] (0 = front, -y) to the convex hull of the points P
    near height Z[k]. (The support function itself, plotted radially, bulges into lobes: a notch at the
    sternum between the pecs.)"""
    R = np.zeros((len(Z), len(th)))
    c = np.array([cx, cy])
    for k, z in enumerate(Z):
        sl = np.abs(P[:, 2] - z) < band
        if sl.sum() < 5:
            R[k] = R[k - 1] if k else 0.05
            continue
        H = _hull(P[sl, :2])
        R[k] = [_ray_hull(H, c, np.array([math.sin(a), -math.cos(a)])) for a in th]
    return R


def bulky(rec):
    """Armour a cloak is never worn over (the Cloak excludes it - hum_export): pauldrons, gorgets and plate.
    The cloak fits everything else (shirts, coats, gambesons, mail). Fitted to those too, every cloak was a
    stiff ring at chin height, 18-24 cm out, and they collided with it anyway."""
    return rec.get("slot") in ("shoulders", "gorget") or rec.get("material") == "plate"


def cloak_excludes():
    return sorted(n for n, r in C.GARMENTS.items() if bulky(r))


def _worn_under(B, shoulder):
    """Points of every body garment already built that can be worn under the cloak (LOD0; not the arms, which
    are out in the rest pose and covered by the hanging-arm proxy; not other capes, worn instead of it; not
    bulky armour): the cloak's hull clears the widest of them."""
    import bpy
    x_max = max(abs(shoulder["l"][0]), abs(shoulder["r"][0])) + 0.02
    pts = [np.zeros((0, 3))]
    for ob in bpy.data.objects:
        if not ob.name.startswith("Cloth_") or ob.name.startswith(("Cloth_Cloak",)):
            continue
        gname, tag, lod = C.parse_cloth(ob.name)
        if lod or tag != (C.BUILD["tag"] if C.BUILD else None):
            continue
        rec = C.GARMENTS.get(gname)
        if rec is None or rec.get("headgear") or rec.get("slot") == "cloak" or bulky(rec):
            continue
        import hum_builds, hum_rig
        Pn = hum_builds.build_coords(ob, hum_rig.SK)
        pts.append(Pn[np.abs(Pn[:, 0]) < x_max][::3])
    return np.vstack(pts)


def _hood_ring(cy, z, th):
    """This build's CloakHood support ring at height z (None if it isn't built or doesn't reach z)."""
    import bpy
    import hum_builds
    import hum_rig
    hood = bpy.data.objects.get(C.cloth_name("CloakHood"))
    if hood is None:
        return None
    H = hum_builds.build_coords(hood, hum_rig.SK)
    if (np.abs(H[:, 2] - z) < 0.012).sum() < 5:
        return None
    return _support_rings(H, 0.0, cy, np.array([z]), th, band=0.012)[0]


def _cloak_radii(P, Z, TH, cy, z_neck, z_sh, t):
    """R[k, j]: the cape's rings around the points P, with its ease, flare and folds. Rings above the body
    mesh's neck (the head is its own object: the taller builds' collar) take the first ring below that has
    points."""
    R = np.zeros_like(TH)
    band = np.where(np.arange(len(Z)) >= 4, 0.035, 0.02)
    have = np.array([(np.abs(P[:, 2] - Z[k]) < band[k]).sum() >= 5 for k in range(len(Z))])
    first = int(np.argmax(have))
    for k in range(len(Z)):
        kk = max(k, first)
        R[k] = _support_rings(P, 0.0, cy, Z[kk:kk + 1], TH[k], band=band[kk])[0]
    for _ in range(4):
        R[:, 1:-1] = 0.5 * R[:, 1:-1] + 0.25 * (R[:, :-2] + R[:, 2:])
    for k in range(5, len(Z)):                                            # never narrower going down
        R[k] = np.maximum(R[k], R[k - 1])
    for _ in range(2):
        R[1:-1] = 0.5 * R[1:-1] + 0.25 * (R[:-2] + R[2:])
    off = 0.025 + 0.012 * ss(z_neck, z_sh, Z) + 0.07 * t ** 1.6             # flares toward the hem
    off = off + 0.012 * ss(z_sh, z_neck + 0.02, Z)                          # a looser collar over the hood's hem
    folds = 0.012 * t[:, None] * np.sin(9 * (TH - math.pi))
    return R + off[:, None] + folds


def _cloak(B):
    co = B.co
    shoulder = {s: B.j[f"upperarm_{s}"] for s in "lr"}
    z_neck = float(B.j["neck_01"][2])
    z_sh = float(max(shoulder["l"][2], shoulder["r"][2]))
    knee = float(B.j["calf_l"][2])
    z_hem = knee - 0.16
    cy = float(B.j["spine_02"][1])
    # the arms as they hang when animated: vertical columns from the shoulder joints down to the hips
    arm_pts = []
    L = float(np.linalg.norm(B.j["hand_l"] - B.j["upperarm_l"])) + 0.08
    for s in "lr":
        a = shoulder[s]
        for swing in (0.0, math.radians(15), math.radians(30)):        # hanging, and swung back when walking
            d = np.array([0.0, math.sin(swing), -math.cos(swing)])
            for u in np.linspace(0.05, 1.0, 16):
                c = np.array([a[0] * 1.02, a[1], a[2]]) + d * L * u
                for ang in np.linspace(0, 2 * math.pi, 12, endpoint=False):
                    arm_pts.append(c + np.array([0.06 * math.cos(ang), 0.06 * math.sin(ang), 0.0]))
        for v in np.linspace(0, 2 * math.pi, 12, endpoint=False):      # the deltoid over the joint
            arm_pts.append(a + np.array([0.055 * math.cos(v), 0.055 * math.sin(v), 0.035]))
    body = co[np.isin(B.part, ["torso", "neck", "leg_l", "leg_r"])]
    P = np.vstack([body, np.array(arm_pts), _worn_under(B, shoulder)])
    # rings: collar, over the shoulders, then straight down
    Z = np.r_[np.linspace(z_neck + 0.05, z_sh + 0.05, 4), np.linspace(z_sh + 0.01, z_sh - 0.12, 5),
              np.linspace(z_sh - 0.15, z_hem, 14)]
    t = np.clip((z_sh + 0.05 - Z) / (z_sh - z_hem), 0, 1)             # 0 at the shoulders .. 1 at the hem
    segs = 48
    th_unit = np.linspace(-1, 1, segs + 1)
    # collar almost closed -> over the shoulder tops -> behind the arms from the armpits down
    z_pit = z_sh - 0.10
    span = np.where(Z > z_sh + 0.02,
                    CLOAK_SPAN_TOP + (CLOAK_SPAN_SHOULDER - CLOAK_SPAN_TOP) * ss(z_neck + 0.03, z_sh + 0.02, Z),
                    CLOAK_SPAN_SHOULDER + (CLOAK_SPAN - CLOAK_SPAN_SHOULDER) * ss(z_sh + 0.02, z_pit, Z))
    TH = np.array([math.pi + th_unit * sp for sp in span])                # centred at the back
    R = _cloak_radii(P, Z, TH, cy, z_neck, z_sh, t)
    # the collar tucks 1.2 cm inside the hood, which then covers its edge (seen from above, a collar outside
    # the hood left a ring-shaped gap into the cloak); the next ring eases out from it
    r_hood = _hood_ring(cy, Z[0], TH[0])
    if r_hood is not None:
        neck = co[B.part == "neck"]
        zq = min(Z[0], float(neck[:, 2].max()) - 0.01)                  # the neck mesh's top on tall builds
        r_neck = _support_rings(neck, 0.0, cy, np.array([zq]), TH[0], band=0.015)[0] + 0.012
        R[0] = np.minimum(R[0], np.maximum(r_hood - 0.012, r_neck))
        R[1] = np.minimum(R[1], 0.5 * (R[0] + R[2]) + 0.01)
    n = segs + 1
    # a rolled edge: the collar's top turned in 6 mm
    Zs = np.r_[Z[0] + 0.006, Z]
    Rs = np.vstack([R[0] - 0.006, R])
    THs = np.vstack([TH[0], TH])
    V = np.array([(Rs[k, j] * math.sin(THs[k, j]), cy - Rs[k, j] * math.cos(THs[k, j]), Zs[k])
                  for k in range(len(Zs)) for j in range(n)])
    F = [((k + 1) * n + j, (k + 1) * n + j + 1, k * n + j + 1, k * n + j) for k in range(len(Zs) - 1) for j in range(n - 1)]
    F = A._outward(V, F, np.array([0.0, cy, float(np.mean(Z))]))
    U = np.array([(th_unit[j] * float(R.mean()) * 2.2 / 0.25, (Z[0] - Zs[k]) / 0.25 - (0.0 if k else 0.006 / 0.25))
                  for k in range(len(Zs)) for j in range(n)])
    V, F = C.add_rim(V, F, 0.005, B)
    U = np.vstack([U, np.zeros((len(V) - len(U), 2))])
    # the clasp: two iron studs where the collar meets at the throat
    O = [np.array([0.0, cy, Z[1]])] * 2
    D = [np.array([math.sin(math.pi + s * CLOAK_SPAN_TOP * 0.97), -math.cos(math.pi + s * CLOAK_SPAN_TOP * 0.97), 0])
         for s in (-1, 1)]
    Pc, Nc = A.cast(V, F, O, D)
    part = A.with_studs(V, F, U, "skirt", Pc, Nc)
    return [part + (cloak_weights(B),)]


def shoulder_share(P, joints):
    """(n x 2) share of each vertex that rides the left / right arm: the cloth draped over a shoulder cap, so
    an arm raised past the shoulder (a chop, a reach) lifts it instead of pushing through it. Full over the
    shoulder joint, fading toward the spine, down to the armpit and onto the back panel (which hangs behind
    the arm). hum_helpers splits it half onto the deltoid helper."""
    P = np.asarray(P, float)
    A = np.zeros((len(P), 2))
    for k, (s, sx) in enumerate((("l", 1.0), ("r", -1.0))):
        J = np.asarray(joints[f"upperarm_{s}"], float)
        # long, gentle ramps: a short one stretched the cloth next to a raised arm so much that the folded rim
        # parted from the edge (a torn look)
        la = ss(0.0, 0.18, P[:, 0] * sx)                           # out over that shoulder
        vf = ss(J[2] - 0.50, J[2] - 0.02, P[:, 2])                 # from well below the armpit up
        bf = 1.0 - 0.85 * ss(J[1] + 0.02, J[1] + 0.12, P[:, 1])    # little on the back panel (+y is back):
                                                                   # it humped up behind raised arms
        A[:, k] = 0.85 * la * vf * bf
    return A


def spine_rows(P, sk, joints):
    """The cape on the spine by height: collar on neck/spine_03, the back on spine_03 -> spine_02, below the
    hips on the pelvis (a cape doesn't follow the thighs)."""
    P = np.asarray(P, float)
    z = P[:, 2]
    z_neck, z3, z2, zp = (float(joints[b][2]) for b in ("neck_01", "spine_03", "spine_02", "pelvis"))
    ix = sk.index
    W = np.zeros((len(P), len(sk.bones)))
    a = ss(z3, z_neck, z) * 0.5
    upper = ss(z2, z3, z)
    mid = (1 - upper) * ss(zp, z2, z)
    W[:, ix["neck_01"]] = a
    W[:, ix["spine_03"]] = (1 - a) * upper
    W[:, ix["spine_02"]] = mid
    W[:, ix["pelvis"]] = np.maximum(1 - a - (1 - a) * upper - mid, 0.0)
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


def with_shoulders(W, P, sk, joints):
    """Rows with the shoulder share moved onto the upper arms."""
    W = np.array(W, float)
    A = shoulder_share(P, joints)
    W *= (1.0 - A.sum(1))[:, None]
    W[:, sk.index["upperarm_l"]] += A[:, 0]
    W[:, sk.index["upperarm_r"]] += A[:, 1]
    return W


def with_chain(W, P, sk, joints):
    """The spine part of the rows below the upper back onto the cape chain (hum_helpers.CAPE), blended between
    neighbouring links by height; the collar, shoulders and arm shares stay."""
    import hum_helpers as HH
    if HH.CAPE[0] not in sk.index:
        return W
    W = np.array(W, float)
    P = np.asarray(P, float)
    z = P[:, 2]
    ix = sk.index
    heads = [HH.node(joints, HH.HELPERS[b]) for b in HH.CAPE]
    tip = HH.node(joints, HH.HELPERS[HH.CAPE[-1]], "tail")
    zs = [h[2] for h in heads] + [tip[2]]
    mids = [(zs[i] + zs[i + 1]) / 2 for i in range(len(HH.CAPE))]           # each link's centre height
    c = ss(zs[0] + 0.06, zs[0] - 0.10, z)                                     # 0 over the shoulders .. 1 below
    spine = [ix[b] for b in ("neck_01", "spine_03", "spine_02", "spine_01", "pelvis")]
    S = W[:, spine].sum(1) * c
    W[:, spine] *= (1 - c)[:, None]
    # link weights: linear between neighbouring centres (above the first all on it, below the last all on it)
    L = np.zeros((len(P), len(HH.CAPE)))
    for k in range(len(HH.CAPE)):
        w = np.ones(len(P))
        if k > 0:
            w = np.where(z < mids[k - 1], np.clip((mids[k - 1] - z) / (mids[k - 1] - mids[k]), 0, 1), 0.0)
        if k < len(HH.CAPE) - 1:
            w = np.where(z < mids[k], np.clip((z - mids[k + 1]) / (mids[k] - mids[k + 1]), 0, 1), w)
        L[:, k] = w
    L /= np.maximum(L.sum(1, keepdims=True), 1e-9)
    for k, b in enumerate(HH.CAPE):
        W[:, ix[b]] += S * L[:, k]
    return W


def cape_weights(P, sk, joints):
    """A cape's rows from scratch: spine by height, shoulder caps on the arms, the back on the cape chain."""
    W = spine_rows(P, sk, joints)
    W = with_shoulders(W, P, sk, joints)
    W = with_chain(W, P, sk, joints)
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


def smooth_on_mesh(W, me, iterations=6):
    """Average each row with its mesh neighbours: the folded rim follows its edge exactly (with the arms up the
    rim and the edge parted where the weights change fast - a torn look)."""
    e = np.zeros(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", e)
    e = e.reshape(-1, 2)
    n = len(W)
    deg = np.bincount(e.ravel(), minlength=n).astype(float)
    for _ in range(iterations):
        S = np.zeros_like(W)
        np.add.at(S, e[:, 0], W[e[:, 1]])
        np.add.at(S, e[:, 1], W[e[:, 0]])
        W = np.where(deg[:, None] > 0, 0.5 * W + 0.5 * S / np.maximum(deg, 1)[:, None], W)
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


def reskin(ob, arm, sk):
    """Re-weight an existing cloak / cape mesh in place (all builds and LODs), keeping its build fit."""
    import hum_rig, hum_helpers
    n = len(ob.data.vertices)
    P = np.zeros(n * 3)
    ob.data.vertices.foreach_get("co", P)
    P = P.reshape(-1, 3)
    joints = {b.name: np.array(b.head_local) for b in arm.data.bones}
    W = hum_rig.weights_of(ob, sk)
    W2 = hum_helpers.redistribute(smooth_on_mesh(cape_weights(P, sk, joints), ob.data), P, sk, joints, ob.data,
                                  hum_helpers.hanging_mask(ob))
    hum_helpers.rest_shift(ob, W, W2, sk)           # joints move differently per build
    for j in np.flatnonzero(np.abs(W2 - W).max(0) > 1e-5):
        name = sk.bones[j]
        vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        vg.remove(list(range(n)))
        nz = np.flatnonzero(W2[:, j] > 1e-4)
        vals = np.round(W2[nz, j], 5)
        for v in np.unique(vals):
            vg.add(nz[vals == v].tolist(), float(v), 'REPLACE')
    return W2


def cloak_weights(B):
    """Per vertex (hum_cloth build path): cape_weights with the build's own joints."""
    def weights(V, sk):
        joints = {b: np.asarray(B.j[b], float) for b in B.j}
        return cape_weights(V, sk, joints)
    return weights


def hood_profile(Hs):
    """Heights and the face opening of the cloak's hood (shared by the hood and the hair cut):
    open_half(z) = half-angle of the face opening from the front (0 = closed): the crown and the throat are
    closed; between the hairline and the chin the face is open (not the ears)."""
    F_ = Hs.H.F
    z_top = float(Hs.co[:, 2].max())
    z_open = float(Hs.eye_z) + 0.078                                  # at the hairline: the fringe shows
    z_chin = float(F_.chin[2])
    z_bot = float(Hs.co[:, 2].min()) - 0.02                         # the hem tucks inside the cloak's collar
    face = math.radians(62)

    def open_half(z):
        z = np.asarray(z, float)
        top = ss(z_open + 0.03, z_open - 0.025, z) ** 0.6            # an arched top edge (no square corners)
        bottom = ss(z_chin - 0.03, z_chin - 0.005, z)                # 1 above the throat
        return face * top * bottom
    return z_top, z_open, z_chin, z_bot, open_half


def _cloak_hood(Hs, peak=True, off=0.02, drop=0.0, flare=0.006, over=()):
    """A close hood made like a real one: two panels sewn along a seam from the forehead over the crown to a
    point behind the head (seen from the side a triangle, from the front a pointed arch). The crown is the
    convex hull of the head (offset) and that seam; the face is open from the hairline to the chin,
    closed around the throat, a short collar flaring over the shoulders. Sits ~1.3 cm off the head: the hair
    under it is cut away (HoodCut UV), only what shows in the face opening (and hangs below the collar in
    front) stays."""
    import bpy
    body = bpy.data.objects["Body"]
    kb = body.data.shape_keys.key_blocks[0] if body.data.shape_keys else None
    Bc = np.array([d.co[:] for d in kb.data]) if kb else np.array([v.co[:] for v in body.data.vertices])
    z_top, z_open, z_chin, z_bot, open_half = hood_profile(Hs)
    z_bot = z_bot - drop                                              # coifs reach down over the shoulders
    P = np.vstack([Hs.co, Bc[(Bc[:, 2] < float(Hs.co[:, 2].min()) + 0.02) & (Bc[:, 2] > z_bot - 0.04)
                               & (np.hypot(Bc[:, 0], Bc[:, 1] - Hs.cy) < 0.2)]])
    # the garments it's worn over (a coif over the gambeson / hauberk): its cape lies on them
    for name in over:
        g = bpy.data.objects.get(C.cloth_name(name))
        if g is None:
            continue
        import hum_builds, hum_rig
        G = hum_builds.build_coords(g, hum_rig.SK)
        G = G[(G[:, 2] < float(Hs.co[:, 2].min()) + 0.02) & (G[:, 2] > z_bot - 0.04)
              & (np.hypot(G[:, 0], G[:, 1] - Hs.cy) < 0.2)]
        P = np.vstack([P, G])
    z_dome = z_open + 0.035                                           # above: the crown hull (closed rings)
    crown = _hood_crown(Hs, z_open, off=off, peak=peak)
    z_hi = float(crown[0][:, 2].max())
    Z = np.r_[z_dome + (z_hi - 0.002 - z_dome) * np.linspace(1.0, 0.0, 16)[:-1],
              np.linspace(z_dome, z_chin - 0.035, 18)[:-1], np.linspace(z_chin - 0.035, z_bot, 5)]
    segs = 44
    u = np.linspace(-1, 1, segs + 1)
    span = math.pi - open_half(Z)
    TH = np.array([math.pi + u * sp for sp in span])
    R = np.zeros_like(TH)
    for k in range(len(Z)):
        R[k] = _support_rings(P, Hs.cx, float(Hs.cy), np.array([min(Z[k], z_dome)]), TH[k], band=0.008)[0]
    closed = span > math.pi - 1e-3                                    # closed rings wrap: no seam notch
    for _ in range(3):
        R[:, 1:-1] = 0.5 * R[:, 1:-1] + 0.25 * (R[:, :-2] + R[:, 2:])
        R[closed, 0] = R[closed, -1] = 0.5 * (R[closed, 0] + R[closed, -1])
        R[1:-1] = 0.5 * R[1:-1] + 0.25 * (R[:-2] + R[2:])
    f = np.clip((z_chin - 0.035 - Z) / (z_chin - 0.035 - z_bot), 0, 1)   # 0 above the collar .. 1 at its hem
    back = 0.5 - 0.5 * np.cos(TH - math.pi)                           # 1 at the back, 0 at the front
    off = 0.013 + (0.004 + flare * f[:, None]) * (0.6 + 0.4 * back)
    off = off + 0.004 * ss(z_chin, z_open, Z)[:, None]
    R = R + off
    n = segs + 1
    CX = np.full(len(Z), Hs.cx)
    cy = np.full(len(Z), Hs.cy)
    # crown rows: sections of the hull (head + seam), about each section's centroid
    for k in np.where(Z > z_chin - 0.035 + 1e-6)[0]:
        sec = _hull_section(crown, Z[k])
        if sec is None or len(sec) < 3:
            continue
        # rows with the face opening keep the head's axis (the opening is measured from it); closed crown
        # rows go round their own section (it reaches back to the point)
        ctr = np.array([Hs.cx, Hs.cy]) if open_half(Z[k]) > 0.01 else sec.mean(0)
        CX[k], cy[k] = ctr
        R[k] = [_ray_hull(sec, ctr, np.array([math.sin(a), -math.cos(a)])) for a in TH[k]]
        # low on the head (nape, jaw) the neck and what's worn under (a gambeson's collar rises up the nape)
        # must stay inside too
        if Z[k] < float(Hs.co[:, 2].min()) + 0.08:
            sl = np.abs(P[:, 2] - Z[k]) < 0.012
            if sl.sum() >= 5:
                H2 = _hull(P[sl, :2])
                if len(H2) >= 3 and _ray_hull(H2, ctr, np.array([0.0, 1.0])) > 0:
                    R2 = np.array([_ray_hull(H2, ctr, np.array([math.sin(a), -math.cos(a)])) for a in TH[k]])
                    R[k] = np.maximum(R[k], R2 + off[k])
    # the hem slopes: just under the chin in front, down over the cloak collar at the sides and back
    z_c = z_chin - 0.035
    z_front = z_chin - 0.05
    ZK = np.repeat(Z[:, None], n, 1)
    g = np.clip((z_c - Z) / (z_c - z_bot), 0, 1)[:, None]
    # the hem, seen from the front, is an oval around the neck: a short rounded dip on the chest, high over the
    # shoulders, deepest at the back (no square bib)
    cf = np.cos(TH)                                                   # 1 at the front, -1 at the back
    d_back = z_c - z_bot
    depth = d_back * (0.3 + 0.2 * np.maximum(cf, 0) ** 2 + 0.7 * np.maximum(-cf, 0) ** 1.5)
    zb = z_c - depth
    ZK = np.where(Z[:, None] < z_c, z_c - g * (z_c - zb), ZK)
    # collar rows: each vertex sits at its own height (the front hem is higher than the back), so its
    # radius comes from the body there - it lies on the chest instead of hanging as a tube
    for k in np.where(Z < z_c - 1e-6)[0]:
        for j in range(n):
            R[k, j] = _support_rings(P, Hs.cx, float(Hs.cy), np.array([ZK[k, j]]), TH[k, j:j + 1],
                                     band=0.012)[0][0] + off[k, j]
    rows = np.where(Z < z_c - 1e-6)[0]
    for _ in range(6):
        R[rows, 1:-1] = 0.5 * R[rows, 1:-1] + 0.25 * (R[rows, :-2] + R[rows, 2:])
        R[rows, 0] = R[rows, -1] = 0.5 * (R[rows, 0] + R[rows, -1])
        if len(rows) > 2:
            R[rows[1:-1]] = 0.5 * R[rows[1:-1]] + 0.25 * (R[rows[:-2]] + R[rows[2:]])
    # the capelet's outline: an oval through its widest points (front, back, sides), grown just enough to
    # contain the shoulders - not their squared outline. Blends in from the neck down to the hem.
    for k in rows:
        sx, sy = np.sin(TH[k]), -np.cos(TH[k])
        Rk = R[k]
        a = max(float(np.max(Rk * np.abs(sx))), 1e-3)
        bf = max(float(np.max(np.where(sy < 0, -Rk * sy, 0.0))), 1e-3)
        bb = max(float(np.max(np.where(sy > 0, Rk * sy, 0.0))), 1e-3)
        b = np.where(sy < 0, bf, bb)
        re = 1.0 / np.sqrt((sx / a) ** 2 + (sy / b) ** 2)
        s = max(1.0, float(np.max(Rk / re)))
        w = 0.45 * float(ss(0.0, 0.5, float(g[k, 0])))     # rounds the outline, still hugs the shoulders
        R[k] = Rk * (1 - w) + re * s * w
    V = [(CX[k] + R[k, j] * math.sin(TH[k, j]), cy[k] - R[k, j] * math.cos(TH[k, j]), ZK[k, j])
         for k in range(len(Z)) for j in range(n)]
    tip = len(V)
    top = crown[0][int(np.argmax(crown[0][:, 2]))]
    V.append(tuple(top))                                              # the top of the seam
    V = np.array(V)
    F = [((k + 1) * n + j, (k + 1) * n + j + 1, k * n + j + 1, k * n + j) for k in range(len(Z) - 1) for j in range(n - 1)]
    F += [(j + 1, j, tip) for j in range(n - 1)]
    fade = np.r_[np.repeat(f, n), 0.0]
    V, F, fade = _weld(V, F, fade)                                      # closed rings: no seam line
    F = A._outward(V, F, np.array([Hs.cx, Hs.cy, float(np.mean(Z))]))
    V2, F2 = C.add_rim(V, F, 0.004, Hs)
    fade = np.r_[fade, np.zeros(len(V2) - len(V))]
    for i in range(len(V), len(V2)):
        fade[i] = fade[int(np.argmin(np.linalg.norm(V - V2[i], axis=1)))]
    return [(V2, F2, None, "shell", np.zeros(len(V2)), ("neckfade", fade))]


def _hood_crown(Hs, z_open, off=0.02, peak=True):
    """Convex hull (verts, edges) of the head above the face opening, offset by `off`, and the hood's seam:
    from the top of the forehead back over the crown to a point behind the head."""
    import bmesh
    from mathutils import Vector
    up = np.ones(len(Hs.co), bool)
    pts = list(Hs.co[up] + Hs.no[up] * off)
    top = Hs.co[np.argmax(Hs.co[:, 2])]
    front = Hs.co[up][np.argmin(Hs.co[up][:, 1])]
    back_y = float(Hs.co[up][:, 1].max())
    a = np.array([Hs.cx, front[1] + 0.04, top[2] + off + 0.004])       # seam start, over the front of the crown
    b = np.array([Hs.cx, back_y + 0.07, top[2] - 0.015])              # the point: behind the crown
    if peak:
        for t in np.linspace(0, 1, 12):
            pts.append(a + (b - a) * t)
    bm = bmesh.new()
    for p in pts:
        bm.verts.new(Vector(p))
    bmesh.ops.convex_hull(bm, input=bm.verts[:])
    for v in [v for v in bm.verts if not v.link_faces]:
        bm.verts.remove(v)
    bm.verts.index_update()
    V = np.array([v.co[:] for v in bm.verts])
    E = np.array([(e.verts[0].index, e.verts[1].index) for e in bm.edges])
    bm.free()
    return V, E


def _hull_section(crown, z):
    """The convex polygon where the plane at height z cuts the hull."""
    V, E = crown
    a, b = V[E[:, 0]], V[E[:, 1]]
    m = (a[:, 2] - z) * (b[:, 2] - z) < 0
    if m.sum() < 3:
        return None
    t = (z - a[m, 2]) / (b[m, 2] - a[m, 2])
    P = a[m, :2] + (b[m, :2] - a[m, :2]) * t[:, None]
    return _hull(P)


def _weld(V, F, extra, eps=1e-5):
    """Merge coincident vertices (the duplicated seam of closed rings); drops degenerate faces."""
    key = {}
    remap = np.empty(len(V), np.int64)
    keep = []
    for i, p in enumerate(V):
        k = tuple(np.round(np.asarray(p) / eps).astype(np.int64))
        if k not in key:
            key[k] = len(keep)
            keep.append(i)
        remap[i] = key[k]
    F2 = []
    for f in F:
        g = [int(remap[i]) for i in f]
        g = [x for j, x in enumerate(g) if x not in g[:j]]
        if len(g) >= 3:
            F2.append(tuple(g))
    return np.asarray(V)[keep], F2, np.asarray(extra)[keep]


def hood_cut(Hs, P, beard=False):
    """Per hair vertex: > 0 = hidden under the hood (and the cloak behind it). Hair stays where it shows in
    the face opening; below the collar it stays in front of the shoulders (under the cape at the back).
    Beards stay in front below the chin (only their sideburns go under the hood)."""
    z_top, z_open, z_chin, z_bot, open_half = hood_profile(Hs)
    th = np.arctan2(np.abs(P[:, 0] - Hs.cx), -(P[:, 1] - Hs.cy))      # 0 front .. pi back
    z = P[:, 2]
    # in the face opening, and a little past its edge (locks framing the face spill over the hood's rim)
    h = th - (open_half(z) + 0.08 * (open_half(z) > 0.3))
    if beard:
        below = z < z_chin
        h = np.where(below, th - 1.3, h)
    else:
        # below the chin, locks in front of the shoulders hang out of the hood over the chest
        below = z < z_chin
        h = np.where(below, th - 1.05, h)
    return np.where(np.abs(h) < 1e-4, 1e-4, h)


R_ = C.REGIONS
CLOAK = {
    "Cloak": dict(slot="cloak", layer=5, material="cloth", build=_cloak, smooth_keys=10, hide=[], cover=[],
                  companions=["CloakHood"]),
    "CloakHood": dict(slot="head", layer=5, material="cloth", build=_cloak_hood, headgear=True, hoodcut=True,
                      # hides nothing: from below, the throat shows under the hood's cowl (hiding the neck and
                      # collar regions left a hole there - the head looked cut off); it doesn't poke through
                      companion=True, hide=[], cover=[]),
}
