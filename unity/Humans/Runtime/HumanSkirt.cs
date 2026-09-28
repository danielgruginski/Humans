using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// The skirt ring (xh_skirtNN_hip / _knee / _hem, hum_helpers.RING): columns round the hips, each a link from
    /// the hips to just outside the knees and one on toward the hem. Their knee and hem points are Verlet points
    /// pulled toward a target pose, with gravity, damping and collision capsules on the legs; the links then turn
    /// to follow them. The target hangs in the character's frame; seated (both thighs raised) it follows the
    /// thighs - over the lap, the back tucked under them - and the points stiffen onto it. So a knee or a heel
    /// pushes only the cloth it reaches, and the rest hangs, swings and trails. (Rigid panels turning with the
    /// thighs lifted whole quarters of a skirt when running.)
    /// Runs after the Animator and HumanHelperBones, at a fixed 60 Hz. HumanSetup fills it from human_rig.json;
    /// HumanFace enables it only while a garment with a skirt is worn.
    /// </summary>
    [DefaultExecutionOrder(150)]
    public class HumanSkirt : MonoBehaviour
    {
        [Serializable]
        public struct Column
        {
            public Transform hip, knee, hem;             // the links and the knee link's tip
            public Quaternion hipRest, kneeRest;         // local rotations in the bind pose
            public Vector3 hangHip, hangKnee;            // the links' bind directions in the facing transform's space
            public Vector3 kneeInThighL, kneeInThighR;   // the knee point in each thigh's space (bind pose)
            [Range(0f, 1f)] public float side;           // the left thigh's share of the column (seated)
        }

        [Serializable]
        public struct Capsule
        {
            public Transform a, b;
            [Tooltip("The far end in b's space (zero: b's origin)")] public Vector3 bLocal;
            public float radius;
        }

        public Column[] columns = Array.Empty<Column>();
        [Tooltip("The character's frame: the ring hangs in it")] public Transform facing;
        public Transform thighL, thighR;
        public Quaternion thighLRest, thighRRest;        // bind local rotations: their raise is measured from them
        public Vector3 thighAxisL = Vector3.up, thighAxisR = Vector3.up;   // toward the knee, in the thigh's space
        [Tooltip("Both thighs raised this far (deg, the less raised one): seated - the ring follows the thighs")]
        public Vector2 raise = new Vector2(45f, 70f);

        [Range(0f, 1f), Tooltip("Pull toward the hanging pose per step")] public float stiffness = 0.15f;
        [Range(0f, 1f), Tooltip("Velocity lost per step")] public float damping = 0.08f;
        [Tooltip("Scale of gravity on the points (the target already hangs: more sags the skirt at rest)")]
        public float gravity = 0.3f;
        [Tooltip("Cloth kept off the legs (on top of the capsules: boots, the cloth itself)")] public float thickness = 0.05f;
        [Tooltip("How far the ring's knee and hem points stand off the legs at rest (hum_helpers.RING)")]
        public float clearance = 0.03f;
        [Tooltip("How far the cloth between two columns may stretch past the hanging pose's spacing")]
        public float stretch = 3f;
        [Tooltip("A leg's push fades out over this far past a column's slice")] public float fade = 0.05f;
        [Tooltip("How far the cloth below the knee may stretch (the feet in a running stride are further apart than a " +
                 "dress's hem is wide: rigid, the hem could only swing up round them)")]
        public float elastic = 1.35f;
        [Tooltip("And the cloth from the hips to the knee (a raised knee stretches it forward rather than lifting the hem)")]
        public float elasticHip = 1.25f;
        [Tooltip("A leg's push carries the cloth up by this much of how far out it goes")]
        public float lift = 0.5f;          // (the chain runs 3 cm off the legs; a dress's hem has 2-3 times its girth)
        public Capsule[] colliders = Array.Empty<Capsule>();

        float[] slackHip = Array.Empty<float>(), slackKnee = Array.Empty<float>();
        /// <summary>Per column, how far the worn skirt stands outside the hip / knee link (HumanFace fills them from
        /// the garments): a leg pushes a column only once it reaches the cloth itself.</summary>
        public float[] SlackHip { get { Fit(ref slackHip); return slackHip; } }
        public float[] SlackKnee { get { Fit(ref slackKnee); return slackKnee; } }
        void Fit(ref float[] a) { if (a.Length != columns.Length) a = new float[columns.Length]; }

        const float Step = 1f / 60f;
        Vector3[] p1, p1Prev, p2, p2Prev, t1, t2, root;
        float[] len1, len2;
        float acc;
        bool live;

        void OnEnable() { live = false; }

        void OnDisable()                                                // no skirt worn: the bind pose
        {
            foreach (var c in columns)
            {
                if (c.hip != null) c.hip.localRotation = c.hipRest;
                if (c.knee != null) { c.knee.localRotation = c.kneeRest; c.knee.localScale = Vector3.one; }
            }
            if (kneeRestPos != null)
                for (int i = 0; i < columns.Length && i < kneeRestPos.Length; i++)
            {
                if (columns[i].knee != null) columns[i].knee.localPosition = kneeRestPos[i];
            }
        }

        float Raised(Transform thigh, Quaternion rest, Vector3 axis) =>
            Vector3.Angle(thigh.rotation * axis, thigh.parent.rotation * rest * axis);

        /// <summary>0 standing .. 1 seated (both thighs raised).</summary>
        public float Seated()
        {
            if (thighL == null || thighR == null) return 0f;
            float r = Mathf.Min(Raised(thighL, thighLRest, thighAxisL), Raised(thighR, thighRRest, thighAxisR));
            float u = Mathf.Clamp01((r - raise.x) / Mathf.Max(raise.y - raise.x, 1e-3f));
            return u * u * (3f - 2f * u);
        }

        void LateUpdate()
        {
            int n = columns.Length;
            if (n == 0 || facing == null) return;
            if (p1 == null || p1.Length != n)
            {
                p1 = new Vector3[n]; p1Prev = new Vector3[n]; p2 = new Vector3[n]; p2Prev = new Vector3[n];
                t1 = new Vector3[n]; t2 = new Vector3[n]; root = new Vector3[n];
                len1 = new float[n]; len2 = new float[n];
                live = false;
            }
            // the bind pose on whatever the animation did to the pelvis, then the targets
            for (int c = 0; c < n; c++)
            {
                columns[c].hip.localRotation = columns[c].hipRest;
                columns[c].knee.localRotation = columns[c].kneeRest;
                columns[c].knee.localScale = Vector3.one;
            }
            if (kneeRestPos == null || kneeRestPos.Length != n)            // the knee links' bind offsets on the hip links
            {
                kneeRestPos = new Vector3[n];
                for (int c = 0; c < n; c++) kneeRestPos[c] = columns[c].knee.localPosition;
            }
            for (int c = 0; c < n; c++) columns[c].knee.localPosition = kneeRestPos[c];
            if (kneeAxis == null || kneeAxis.Length != n)                  // each knee link's axis in its own space
            {
                kneeAxis = new int[n];
                for (int c = 0; c < n; c++)
                {
                    var ax = columns[c].knee.InverseTransformDirection(columns[c].hem.position - columns[c].knee.position);
                    float x = Mathf.Abs(ax.x), y = Mathf.Abs(ax.y), z = Mathf.Abs(ax.z);
                    kneeAxis[c] = x >= y && x >= z ? 0 : y >= z ? 1 : 2;
                }
            }
            float k = Seated();
            var fr = facing.rotation;
            var hips = Vector3.zero;
            for (int c = 0; c < n; c++) hips += columns[c].hip.position;
            hips /= n;
            var slackHip = SlackHip;
            for (int c = 0; c < n; c++)
            {
                var col = columns[c];
                Vector3 p0 = col.hip.position, k0 = col.knee.position, h0 = col.hem.position;
                float l1 = (k0 - p0).magnitude, l2 = (h0 - k0).magnitude;
                var a = p0 + fr * col.hangHip * l1;
                var b = a + fr * col.hangKnee * l2;
                if (k > 0f)
                {
                    var s = Vector3.Lerp(thighR.TransformPoint(col.kneeInThighR), thighL.TransformPoint(col.kneeInThighL), col.side);
                    // the cloth, not the chain, onto the thighs: turned with the link, the cloth's outward offset (its
                    // slack) stood a short skirt up over the lap like a tray. Aim so that offset lands on the point
                    var rest = fr * col.hangHip;
                    var turn = Quaternion.FromToRotation(rest, (s - p0).normalized);
                    var o = Vector3.ProjectOnPlane(p0 - hips, facing.up).normalized;
                    if (slackHip[c] < 0.5f) s -= turn * o * slackHip[c];
                    s = p0 + (s - p0).normalized * l1;
                    a = Vector3.Lerp(a, s, k);
                    b = Vector3.Lerp(b, s + fr * col.hangKnee * l2, k);
                }
                root[c] = p0; t1[c] = a; t2[c] = b; len1[c] = l1; len2[c] = l2;
            }
            if (!live || (p1[0] - t1[0]).sqrMagnitude > 1f)              // first frame or a teleport
            {
                Array.Copy(t1, p1, n); Array.Copy(t1, p1Prev, n);
                Array.Copy(t2, p2, n); Array.Copy(t2, p2Prev, n);
                acc = 0f;
                live = true;
            }
            acc = Mathf.Min(acc + Time.deltaTime, 4 * Step);
            float stiff = Mathf.Lerp(stiffness, 1f, k);
            seated = k;
            while (acc >= Step)
            {
                acc -= Step;
                Simulate(n, stiff);
            }
            // turn each link so its tip lands on its simulated point
            for (int c = 0; c < n; c++)
            {
                var col = columns[c];
                var from = col.knee.position - root[c];
                var to = p1[c] - root[c];
                if (from.sqrMagnitude > 1e-10f && to.sqrMagnitude > 1e-10f)
                {
                    col.hip.rotation = Quaternion.FromToRotation(from, to) * col.hip.rotation;
                    // the knee link slides out along it to its point: the cloth through the knee stretches instead of
                    // the hip link swinging up to reach (a raised knee lifted the whole front hem)
                    float st = to.magnitude / from.magnitude;
                    if (st > 1.001f) col.knee.localPosition = kneeRestPos[c] * st;
                }
                var kp = col.knee.position;
                from = col.hem.position - kp;
                to = p2[c] - kp;
                if (from.sqrMagnitude > 1e-10f && to.sqrMagnitude > 1e-10f)
                {
                    col.knee.rotation = Quaternion.FromToRotation(from, to) * col.knee.rotation;
                    // the cloth below the knee stretches to reach its point (elastic: a heel pushes it out at hem
                    // height instead of swinging it up)
                    float st = to.magnitude / from.magnitude;
                    if (st > 1.001f)
                    {
                        var sc = Vector3.one;
                        sc[kneeAxis[c]] = st;
                        col.knee.localScale = sc;
                    }
                }
            }
        }

        float seated;
        int[] kneeAxis;
        Vector3[] kneeRestPos;

        void Simulate(int n, float stiff)
        {
            var g = Physics.gravity * (gravity * Step * Step);
            for (int c = 0; c < n; c++)
            {
                Integrate(ref p1[c], ref p1Prev[c], t1[c], g, stiff);
                Integrate(ref p2[c], ref p2Prev[c], t2[c], g, stiff);
            }
            // each column's outward direction round the hips (level): the way a leg pushes that cloth
            var up = facing.up;
            var centre = Vector3.zero;
            for (int c = 0; c < n; c++) centre += root[c];
            centre /= n;
            for (int it = 0; it < 3; it++)
            {
                for (int c = 0; c < n; c++)
                {
                    var o = Vector3.ProjectOnPlane(t1[c] - centre, up).normalized;
                    // both links are elastic (they stretch rather than swing up round a leg), never shorter
                    var d1 = p1[c] - root[c];
                    p1[c] = root[c] + Dir(d1, t1[c] - root[c]) * Mathf.Clamp(d1.magnitude, len1[c], len1[c] * elasticHip);
                    var d2 = p2[c] - p1[c];
                    p2[c] = p1[c] + Dir(d2, t2[c] - t1[c]) * Mathf.Clamp(d2.magnitude, len2[c], len2[c] * elastic);
                    // and stay off the legs: the hip link first (the knee link rides its push), then the knee link
                    var before = p1[c];
                    Collide(root[c], ref p1[c], t1[c] - root[c], o, 0.6f, SlackHip[c], centre, up, 1f - seated);
                    p2[c] += p1[c] - before;
                    Collide(p1[c], ref p2[c], t2[c] - t1[c], o, 0.2f, SlackKnee[c], centre, up, 1f - seated);
                }
                // the cloth between neighbouring columns doesn't stretch: a column a knee pushes drags its
                // neighbours along (a tent over the knee, not a slit beside it)
                for (int c = 0; c < n; c++)
                {
                    int d = (c + 1) % n;
                    Limit(ref p1[c], ref p1[d], (t1[c] - t1[d]).magnitude * stretch);
                    Limit(ref p2[c], ref p2[d], (t2[c] - t2[d]).magnitude * stretch);
                }
            }
            // the legs have the last word (the neighbours' pull had drawn a pushed column back into the heel)
            for (int c = 0; c < n; c++)
            {
                var o = Vector3.ProjectOnPlane(t1[c] - centre, up).normalized;
                var before = p1[c];
                Collide(root[c], ref p1[c], t1[c] - root[c], o, 0.6f, SlackHip[c], centre, up, 1f - seated);
                p2[c] += p1[c] - before;
                Collide(p1[c], ref p2[c], t2[c] - t1[c], o, 0.2f, SlackKnee[c], centre, up, 1f - seated);
            }
        }

        static void Limit(ref Vector3 a, ref Vector3 b, float max)
        {
            var d = b - a;
            float m = d.magnitude;
            if (m <= max || m < 1e-8f) return;
            var fix = d * (0.5f * (m - max) / m);
            a += fix;
            b -= fix;
        }

        void Integrate(ref Vector3 p, ref Vector3 prev, Vector3 target, Vector3 g, float stiff)
        {
            var v = (p - prev) * (1f - damping);
            prev = p;
            p += v + g;
            p += (target - p) * stiff;
        }

        static Vector3 Dir(Vector3 d, Vector3 fallback) =>
            d.sqrMagnitude > 1e-10f ? d.normalized : fallback.normalized;

        /// <summary>Keep the cloth of column c's link a -> tip outside the legs. Each column owns a slice of the ring
        /// (360 / n degrees round the hips); for three points from `from` to the tip (the hip link only from 0.6
        /// down: its top sits on the flesh the thigh capsule's top overlaps), a leg capsule's nearest point at that
        /// height inside the slice (fading out over `fade` past it) reaches out along o, the column's outward
        /// direction, to its distance + radius: the cloth there (the point + the garment's slack) must reach
        /// further, or the point moves out along o - the tip by that push / t. One-sided and by slice, so a shin a
        /// heel strike swung past the hem in one frame, or a heel kicked up between two columns, still pushes the
        /// cloth out (a leg pushed straight out from its axis parted two columns and came out between them; a
        /// point test missed a heel between two columns).</summary>
        void Collide(Vector3 a, ref Vector3 tip, Vector3 hang, Vector3 o, float from, float slack, Vector3 centre, Vector3 up, float scale)
        {
            if (scale <= 0f) return;
            float slice = Mathf.Tan(Mathf.PI / Mathf.Max(columns.Length, 3));
            // the cloth stands slack out from the link at right angles to it: tilted from hanging, less of that
            // is outward (a knee link pushed back by a heel tips the cloth's offset up)
            float tilt = Mathf.Max(Vector3.Dot(Dir(tip - a, hang), hang.normalized), 0.3f);
            // the legs count as thicker by `thickness` (boots, and the cloth's own), but never so thick that they
            // reach the cloth standing still: at most the chain's gap plus the garment's slack, less 2 cm (the
            // capsules are a boot's size, ~1 cm over the leg the chain was measured on). A thicker margin on the tight
            // sides of a dress pushed them out standing still - the skirt flew
            float margin = Mathf.Max(Mathf.Min(thickness, clearance + slack - 0.02f), 0f);
            for (int s = 0; s < 3; s++)
            {
                float t = Mathf.Lerp(from, 1f, s / 2f);
                var q = a + (tip - a) * t;
                foreach (var cap in colliders)
                {
                    if (cap.a == null || cap.b == null) continue;
                    Vector3 ca = cap.a.position, cb = cap.bLocal == Vector3.zero ? cap.b.position : cap.b.TransformPoint(cap.bLocal);
                    var ab = cb - ca;
                    float u = Mathf.Clamp01(Vector3.Dot(q - ca, ab) / Mathf.Max(ab.sqrMagnitude, 1e-8f));
                    var A = ca + ab * u;
                    float r = cap.radius + margin;
                    if (Mathf.Abs(Vector3.Dot(q - A, up)) > r) continue;          // not at this height
                    var h = Vector3.ProjectOnPlane(A - centre, up);
                    float along = Vector3.Dot(h, o);
                    if (along <= 0f) continue;                                    // the other side
                    float lat = (h - o * along).magnitude;
                    float half = along * slice + r;
                    if (lat >= half + fade) continue;                             // another column's slice
                    float k = lat <= half ? 1f : 1f - (lat - half) / fade;
                    float reach = along + r;
                    float cloth = Vector3.Dot(Vector3.ProjectOnPlane(q - centre, up), o) + slack * tilt;
                    if (cloth >= reach) continue;
                    // out, and up by `lift` of that: the leg catches the cloth and carries it up over itself (the feet
                    // in a running stride are further apart than the hem is wide: it has to rise, not only stretch)
                    var push = (o + up * lift) * ((reach - cloth) * k * scale);
                    tip += push / t;
                    q += push;
                }
            }
        }
    }
}
