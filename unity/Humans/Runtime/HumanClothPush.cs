using System;
using System.Collections.Generic;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Cloth kept out of the limbs on the GPU (2026-10-28, Daniel: after the cape and skirt sims, arms, a shield and a
    /// raised thigh still showed through in places - "the fix improved the situation, but did not solve the issue"). The
    /// Humans/Cloth vertex stage pushes a garment's vertex out of each limb's capsule (tapered, as thick as the clothes
    /// worn on that limb) and out of held props' (a shield: <see cref="SetProp"/>) - by how far it sank in beyond where
    /// it lay at rest (the garment's rest position, uv2/uv3, against the limb's rest capsule), so cloth that hugs the hips
    /// or lies on the shoulders at rest never moves: only what the motion pushed in comes back out. A cloak pushes with all
    /// its vertices against the arms, the legs and the props; a garment that hangs (a skirt) with its hanging part against
    /// the legs. HumanFace refits it when the clothes change (from the pieces' <see cref="HumanPiece.LimbFit"/>, measured
    /// at setup: a build's meshes aren't readable); it writes the capsules after the sims each frame (execution order 300,
    /// after HumanSkirt, the cape's chains and a game's held props). The same capsules keep a simulated cloak
    /// (<see cref="HumanClothSim"/>, spike) out: <see cref="Capsules"/>.
    /// </summary>
    [DefaultExecutionOrder(300)]
    public class HumanClothPush : MonoBehaviour
    {
        public const int Max = 16;

        [Serializable]
        public struct Limb
        {
            public Transform a, b;                        // the limb's bone and its child (the far end)
            public bool arm;                              // an arm's (a cloak is pushed off it; a skirt only off the legs)
        }

        [Tooltip("Upper arm, forearm, hand (each side), thigh, shin (each side): HumanSetup fills them")]
        public Limb[] limbs = Array.Empty<Limb>();
        [Tooltip("The bare body's thickness round each limb (the neutral body, at setup)")]
        public HumanPiece.LimbFit[] body = Array.Empty<HumanPiece.LimbFit>();
        [Tooltip("The limbs' ends in the bind pose (Blender axes, neutral build), as the garments' rest positions")]
        [SerializeField] Vector3[] bindA = Array.Empty<Vector3>(), bindB = Array.Empty<Vector3>();
        [Tooltip("Kept between a limb's clothes and the garment pushed off them (m)")]
        public float margin = 0.006f;

        struct Fitted { public float ra, rb; public Vector3 restA, restB; }   // rest metres; rest ends in Blender axes
        Fitted[] fitted = Array.Empty<Fitted>();
        readonly List<(Renderer r, bool cloak)> pushers = new List<(Renderer, bool)>();
        readonly Dictionary<string, (Transform a, Transform b, float r)[]> props = new Dictionary<string, (Transform, Transform, float)[]>();
        readonly Vector4[] nowA = new Vector4[Max], nowB = new Vector4[Max], restA = new Vector4[Max], restB = new Vector4[Max];
        MaterialPropertyBlock mpb;

        static readonly int IdA = Shader.PropertyToID("_PushA"), IdB = Shader.PropertyToID("_PushB"),
            IdRestA = Shader.PropertyToID("_PushRestA"), IdRestB = Shader.PropertyToID("_PushRestB"),
            IdN = Shader.PropertyToID("_PushN"), IdAll = Shader.PropertyToID("_PushAll"), IdScale = Shader.PropertyToID("_PushScale");

        /// <summary>The limbs' bones (a, b) and whether each is an arm, as HumanSetup lays them out.</summary>
        public static readonly (string a, string b, bool arm)[] Layout =
        {
            ("upperarm_l", "lowerarm_l", true), ("lowerarm_l", "hand_l", true), ("hand_l", "middle_01_l", true),
            ("upperarm_r", "lowerarm_r", true), ("lowerarm_r", "hand_r", true), ("hand_r", "middle_01_r", true),
            ("thigh_l", "calf_l", false), ("calf_l", "foot_l", false),
            ("thigh_r", "calf_r", false), ("calf_r", "foot_r", false),
        };

        /// <summary>A held prop's capsules (world radius; null: none): a cloak is pushed off them as off the arms.</summary>
        public void SetProp(string key, (Transform a, Transform b, float r)[] caps)
        {
            if (caps == null || caps.Length == 0) props.Remove(key); else props[key] = caps;
        }

        /// <summary>The worn garments' renderers (cloaks push with every vertex, hanging garments with their hanging part)
        /// and the limbs' capsules: as thick as the thickest worn piece round each (cloaks never count), the bare body
        /// where nothing is worn.</summary>
        public void Refit(IList<(Renderer r, HumanPiece piece, bool cloak, bool hangs)> worn)
        {
            pushers.Clear();
            foreach (var w in worn)
                if (w.r != null && (w.cloak || w.hangs)) pushers.Add((w.r, w.cloak));
            fitted = new Fitted[limbs.Length];
            for (int k = 0; k < limbs.Length; k++)
            {
                if (limbs[k].a == null) continue;
                string bone = limbs[k].a.name;
                var f = new Fitted();
                var off = Vector3.zero;
                bool hasOff = false;
                var b = Find(body, bone);
                if (b != null && b.count > 0) { f.ra = b.ra; f.rb = b.rb; }
                var seen = new HashSet<HumanPiece>();
                foreach (var w in worn)
                {
                    if (w.cloak || w.piece == null || !seen.Add(w.piece)) continue;
                    var p = Find(w.piece.limbs, bone);
                    if (p == null || p.count == 0) continue;
                    f.ra = Mathf.Max(f.ra, p.ra);
                    f.rb = Mathf.Max(f.rb, p.rb);
                    if (!hasOff) { off = p.offset; hasOff = true; }
                }
                f.ra += margin; f.rb += margin;
                // the rest capsule: the bind ends moved by the build's offset of the bone (the far end's own is near it)
                f.restA = (k < bindA.Length ? bindA[k] : Vector3.zero) + off;
                f.restB = (k < bindB.Length ? bindB[k] : Vector3.zero) + off;
                fitted[k] = f;
            }
        }

        static HumanPiece.LimbFit Find(HumanPiece.LimbFit[] fits, string bone)
        {
            if (fits == null) return null;
            foreach (var f in fits) if (f != null && f.bone == bone) return f;
            return null;
        }

        void LateUpdate()
        {
            if (pushers.Count > 0) Apply();
        }

        /// <summary>The capsules where the pose put them, onto each pushing renderer (LateUpdate's; a check tool's own).</summary>
        public void Apply()
        {
            mpb ??= new MaterialPropertyBlock();
            float scale = limbs.Length > 0 && limbs[0].a != null ? limbs[0].a.lossyScale.x : 1f;
            foreach (var (r, cloak) in pushers)
            {
                if (r == null || !r.gameObject.activeInHierarchy) continue;
                int n = 0;
                for (int k = 0; k < limbs.Length && n < Max; k++)
                {
                    var L = limbs[k];
                    if (L.a == null || L.b == null || fitted.Length <= k || fitted[k].rb <= 0f) continue;
                    if (L.arm && !cloak) continue;                       // a skirt is pushed off the legs only
                    var f = fitted[k];
                    nowA[n] = new Vector4(L.a.position.x, L.a.position.y, L.a.position.z, f.ra * scale);
                    nowB[n] = new Vector4(L.b.position.x, L.b.position.y, L.b.position.z, f.rb * scale);
                    restA[n] = new Vector4(f.restA.x, f.restA.y, f.restA.z, f.ra);
                    restB[n] = new Vector4(f.restB.x, f.restB.y, f.restB.z, f.rb);
                    n++;
                }
                if (cloak)
                    foreach (var caps in props.Values)
                        foreach (var (a, b, rad) in caps)
                        {
                            if (n >= Max || a == null || b == null) continue;
                            nowA[n] = new Vector4(a.position.x, a.position.y, a.position.z, rad);
                            nowB[n] = new Vector4(b.position.x, b.position.y, b.position.z, rad);
                            restA[n] = restB[n] = Vector4.zero;          // a prop has no rest: all of it pushes
                            n++;
                        }
                for (int k = n; k < Max; k++) nowA[k] = nowB[k] = restA[k] = restB[k] = Vector4.zero;
                r.GetPropertyBlock(mpb);                                 // HumanFace's colours stay
                mpb.SetVectorArray(IdA, nowA);
                mpb.SetVectorArray(IdB, nowB);
                mpb.SetVectorArray(IdRestA, restA);
                mpb.SetVectorArray(IdRestB, restB);
                mpb.SetFloat(IdN, n);
                mpb.SetFloat(IdAll, cloak ? 1f : 0f);
                mpb.SetFloat(IdScale, scale);
                r.SetPropertyBlock(mpb);
            }
        }

        /// <summary>The capsules where the pose put them (world ends, radius in w), for <see cref="HumanClothSim"/>: the
        /// limbs (the arms only when <paramref name="arms"/>: a cloak's, not a skirt's), then the held props' (with the
        /// arms).</summary>
        public void Capsules(List<Vector4> a, List<Vector4> b, bool arms)
        {
            a.Clear(); b.Clear();
            float scale = limbs.Length > 0 && limbs[0].a != null ? limbs[0].a.lossyScale.x : 1f;
            for (int k = 0; k < limbs.Length; k++)
            {
                var L = limbs[k];
                if (L.a == null || L.b == null || fitted.Length <= k || fitted[k].rb <= 0f || (L.arm && !arms)) continue;
                a.Add(new Vector4(L.a.position.x, L.a.position.y, L.a.position.z, fitted[k].ra * scale));
                b.Add(new Vector4(L.b.position.x, L.b.position.y, L.b.position.z, fitted[k].rb * scale));
            }
            if (!arms) return;
            foreach (var caps in props.Values)
                foreach (var (pa, pb, rad) in caps)
                {
                    if (pa == null || pb == null) continue;
                    a.Add(new Vector4(pa.position.x, pa.position.y, pa.position.z, rad));
                    b.Add(new Vector4(pb.position.x, pb.position.y, pb.position.z, rad));
                }
        }

#if UNITY_EDITOR
        /// <summary>Setup (the meshes are readable in the editor): how thick a renderer's mesh is round each limb in the bind
        /// pose - the vertices riding the limb's bone (weight 0.8+; never a hanging part, uv1.x = 0), radii near each end
        /// (the 90th percentile: cuffs and folds stay out), the build's offset of the bone (rest uv2/uv3 less the mesh), and
        /// the limb's bind ends (Blender axes, neutral).</summary>
        public static HumanPiece.LimbFit[] Fit(SkinnedMeshRenderer smr, out Vector3[] endA, out Vector3[] endB, float pct = 0.9f)
        {
            var fits = new HumanPiece.LimbFit[Layout.Length];
            endA = new Vector3[Layout.Length];
            endB = new Vector3[Layout.Length];
            var mesh = smr.sharedMesh;
            var v = mesh.vertices;
            var bw = mesh.boneWeights;
            var bp = mesh.bindposes;
            var names = Array.ConvertAll(smr.bones, b => b != null ? b.name : "");
            var uv1 = new List<Vector2>(); mesh.GetUVs(1, uv1);
            var uv2 = new List<Vector2>(); mesh.GetUVs(2, uv2);
            var uv3 = new List<Vector2>(); mesh.GetUVs(3, uv3);
            bool region = uv1.Count == v.Length, rest = uv2.Count == v.Length && uv3.Count == v.Length;
            for (int k = 0; k < Layout.Length; k++)
            {
                var (a, b, _) = Layout[k];
                var fit = new HumanPiece.LimbFit { bone = a };
                fits[k] = fit;
                int ia = Array.IndexOf(names, a), ib = Array.IndexOf(names, b);
                if (ia < 0 || ib < 0) continue;
                Vector3 oa = bp[ia].inverse.GetColumn(3), ob = bp[ib].inverse.GetColumn(3);
                endA[k] = Blender(oa); endB[k] = Blender(ob);
                var end = bp[ia].MultiplyPoint3x4(ob);                   // the far end in the bone's bind space
                float len2 = Mathf.Max(end.sqrMagnitude, 1e-8f);
                var nearA = new List<float>(); var nearB = new List<float>();
                var off = Vector3.zero; int offN = 0;
                for (int i = 0; i < v.Length; i++)
                {
                    float w = Weight(bw[i], ia);
                    if (w < 0.8f) continue;
                    if (region && Mathf.RoundToInt(uv1[i].x) == 0 && smr.name.StartsWith("Cloth_")) continue;
                    var p = bp[ia].MultiplyPoint3x4(v[i]);
                    float t = Mathf.Clamp01(Vector3.Dot(p, end) / len2);
                    float r = (p - end * t).magnitude;
                    if (t < 0.45f) nearA.Add(r);
                    if (t > 0.55f) nearB.Add(r);
                    if (rest && w > 0.98f) { off += new Vector3(uv2[i].x, uv2[i].y, uv3[i].x) - Blender(v[i]); offN++; }
                }
                fit.count = nearA.Count + nearB.Count;
                fit.ra = Pct(nearA, pct);
                fit.rb = Pct(nearB, pct);
                if (nearA.Count == 0) fit.ra = fit.rb;
                if (nearB.Count == 0) fit.rb = fit.ra;
                fit.offset = offN > 0 ? off / offN : Vector3.zero;
            }
            return fits;
        }

        static float Pct(List<float> v, float pct)
        {
            if (v.Count == 0) return 0f;
            v.Sort();
            return v[Mathf.Clamp(Mathf.RoundToInt(pct * (v.Count - 1)), 0, v.Count - 1)];
        }

        /// <summary>HumanSetup: the limbs from the bone map and the bare body's fit.</summary>
        public void Setup(Func<string, Transform> bone, SkinnedMeshRenderer bodyLod0)
        {
            limbs = Array.ConvertAll(Layout, l => new Limb { a = bone(l.a), b = bone(l.b), arm = l.arm });
            body = bodyLod0 != null ? Fit(bodyLod0, out bindA, out bindB) : Array.Empty<HumanPiece.LimbFit>();
        }
#endif

        static float Weight(BoneWeight w, int bi) =>
            (w.boneIndex0 == bi ? w.weight0 : 0f) + (w.boneIndex1 == bi ? w.weight1 : 0f) +
            (w.boneIndex2 == bi ? w.weight2 : 0f) + (w.boneIndex3 == bi ? w.weight3 : 0f);

        /// <summary>a mesh-space point (Unity's import of the Blender mesh: x mirrored) in Blender's axes, as uv2/uv3</summary>
        static Vector3 Blender(Vector3 p) => new Vector3(-p.x, p.y, p.z);
    }
}
