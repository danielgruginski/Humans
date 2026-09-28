# For each strained key of the combat clips in NAMES: the blade direction nearest the authored one that the
# wrist holds comfortably (coordinate descent on az/el, or dx/psi for the "V" form). Prints replacement keys.
import math, importlib, hum_anim as H
importlib.reload(H)
rig = H.Rig()
W_DIR = globals().get("W_DIR", 4.0)          # cost per degree^2 of turning the blade off the authored direction
MAXD = globals().get("MAXD", 40.0)


def grab(n):
    got = {}
    real = H._combat
    def fake(rig_, t, K, form, pivot, hands, shield=None, free=False):
        got.update(K=K, form=form, pivot=pivot, hands=hands, shield=shield)
        return real(rig_, t, K, form, pivot, hands, shield, free=True)
    H._combat = fake
    try:
        H.BUILD[n](rig, 0.0)
    finally:
        H._combat = real
    return got


def solve(c, K, i):
    """Key i's pose as _combat solves it: free, or near the elbows the key carries."""
    free = dict(K[i][3]) if len(K[i]) > 3 else True
    return H._combat(rig, K[i][0], K, c["form"], c["pivot"], c["hands"], c["shield"], free=free)


def parts(c, K, i):
    p = solve(c, K, i)
    return " ".join("%s(tw %.0f fl %.0f dv %.0f)" % (s, *H.wrist_strain(rig, p, s)) for s, _ in c["hands"])


def strain(c, K, i):
    p = solve(c, K, i)
    out = 0.0
    for s, _ in c["hands"]:
        out += H.wrist_comfort(s, *H.wrist_strain(rig, p, s))
    return out


for n in NAMES:
    c = grab(n)
    K = list(c["K"])
    for i in range(1, len(K) - 1):
        if K[i][1] == K[0][1]:
            continue                             # back on guard: the guard is shared, leave it
        only = globals().get("ONLY", {}).get(n)
        if only is not None and round(K[i][0], 3) not in only:
            continue
        base = strain(c, K, i)
        was = parts(c, K, i)
        if base < globals().get("THRESH", 2500):
            continue
        v0 = list(K[i][1])
        V = c["form"] == "V"
        POS = globals().get("POS", False); W_POS = globals().get("W_POS", 20.0)
        def with_(da, db, pa=0.0, pb=0.0):
            v = list(v0)
            if V:
                v[3] = v0[3] + da / 57.3; v[4] = v0[4] + db
                v[2] = v0[2] + pa; v[1] = v0[1] + pb / 100          # th degrees, r cm
            else:
                v[3] = v0[3] + da; v[4] = v0[4] + db
                if c["form"] == "C":
                    v[1] = v0[1] + pa / 100; v[2] = v0[2] + pb / 100  # y, h cm
                else:
                    v[1] = v0[1] + pa; v[2] = v0[2] + pb / 100        # phi degrees, h cm
            K2 = list(K); K2[i] = (K[i][0], tuple(v), *K[i][2:])
            return K2, v
        def cost(x):
            if max(abs(e) for e in x) > MAXD:
                return 1e12
            K2, _ = with_(*x)
            return strain(c, K2, i) + W_DIR * (x[0] ** 2 + x[1] ** 2) + W_POS * (x[2] ** 2 + x[3] ** 2)
        x = [0.0, 0.0, 0.0, 0.0]
        dims = 4 if POS else 2
        best = (cost(x), x)
        for step in (16.0, 8.0, 4.0, 2.0):
            moved = True
            while moved:
                moved = False
                for d in range(dims):
                    for sg in (step, -step):
                        y = list(best[1]); y[d] += sg
                        cc = cost(y)
                        if cc < best[0] - 1:
                            best = (cc, y); moved = True
        K2, v = with_(*best[1])
        best = (best[0], *best[1])
        after = strain(c, K2, i)
        K[i] = K2[i]
        print(f"{n} key {K[i][0]:.2f}: strain {base:.0f} -> {after:.0f} (turn {best[1]:+.0f}, {best[2]:+.0f}; move {best[3]:+.0f}, {best[4]:+.0f})  "
              f"{tuple(round(x, 3) for x in v)}")
        print(f"      {was}  ->  {parts(c, K, i)}")
