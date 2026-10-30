using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Humans
{
    /// <summary>
    /// A cloak simulated on the GPU (spike D, 2026-10-28: Daniel's pick after the stateless push-out didn't lower the
    /// pokes). The cloak as skinned - its own bones, the cape's chains among them - is the target: each particle (a
    /// welded vertex) follows it with a damped offset, keeps the target's edge and bend lengths, stays within its max
    /// distance of it (about 0 where the cloak rides the body, more down the cape), and is pushed out of the limbs' and
    /// held props' capsules (<see cref="HumanClothPush"/>; the cape only) and off the worn layers under it (the nearest
    /// skinned point of the shirt, the tunic, the body where it shows). HumanClothSim.compute does the work; Humans/Cloth
    /// draws the result (_SimOut, a position and a normal per mesh vertex, world space) in place of its skinning. Runs
    /// after the chains and the helper bones (execution order 310).
    /// </summary>
    [DefaultExecutionOrder(310)]
    public class HumanClothSim : MonoBehaviour
    {
        /// <summary>A simulated garment, from its LOD0 mesh (<see cref="BuildCloth"/>).</summary>
        [Serializable]
        public class Cloth
        {
            public string[] bones = Array.Empty<string>();        // the bones it is skinned to, by name
            public Matrix4x4[] bindposes = Array.Empty<Matrix4x4>();
            public Vector4[] rest = Array.Empty<Vector4>();        // a particle: mesh space, w = max distance (m)
            public Vector4[] restN = Array.Empty<Vector4>();       // normal, w = 1 kept out of the capsules (hangs)
            public int[] skinI = Array.Empty<int>();               // 4 a particle, into bones
            public Vector4[] skinW = Array.Empty<Vector4>();
            public int[] vertParticle = Array.Empty<int>();        // mesh vertex -> particle
            public int[] linkStart = Array.Empty<int>(), linkOther = Array.Empty<int>();
            public float[] linkW = Array.Empty<float>();           // edges 1, bends (across an edge) 0.5
            public int[] tris = Array.Empty<int>(), triStart = Array.Empty<int>(), triList = Array.Empty<int>();
            public float normalSign = 1f;                          // the triangles' winding against the mesh normals
        }

        /// <summary>A worn layer the cloth stays outside: points sampled over its LOD0 (<see cref="BuildLayer"/>).</summary>
        [Serializable]
        public class Layer
        {
            public string[] bones = Array.Empty<string>();
            public Matrix4x4[] bindposes = Array.Empty<Matrix4x4>();
            public Vector4[] rest = Array.Empty<Vector4>();        // mesh space, w = body region (uv1.x: hidden ones skip)
            public Vector3[] restN = Array.Empty<Vector3>();
            public int[] skinI = Array.Empty<int>();
            public Vector4[] skinW = Array.Empty<Vector4>();
        }

        public ComputeShader shader;
        // Defaults tuned 2026-10-28 on MStrong in tunic + cloak + plank shield (MedievalSetting ClothPokeCheck: points out
        // of the cloak per frame over run, combat stance, two attacks: skinned 46, push-out 32, this 26)
        [Header("Motion")]
        public int substeps = 6;
        [Tooltip("Jacobi passes (pairs) a substep")] public int iterations = 4;
        [Tooltip("Of the offset's speed, lost a substep")] public float damping = 0.3f;
        [Tooltip("Of the offset, eased back to the target a substep")] public float stiffness = 0.08f;
        public float omega = 1f;
        [Header("Collision")]
        [Tooltip("Kept in front of a layer (m)")] public float gap = 0.008f;
        [Tooltip("Deeper behind a layer's point than this: another part of it, left alone (m)")] public float deep = 0.06f;
        [Tooltip("A layer point farther than this isn't the one under the particle (m)")] public float reach = 0.06f;
        [Tooltip("Added to the capsules' radii (m; below 0: the fits are generous, the cape lies inside them at rest)")]
        public float skin = -0.02f;

        public bool Bound => cloth != null;

        struct I4 { public int x, y, z, w; }

        SkinnedMeshRenderer cloth;
        Cloth data;
        HumanClothPush colliders;
        Transform[] bones = Array.Empty<Transform>();
        Matrix4x4[] bindposes = Array.Empty<Matrix4x4>(), palette = Array.Empty<Matrix4x4>();
        int nParticle, nVertex, nLayer, nCaps;
        bool first = true;
        readonly List<GraphicsBuffer> owned = new List<GraphicsBuffer>();
        GraphicsBuffer bBones, bPos, bPos2, bCaps, bOut;
        readonly List<Vector4> capA = new List<Vector4>(), capB = new List<Vector4>();
        Vector4[] caps = new Vector4[4], capsLast = new Vector4[0];
        MaterialPropertyBlock mpb;
        int kSkinCloth, kSkinLayer, kBegin, kIntegrate, kLinks, kCollide, kNormals, kOutput;
        static GraphicsBuffer dummy;

        static readonly int IdOut = Shader.PropertyToID("_SimOut"), IdOn = Shader.PropertyToID("_SimOn"),
            IdHide = Shader.PropertyToID("_Hide"), IdPos = Shader.PropertyToID("_Pos"), IdPos2 = Shader.PropertyToID("_Pos2");

        /// <summary>Simulates <paramref name="r"/> (its LOD0) from <paramref name="d"/>, kept off <paramref name="layers"/>
        /// (their shown regions: the renderer's _Hide) and the capsules of <paramref name="caps"/>.</summary>
        public void Bind(SkinnedMeshRenderer r, Cloth d, IList<(SkinnedMeshRenderer r, Layer d)> layers, HumanClothPush caps)
        {
            Unbind();
            if (r == null || d == null || d.rest.Length == 0 || shader == null) return;
            mpb ??= new MaterialPropertyBlock();
            cloth = r; data = d; colliders = caps;
            var bl = new List<Transform>();
            var bp = new List<Matrix4x4>();
            Add(r, d.bones, d.bindposes, bl, bp);
            var lRest = new List<Vector4>(); var lN = new List<Vector4>();
            var lI = new List<I4>(); var lW = new List<Vector4>();
            if (layers != null)
                foreach (var (lr, ld) in layers)
                {
                    if (lr == null || ld == null || !lr.gameObject.activeInHierarchy) continue;
                    lr.GetPropertyBlock(mpb);
                    int hide = (int)mpb.GetFloat(IdHide);
                    int off = bl.Count;
                    Add(lr, ld.bones, ld.bindposes, bl, bp);
                    for (int i = 0; i < ld.rest.Length; i++)
                    {
                        if (((hide >> Mathf.RoundToInt(ld.rest[i].w)) & 1) != 0) continue;
                        lRest.Add(new Vector4(ld.rest[i].x, ld.rest[i].y, ld.rest[i].z, 1));
                        lN.Add(ld.restN[i]);
                        lI.Add(new I4 { x = ld.skinI[i * 4] + off, y = ld.skinI[i * 4 + 1] + off, z = ld.skinI[i * 4 + 2] + off, w = ld.skinI[i * 4 + 3] + off });
                        lW.Add(ld.skinW[i]);
                    }
                }
            bones = bl.ToArray();
            bindposes = bp.ToArray();
            palette = new Matrix4x4[bones.Length];
            nParticle = d.rest.Length;
            nVertex = d.vertParticle.Length;
            nLayer = lRest.Count;
            var skinI = new I4[nParticle];
            for (int i = 0; i < nParticle; i++)
                skinI[i] = new I4 { x = d.skinI[i * 4], y = d.skinI[i * 4 + 1], z = d.skinI[i * 4 + 2], w = d.skinI[i * 4 + 3] };

            kSkinCloth = shader.FindKernel("SkinCloth"); kSkinLayer = shader.FindKernel("SkinLayer");
            kBegin = shader.FindKernel("Begin"); kIntegrate = shader.FindKernel("Integrate");
            kLinks = shader.FindKernel("Links"); kCollide = shader.FindKernel("Collide");
            kNormals = shader.FindKernel("Normals"); kOutput = shader.FindKernel("Output");

            bBones = Buf(palette, 64);
            var bRest = Buf(d.rest, 16); var bRestN = Buf(d.restN, 16);
            var bSkinI = Buf(skinI, 16); var bSkinW = Buf(d.skinW, 16);
            var bTarget = New(nParticle, 16); var bTargetPrev = New(nParticle, 16); var bTargetN = New(nParticle, 16);
            bPos = New(nParticle, 16); bPos2 = New(nParticle, 16);
            var bOff = New(nParticle, 16); var bNear = New(nParticle, 4);
            var bLinkStart = Buf(d.linkStart, 4); var bLinkOther = Buf(d.linkOther, 4); var bLinkW = Buf(d.linkW, 4);
            var bTriStart = Buf(d.triStart, 4); var bTriList = Buf(d.triList, 4); var bTris = Buf(d.tris, 4);
            var bNormal = New(nParticle, 16);
            var bVert = Buf(d.vertParticle, 4);
            bOut = New(nVertex * 2, 16);
            var bLRest = Buf(lRest.ToArray(), 16); var bLN = Buf(lN.ToArray(), 16);
            var bLI = Buf(lI.ToArray(), 16); var bLW = Buf(lW.ToArray(), 16);
            var bLPos = New(Mathf.Max(nLayer, 1), 16); var bLNrm = New(Mathf.Max(nLayer, 1), 16);
            bCaps = New(64, 16);

            void Set(int k, string name, GraphicsBuffer b) => shader.SetBuffer(k, name, b);
            foreach (var k in new[] { kSkinCloth, kSkinLayer, kBegin, kIntegrate, kLinks, kCollide, kNormals, kOutput })
            {
                Set(k, "_Bones", bBones);
                Set(k, "_Rest", bRest); Set(k, "_RestN", bRestN); Set(k, "_SkinI", bSkinI); Set(k, "_SkinW", bSkinW);
                Set(k, "_Target", bTarget); Set(k, "_TargetPrev", bTargetPrev); Set(k, "_TargetN", bTargetN);
                Set(k, "_Pos", bPos); Set(k, "_Pos2", bPos2); Set(k, "_Off", bOff); Set(k, "_Near", bNear);
                Set(k, "_LinkStart", bLinkStart); Set(k, "_LinkOther", bLinkOther); Set(k, "_LinkW", bLinkW);
                Set(k, "_TriStart", bTriStart); Set(k, "_TriList", bTriList); Set(k, "_Tris", bTris);
                Set(k, "_Normal", bNormal); Set(k, "_VertParticle", bVert); Set(k, "_Out", bOut);
                Set(k, "_LRest", bLRest); Set(k, "_LRestN", bLN); Set(k, "_LSkinI", bLI); Set(k, "_LSkinW", bLW);
                Set(k, "_LPos", bLPos); Set(k, "_LNrm", bLNrm); Set(k, "_Caps", bCaps);
            }
            first = true;
            capsLast = Array.Empty<Vector4>();
        }

        static void Add(SkinnedMeshRenderer r, string[] names, Matrix4x4[] binds, List<Transform> bl, List<Matrix4x4> bp)
        {
            var by = new Dictionary<string, Transform>();
            foreach (var b in r.bones) if (b != null) by[b.name] = b;
            for (int k = 0; k < names.Length; k++)
            {
                by.TryGetValue(names[k], out var t);
                bl.Add(t != null ? t : r.rootBone);
                bp.Add(binds[k]);
            }
        }

        GraphicsBuffer New(int count, int stride)
        {
            var b = new GraphicsBuffer(GraphicsBuffer.Target.Structured, Mathf.Max(count, 1), stride);
            owned.Add(b);
            return b;
        }

        GraphicsBuffer Buf<T>(T[] values, int stride) where T : struct
        {
            var b = New(values.Length, stride);
            if (values.Length > 0) b.SetData(values);
            return b;
        }

        /// <summary>Stops simulating: the renderer draws its skinning again.</summary>
        public void Unbind()
        {
            if (cloth != null)
            {
                mpb ??= new MaterialPropertyBlock();
                cloth.GetPropertyBlock(mpb);
                mpb.SetFloat(IdOn, 0f);
                cloth.SetPropertyBlock(mpb);
            }
            foreach (var b in owned) b?.Release();
            owned.Clear();
            cloth = null; data = null;
        }

        void OnDisable() => Unbind();

        void LateUpdate()
        {
#if UNITY_EDITOR
            if (following != null && !rebinding && Stale()) Rebind();
#endif
            if (cloth != null) Tick(Time.deltaTime);
        }

        /// <summary>One frame (LateUpdate's; a check tool's own after posing).</summary>
        public void Tick(float dt)
        {
            if (cloth == null || shader == null || !cloth.gameObject.activeInHierarchy) return;
            for (int k = 0; k < bones.Length; k++)
                palette[k] = bones[k] != null ? bones[k].localToWorldMatrix * bindposes[k] : Matrix4x4.identity;
            bBones.SetData(palette);

            if (colliders != null) colliders.Capsules(capA, capB, true); else { capA.Clear(); capB.Clear(); }
            nCaps = Mathf.Min(capA.Count, 16);
            if (caps.Length < nCaps * 4) caps = new Vector4[nCaps * 4];
            bool sameCaps = capsLast.Length == nCaps * 4 && !first;
            for (int c = 0; c < nCaps; c++)
            {
                caps[c * 4] = capA[c]; caps[c * 4 + 1] = capB[c];
                caps[c * 4 + 2] = sameCaps ? capsLast[c * 4] : capA[c];
                caps[c * 4 + 3] = sameCaps ? capsLast[c * 4 + 1] : capB[c];
            }
            if (nCaps > 0) bCaps.SetData(caps, 0, 0, nCaps * 4);
            if (capsLast.Length != nCaps * 4) capsLast = new Vector4[nCaps * 4];
            Array.Copy(caps, capsLast, nCaps * 4);

            var s = shader;
            s.SetInt("_N", nParticle); s.SetInt("_NV", nVertex); s.SetInt("_NL", nLayer); s.SetInt("_NC", nCaps);
            s.SetInt("_First", first ? 1 : 0);
            s.SetFloat("_Damp", damping); s.SetFloat("_Stiff", stiffness); s.SetFloat("_Omega", omega);
            s.SetFloat("_Gap", gap); s.SetFloat("_Deep", deep); s.SetFloat("_Reach", reach); s.SetFloat("_Skin", skin);
            s.SetFloat("_NormalSign", data.normalSign);
            int gp = (nParticle + 63) / 64;
            s.Dispatch(kSkinCloth, gp, 1, 1);
            if (nLayer > 0) s.Dispatch(kSkinLayer, (nLayer + 63) / 64, 1, 1);
            s.Dispatch(kBegin, gp, 1, 1);
            int n = Mathf.Max(1, substeps);
            for (int k = 0; k < n; k++)
            {
                s.SetFloat("_S0", k / (float)n);
                s.SetFloat("_S1", (k + 1) / (float)n);
                s.Dispatch(kIntegrate, gp, 1, 1);
                for (int it = 0; it < iterations; it++)
                {
                    s.SetBuffer(kLinks, IdPos, bPos); s.SetBuffer(kLinks, IdPos2, bPos2);
                    s.Dispatch(kLinks, gp, 1, 1);
                    s.SetBuffer(kLinks, IdPos, bPos2); s.SetBuffer(kLinks, IdPos2, bPos);
                    s.Dispatch(kLinks, gp, 1, 1);
                }
                s.Dispatch(kCollide, gp, 1, 1);
            }
            s.SetBuffer(kLinks, IdPos, bPos); s.SetBuffer(kLinks, IdPos2, bPos2);
            s.Dispatch(kNormals, gp, 1, 1);
            s.Dispatch(kOutput, (nVertex + 63) / 64, 1, 1);
            first = false;

            cloth.GetPropertyBlock(mpb);                                     // HumanFace's colours stay
            mpb.SetBuffer(IdOut, bOut);
            mpb.SetFloat(IdOn, 1f);
            cloth.SetPropertyBlock(mpb);
        }

        /// <summary>The simulated positions and normals, a pair per mesh vertex (a check tool's; reads back from the GPU).</summary>
        public Vector4[] ReadBack()
        {
            if (bOut == null || cloth == null) return Array.Empty<Vector4>();
            var v = new Vector4[nVertex * 2];
            bOut.GetData(v);
            return v;
        }

        /// <summary>Humans/Cloth reads _SimOut only when _SimOn is set; this keeps something bound everywhere else.</summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        public static void BindDummy()
        {
            if (dummy == null || !dummy.IsValid()) dummy = new GraphicsBuffer(GraphicsBuffer.Target.Structured, 2, 16);
            Shader.SetGlobalBuffer(IdOut, dummy);
        }

#if UNITY_EDITOR
        [UnityEditor.InitializeOnLoadMethod]
        static void BindDummyInEditor() => BindDummy();

        // ---- trying it in play mode (the editor only: the data comes from the meshes, readable there) ----
        static readonly string[] Cloaks = { "Cloth_Cloak_", "Cloth_ElvenCape_", "Cloth_KnightCape_" };
        HumanFace following;
        readonly List<SkinnedMeshRenderer> boundLayers = new List<SkinnedMeshRenderer>();
        int wornSig;

        /// <summary>Simulates whatever cloak <paramref name="face"/> wears, binding again when the clothes change
        /// (a game's check menu). False: no cloak worn now.</summary>
        public bool Follow(HumanFace face)
        {
            following = face;
            return AutoBind();
        }

        static bool IsCloak(SkinnedMeshRenderer r) => Array.Exists(Cloaks, c => r.sharedMesh.name.StartsWith(c));

        static bool Lod0(SkinnedMeshRenderer r) =>
            r.sharedMesh != null && r.enabled && r.gameObject.activeInHierarchy && !r.name.EndsWith("_L1") && !r.name.EndsWith("_L2");

        // the worn LOD0 renderers that matter: the cloak, and the layers under it (the body and head where they show,
        // every garment but a cloak and its hood)
        void Worn(out SkinnedMeshRenderer cape, List<SkinnedMeshRenderer> layers, out int sig)
        {
            cape = null; sig = 17; layers.Clear();
            foreach (var r in following.GetComponentsInChildren<SkinnedMeshRenderer>(false))
            {
                if (!Lod0(r)) continue;
                if (IsCloak(r)) { if (cape == null) cape = r; }
                else if (r.name == "Body" || r.name == "Head" ||
                         (r.sharedMesh.name.StartsWith("Cloth_") && !r.sharedMesh.name.StartsWith("Cloth_CloakHood"))) layers.Add(r);
                else continue;
                sig = sig * 31 + r.GetInstanceID();
            }
        }

        bool AutoBind()
        {
            Worn(out var cape, boundLayers, out wornSig);
            if (cape == null) { Unbind(); return false; }
            var layers = new List<(SkinnedMeshRenderer, Layer)>();
            foreach (var r in boundLayers) layers.Add((r, BuildLayer(r)));
            Bind(cape, BuildCloth(cape), layers, following.GetComponent<HumanClothPush>());
            return true;
        }

        // the human meshes are not Read/Write: play mode refuses their vertices inside the player loop, an editor call
        // reads them, so a rebind waits for the next one
        bool rebinding;
        void Rebind()
        {
            rebinding = true;
            UnityEditor.EditorApplication.delayCall += () =>
            {
                if (this == null) return;
                rebinding = false;
                if (following != null) AutoBind();
            };
        }

        readonly List<SkinnedMeshRenderer> scratch = new List<SkinnedMeshRenderer>();
        bool Stale()
        {
            if (cloth != null && !cloth.gameObject.activeInHierarchy) return true;
            foreach (var l in boundLayers) if (l == null || !l.gameObject.activeInHierarchy) return true;
            if (Time.frameCount % 20 != 0) return false;
            Worn(out _, scratch, out int sig);
            return sig != wornSig;
        }

        static Vector3Int Key(Vector3 p) => Vector3Int.RoundToInt(p * 2000f);

        static bool Hangs(string bone) => bone.StartsWith("xh_cape") || bone.StartsWith("xh_wing");

        /// <summary>Setup (the meshes are readable in the editor): a garment's particles (its LOD0's vertices, welded),
        /// their skinning, max distance (<paramref name="maxBody"/> where it rides the body's bones,
        /// <paramref name="maxHang"/> where the cape's chains carry it), links and triangles.</summary>
        public static Cloth BuildCloth(SkinnedMeshRenderer smr, float maxHang = 0.12f, float maxBody = 0.01f)
        {
            var mesh = smr.sharedMesh;
            var v = mesh.vertices; var nrm = mesh.normals; var bw = mesh.boneWeights; var bp = mesh.bindposes;
            var names = Array.ConvertAll(smr.bones, b => b != null ? b.name : "");
            var tri = mesh.triangles;
            var d = new Cloth();
            var of = new Dictionary<Vector3Int, int>();
            var first = new List<int>();
            d.vertParticle = new int[v.Length];
            var nsum = new List<Vector3>();
            for (int i = 0; i < v.Length; i++)
            {
                var k = Key(v[i]);
                if (!of.TryGetValue(k, out var p)) { p = first.Count; of[k] = p; first.Add(i); nsum.Add(Vector3.zero); }
                d.vertParticle[i] = p;
                nsum[p] += nrm[i];
            }
            int n = first.Count;
            var used = new Dictionary<int, int>();
            int Use(int bi) { if (!used.TryGetValue(bi, out var u)) { u = used.Count; used[bi] = u; } return u; }
            d.rest = new Vector4[n]; d.restN = new Vector4[n]; d.skinI = new int[n * 4]; d.skinW = new Vector4[n];
            for (int p = 0; p < n; p++)
            {
                int i = first[p];
                var w = bw[i];
                float body = (Hangs(names[w.boneIndex0]) ? 0 : w.weight0) + (Hangs(names[w.boneIndex1]) ? 0 : w.weight1)
                           + (Hangs(names[w.boneIndex2]) ? 0 : w.weight2) + (Hangs(names[w.boneIndex3]) ? 0 : w.weight3);
                d.rest[p] = new Vector4(v[i].x, v[i].y, v[i].z, Mathf.Lerp(maxHang, maxBody, Mathf.SmoothStep(0f, 1f, body)));
                var nn = nsum[p].normalized;
                d.restN[p] = new Vector4(nn.x, nn.y, nn.z, body < 0.5f ? 1f : 0f);
                d.skinI[p * 4] = Use(w.boneIndex0); d.skinI[p * 4 + 1] = Use(w.boneIndex1);
                d.skinI[p * 4 + 2] = Use(w.boneIndex2); d.skinI[p * 4 + 3] = Use(w.boneIndex3);
                d.skinW[p] = new Vector4(w.weight0, w.weight1, w.weight2, w.weight3);
            }
            d.bones = new string[used.Count]; d.bindposes = new Matrix4x4[used.Count];
            foreach (var kv in used) { d.bones[kv.Value] = names[kv.Key]; d.bindposes[kv.Value] = bp[kv.Key]; }

            // triangles (welded, degenerate ones out), edges, and a bend across each edge two triangles share
            var tris = new List<int>();
            var edgeOpp = new Dictionary<long, List<int>>();
            long E(int a, int b) => a < b ? ((long)a << 32) | (uint)b : ((long)b << 32) | (uint)a;
            float sign = 0f;
            for (int t = 0; t < tri.Length; t += 3)
            {
                int a = d.vertParticle[tri[t]], b = d.vertParticle[tri[t + 1]], c = d.vertParticle[tri[t + 2]];
                if (a == b || b == c || a == c) continue;
                tris.Add(a); tris.Add(b); tris.Add(c);
                var fn = Vector3.Cross(v[first[b]] - v[first[a]], v[first[c]] - v[first[a]]);
                sign += Vector3.Dot(fn, nsum[a] + nsum[b] + nsum[c]);
                foreach (var (x, y, z) in new[] { (a, b, c), (b, c, a), (c, a, b) })
                {
                    if (!edgeOpp.TryGetValue(E(x, y), out var l)) edgeOpp[E(x, y)] = l = new List<int>();
                    l.Add(z);
                }
            }
            d.tris = tris.ToArray();
            d.normalSign = sign >= 0 ? 1f : -1f;
            var links = new List<(int a, int b, float w)>();
            var bends = new HashSet<long>();
            foreach (var kv in edgeOpp)
            {
                links.Add(((int)(kv.Key >> 32), (int)(kv.Key & 0xffffffff), 1f));
                if (kv.Value.Count == 2 && kv.Value[0] != kv.Value[1] && !edgeOpp.ContainsKey(E(kv.Value[0], kv.Value[1]))
                    && bends.Add(E(kv.Value[0], kv.Value[1])))
                    links.Add((kv.Value[0], kv.Value[1], 0.5f));
            }
            var per = new List<(int o, float w)>[n];
            for (int p = 0; p < n; p++) per[p] = new List<(int, float)>();
            foreach (var (a, b, w) in links) { per[a].Add((b, w)); per[b].Add((a, w)); }
            d.linkStart = new int[n + 1];
            var lo = new List<int>(); var lw = new List<float>();
            for (int p = 0; p < n; p++)
            {
                d.linkStart[p] = lo.Count;
                foreach (var (o, w) in per[p]) { lo.Add(o); lw.Add(w); }
            }
            d.linkStart[n] = lo.Count;
            d.linkOther = lo.ToArray(); d.linkW = lw.ToArray();
            var tper = new List<int>[n];
            for (int p = 0; p < n; p++) tper[p] = new List<int>();
            for (int t = 0; t < tris.Count / 3; t++) { tper[tris[t * 3]].Add(t); tper[tris[t * 3 + 1]].Add(t); tper[tris[t * 3 + 2]].Add(t); }
            d.triStart = new int[n + 1];
            var tl = new List<int>();
            for (int p = 0; p < n; p++) { d.triStart[p] = tl.Count; tl.AddRange(tper[p]); }
            d.triStart[n] = tl.Count;
            d.triList = tl.ToArray();
            return d;
        }

        /// <summary>Setup: a layer's points, one a <paramref name="cell"/> (m) cube of its LOD0's welded vertices (in the
        /// renderer's blend shapes: the body's build), with their body region (uv1.x), normal and skinning.</summary>
        public static Layer BuildLayer(SkinnedMeshRenderer smr, float cell = 0.02f)
        {
            var mesh = smr.sharedMesh;
            var v = mesh.vertices; var nrm = mesh.normals; var bw = mesh.boneWeights; var bp = mesh.bindposes;
            var dv = new Vector3[v.Length];
            for (int s = 0; s < mesh.blendShapeCount; s++)
            {
                float w = smr.GetBlendShapeWeight(s) / 100f;
                if (Mathf.Abs(w) < 1e-4f) continue;
                mesh.GetBlendShapeFrameVertices(s, mesh.GetBlendShapeFrameCount(s) - 1, dv, null, null);
                for (int i = 0; i < v.Length; i++) v[i] += dv[i] * w;
            }
            var names = Array.ConvertAll(smr.bones, b => b != null ? b.name : "");
            var uv1 = new List<Vector2>(); mesh.GetUVs(1, uv1);
            var cells = new Dictionary<Vector3Int, int>();
            var nsum = new Dictionary<Vector3Int, Vector3>();
            for (int i = 0; i < v.Length; i++)
            {
                var k = Key(v[i]);
                nsum[k] = (nsum.TryGetValue(k, out var s) ? s : Vector3.zero) + nrm[i];
                var c = Vector3Int.FloorToInt(v[i] / cell);
                if (!cells.ContainsKey(c)) cells[c] = i;
            }
            var used = new Dictionary<int, int>();
            int Use(int bi) { if (!used.TryGetValue(bi, out var u)) { u = used.Count; used[bi] = u; } return u; }
            var d = new Layer();
            int n = cells.Count;
            d.rest = new Vector4[n]; d.restN = new Vector3[n]; d.skinI = new int[n * 4]; d.skinW = new Vector4[n];
            int p = 0;
            foreach (var i in cells.Values)
            {
                var w = bw[i];
                d.rest[p] = new Vector4(v[i].x, v[i].y, v[i].z, uv1.Count == v.Length ? uv1[i].x : 0f);
                d.restN[p] = nsum[Key(v[i])].normalized;
                d.skinI[p * 4] = Use(w.boneIndex0); d.skinI[p * 4 + 1] = Use(w.boneIndex1);
                d.skinI[p * 4 + 2] = Use(w.boneIndex2); d.skinI[p * 4 + 3] = Use(w.boneIndex3);
                d.skinW[p] = new Vector4(w.weight0, w.weight1, w.weight2, w.weight3);
                p++;
            }
            d.bones = new string[used.Count]; d.bindposes = new Matrix4x4[used.Count];
            foreach (var kv in used) { d.bones[kv.Value] = names[kv.Key]; d.bindposes[kv.Value] = bp[kv.Key]; }
            return d;
        }
#endif
    }
}
