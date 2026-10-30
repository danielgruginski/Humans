using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Humans.EditorTools
{
    /// <summary>
    /// The hair spike (2026-10-29, strand cards + Humans/HairCards + HumanHairSim): Tools/Humans/Hair Cards Spike/Install
    /// sets up Models/Human_HairCards.fbx (hum_cards.export: the spike pieces, apart from Human_Hair.fbx), the strand
    /// atlas T_Hair_Cards and M_HumanHairCards, and cuts the pieces (Hair_LongStrands, Hair_PonytailStrands, each with
    /// _L1/_L2) into Resources/HumanPieces like HumanSetup does, so a face wears them by style name ("LongStrands").
    /// HumanSetup's Rebuild keeps these pieces and lists them on the prefab; HumanFace wears them for their plain styles.
    /// </summary>
    public static class HumanHairCardsSpike
    {
        const string Root = HumanSetup.Root;
        const string Fbx = Root + "/Models/Human_HairCards.fbx";
        const string Atlas = Root + "/Textures/T_Hair_Cards.png";
        const string Strands = Root + "/Textures/T_Hair_Strands.png";
        const string MatPath = Root + "/Materials/M_HumanHairCards.mat";
        public static readonly string[] Styles = { "LongStrands", "LongThinStrands", "PonytailStrands", "CropStrands", "SweptStrands", "BunStrands", "SidePartStrands", "CurlyStrands", "MohawkStrands" };
        public static readonly string[] BeardStyles = { "FullStrands", "WizardStrands", "DwarfStrands", "GoateeStrands", "MustacheStrands", "ShortStrands", "ShortSideburnsStrands", "ChinStrapStrands" };
        const float ShortHair = 0.09f;

        [MenuItem("Tools/Humans/Hair Cards Spike/Install")]
        public static void Install()
        {
            if (!(AssetImporter.GetAtPath(Atlas) is TextureImporter ti)) { Debug.LogError($"[HairCards] missing {Atlas}"); return; }
            ti.sRGBTexture = false;                       // data: shade, strand id, coverage
            ti.alphaSource = TextureImporterAlphaSource.FromInput;
            ti.alphaIsTransparency = false;
            ti.mipmapEnabled = true;
            ti.mipMapsPreserveCoverage = true;            // the cut keeps the strands' coverage down the mips (no balding at range)
            ti.alphaTestReferenceValue = 0.5f;
            ti.wrapMode = TextureWrapMode.Clamp;
            ti.maxTextureSize = 1024;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
            ti.SaveAndReimport();

            if (!(AssetImporter.GetAtPath(Fbx) is ModelImporter mi)) { Debug.LogError($"[HairCards] missing {Fbx}"); return; }
            mi.importBlendShapes = true;
            mi.importNormals = ModelImporterNormals.Import;
            mi.importBlendShapeNormals = ModelImporterNormals.None;
            mi.importTangents = ModelImporterTangents.CalculateMikk;   // the strand direction (bitangent: +v root -> tip)
            mi.materialImportMode = ModelImporterMaterialImportMode.None;
            mi.animationType = ModelImporterAnimationType.Generic;
            mi.avatarSetup = ModelImporterAvatarSetup.NoAvatar;
            mi.importAnimation = false; mi.importCameras = false; mi.importLights = false;
            mi.meshCompression = ModelImporterMeshCompression.Off;
            mi.isReadable = false;
            mi.SaveAndReimport();

            var sh = Shader.Find("Humans/HairCards");
            if (sh == null) { Debug.LogError("[HairCards] shader Humans/HairCards not found (compile error?)"); return; }
            var mat = AssetDatabase.LoadAssetAtPath<Material>(MatPath);
            if (mat == null) { mat = new Material(sh); AssetDatabase.CreateAsset(mat, MatPath); }
            else mat.shader = sh;
            // the look is tuned in the shader: its defaults overwrite the material's numbers (a saved material kept the
            // first ones; colours come per character by property block)
            for (int i = 0; i < sh.GetPropertyCount(); i++)
            {
                var t = sh.GetPropertyType(i);
                if (t == UnityEngine.Rendering.ShaderPropertyType.Float || t == UnityEngine.Rendering.ShaderPropertyType.Range)
                    mat.SetFloat(sh.GetPropertyNameId(i), sh.GetPropertyDefaultFloatValue(i));
            }
            mat.SetTexture("_Cards", AssetDatabase.LoadAssetAtPath<Texture2D>(Atlas));
            mat.SetTexture("_Strands", AssetDatabase.LoadAssetAtPath<Texture2D>(Strands));
            mat.enableInstancing = false;
            EditorUtility.SetDirty(mat);

            var go = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Fbx));
            PrefabUtility.UnpackPrefabInstance(go, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
            var cut = new SortedDictionary<string, List<HumanPiece.Lod>>(System.StringComparer.Ordinal);
            try
            {
                foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    int i = smr.name.LastIndexOf("_L", System.StringComparison.Ordinal);
                    int lod = i > 0 && i + 2 < smr.name.Length && char.IsDigit(smr.name[i + 2]) ? smr.name[i + 2] - '0' : 0;
                    string piece = lod == 0 ? smr.name : smr.name.Substring(0, i);
                    if (!cut.TryGetValue(piece, out var lods)) cut[piece] = lods = new List<HumanPiece.Lod>();
                    while (lods.Count <= lod) lods.Add(new HumanPiece.Lod());
                    lods[lod] = new HumanPiece.Lod
                    {
                        name = smr.name, mesh = smr.sharedMesh,
                        materials = Enumerable.Repeat(mat, smr.sharedMesh.subMeshCount).ToArray(),
                        bones = smr.bones.Select(b => b != null ? b.name : "").ToArray(),
                        rootBone = smr.rootBone != null ? smr.rootBone.name : "",
                        bounds = smr.localBounds,
                        position = smr.transform.localPosition, rotation = smr.transform.localRotation, scale = smr.transform.localScale,
                    };
                }
            }
            finally { Object.DestroyImmediate(go); }
            foreach (var kv in cut)
            {
                string path = $"{HumanSetup.PieceDir}/{kv.Key}.asset";
                var asset = AssetDatabase.LoadAssetAtPath<HumanPiece>(path);
                bool fresh = asset == null;
                if (fresh) asset = ScriptableObject.CreateInstance<HumanPiece>();
                asset.lods = kv.Value.ToArray();
                asset.limbs = new HumanPiece.LimbFit[0];
                // the sim's data per LOD (LOD2, the colony camera, isn't simulated)
                asset.hairSim = asset.lods.Select((l, i) => i < 2 && l.mesh != null ? HairSimOf(l.mesh, l.bones, HeadVerts()) : new HumanPiece.HairSim()).ToArray();
                // short hair (no strand past ShortHair m) isn't simulated: nothing on it swings
                for (int i = 0; i < asset.hairSim.Length; i++)
                    if (asset.hairSim[i].path.Length > 0 && asset.hairSim[i].path.Max() < ShortHair) asset.hairSim[i] = new HumanPiece.HairSim();
                if (fresh) AssetDatabase.CreateAsset(asset, path);
                else EditorUtility.SetDirty(asset);
            }
            int layers = WriteLayers();
            AssetDatabase.SaveAssets();
            HumanFace.ClearPieceCache();
            HumanHairSimData.ClearCache();
            Debug.Log($"[HairCards] {cut.Count} pieces: " + string.Join(", ", cut.Select(kv =>
                $"{kv.Key} ({kv.Value.Count(l => l.mesh != null)} LODs, {kv.Value[0].mesh.vertexCount} verts)")) +
                $"; sim layers on {layers} garment pieces + the body and head");
        }

        const string DataPath = HumanSetup.Root + "/Resources/" + HumanHairSimData.Path + ".asset";

        /// <summary>The layers simulated hair stays off: every garment piece's LOD0 / LOD1 (HumanPiece.simLayers) and the
        /// prefab's body and head (HumanHairSimData, with the compute shader so builds carry it). Returns the garments done.</summary>
        static int WriteLayers()
        {
            int n = 0;
            foreach (var guid in AssetDatabase.FindAssets("t:HumanPiece", new[] { HumanSetup.PieceDir }))
            {
                var piece = AssetDatabase.LoadAssetAtPath<HumanPiece>(AssetDatabase.GUIDToAssetPath(guid));
                if (piece == null || !piece.name.StartsWith("Cloth_")) continue;
                piece.simLayers = piece.lods.Select((l, i) => i < 2 && l != null && l.mesh != null ? LayerOf(l.mesh, l.bones) : new HumanPiece.SimLayer()).ToArray();
                EditorUtility.SetDirty(piece);
                n++;
            }
            var data = AssetDatabase.LoadAssetAtPath<HumanHairSimData>(DataPath);
            bool fresh = data == null;
            if (fresh) data = ScriptableObject.CreateInstance<HumanHairSimData>();
            data.shader = SimShader();
            var hf = AssetDatabase.LoadAssetAtPath<GameObject>(HumanSetup.PrefabPath)?.GetComponent<HumanFace>();
            if (hf != null)
            {
                HumanPiece.SimLayer Of(SkinnedMeshRenderer r) =>
                    r != null && r.sharedMesh != null ? LayerOf(r.sharedMesh, r.bones.Select(b => b != null ? b.name : "").ToArray()) : new HumanPiece.SimLayer();
                data.body = new[] { Of(hf.bodies.Length > 0 ? hf.bodies[0] : null), Of(hf.bodies.Length > 1 ? hf.bodies[1] : null) };
                data.head = new[] { Of(hf.head), Of(hf.lowerLods != null && hf.lowerLods.Length > 0 ? hf.lowerLods[0].head : null) };
            }
            if (fresh) AssetDatabase.CreateAsset(data, DataPath);
            else EditorUtility.SetDirty(data);
            return n;
        }

        /// <summary>A strand-card mesh's particles (uv4.x: a card row; uv4.y root -> tip): their vertices, strands (rows
        /// are consecutive, the root first), path lengths (unkeyed rest) and skinning (the row's first vertex's).</summary>
        /// <summary>The prefab head's rest vertices (the hair pieces share its mesh space), for HairSimOf's hold.</summary>
        static Vector3[] HeadVerts()
        {
            var hf = AssetDatabase.LoadAssetAtPath<GameObject>(HumanSetup.PrefabPath)?.GetComponent<HumanFace>();
            return hf != null && hf.head != null && hf.head.sharedMesh != null ? hf.head.sharedMesh.vertices : null;
        }

        public static HumanPiece.HairSim HairSimOf(Mesh mesh, string[] boneNames, Vector3[] head = null)
        {
            var guide = new List<Vector2>();
            mesh.GetUVs(4, guide);
            var d = new HumanPiece.HairSim();
            if (guide.Count != mesh.vertexCount) return d;
            var v = mesh.vertices; var bw = mesh.boneWeights; var bp = mesh.bindposes;
            int n = 0;
            foreach (var g in guide) n = Mathf.Max(n, Mathf.RoundToInt(g.x) + 1);
            if (n == 0) return d;
            var verts = new List<int>[n];
            for (int p = 0; p < n; p++) verts[p] = new List<int>();
            var s = new float[n];
            for (int i = 0; i < v.Length; i++)
            {
                int p = Mathf.RoundToInt(guide[i].x);
                if (p < 0) continue;
                verts[p].Add(i);
                s[p] = guide[i].y;
            }
            var rest = new Vector3[n];
            d.vertStart = new int[n + 1];
            var list = new List<int>();
            for (int p = 0; p < n; p++)
            {
                d.vertStart[p] = list.Count;
                list.AddRange(verts[p]);
                foreach (var i in verts[p]) rest[p] += v[i];
                rest[p] /= Mathf.Max(verts[p].Count, 1);
            }
            d.vertStart[n] = list.Count;
            d.vertList = list.ToArray();
            var used = new Dictionary<int, int>();
            int Use(int bi) { if (!used.TryGetValue(bi, out var u)) { u = used.Count; used[bi] = u; } return u; }
            d.parent = new int[n]; d.path = new float[n]; d.skinI = new int[n * 4]; d.skinW = new Vector4[n];
            for (int p = 0; p < n; p++)
            {
                d.parent[p] = p > 0 && s[p] > 1e-4f && s[p - 1] < s[p] ? p - 1 : -1;
                d.path[p] = d.parent[p] < 0 ? 0f : d.path[p - 1] + Vector3.Distance(rest[p], rest[p - 1]);
                var w = verts[p].Count > 0 ? bw[verts[p][0]] : new BoneWeight { weight0 = 1f };
                d.skinI[p * 4] = Use(w.boneIndex0); d.skinI[p * 4 + 1] = Use(w.boneIndex1);
                d.skinI[p * 4 + 2] = Use(w.boneIndex2); d.skinI[p * 4 + 3] = Use(w.boneIndex3);
                d.skinW[p] = new Vector4(w.weight0, w.weight1, w.weight2, w.weight3);
            }
            d.bones = new string[used.Count]; d.bindposes = new Matrix4x4[used.Count];
            foreach (var kv in used) { d.bones[kv.Value] = kv.Key < boneNames.Length ? boneNames[kv.Key] : ""; d.bindposes[kv.Value] = bp[kv.Key]; }
            // hold: each strand's length from the root while it lies on the head (within 2.5 cm of a head vertex: the
            // head's 5k vertices are sparse over the top - every other one within 2 cm let hair lying flat on the
            // crown of the ponytail and the bun go free, a flick of strands at the run's bounce)
            d.hold = new float[n];
            if (head != null && head.Length > 0)
            {
                float held = 0f;
                bool on = false;
                for (int p = 0; p < n; p++)
                {
                    if (d.parent[p] < 0) { held = 0f; on = true; }
                    if (on)
                    {
                        float best = float.MaxValue;
                        for (int k = 0; k < head.Length; k++) best = Mathf.Min(best, (head[k] - rest[p]).sqrMagnitude);
                        if (best < 0.025f * 0.025f) held = d.path[p];
                        else on = false;
                    }
                    d.hold[p] = held;
                }
                for (int p = n - 1; p > 0; p--)                 // every particle of a strand carries the strand's hold
                    if (d.parent[p] >= 0 && p + 1 < n && d.parent[p + 1] == p) d.hold[p] = d.hold[p + 1];
            }
            return d;
        }

        /// <summary>A layer's points: one vertex a <paramref name="cell"/> (m) cube of the mesh's rest, with its body region
        /// (uv1.x) and skinning.</summary>
        public static HumanPiece.SimLayer LayerOf(Mesh mesh, string[] boneNames, float cell = 0.02f)
        {
            var v = mesh.vertices; var bw = mesh.boneWeights; var bp = mesh.bindposes;
            var uv1 = new List<Vector2>(); mesh.GetUVs(1, uv1);
            var cells = new Dictionary<Vector3Int, int>();
            for (int i = 0; i < v.Length; i++)
            {
                var c = Vector3Int.FloorToInt(v[i] / cell);
                if (!cells.ContainsKey(c)) cells[c] = i;
            }
            var used = new Dictionary<int, int>();
            int Use(int bi) { if (!used.TryGetValue(bi, out var u)) { u = used.Count; used[bi] = u; } return u; }
            var d = new HumanPiece.SimLayer();
            int n = cells.Count;
            d.verts = new int[n]; d.region = new int[n]; d.skinI = new int[n * 4]; d.skinW = new Vector4[n];
            int k = 0;
            foreach (var i in cells.Values)
            {
                var w = bw[i];
                d.verts[k] = i;
                d.region[k] = uv1.Count == v.Length ? Mathf.Clamp(Mathf.RoundToInt(uv1[i].x), 0, 30) : 0;
                d.skinI[k * 4] = Use(w.boneIndex0); d.skinI[k * 4 + 1] = Use(w.boneIndex1);
                d.skinI[k * 4 + 2] = Use(w.boneIndex2); d.skinI[k * 4 + 3] = Use(w.boneIndex3);
                d.skinW[k] = new Vector4(w.weight0, w.weight1, w.weight2, w.weight3);
                k++;
            }
            d.bones = new string[used.Count]; d.bindposes = new Matrix4x4[used.Count];
            foreach (var kv in used) { d.bones[kv.Value] = kv.Key < boneNames.Length ? boneNames[kv.Key] : ""; d.bindposes[kv.Value] = bp[kv.Key]; }
            return d;
        }

        public static IEnumerable<string> PieceNames() => Styles.Select(s => "Hair_" + s).Concat(BeardStyles.Select(s => "Beard_" + s));

        /// <summary>A human offers these pieces too: HumanFace wears them for their plain styles.</summary>
        public static void Offer(HumanFace hf)
        {
            var add = PieceNames().Where(n => hf.pieces == null || !hf.pieces.Contains(n)).ToArray();
            if (add.Length > 0) hf.pieces = (hf.pieces ?? new string[0]).Concat(add).ToArray();
        }

        /// <summary>The Human prefab's list gets them (every human in the game and the showcase comes from it).</summary>
        [MenuItem("Tools/Humans/Hair Cards Spike/Offer on the Human prefab")]
        public static void OfferOnPrefab()
        {
            const string path = "Assets/Humans/Prefabs/Human.prefab";
            var root = PrefabUtility.LoadPrefabContents(path);
            try
            {
                Offer(root.GetComponent<HumanFace>());
                PrefabUtility.SaveAsPrefabAsset(root, path);
            }
            finally { PrefabUtility.UnloadPrefabContents(root); }
        }

        public static ComputeShader SimShader()
        {
            var guid = AssetDatabase.FindAssets("HumanHairSim t:ComputeShader").FirstOrDefault();
            return guid != null ? AssetDatabase.LoadAssetAtPath<ComputeShader>(AssetDatabase.GUIDToAssetPath(guid)) : null;
        }
    }
}
