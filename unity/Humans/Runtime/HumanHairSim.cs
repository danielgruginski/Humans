using System;
using System.Collections.Generic;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Strand-card hair simulated on the GPU (the hair spike, 2026-10-29: Daniel wanted hair "physically reacting like
    /// cloth is doing", with a new hair material: Humans/HairCards, Blender side hum_cards.py / hum_drape.py). Each row of
    /// a card is a particle (the mesh's uv4.x), a card's rows root -> tip a strand. The hair as skinned (face keys, head /
    /// neck / spine / clavicle weights) is the target: strands keep their momentum in world space, ease back toward the
    /// target (strongly at the root), keep their lengths, stay within a max distance of it that grows along the strand, and
    /// stay off the worn layers (body, head, clothes). HumanHairSim.compute does the work; Humans/HairCards carries every
    /// vertex by its row's particle (_HairSim) in all its passes.
    /// Builds ("Sim in builds", same day): everything it reads was made at setup (HumanPiece.hairSim / simLayers,
    /// HumanHairSimData: vertex indices and skinning, no positions); the rest positions - the character's face and build
    /// keys in them - come from Unity's own GPU skinning once the renderers have been drawn (RestHair / RestLayer undo it),
    /// so no mesh has to be readable. HumanFace adds it to anyone wearing simulated hair (Ensure). LOD0 and LOD1 have a run
    /// each; a run ticks while its hair renderer is visible and within simDistance of the main camera, and starts again on
    /// its target when it comes back. Execution order 320: after the helper bones, the chains and the cloth sim.
    /// </summary>
    [DefaultExecutionOrder(320)]
    public class HumanHairSim : MonoBehaviour
    {
        public ComputeShader shader;
        [Tooltip("Simulated within this distance of the main camera (m); beyond it the hair is skinned")]
        public float simDistance = 25f;
        [Tooltip("The LODs simulated (LOD2 at the colony camera is never)")] public int maxLod = 1;
        [Header("Motion")]
        [Tooltip("Longest substep (s): as many substeps a frame as that takes (1/120 s let a running head's crown cards fly apart)")]
        public float maxStep = 1f / 240f;
        [Tooltip("Passes over a strand's lengths a substep")] public int iterations = 3;
        [Tooltip("Of the swing (the motion relative to the target), lost every 1/240 s")] public float damping = 0.08f;
        [Tooltip("Of the motion itself, lost every 1/240 s (air: how far hair trails a moving head)")] public float drag = 0.003f;
        [Tooltip("Down (m/s2): a little only, the style already hangs")] public float gravity = 3f;
        [Tooltip("Of the way back to the target, every 1/240 s, at the root")] public float followRoot = 0.35f;
        [Tooltip("... and from followLength along the strand on")] public float followTip = 0.02f;
        [Tooltip("Along the strand (m) the follow eases from root to tip")] public float followLength = 0.1f;
        [Tooltip("Max distance from the target, of the way along the strand")] public float maxRatio = 0.85f;
        [Tooltip("... and never farther than this (m)")] public float maxDistance = 0.2f;
        [Header("Collision")]
        [Tooltip("Kept in front of a layer (m)")] public float gap = 0.006f;
        [Tooltip("Deeper behind a layer's point than this: another part of it, left alone (m)")] public float deep = 0.05f;
        [Tooltip("A layer point farther than this from the target isn't the one under the particle (m)")] public float reach = 0.06f;
        [Tooltip("A layer point's plane holds this far across (m): an endless one lifted the front locks off the chest")]
        public float disk = 0.035f;
        [Tooltip("Hair resting deeper than this behind a layer point's plane isn't over it (m)")] public float inside = 0.015f;
        [Tooltip("A target moved farther than this in a frame: a teleport, the hair starts on it again (m)")] public float teleport = 0.5f;

        struct I4 { public int x, y, z, w; }
        struct I2 { public int x, y; }

        /// <summary>One LOD's simulation: its hair renderer and data, the same LOD's layers, their buffers.</summary>
        class Run
        {
            public int lod;
            public SkinnedMeshRenderer hair;
            public HumanPiece.HairSim data;
            public readonly List<(SkinnedMeshRenderer r, int offset, int count)> layers = new List<(SkinnedMeshRenderer, int, int)>();
            public Transform[] bones;
            public Matrix4x4[] bindposes, palette, palettePrev;
            public bool havePrev, restReady, first = true, on;
            public int nParticle, nLayer, nStrand, boundFrame;
            public float knobSig;
            public readonly List<GraphicsBuffer> owned = new List<GraphicsBuffer>();
            public GraphicsBuffer bones_, rest, param, outB, skinI, skinW, vertStart, vertList, link, strands,
                target, targetPrev, pos, prev, near, lRest, lRestN, lSkinI, lSkinW, lVert, lPos, lNrm;
        }

        readonly Run[] runs = new Run[3];
        HumanFace face;
        int wornSig;
        MaterialPropertyBlock mpb;
        int kRestHair, kRestLayer, kSkinHair, kSkinLayer, kBegin, kSimulate, kOutput;
        static GraphicsBuffer dummy;

        static readonly int IdSim = Shader.PropertyToID("_HairSim"), IdOn = Shader.PropertyToID("_HairSimOn"),
            IdHide = Shader.PropertyToID("_Hide");

        public bool Bound => runs[0] != null || runs[1] != null;

        /// <summary>Whether a LOD's run has its rest positions (from the GPU skinning) and simulates (a check tool's).</summary>
        public bool Ready(int lod = 0) => lod >= 0 && lod < runs.Length && runs[lod] != null && runs[lod].restReady;

        // ------------------------------------------------------------------ attaching

        /// <summary>Called by HumanFace after it applies a face (play mode): a sim on whoever wears simulated hair (none:
        /// removed).</summary>
        public static void Ensure(HumanFace f)
        {
            if (f == null || !Application.isPlaying) return;
            bool wants = WornHair(f, 0, out _) != null || WornHair(f, 1, out _) != null;
            var sim = f.GetComponent<HumanHairSim>();
            if (!wants) { if (sim != null) Destroy(sim); return; }
            if (sim == null) sim = f.gameObject.AddComponent<HumanHairSim>();
            sim.BindTo(f);
        }

        /// <summary>The worn hair renderer at a LOD with simulation data (null: none).</summary>
        static SkinnedMeshRenderer WornHair(HumanFace f, int lod, out HumanPiece.HairSim data)
        {
            data = null;
            var root = lod == 0 ? f.hairRoot : f.lowerLods != null && lod - 1 < f.lowerLods.Length ? f.lowerLods[lod - 1]?.hairRoot : null;
            if (root == null) return null;
            foreach (Transform t in root)
            {
                if (!t.gameObject.activeSelf || !t.name.StartsWith("Hair_") || !t.TryGetComponent<SkinnedMeshRenderer>(out var r)) continue;
                var piece = Resources.Load<HumanPiece>(HumanPiece.Folder + "/" + PieceName(t.name));
                data = piece != null ? piece.HairAt(lod) : null;
                if (data != null) return r;
            }
            return null;
        }

        static string PieceName(string n)
        {
            int i = n.LastIndexOf("_L", StringComparison.Ordinal);
            return i > 0 && i + 2 < n.Length && char.IsDigit(n[i + 2]) ? n.Substring(0, i) : n;
        }

        static int LodOf(string n)
        {
            int i = n.LastIndexOf("_L", StringComparison.Ordinal);
            return i > 0 && i + 2 < n.Length && char.IsDigit(n[i + 2]) ? n[i + 2] - '0' : 0;
        }

        /// <summary>(Re)binds every simulated LOD of <paramref name="f"/>'s worn hair; the rest positions follow once the
        /// renderers have been drawn (the next frames, or a check tool's render before its Tick).</summary>
        public void BindTo(HumanFace f)
        {
            face = f;
            if (shader == null) shader = HumanHairSimData.Get()?.shader;
            for (int l = 0; l < runs.Length; l++) { Free(runs[l]); runs[l] = null; }
            if (shader == null) { Debug.LogWarning("[HumanHairSim] no compute shader (Resources/HumanHairSimData)"); return; }
            mpb ??= new MaterialPropertyBlock();
            kRestHair = shader.FindKernel("RestHair"); kRestLayer = shader.FindKernel("RestLayer");
            kSkinHair = shader.FindKernel("SkinHair"); kSkinLayer = shader.FindKernel("SkinLayer");
            kBegin = shader.FindKernel("Begin"); kSimulate = shader.FindKernel("Simulate"); kOutput = shader.FindKernel("Output");
            for (int l = 0; l <= Mathf.Min(maxLod, runs.Length - 1); l++)
            {
                var hair = WornHair(f, l, out var data);
                if (hair != null) runs[l] = Make(f, l, hair, data);
            }
            wornSig = Signature(f);
        }

        // the worn renderers and the face's keys: a change means binding again
        static int Signature(HumanFace f)
        {
            int sig = 17;
            foreach (var r in f.GetComponentsInChildren<SkinnedMeshRenderer>(false))
            {
                sig = sig * 31 + r.GetInstanceID();
                var m = r.sharedMesh;
                if (m != null && r.name.StartsWith("Hair_") && m.blendShapeCount > 0)
                    for (int i = 0; i < m.blendShapeCount; i += 7) sig = sig * 31 + Mathf.RoundToInt(r.GetBlendShapeWeight(i) * 10f);
            }
            return sig;
        }

        Run Make(HumanFace f, int lod, SkinnedMeshRenderer hair, HumanPiece.HairSim d)
        {
            var run = new Run { lod = lod, hair = hair, data = d, boundFrame = Time.frameCount };
            var bl = new List<Transform>();
            var bp = new List<Matrix4x4>();
            Add(hair, d.bones, d.bindposes, bl, bp);
            // the layers at the same LOD: body, head (HumanHairSimData), every worn garment (its piece's simLayers)
            var sd = HumanHairSimData.Get();
            var lVert = new List<int>(); var lI = new List<I4>(); var lW = new List<Vector4>();
            void Layer(SkinnedMeshRenderer r, HumanPiece.SimLayer ld)
            {
                if (r == null || ld == null || !r.gameObject.activeInHierarchy || !r.enabled) return;
                r.GetPropertyBlock(mpb);
                int hide = (int)mpb.GetFloat(IdHide);
                int off = bl.Count;
                Add(r, ld.bones, ld.bindposes, bl, bp);
                int start = lVert.Count;
                for (int i = 0; i < ld.verts.Length; i++)
                {
                    if (((hide >> ld.region[i]) & 1) != 0) continue;
                    lVert.Add(ld.verts[i]);
                    lI.Add(new I4 { x = ld.skinI[i * 4] + off, y = ld.skinI[i * 4 + 1] + off, z = ld.skinI[i * 4 + 2] + off, w = ld.skinI[i * 4 + 3] + off });
                    lW.Add(ld.skinW[i]);
                }
                if (lVert.Count > start) run.layers.Add((r, start, lVert.Count - start));
            }
            var body = f.bodies != null && lod < f.bodies.Length ? f.bodies[lod] : null;
            var head = lod == 0 ? f.head : f.lowerLods != null && lod - 1 < f.lowerLods.Length ? f.lowerLods[lod - 1]?.head : null;
            if (sd != null) { Layer(body, sd.Body(lod)); Layer(head, sd.Head(lod)); }
            if (f.clothRoot != null)
                foreach (Transform t in f.clothRoot)
                {
                    if (!t.gameObject.activeSelf || LodOf(t.name) != lod || !t.TryGetComponent<SkinnedMeshRenderer>(out var r)) continue;
                    var piece = Resources.Load<HumanPiece>(HumanPiece.Folder + "/" + PieceName(t.name));
                    Layer(r, piece != null ? piece.LayerAt(lod) : null);
                }
            // GPU skinning into raw buffers: the rest comes from them
            hair.vertexBufferTarget |= GraphicsBuffer.Target.Raw;
            foreach (var (r, _, _) in run.layers) r.vertexBufferTarget |= GraphicsBuffer.Target.Raw;

            run.bones = bl.ToArray();
            run.bindposes = bp.ToArray();
            run.palette = new Matrix4x4[run.bones.Length];
            run.palettePrev = new Matrix4x4[run.bones.Length];
            int n = run.nParticle = d.parent.Length;
            run.nLayer = lVert.Count;
            var skinI = new I4[n];
            var link = new I2[n];
            var strands = new List<int>();
            for (int i = 0; i < n; i++)
            {
                skinI[i] = new I4 { x = d.skinI[i * 4], y = d.skinI[i * 4 + 1], z = d.skinI[i * 4 + 2], w = d.skinI[i * 4 + 3] };
                int child = i + 1 < n && d.parent[i + 1] == i ? i + 1 : -1;
                link[i] = new I2 { x = d.parent[i], y = child };
                if (d.parent[i] < 0) strands.Add(i);
            }
            strands.Add(n);
            run.nStrand = strands.Count - 1;

            GraphicsBuffer New(int count, int stride)
            {
                var b = new GraphicsBuffer(GraphicsBuffer.Target.Structured, Mathf.Max(count, 1), stride);
                run.owned.Add(b);
                return b;
            }
            GraphicsBuffer Buf<T>(T[] v, int stride) where T : struct
            {
                var b = New(v.Length, stride);
                if (v.Length > 0) b.SetData(v);
                return b;
            }
            run.bones_ = Buf(run.palette, 64);
            run.rest = New(n, 16); run.param = New(n, 16); run.outB = New(n * 3, 16);
            run.skinI = Buf(skinI, 16); run.skinW = Buf(d.skinW, 16);
            run.vertStart = Buf(d.vertStart, 4); run.vertList = Buf(d.vertList, 4);
            run.link = Buf(link, 8); run.strands = Buf(strands.ToArray(), 4);
            run.target = New(n, 16); run.targetPrev = New(n, 16); run.pos = New(n, 16); run.prev = New(n, 16); run.near = New(n, 4);
            run.lRest = New(run.nLayer, 16); run.lRestN = New(run.nLayer, 16);
            run.lSkinI = Buf(lI.ToArray(), 16); run.lSkinW = Buf(lW.ToArray(), 16); run.lVert = Buf(lVert.ToArray(), 4);
            run.lPos = New(run.nLayer, 16); run.lNrm = New(run.nLayer, 16);
            ApplyKnobs(run);
            return run;
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

        float KnobSig() => followRoot * 3.1f + followTip * 7.3f + followLength * 11.7f + maxRatio * 13.1f + maxDistance * 17.9f;

        /// <summary>The per-particle follow and max distance from the knobs (again when they change).</summary>
        void ApplyKnobs(Run run)
        {
            var param = new Vector4[run.nParticle];
            var hold = run.data.hold;
            for (int i = 0; i < run.nParticle; i++)
            {
                // from where its strand leaves the head (by path alone the crown's strands, 10 cm over the head before
                // they fall, sagged and flapped there when running: dark blotches on the crown)
                float d = Mathf.Max(0f, run.data.path[i] - (hold != null && i < hold.Length ? hold[i] : 0f));
                float f = Mathf.Lerp(followRoot, followTip, Mathf.SmoothStep(0f, 1f, d / Mathf.Max(followLength, 1e-4f)));
                param[i] = new Vector4(f, d, Mathf.Min(d * maxRatio + 0.003f, maxDistance), 0);
            }
            run.param.SetData(param);
            run.knobSig = KnobSig();
        }

        static void Free(Run run)
        {
            if (run == null) return;
            foreach (var b in run.owned) b?.Release();
            run.owned.Clear();
        }

        void SetOn(Run run, bool on)
        {
            if (run.hair == null) return;
            run.hair.GetPropertyBlock(mpb);                                  // HumanFace's colours stay
            if (on) mpb.SetBuffer(IdSim, run.outB);
            mpb.SetFloat(IdOn, on ? 1f : 0f);
            run.hair.SetPropertyBlock(mpb);
            run.on = on;
        }

        void OnDisable()
        {
            for (int l = 0; l < runs.Length; l++)
            {
                if (runs[l] != null) SetOn(runs[l], false);
                Free(runs[l]);
                runs[l] = null;
            }
        }

        // ------------------------------------------------------------------ the frame

        void LateUpdate()
        {
            if (face == null) return;
            if (Time.frameCount % 20 == 0 && Signature(face) != wornSig) { BindTo(face); return; }
            var cam = Camera.main;
            foreach (var run in runs)
            {
                if (run == null || run.hair == null) continue;
                bool near = cam == null || (run.hair.bounds.center - cam.transform.position).sqrMagnitude < simDistance * simDistance;
                bool active = run.hair.gameObject.activeInHierarchy && run.hair.isVisible && near;
                if (!active)
                {
                    if (run.on) SetOn(run, false);
                    run.first = true;                                          // starts on its target when it comes back
                    run.havePrev = false;
                    run.boundFrame = Time.frameCount;
                    continue;
                }
                Tick(run, Time.deltaTime, false);
            }
        }

        /// <summary>One frame of every bound LOD, visible or not (a check tool's own, after posing; render once after binding
        /// so the rest can be read from the skinning).</summary>
        public void Tick(float dt)
        {
            foreach (var run in runs) if (run != null) Tick(run, dt, true);
        }

        void Tick(Run run, float dt, bool force)
        {
            if (shader == null || run.hair == null) return;
            if (!Mathf.Approximately(run.knobSig, KnobSig())) ApplyKnobs(run);
            for (int k = 0; k < run.bones.Length; k++)
                run.palette[k] = run.bones[k] != null ? run.bones[k].localToWorldMatrix * run.bindposes[k] : Matrix4x4.identity;
            var s = shader;
            if (!run.restReady)
            {
                // the renderers' last skinning was drawn with last frame's bones (a check tool renders the pose it ticks)
                bool can = force || (run.havePrev && Time.frameCount > run.boundFrame + 1);
                if (can && TryRest(run, force ? run.palette : run.palettePrev)) { run.restReady = true; run.first = true; }
                if (!run.restReady)
                {
                    Array.Copy(run.palette, run.palettePrev, run.palette.Length);
                    run.havePrev = true;
                    return;
                }
            }
            run.bones_.SetData(run.palette);
            dt = Mathf.Clamp(dt, 1e-4f, 0.1f);
            int n = Mathf.Clamp(Mathf.CeilToInt(dt / Mathf.Max(maxStep, 1e-3f) - 1e-3f), 2, 24);
            float h = dt / n;
            s.SetInt("_N", run.nParticle); s.SetInt("_NL", run.nLayer); s.SetInt("_NS", run.nStrand); s.SetInt("_Sub", n);
            s.SetInt("_Iter", Mathf.Max(1, iterations));
            s.SetInt("_First", run.first ? 1 : 0);
            s.SetFloat("_Damp", damping); s.SetFloat("_Drag", drag); s.SetFloat("_Gravity", gravity);
            s.SetFloat("_Dt", h); s.SetFloat("_StepK", h * 240f);
            s.SetFloat("_Gap", gap); s.SetFloat("_Deep", deep); s.SetFloat("_Reach", reach); s.SetFloat("_Teleport", teleport);
            s.SetFloat("_Disk", disk); s.SetFloat("_Inside", inside);
            Bind(run, kSkinHair); Bind(run, kSkinLayer); Bind(run, kBegin); Bind(run, kSimulate); Bind(run, kOutput);
            int gp = (run.nParticle + 63) / 64;
            s.Dispatch(kSkinHair, gp, 1, 1);
            if (run.nLayer > 0) s.Dispatch(kSkinLayer, (run.nLayer + 63) / 64, 1, 1);
            s.Dispatch(kBegin, gp, 1, 1);
            s.Dispatch(kSimulate, (run.nStrand + 63) / 64, 1, 1);
            s.Dispatch(kOutput, gp, 1, 1);
            run.first = false;
            Array.Copy(run.palette, run.palettePrev, run.palette.Length);
            run.havePrev = true;
            run.hair.GetPropertyBlock(mpb);                                  // HumanFace's Apply clears the block
            if (!run.on || mpb.GetFloat(IdOn) < 0.5f) SetOn(run, true);
        }

        void Bind(Run run, int k)
        {
            var s = shader;
            s.SetBuffer(k, "_Bones", run.bones_);
            s.SetBuffer(k, "_Rest", run.rest); s.SetBuffer(k, "_Param", run.param); s.SetBuffer(k, "_Link", run.link);
            s.SetBuffer(k, "_StrandStart", run.strands);
            s.SetBuffer(k, "_SkinI", run.skinI); s.SetBuffer(k, "_SkinW", run.skinW);
            s.SetBuffer(k, "_VertStart", run.vertStart); s.SetBuffer(k, "_VertList", run.vertList);
            s.SetBuffer(k, "_Target", run.target); s.SetBuffer(k, "_TargetPrev", run.targetPrev);
            s.SetBuffer(k, "_Pos", run.pos); s.SetBuffer(k, "_Prev", run.prev); s.SetBuffer(k, "_Near", run.near);
            s.SetBuffer(k, "_Out", run.outB);
            s.SetBuffer(k, "_LRest", run.lRest); s.SetBuffer(k, "_LRestN", run.lRestN);
            s.SetBuffer(k, "_LSkinI", run.lSkinI); s.SetBuffer(k, "_LSkinW", run.lSkinW); s.SetBuffer(k, "_LVert", run.lVert);
            s.SetBuffer(k, "_LPos", run.lPos); s.SetBuffer(k, "_LNrm", run.lNrm);
        }

        static Matrix4x4 SkinSpace(SkinnedMeshRenderer r)
        {
            // GPU skinning writes the root bone's space at unit scale (measured: 0.000 cm against BakeMesh)
            var t = r.rootBone != null ? r.rootBone : r.transform;
            return Matrix4x4.TRS(t.position, t.rotation, Vector3.one);
        }

        /// <summary>The rest positions from the renderers' GPU skinning, undone with the palette they were skinned with.
        /// False: the hair has no skinned buffer yet (not drawn since it was bound). A layer without one (not drawn: off
        /// screen, like boots below a close-up) is left out - its points moved far away, never the nearest; first cut
        /// waited for every layer, and the trousers out of a head shot kept the sim from ever starting.</summary>
        bool TryRest(Run run, Matrix4x4[] pal)
        {
            var hb = run.hair.GetVertexBuffer();
            if (hb == null) return false;
            var lbs = new GraphicsBuffer[run.layers.Count];
            try
            {
                for (int i = 0; i < lbs.Length; i++)
                {
                    lbs[i] = run.layers[i].r.GetVertexBuffer();
                    if (lbs[i] != null) continue;
                    var (_, off0, cnt0) = run.layers[i];
                    var far = new Vector4[cnt0];
                    for (int k = 0; k < cnt0; k++) far[k] = new Vector4(1e5f, 1e5f, 1e5f, 1f);
                    run.lRest.SetData(far, 0, off0, cnt0);
                    run.lRestN.SetData(far, 0, off0, cnt0);
                }
                var s = shader;
                run.bones_.SetData(pal);
                Bind(run, kRestHair);
                s.SetBuffer(kRestHair, "_Skinned", hb);
                s.SetMatrix("_SkinToWorld", SkinSpace(run.hair));
                s.SetInt("_Stride", hb.stride);
                s.SetInt("_N", run.nParticle);
                s.Dispatch(kRestHair, (run.nParticle + 63) / 64, 1, 1);
                Bind(run, kRestLayer);
                for (int i = 0; i < lbs.Length; i++)
                {
                    if (lbs[i] == null) continue;
                    var (r, off, cnt) = run.layers[i];
                    s.SetBuffer(kRestLayer, "_Skinned", lbs[i]);
                    s.SetMatrix("_SkinToWorld", SkinSpace(r));
                    s.SetInt("_Stride", lbs[i].stride);
                    s.SetInt("_LOffset", off);
                    s.SetInt("_LCount", cnt);
                    s.Dispatch(kRestLayer, (cnt + 63) / 64, 1, 1);
                }
                return true;
            }
            finally
            {
                hb.Dispose();
                foreach (var b in lbs) b?.Dispose();
            }
        }

        /// <summary>Target, position and rotation per particle of a LOD's run (a check tool's; reads back from the GPU).</summary>
        public Vector4[] ReadBack(int lod = 0)
        {
            var run = lod >= 0 && lod < runs.Length ? runs[lod] : null;
            if (run == null || !run.restReady) return Array.Empty<Vector4>();
            var v = new Vector4[run.nParticle * 3];
            run.outB.GetData(v);
            return v;
        }

        /// <summary>A run's rest positions as the GPU found them (a check tool's: against the mesh's own).</summary>
        public Vector4[] ReadRest(int lod = 0)
        {
            var run = lod >= 0 && lod < runs.Length ? runs[lod] : null;
            if (run == null || !run.restReady) return Array.Empty<Vector4>();
            var v = new Vector4[run.nParticle];
            run.rest.GetData(v);
            return v;
        }

        /// <summary>Humans/HairCards reads _HairSim only when _HairSimOn is set; this keeps something bound everywhere else.</summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        public static void BindDummy()
        {
            if (dummy == null || !dummy.IsValid()) dummy = new GraphicsBuffer(GraphicsBuffer.Target.Structured, 3, 16);
            Shader.SetGlobalBuffer(IdSim, dummy);
        }

#if UNITY_EDITOR
        [UnityEditor.InitializeOnLoadMethod]
        static void BindDummyInEditor() => BindDummy();
#endif
    }
}
