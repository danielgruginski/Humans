# Per clip: the worst wrist twist / flex / deviation (Humanoid limits +-90 / +-80 / +-40) and the largest
# frame-to-frame elbow and hand turn, from the clip functions directly (no baking). NAMES: clip list.
import math, importlib, hum_anim as H
importlib.reload(H)
rig = H.Rig()
for n in NAMES:
    fn = H.BUILD[n]; N = H.CLIPS[n][0]
    worst = {}; prev = None; step = (0.0, "", 0); estep = (0.0, "", 0)
    for f in range(N + 1):
        p = fn(rig, f / N)
        for s in "lr":
            tw, fl, dv = H.wrist_strain(rig, p, s)
            for k, v, lim in (("tw", tw, 90), ("fl", fl, 80), ("dv", dv, 40)):
                key = s + k
                if abs(v) / lim > worst.get(key, (0, 0, 0))[0]:
                    worst[key] = (abs(v) / lim, v, f)
        if prev is not None:
            for b in ("lowerarm_l", "lowerarm_r", "hand_l", "hand_r"):
                a = math.degrees(prev[0][b].rotation_difference(p.D[b]).angle)
                a = min(a, 360 - a)
                if a > step[0]:
                    step = (a, b, f)
            for s in p.elbow:
                if s in prev[1] and abs(p.elbow[s] - prev[1][s]) > estep[0]:
                    estep = (abs(p.elbow[s] - prev[1][s]), s, f)
        prev = ({b: p.D[b].copy() for b in ("lowerarm_l", "lowerarm_r", "hand_l", "hand_r")}, dict(p.elbow))
    over = [f"{k} {v[1]:.0f}@{v[2]}" for k, v in sorted(worst.items()) if v[0] > 0.9]
    print(f"{n}: turn {step[0]:.0f} ({step[1]}@{step[2]}), elbow step {estep[0]:.0f} ({estep[1]}@{estep[2]})"
          f" | near/over limit: {', '.join(over) or '-'}")
