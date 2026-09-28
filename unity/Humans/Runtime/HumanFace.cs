using System;
using System.Collections.Generic;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Applies a HumanFaceData to the head (SkinnedMeshRenderer with the face blend shapes, skin on submesh 0,
    /// eyes on submesh 1) and to the hair/beard/brow pieces under hairRoot (named Hair_X, Beard_X, Brows_X; each
    /// carries the face keys that move it). Colours go through MaterialPropertyBlocks: all humans share the
    /// three materials.
    /// Garments (Cloth_X, Cloth_X_L1, ...) under clothRoot are switched on by the outfit and coloured per renderer;
    /// the body regions they cover are clipped by the body shader (_Hide bit mask).
    /// </summary>
    [ExecuteAlways]
    public class HumanFace : MonoBehaviour
    {
        [Serializable]
        public class LodSet
        {
            public SkinnedMeshRenderer head;
            public Transform hairRoot;
            [Tooltip("Minimum painted-brow strength (LODs without brow geometry)")]
            public float minPaintedBrows;
        }

        public TextAsset config;
        [Header("LOD0 (portrait)")]
        public SkinnedMeshRenderer head;
        public Transform hairRoot;
        [Header("Lower LODs (same keys, piece names end in _L<n>)")]
        public LodSet[] lowerLods = new LodSet[0];

        [Header("Body (optional): bodies per LOD, skeleton driven by the keys")]
        public SkinnedMeshRenderer[] bodies = new SkinnedMeshRenderer[0];
        public Transform clothRoot;                       // Cloth_<garment>[_L<n>], skinned to the same skeleton
        public HumanRigData rig;
        public Transform modelRoot;                       // the imported model (Animator); height scales it
        public Animator animator;
        public Transform[] bones = new Transform[0];      // matches rig.bones
        public Vector3[] restLocal = new Vector3[0];      // bone local positions in the rest pose
        public Matrix4x4[] restToParent = new Matrix4x4[0];   // model-space vector -> parent-local vector (rest)
        [Tooltip("Motion controllers by sex (HumanSetup builds one shared Humans_Motion controller from our own clips)")]
        public RuntimeAnimatorController maleController, femaleController;
        [Tooltip("Roll a random face from `seed` when the game starts")]
        public bool randomOnStart;
        public int seed;
        public HumanFaceData face = new HumanFaceData();

        static readonly int IdTone = Shader.PropertyToID("_Tone"), IdLip = Shader.PropertyToID("_Lip"),
            IdHair = Shader.PropertyToID("_Hair"), IdLash = Shader.PropertyToID("_Lash"),
            IdBlush = Shader.PropertyToID("_Blush"), IdFreckles = Shader.PropertyToID("_Freckles"),
            IdStubble = Shader.PropertyToID("_Stubble"), IdAge = Shader.PropertyToID("_Age"),
            IdBrows = Shader.PropertyToID("_Brows"), IdScalp = Shader.PropertyToID("_Scalp"),
            IdBeardShadow = Shader.PropertyToID("_BeardShadow"), IdIris = Shader.PropertyToID("_Iris"),
            IdRoot = Shader.PropertyToID("_HairRoot"), IdTip = Shader.PropertyToID("_HairTip"),
            IdStreak = Shader.PropertyToID("_HairStreak"), IdStreaks = Shader.PropertyToID("_Streaks"),
            IdOmbre = Shader.PropertyToID("_Ombre"), IdCloth = Shader.PropertyToID("_Cloth"),
            IdTop = Shader.PropertyToID("_Top"), IdHide = Shader.PropertyToID("_Hide"),
            IdColor = Shader.PropertyToID("_Color"), IdCapCut = Shader.PropertyToID("_CapCut"),
            IdHoodCut = Shader.PropertyToID("_HoodCut"), IdSuit = Shader.PropertyToID("_Suit"),
            IdSuitColor = Shader.PropertyToID("_SuitColor");

        static readonly Dictionary<Mesh, string[]> ShapeNames = new Dictionary<Mesh, string[]>();        MaterialPropertyBlock mpb;

        public HumanFaceConfig Config => HumanFaceConfig.Load(config);

        void Start()
        {
            if (Application.isPlaying && randomOnStart) Randomize(seed);
            else Apply();
        }

        void OnValidate()
        {
#if UNITY_EDITOR
            // SetActive is not allowed inside OnValidate: apply on the next editor tick
            UnityEditor.EditorApplication.delayCall += () => { if (this != null && config != null && head != null) Apply(); };
#endif
        }

        public void Randomize(int newSeed)
        {
            seed = newSeed;
            face = HumanFaceGenerator.Random(Config, newSeed);
            Apply();
        }

        /// <summary>Hair/beard/brow piece names available under hairRoot, by prefix ("Hair_", "Beard_", "Brows_").</summary>
        public List<string> Styles(string prefix)
        {
            var list = new List<string>();
            if (hairRoot == null) return list;
            foreach (Transform t in hairRoot)
                if (t.name.StartsWith(prefix)) list.Add(t.name.Substring(prefix.Length));
            list.Sort();
            return list;
        }

        public void Apply()
        {
            if (config == null || head == null || face == null) return;
            var weights = face.ToKeyWeights(Config);
            mpb ??= new MaterialPropertyBlock();
            ApplySet(head, hairRoot, 0f, weights);
            if (lowerLods != null)
                foreach (var l in lowerLods)
                    if (l != null && l.head != null) ApplySet(l.head, l.hairRoot, l.minPaintedBrows, weights);
            var bodyWeights = HumanFaceData.BodyOnly(Config, weights);     // the build: body and skeleton
            int hide = Config.HideMask(face.GarmentNames);
            var suit = Config.SuitColor(face.outfit);
            foreach (var b in bodies)
            {
                if (b == null) continue;
                SetWeights(b, bodyWeights);
                mpb.Clear();
                mpb.SetColor(IdTone, face.tone);
                mpb.SetColor(IdCloth, face.cloth);
                mpb.SetFloat(IdBlush, face.blush);
                mpb.SetFloat(IdFreckles, face.freckles);
                mpb.SetFloat(IdTop, face.chestBand);
                mpb.SetFloat(IdHide, hide);
                mpb.SetFloat(IdSuit, suit.HasValue ? 1f : 0f);
                if (suit.HasValue) mpb.SetColor(IdSuitColor, suit.Value);
                b.SetPropertyBlock(mpb);
            }
            ApplyClothes(weights);
            if (animator != null && maleController != null && femaleController != null)
            {
                var want = face.sex >= 0 ? maleController : femaleController;
                if (animator.runtimeAnimatorController != want) animator.runtimeAnimatorController = want;
            }
            ApplySkeleton(bodyWeights);
        }

        /// <summary>Bones move by the keys' joint deltas; height scales the model; animated hips get lifted.</summary>
        void ApplySkeleton(Dictionary<string, float> weights)
        {
            if (rig == null || bones == null || bones.Length != rig.bones.Length || restLocal.Length != bones.Length) return;
            var d = new Vector3[bones.Length];
            foreach (var k in rig.keys)
            {
                if (!weights.TryGetValue(k.key, out var w)) continue;
                w /= 100f;
                for (int i = 0; i < k.bones.Length; i++) d[k.bones[i]] += w * k.deltas[i];
            }
            for (int i = 0; i < bones.Length; i++)
            {
                if (bones[i] == null) continue;
                int p = rig.parents[i];
                var rel = d[i] - (p >= 0 ? d[p] : Vector3.zero);
                bones[i].localPosition = restLocal[i] + restToParent[i].MultiplyVector(rel);
            }
            if (modelRoot == null) return;
            float s = rig.HeightScale(face.height);
            modelRoot.localScale = Vector3.one * s;
            // a Humanoid Animator places the hips at the base avatar's height: lift by the pelvis delta
            bool animated = Application.isPlaying && animator != null && animator.isHuman && animator.runtimeAnimatorController != null;
            modelRoot.localPosition = animated ? Vector3.up * (s * d[rig.hipsIndex].y) : Vector3.zero;
        }

        void ApplyClothes(Dictionary<string, float> weights)
        {
            if (clothRoot == null) return;
            foreach (Transform t in clothRoot)
            {
                if (!t.name.StartsWith("Cloth_")) continue;
                // Cloth_<garment>_<build tag>[_L<n>]: only this character's build is shown
                var parts = BaseName(t.name).Substring(6).Split('_');
                string g = parts[0];
                if (parts.Length > 1 && parts[1] != face.build)
                {
                    if (t.gameObject.activeSelf) t.gameObject.SetActive(false);
                    continue;
                }
                Color? col = null;
                foreach (var o in face.outfit) if (o.garment == g) col = o.color;
                bool on = col.HasValue;
                if (t.gameObject.activeSelf != on) t.gameObject.SetActive(on);
                var smr = t.GetComponent<SkinnedMeshRenderer>();
                if (!on || smr == null) continue;
                SetWeights(smr, weights);
                mpb.Clear();
                mpb.SetColor(IdColor, col.Value);
                mpb.SetFloat(IdHide, Config.LayerHideMask(g, face.GarmentNames));
                smr.SetPropertyBlock(mpb);
            }
            // the cape's spring chain only runs while a cape (cloak slot) is worn
            var chain = GetComponent<HumanSpringChain>();
            if (chain != null)
            {
                bool cape = false;
                foreach (var n in face.GarmentNames) cape |= Config.FindGarment(n)?.slot == "cloak";
                if (chain.enabled != cape) chain.enabled = cape;
            }
            // and the skirt ring while a skirt is
            var skirt = GetComponent<HumanSkirt>();
            if (skirt != null)
            {
                bool on = Config.Skirted(face.GarmentNames);
                if (on) Config.SkirtSlackOf(face.GarmentNames, face.build, skirt.SlackHip, skirt.SlackKnee);
                if (skirt.enabled != on) skirt.enabled = on;
            }
        }

        static string BaseName(string n)
        {
            int i = n.LastIndexOf("_L", StringComparison.Ordinal);
            return i > 0 && i + 2 < n.Length && char.IsDigit(n[i + 2]) ? n.Substring(0, i) : n;
        }

        void ApplySet(SkinnedMeshRenderer head, Transform hairRoot, float minBrows, Dictionary<string, float> weights)
        {
            head.enabled = !Config.HidesHead(face.GarmentNames);
            SetWeights(head, weights);
            mpb.Clear();
            mpb.SetColor(IdTone, face.tone);
            mpb.SetColor(IdLip, face.lip);
            mpb.SetColor(IdHair, face.hairRoot);
            mpb.SetColor(IdLash, face.lash);
            mpb.SetFloat(IdBlush, face.blush);
            mpb.SetFloat(IdFreckles, face.freckles);
            mpb.SetFloat(IdStubble, face.stubble);
            mpb.SetFloat(IdAge, face.ageLines);
            mpb.SetFloat(IdBrows, Mathf.Max(face.paintedBrows, minBrows));
            mpb.SetFloat(IdScalp, string.IsNullOrEmpty(face.hairStyle) ? 0f : face.hairlineTint);
            mpb.SetFloat(IdBeardShadow, string.IsNullOrEmpty(face.beardStyle) ? 0f : face.beardShadow);
            head.SetPropertyBlock(mpb, 0);
            mpb.Clear();
            mpb.SetColor(IdIris, face.iris);
            head.SetPropertyBlock(mpb, 1);

            if (hairRoot == null) return;
            float capCut = Config.CapCut(face.GarmentNames);
            bool noHair = Config.HidesHair(face.GarmentNames);
            bool noFaceHair = Config.HidesFaceHair(face.GarmentNames);
            float hoodCut = Config.HoodCut(face.GarmentNames) ? 1f : 0f;
            foreach (Transform t in hairRoot)
            {
                var smr = t.GetComponent<SkinnedMeshRenderer>();
                string n = BaseName(t.name);
                bool on = !noFaceHair && ((n == "Hair_" + face.hairStyle && !noHair) || n == "Beard_" + face.beardStyle
                                          || n == "Brows_" + face.browStyle);
                if (t.gameObject.activeSelf != on) t.gameObject.SetActive(on);
                if (!on || smr == null) continue;
                SetWeights(smr, weights);
                mpb.Clear();
                if (n.StartsWith("Hair_"))
                {
                    mpb.SetColor(IdRoot, face.hairRoot);
                    mpb.SetColor(IdTip, face.hairTip);
                    mpb.SetColor(IdStreak, face.hairStreak);
                    mpb.SetFloat(IdStreaks, face.streaks);
                    mpb.SetFloat(IdOmbre, face.ombre);
                }
                else
                {
                    var c = n.StartsWith("Beard_") ? face.beardColor : face.browColor;
                    mpb.SetColor(IdRoot, c);
                    mpb.SetColor(IdTip, c);
                    mpb.SetColor(IdStreak, c);
                    mpb.SetFloat(IdStreaks, 0f);
                    mpb.SetFloat(IdOmbre, 0f);
                }
                mpb.SetFloat(IdCapCut, capCut);
                mpb.SetFloat(IdHoodCut, hoodCut);
                smr.SetPropertyBlock(mpb);
            }
        }

        static void SetWeights(SkinnedMeshRenderer smr, Dictionary<string, float> weights)
        {
            var mesh = smr.sharedMesh;
            if (mesh == null) return;
            if (!ShapeNames.TryGetValue(mesh, out var names) || names.Length != mesh.blendShapeCount)
            {
                names = new string[mesh.blendShapeCount];
                for (int i = 0; i < names.Length; i++)
                {
                    var s = mesh.GetBlendShapeName(i);
                    int dot = s.LastIndexOf('.');                 // some importers prefix "Mesh.Key"
                    names[i] = dot >= 0 ? s.Substring(dot + 1) : s;
                }
                ShapeNames[mesh] = names;
            }
            for (int i = 0; i < names.Length; i++)
                smr.SetBlendShapeWeight(i, weights.TryGetValue(names[i], out var w) ? w : 0f);
        }
    }
}
