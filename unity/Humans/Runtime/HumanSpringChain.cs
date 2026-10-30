using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// A cape's spring chain (xh_cape_0..2, down the back of a cloak or cape): Verlet points along the links,
    /// pulled toward the hanging pose (the cut as on an upright body, streaming back by `stream` at a run), with gravity, damping
    /// and collision capsules on the spine, pelvis and legs and round a worn skirt's cloth (HumanSkirt's ring);
    /// the links then turn to follow the points. Runs after the Animator and HumanHelperBones, at a fixed 60 Hz,
    /// so the cape trails when the character runs or turns and settles back when it stops. Cheap enough for a crowd
    /// (2026-10-12, as HumanSkirt): only while drawn, the capsules read once a frame, at most two steps a frame.
    /// HumanSetup fills it from human_rig.json (hum_helpers.CAPE in Blender, where the chain is rigid).
    /// </summary>
    [DefaultExecutionOrder(200)]
    public class HumanSpringChain : MonoBehaviour
    {
        [Serializable]
        public struct Capsule
        {
            public Transform a, b;
            public float radius;
            [Tooltip("On the torso (it carries the cape's top): it never pushes a point past where the hanging pose puts it - " +
                     "the cut lies on the back closer than the radius")]
            public bool torso;
            [Tooltip("Pushes a point straight back, not off its axis (an arm under a side chain: a hand just outside the " +
                     "chain lifts the cape's side back over it instead of pressing it inward, behind the hand)")]
            public bool pushBack;
        }

        [Tooltip("The links, from the one hanging off the spine down")]
        public Transform[] bones = Array.Empty<Transform>();
        [Tooltip("Their local rotations in the bind pose")]
        public Quaternion[] restLocal = Array.Empty<Quaternion>();
        [Tooltip("The last link's tip, in its own space")]
        public Vector3 tipLocal = new Vector3(0, 0.25f, 0);

        [Range(0f, 1f), Tooltip("Pull toward the hanging pose per step")] public float stiffness = 0.06f;
        [Range(0f, 1f), Tooltip("Velocity lost per step")] public float damping = 0.12f;
        [Tooltip("Scale of gravity on the points")] public float gravity = 0.6f;
        [Tooltip("Cloth thickness kept off the colliders")] public float thickness = 0.03f;
        [Range(0f, 1f), Tooltip("How far each link of the hanging pose keeps the cut's direction on an upright body (restDirs, " +
                                "hanging by gravity) rather than leaning and swaying with the torso (rigid on the spine, the walk's " +
                                "sway swung the hem from side to side like a board). It turns with the torso's twist, and never " +
                                "forward into the back: on a back bent forward the cape lies on it")]
        public float drape = 1f;
        [Tooltip("Degrees the hanging pose's links turn back at a run, the last one all of it, the first a third")]
        public float stream = 20f;
        [Tooltip("Speeds (m/s, of the character over the ground) over which drape gives way to stream: hung close standing " +
                 "and walking, streaming out behind at a run (the torso's lean carries it back too)")]
        public Vector2 trail = new Vector2(1.8f, 3.4f);
        [Tooltip("Each link's direction in the bind pose, in the space of the first link's parent (spine_03): the cut on an upright body")]
        public Vector3[] restDirs = Array.Empty<Vector3>();
        [Tooltip("World up and the character's back in the bind pose, in the same space (the torso's lean is taken off, its twist kept)")]
        public Vector3 upLocal, backLocal;
        public Capsule[] colliders = Array.Empty<Capsule>();
        [Tooltip("The columns either side on the cape grid (HumanSetup): a point keeps within `stretch` of their spacing in the hanging pose")]
        public HumanSpringChain[] neighbours = Array.Empty<HumanSpringChain>();
        [Tooltip("How far a column may part from a neighbour past the hanging pose's spacing (x): one an arm pushes drags its " +
                 "neighbours along - a tent over the arm, not a slit beside it (with five columns an elbow pushed only a strip)")]
        public float stretch = 1.15f;
        // and a worn skirt's cloth (the ring's links, each as thick as the garment stands out from it): hung closer, the
        // cloak would have a dress's back poking through it
        HumanSkirt ring;
        Vector3[] ringA = Array.Empty<Vector3>(), ringB = Array.Empty<Vector3>();
        float[] ringR = Array.Empty<float>();
        int ringN;
        Vector3 back;                                                   // behind the character, level

        const float Step = 1f / 60f;
        Vector3[] pos, prev, target;
        float[] linkLen;
        float acc, speed;
        Vector3 lastAt;
        bool live;
        Vector3[] capA = Array.Empty<Vector3>(), capB = Array.Empty<Vector3>();
        bool[] capOn = Array.Empty<bool>();
        float[] capR = Array.Empty<float>();                            // per point and capsule
        SkinnedMeshRenderer[] drawn = Array.Empty<SkinnedMeshRenderer>();
        float drawnAt = -10f;

        void OnEnable() { live = false; }

        void OnDisable()                                                // back to hanging (no cape worn)
        {
            for (int i = 0; i < bones.Length && i < restLocal.Length; i++)
                if (bones[i] != null) bones[i].localRotation = restLocal[i];
        }

        /// <summary>any of the character's skinned meshes drawn this frame (by a camera or a shadow); the list is looked
        /// up again every 2 s (garments come and go)</summary>
        bool Drawn()
        {
            if (Time.unscaledTime - drawnAt > 2f || drawn.Length == 0)
            {
                drawn = GetComponentsInChildren<SkinnedMeshRenderer>(false);
                drawnAt = Time.unscaledTime;
            }
            if (drawn.Length == 0) return true;                         // nothing to judge by: as before
            foreach (var r in drawn) if (r != null && r.enabled && r.isVisible) return true;
            return false;
        }

        void LateUpdate()
        {
            if (bones.Length == 0 || restLocal.Length != bones.Length || bones[0] == null) return;
            if (!Drawn()) { live = false; return; }                     // unseen: it stays as it was (afresh when seen)
            Tick(Time.deltaTime);
        }

        /// <summary>a frame of dt seconds after the pose (LateUpdate's; a check tool's own clock)</summary>
        public void Tick(float dt)
        {
            int n = bones.Length;
            if (n == 0 || restLocal.Length != n || bones[0] == null) return;
            if (target == null || target.Length != n + 1)
            {
                target = new Vector3[n + 1];
                pos = new Vector3[n + 1];
                prev = new Vector3[n + 1];
                linkLen = new float[n + 1];
                live = false;
            }
            // the hanging pose: the links at rest on whatever the animation did to the spine
            for (int i = 0; i < n; i++) bones[i].localRotation = restLocal[i];
            for (int i = 0; i < n; i++) target[i] = bones[i].position;
            target[n] = bones[n - 1].TransformPoint(tipLocal);
            for (int i = 1; i <= n; i++) linkLen[i] = (target[i] - target[i - 1]).magnitude;
            if (capA.Length != colliders.Length)
            {
                capA = new Vector3[colliders.Length]; capB = new Vector3[colliders.Length]; capOn = new bool[colliders.Length];
            }
            for (int i = 0; i < colliders.Length; i++)                   // the body where the animation put it
            {
                var c = colliders[i];
                capOn[i] = c.a != null && c.b != null;
                if (!capOn[i]) continue;
                capA[i] = c.a.position;
                capB[i] = c.b.position;
            }
            if (capR.Length != (n + 1) * colliders.Length) capR = new float[(n + 1) * colliders.Length];
            for (int i = 1; i <= n; i++)                                 // each point's reach: a torso capsule's capped by
                for (int k = 0; k < colliders.Length; k++)               // the cut's own distance from it
                {
                    float r = colliders[k].radius + thickness;
                    if (colliders[k].torso && capOn[k]) r = Mathf.Min(r, Distance(target[i], capA[k], capB[k]));
                    capR[i * colliders.Length + k] = r;
                }
            var at = transform.position;                                 // the ground speed, smoothed (a jump: none)
            var moved = Vector3.ProjectOnPlane(at - lastAt, Vector3.up);
            if (live && dt > 0f && moved.sqrMagnitude < 1f)
                speed = Mathf.Lerp(speed, moved.magnitude / dt, 1f - Mathf.Exp(-dt / 0.15f));
            lastAt = at;
            float u = Mathf.Clamp01((speed - trail.x) / Mathf.Max(trail.y - trail.x, 0.01f));
            u = u * u * (3f - 2f * u);
            float hang = drape * (1f - u), lift = stream * u * Mathf.Deg2Rad;
            // the torso's frame with its lean taken off (its twist kept), and the character's back in it, level (a side chain
            // streams and is pushed back, not out sideways)
            var spine = bones[0].parent;
            bool upright = spine != null && restDirs.Length == n && upLocal.sqrMagnitude > 0.5f;
            var level = upright ? Quaternion.FromToRotation(spine.rotation * upLocal, Vector3.up) * spine.rotation : Quaternion.identity;
            back = Vector3.ProjectOnPlane(upright ? level * backLocal : -transform.forward, Vector3.up);
            back = back.sqrMagnitude > 1e-6f ? back.normalized : -transform.forward;
            if (hang > 0f || lift > 0f)                                  // each link turned toward hanging / back, from its new top
            {
                var prevRest = target[0];
                for (int i = 1; i <= n; i++)
                {
                    var rest = target[i];
                    var dir = (rest - prevRest).normalized;
                    if (hang > 0f)
                    {
                        var hung = Vector3.Slerp(dir, upright ? level * restDirs[i - 1] : Vector3.down, hang);
                        float fwd = Vector3.Dot(hung - dir, back);       // not forward into a back bent forward: it lies on it
                        dir = (fwd < 0f ? hung - back * fwd : hung).normalized;
                    }
                    if (lift > 0f) dir = Vector3.RotateTowards(dir, back, lift * i / n, 0f);
                    target[i] = target[i - 1] + dir * linkLen[i];
                    prevRest = rest;
                }
            }
            if (ring == null) TryGetComponent(out ring);
            ringN = 0;
            if (ring != null && ring.enabled)                            // (it has run: execution order 150)
            {
                int m = ring.columns.Length * 3;
                if (ringA.Length != m) { ringA = new Vector3[m]; ringB = new Vector3[m]; ringR = new float[m]; }
                float[] sh = ring.SlackHip, sm = ring.SlackMid, sk = ring.SlackKnee;
                for (int c = 0; c < ring.columns.Length; c++)
                {
                    var col = ring.columns[c];
                    if (col.hip == null || col.mid == null || col.knee == null || col.hem == null) continue;
                    if (sh[c] < 0.5f) { ringA[ringN] = col.hip.position; ringB[ringN] = col.mid.position; ringR[ringN++] = sh[c]; }
                    if (sm[c] < 0.5f) { ringA[ringN] = col.mid.position; ringB[ringN] = col.knee.position; ringR[ringN++] = sm[c]; }
                    if (sk[c] < 0.5f) { ringA[ringN] = col.knee.position; ringB[ringN] = col.hem.position; ringR[ringN++] = sk[c]; }
                }
            }
            if (!live || (pos[0] - target[0]).sqrMagnitude > 4f)       // first frame or a teleport
            {
                Array.Copy(target, pos, n + 1);
                Array.Copy(target, prev, n + 1);
                acc = 0f;
                live = true;
            }
            acc = Mathf.Min(acc + dt, 2 * Step);                         // a slow frame asks for no more work than two steps
            while (acc >= Step)
            {
                acc -= Step;
                Simulate(n);
            }
            // turn each link so its child point lands on the simulated one
            for (int i = 0; i < n; i++)
            {
                var from = (i + 1 < n ? bones[i + 1].position : bones[i].TransformPoint(tipLocal)) - bones[i].position;
                var to = pos[i + 1] - bones[i].position;
                if (from.sqrMagnitude > 1e-8f && to.sqrMagnitude > 1e-8f)
                    bones[i].rotation = Quaternion.FromToRotation(from, to) * bones[i].rotation;
            }
        }

        static float Distance(Vector3 p, Vector3 a, Vector3 b)
        {
            var ab = b - a;
            float t = Mathf.Clamp01(Vector3.Dot(p - a, ab) / Mathf.Max(ab.sqrMagnitude, 1e-8f));
            return (p - (a + ab * t)).magnitude;
        }

        void Simulate(int n)
        {
            pos[0] = prev[0] = target[0];
            var g = Physics.gravity * (gravity * Step * Step);
            for (int i = 1; i <= n; i++)
            {
                var v = (pos[i] - prev[i]) * (1f - damping);
                prev[i] = pos[i];
                pos[i] += v + g;
                pos[i] += (target[i] - pos[i]) * stiffness;
            }
            for (int it = 0; it < 2; it++)
            {
                foreach (var nb in neighbours)                          // not far from the next columns (each does its half;
                {                                                       // theirs as of their last step)
                    if (nb == null || !nb.live || nb.pos == null || nb.pos.Length != n + 1) continue;
                    for (int i = 1; i <= n; i++)
                    {
                        float max = (target[i] - nb.target[i]).magnitude * stretch;
                        var d = pos[i] - nb.pos[i];
                        float m = d.magnitude;
                        if (m > max && m > 1e-6f) pos[i] -= d * (0.5f * (m - max) / m);
                    }
                }
                for (int i = 1; i <= n; i++)                            // links keep their length
                {
                    var d = pos[i] - pos[i - 1];
                    pos[i] = pos[i - 1] + (d.sqrMagnitude > 1e-10f ? d.normalized : (target[i] - target[i - 1]).normalized) * linkLen[i];
                }
                for (int i = 1; i <= n; i++)                            // and stay out of the body
                    for (int k = 0; k < colliders.Length; k++)
                    {
                        if (!capOn[k]) continue;
                        Vector3 a = capA[k], ab = capB[k] - a;
                        float t = Mathf.Clamp01(Vector3.Dot(pos[i] - a, ab) / Mathf.Max(ab.sqrMagnitude, 1e-8f));
                        var q = a + ab * t;
                        var d = pos[i] - q;
                        float r = capR[i * colliders.Length + k];
                        if (d.sqrMagnitude >= r * r) continue;
                        if (colliders[k].pushBack)
                        {
                            float b = Vector3.Dot(d, back);              // |d + s back| = r
                            pos[i] += back * (Mathf.Sqrt(b * b - d.sqrMagnitude + r * r) - b);
                        }
                        else pos[i] = q + (d.sqrMagnitude > 1e-10f ? d.normalized : -transform.forward) * r;
                    }
                for (int i = 1; i <= n; i++)                            // and outside a skirt's cloth: pushed straight back
                    for (int k = 0; k < ringN; k++)                     // (a skirt's back is broad; pushed off a column's
                    {                                                   // side, the cape swung out sideways at a walk)
                        Vector3 a = ringA[k], ab = ringB[k] - a;
                        float t = Mathf.Clamp01(Vector3.Dot(pos[i] - a, ab) / Mathf.Max(ab.sqrMagnitude, 1e-8f));
                        var d = pos[i] - (a + ab * t);
                        float r = ringR[k] + thickness;
                        if (d.sqrMagnitude >= r * r) continue;
                        float b = Vector3.Dot(d, back);                  // |d + s back| = r
                        pos[i] += back * (Mathf.Sqrt(b * b - d.sqrMagnitude + r * r) - b);
                    }
            }
        }
    }
}
