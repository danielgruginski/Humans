using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace Humans.EditorTools
{
    /// <summary>
    /// Tools > Humans > Rebuild Prefab and Showcase
    ///   import settings (Human_Body.fbx as Humanoid, Human_Hair.fbx as Generic, mask textures), materials,
    ///   HumanRigData from human_rig.json (Blender -> model space fitted from the rest skeleton), male/female
    ///   Kevin Iglesias controllers (idle, walk, run), Prefabs/Human.prefab (HumanFace + model: skeleton, bodies and
    ///   heads per LOD + LODGroup; no hair or garments), the pieces (every hairstyle, beard, brows and garment per
    ///   build cut out of Human_Hair.fbx / Human_Cloth_*.fbx into Resources/HumanPieces, made by HumanFace when worn),
    ///   Scenes/Humans_Showcase.unity, renders in Logs/HumanSetup.
    /// </summary>
    public static class HumanSetup
    {
        public const string Root = "Assets/Humans";
        const string Models = Root + "/Models", Textures = Root + "/Textures", Data = Root + "/Data",
            Materials = Root + "/Materials", Prefabs = Root + "/Prefabs", Scenes = Root + "/Scenes", Anim = Root + "/Animation";
        const string BodyFbx = Models + "/Human_Body.fbx", HairFbx = Models + "/Human_Hair.fbx";

        /// <summary>Garments ship as one FBX per outfit family (Human_Cloth_Clothes, _Leather, _Plate, ...).</summary>
        static string[] ClothFbxs() => AssetDatabase.FindAssets("Human_Cloth_ t:Model", new[] { Models })
            .Select(AssetDatabase.GUIDToAssetPath).Where(p => Path.GetFileName(p).StartsWith("Human_Cloth_")).OrderBy(p => p).ToArray();
        const string ConfigPath = Data + "/human_face_config.json", RigJson = Data + "/human_rig.json";
        const string RigAsset = Data + "/HumanRigData.asset";
        public const string PrefabPath = Prefabs + "/Human.prefab";
        /// <summary>one HumanPiece per hairstyle, beard, brows and garment per build (loaded by name when worn)</summary>
        public const string PieceDir = Root + "/Resources/" + HumanPiece.Folder;
        public const string ScenePath = Scenes + "/Humans_Showcase.unity";
        const string Clips = Anim + "/Clips", ClipsJson = Data + "/human_clips.json";

        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Logs", "HumanSetup"));

        [MenuItem("Tools/Humans/Rebuild Prefab and Showcase")]
        public static void RebuildAll()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                Debug.LogError("[HumanSetup] leave play mode first: the showcase scene can't be rebuilt while playing");
                return;
            }
            HumanFaceConfig.ClearCache();
            HumanFace.ClearPieceCache();
            foreach (var d in new[] { Materials, Prefabs, Scenes, Anim, Data, PieceDir }) EnsureFolder(d);
            if (AssetDatabase.LoadAssetAtPath<Object>(Models + "/Human_Head.fbx") != null)
                AssetDatabase.DeleteAsset(Models + "/Human_Head.fbx");            // superseded by Human_Body.fbx
            ConfigureTextures();
            ConfigureModel(BodyFbx, true);
            ConfigureModel(HairFbx, false);
            foreach (var p in ClothFbxs()) ConfigureModel(p, false);
            var mats = BuildMaterials();
            EnsureFolder(Clips);
            ConfigureClips();
            var (male, female) = BuildControllers();
            var prefab = BuildPrefab(mats, male, female);
            BuildScene(prefab);
            RenderChecks();
            Debug.Log($"[HumanSetup] done: {PrefabPath}, {ScenePath}, renders in {OutDir}");
        }

        static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            var parent = Path.GetDirectoryName(path).Replace('\\', '/');
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }

        static void ConfigureTextures()
        {
            foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { Textures }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!(AssetImporter.GetAtPath(path) is TextureImporter ti)) continue;
                bool pattern = path.Contains("T_Cloth_") || path.Contains("T_Plate_Steel");
                bool mask = path.Contains("T_Plate_Ornament");  // a tiling height/coverage mask: data, not colour
                ti.sRGBTexture = pattern;                        // masks and data are not colours; fabric patterns are
                ti.alphaSource = TextureImporterAlphaSource.FromInput;
                ti.alphaIsTransparency = false;
                ti.mipmapEnabled = true;
                ti.wrapMode = path.Contains("Strands") || pattern || mask ? TextureWrapMode.Repeat : TextureWrapMode.Clamp;
                ti.maxTextureSize = mask ? 512 : path.Contains("Eye") || pattern ? 256 : 1024;
                ti.textureCompression = TextureImporterCompression.CompressedHQ;
                if (mask)
                {
                    // T_Plate_Ornament is a vertical strip of square patterns: import it as a texture array
                    ti.GetSourceTextureWidthAndHeight(out int w, out int h);
                    var st = new TextureImporterSettings();
                    ti.ReadTextureSettings(st);
                    st.textureShape = TextureImporterShape.Texture2DArray;
                    st.flipbookColumns = 1;
                    st.flipbookRows = Mathf.Max(1, h / Mathf.Max(w, 1));
                    ti.SetTextureSettings(st);
                    ti.maxTextureSize = 2048;
                }
                ti.SaveAndReimport();
            }
        }

        /// <summary>Body: Humanoid, smooth calculated normals (180 deg; 60 creased nostrils and lids).
        /// Hair and clothes: Generic (keeps the skin), Blender's normals, no blend-shape normals.</summary>
        static void ConfigureModel(string path, bool body)
        {
            if (!(AssetImporter.GetAtPath(path) is ModelImporter mi)) { Debug.LogError($"[HumanSetup] missing {path}"); return; }
            mi.importBlendShapes = true;
            mi.importNormals = body ? ModelImporterNormals.Calculate : ModelImporterNormals.Import;
            mi.normalCalculationMode = ModelImporterNormalCalculationMode.AreaAndAngleWeighted;
            mi.normalSmoothingAngle = 180f;
            mi.importBlendShapeNormals = body ? ModelImporterNormals.Calculate : ModelImporterNormals.None;
            mi.importTangents = ModelImporterTangents.None;
            mi.materialImportMode = ModelImporterMaterialImportMode.None;
            mi.animationType = body ? ModelImporterAnimationType.Human : ModelImporterAnimationType.Generic;
            mi.avatarSetup = body ? ModelImporterAvatarSetup.CreateFromThisModel : ModelImporterAvatarSetup.NoAvatar;
            mi.importAnimation = false;
            mi.importCameras = false;
            mi.importLights = false;
            mi.meshCompression = ModelImporterMeshCompression.Off;
            mi.isReadable = false;
            mi.SaveAndReimport();
            if (body)
            {
                var avatar = AssetDatabase.LoadAllAssetsAtPath(path).OfType<Avatar>().FirstOrDefault();
                Debug.Log($"[HumanSetup] avatar valid={avatar != null && avatar.isValid} human={avatar != null && avatar.isHuman}");
            }
        }

        struct Mats { public Material skin, eye, hair, body, cloth, leather, quilt, mail, plate; }

        static Mats BuildMaterials()
        {
            Material Make(string name, string shader)
            {
                var path = $"{Materials}/{name}.mat";
                var m = AssetDatabase.LoadAssetAtPath<Material>(path);
                var sh = Shader.Find(shader);
                if (sh == null) Debug.LogError($"[HumanSetup] shader {shader} not found (compile error?)");
                if (m == null) { m = new Material(sh); AssetDatabase.CreateAsset(m, path); }
                else m.shader = sh;
                return m;
            }
            Texture2D Tex(string n) => AssetDatabase.LoadAssetAtPath<Texture2D>($"{Textures}/{n}.png");
            var mats = new Mats
            {
                skin = Make("M_HumanSkin", "Humans/Skin"),
                eye = Make("M_HumanEye", "Humans/Eye"),
                hair = Make("M_HumanHair", "Humans/Hair"),
                body = Make("M_HumanBody", "Humans/Body"),
                cloth = Make("M_HumanCloth", "Humans/Cloth"),
                leather = Make("M_HumanLeather", "Humans/Cloth"),
                quilt = Make("M_HumanQuilt", "Humans/Cloth"),
                mail = Make("M_HumanMail", "Humans/Cloth"),
                plate = Make("M_HumanPlate", "Humans/Plate"),
            };
            mats.plate.SetTexture("_Pattern", Tex("T_Plate_Steel"));
            mats.plate.SetTexture("_Ornament", AssetDatabase.LoadAssetAtPath<Texture2DArray>($"{Textures}/T_Plate_Ornament.png"));
            mats.plate.SetFloat("_Smoothness", 0.5f);
            mats.plate.SetFloat("_OrnTile", 1.0f);
            mats.plate.SetVector("_OrnTiles", new Vector4(1f, 0.5f, 1f, 1f));   // acanthus, damask (2x larger)
            mats.plate.SetFloat("_PolishSmoothness", 0.8f);
            mats.cloth.SetTexture("_Pattern", Tex("T_Cloth_Weave"));
            mats.cloth.SetFloat("_Smoothness", 0.12f);
            mats.leather.SetTexture("_Pattern", Tex("T_Cloth_Leather"));
            mats.leather.SetFloat("_Smoothness", 0.35f);
            mats.quilt.SetTexture("_Pattern", Tex("T_Cloth_Quilt"));
            mats.quilt.SetFloat("_Smoothness", 0.08f);
            mats.mail.SetTexture("_Pattern", Tex("T_Cloth_Mail"));
            mats.mail.SetFloat("_Smoothness", 0.42f);
            mats.mail.SetFloat("_Triplanar", 1f);
            mats.mail.SetFloat("_TriTile", 0.24f);                 // 24 rings per tile: 1 cm rings
            foreach (var m in new[] { mats.cloth, mats.leather, mats.quilt, mats.mail }) m.SetColor("_Metal", new Color(0.68f, 0.68f, 0.7f));
            mats.skin.SetTexture("_MaskA", Tex("T_Head_MaskA"));
            mats.skin.SetTexture("_MaskB", Tex("T_Head_MaskB"));
            mats.skin.SetTexture("_MaskC", Tex("T_Head_MaskC"));
            mats.eye.SetTexture("_EyeMask", Tex("T_Eye_Mask"));
            mats.eye.SetFloat("_Smoothness", 0.72f);
            mats.hair.SetTexture("_Strands", Tex("T_Hair_Strands"));
            mats.body.SetTexture("_MaskA", Tex("T_Body_MaskA"));
            mats.body.SetTexture("_MaskB", Tex("T_Body_MaskB"));
            mats.body.SetTexture("_SuitPattern", Tex("T_Cloth_Weave"));
            foreach (var m in new[] { mats.skin, mats.eye, mats.hair, mats.body, mats.cloth, mats.leather, mats.quilt, mats.mail, mats.plate }) EditorUtility.SetDirty(m);
            AssetDatabase.SaveAssets();
            return mats;
        }

        // ------------------------------------------------------------------ animation

        [System.Serializable] class ClipInfo { public string name; public int frames; public bool loop, bakeRootRotation; public float speed; }
        [System.Serializable] class ClipTable { public ClipInfo[] clips; public int fps; }

        /// <summary>Our clips (Human@<clip>.fbx from hum_anim): Humanoid with the body's avatar, so one set drives
        /// every build and both sexes; in place (root height and position baked into the pose); loops from
        /// human_clips.json; the turns keep their yaw as root motion.</summary>
        static void ConfigureClips()
        {
            var json = AssetDatabase.LoadAssetAtPath<TextAsset>(ClipsJson);
            if (json == null) { Debug.LogWarning($"[HumanSetup] no {ClipsJson}: no animation clips"); return; }
            var table = JsonUtility.FromJson<ClipTable>(json.text);
            var avatar = AssetDatabase.LoadAllAssetsAtPath(BodyFbx).OfType<Avatar>().FirstOrDefault();
            foreach (var c in table.clips)
            {
                var path = $"{Clips}/Human@{c.name}.fbx";
                if (!(AssetImporter.GetAtPath(path) is ModelImporter mi)) { Debug.LogWarning($"[HumanSetup] missing {path}"); continue; }
                mi.importCameras = mi.importLights = false;
                mi.materialImportMode = ModelImporterMaterialImportMode.None;
                mi.animationType = ModelImporterAnimationType.Human;
                mi.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
                mi.sourceAvatar = avatar;
                mi.importAnimation = true;
                mi.SaveAndReimport();
                var clips = mi.defaultClipAnimations;
                foreach (var ca in clips)
                {
                    ca.name = c.name;
                    ca.firstFrame = 0;
                    ca.lastFrame = c.frames;
                    ca.loopTime = c.loop;
                    ca.loopPose = false;                          // authored to close exactly
                    ca.lockRootRotation = c.bakeRootRotation;
                    ca.keepOriginalOrientation = true;
                    ca.lockRootHeightY = true;
                    ca.keepOriginalPositionY = true;
                    ca.lockRootPositionXZ = true;
                    ca.keepOriginalPositionXZ = true;
                }
                mi.clipAnimations = clips;
                mi.SaveAndReimport();
            }
        }

        static AnimationClip OwnClip(string name)
        {
            var clip = AssetDatabase.LoadAllAssetsAtPath($"{Clips}/Human@{name}.fbx").OfType<AnimationClip>()
                .FirstOrDefault(c => !c.name.StartsWith("__preview__"));
            if (clip == null) Debug.LogWarning($"[HumanSetup] no clip {name}");
            return clip;
        }

        /// <summary>The "Motion" int picks the state (HumanFace.Motions has the names): 0 Idle, 1 Walk, 2 Run, 3 Chop,
        /// 4 Hammer, 5 Sit (Sit_Down -> Sit_Idle; leaving 5 plays Stand_Up), 6 Death (held; 0 revives), 7 Turn_L90,
        /// 8 Turn_R90 (play once and hold; they carry root rotation), 9 Idle_Look, 10 Idle_Shift; combat (looped, in
        /// a fighting stance): 11 Sword_Idle, 12 Sword_Slash, 13 Sword_Overhead, 14 Shield_Block (sword and shield),
        /// 15 TwoHand_Idle, 16 TwoHand_Swing, 17 TwoHand_Overhead, 18 Spear_Idle, 19 Spear_Thrust, 20 Spear_Jab.</summary>
        public static readonly string[] MotionStates =
            { "Idle", "Walk", "Run", "Chop", "Hammer", "Sit_Down", "Death", "Turn_L90", "Turn_R90", "Idle_Look", "Idle_Shift",
              "Sword_Idle", "Sword_Slash", "Sword_Overhead", "Shield_Block",
              "TwoHand_Idle", "TwoHand_Swing", "TwoHand_Overhead", "Spear_Idle", "Spear_Thrust", "Spear_Jab" };

        /// <summary>The combat states, per stand-in weapon (HumanToolPreview shows each set's props).</summary>
        static readonly string[] SwordStates = { "Sword_Idle", "Sword_Slash", "Sword_Overhead", "Shield_Block" };
        static readonly string[] TwoHandStates = { "TwoHand_Idle", "TwoHand_Swing", "TwoHand_Overhead" };
        static readonly string[] SpearStates = { "Spear_Idle", "Spear_Thrust", "Spear_Jab" };

        static (AnimatorController, AnimatorController) BuildControllers()
        {
            var path = $"{Anim}/Humans_Motion.controller";
            AssetDatabase.DeleteAsset(path);
            foreach (var old in new[] { "Human_M", "Human_F" }) AssetDatabase.DeleteAsset($"{Anim}/{old}.controller");
            var ac = AnimatorController.CreateAnimatorControllerAtPath(path);
            ac.AddParameter("Motion", AnimatorControllerParameterType.Int);
            var sm = ac.layers[0].stateMachine;
            var st = new Dictionary<string, AnimatorState>();
            int k = 0;
            foreach (var n in MotionStates.Concat(new[] { "Sit_Idle", "Stand_Up" }))
            {
                var s = sm.AddState(n, new Vector3(250 + 230 * (k % 4), 60 * (k / 4) * 2, 0));
                s.motion = OwnClip(n);
                st[n] = s;
                k++;
            }
            sm.defaultState = st["Idle"];

            AnimatorStateTransition T(string from, string to, float dur = 0.2f, float exit = -1f)
            {
                var t = st[from].AddTransition(st[to]);
                t.duration = dur;
                t.hasExitTime = exit >= 0;
                if (exit >= 0) t.exitTime = exit;
                return t;
            }
            // free states reach every motion directly
            var free = new[] { "Idle", "Walk", "Run", "Chop", "Hammer", "Turn_L90", "Turn_R90", "Idle_Look", "Idle_Shift", "Stand_Up" }
                .Concat(SwordStates).Concat(TwoHandStates).Concat(SpearStates);
            foreach (var a in free)
                for (int i = 0; i < MotionStates.Length; i++)
                    if (MotionStates[i] != a)
                        T(a, MotionStates[i]).AddCondition(AnimatorConditionMode.Equals, i, "Motion");
            // sitting: down -> idle; leaving 5 stands up first
            T("Sit_Down", "Sit_Idle", 0.1f, 0.95f);
            T("Sit_Down", "Stand_Up", 0.2f).AddCondition(AnimatorConditionMode.NotEqual, 5, "Motion");
            T("Sit_Idle", "Stand_Up", 0.2f).AddCondition(AnimatorConditionMode.NotEqual, 5, "Motion");
            T("Stand_Up", "Idle", 0.15f, 0.95f);
            // turns play once and hold their last frame (the idle pose, 90 degrees round) until Motion changes, so a
            // held 7/8 doesn't spin; death holds until Motion 0
            T("Death", "Idle", 0.4f).AddCondition(AnimatorConditionMode.Equals, 0, "Motion");
            AssetDatabase.SaveAssets();
            return (ac, ac);
        }

        // ------------------------------------------------------------------ rig data

        [System.Serializable] class JBone { public string name, parent; public float[] rest; }
        [System.Serializable] class JDelta { public string bone; public float[] d; }
        [System.Serializable] class JKey { public string key; public JDelta[] bones; }
        [System.Serializable] class JRatios { public float tall, @short; }
        [System.Serializable] class JHelper { public string name, parent, source, drive, mate, baseBone, raiseOf, hang; public float f, fBack, fRaised, raiseFrom, raiseTo; }
        [System.Serializable] class JSpring { public string[] bones; }
        [System.Serializable] class JSkirtColumn { public string hip, knee, hem; public float side; }
        [System.Serializable] class JSkirt { public JSkirtColumn[] columns; public float raiseFrom, raiseTo; }
        [System.Serializable] class JRig { public JBone[] bones; public JKey[] keys; public JRatios heightRatios; public string hipsBone; public JHelper[] helpers; public JSpring[] springs; public JSkirt[] skirts; }

        /// <summary>HumanSkirt per skirt ring in human_rig.json: the columns' bind data (hanging directions in the
        /// Animator's frame, the knee points in each thigh's space) and capsules on the thighs, calves, heels and
        /// toes. Call before anything poses the model.</summary>
        static void AddSkirts(GameObject root, Dictionary<string, Transform> boneMap)
        {
            var json = JsonUtility.FromJson<JRig>(File.ReadAllText(Path.GetFullPath(RigJson)));
            var facing = root.GetComponentInChildren<Animator>(true)?.transform ?? root.transform;
            Transform B(string n) => boneMap.TryGetValue(n, out var t) ? t : null;
            Vector3 AxisOf(Transform t)
            {
                foreach (Transform c in t)
                    if (c.localPosition.sqrMagnitude > 1e-6f) return t.InverseTransformDirection(c.position - t.position).normalized;
                return Vector3.up;
            }
            var inv = Quaternion.Inverse(facing.rotation);
            foreach (var s in json.skirts ?? new JSkirt[0])
            {
                Transform tl = B("thigh_l"), tr = B("thigh_r");
                if (tl == null || tr == null) { Debug.LogWarning("[HumanSetup] skirt: thighs missing"); continue; }
                var cols = new List<HumanSkirt.Column>();
                foreach (var c in s.columns)
                {
                    Transform hip = B(c.hip), knee = B(c.knee), hem = B(c.hem);
                    if (hip == null || knee == null || hem == null) { Debug.LogWarning($"[HumanSetup] skirt column {c.hip}: bones missing"); continue; }
                    cols.Add(new HumanSkirt.Column
                    {
                        hip = hip, knee = knee, hem = hem,
                        hipRest = hip.localRotation, kneeRest = knee.localRotation,
                        hangHip = inv * (knee.position - hip.position).normalized,
                        hangKnee = inv * (hem.position - knee.position).normalized,
                        kneeInThighL = tl.InverseTransformPoint(knee.position),
                        kneeInThighR = tr.InverseTransformPoint(knee.position),
                        side = c.side,
                    });
                }
                var sk = root.AddComponent<HumanSkirt>();
                sk.columns = cols.ToArray();
                sk.facing = facing;
                sk.thighL = tl; sk.thighR = tr;
                sk.thighLRest = tl.localRotation; sk.thighRRest = tr.localRotation;
                sk.thighAxisL = AxisOf(tl); sk.thighAxisR = AxisOf(tr);
                sk.raise = new Vector2(s.raiseFrom, s.raiseTo);
                HumanSkirt.Capsule Cap(string a, string b, float r, Vector3 bLocal = default) =>
                    new HumanSkirt.Capsule { a = B(a), b = B(b), bLocal = bLocal, radius = r };
                // the heel: 5 cm behind and 3.5 cm below the ankle joint, in the foot's space
                Vector3 Heel(string foot) { var f = B(foot); return f == null ? Vector3.zero : f.InverseTransformPoint(f.position - facing.forward * 0.05f - facing.up * 0.035f); }
                sk.colliders = new[]
                {
                    // the legs' own size: the chain runs 3 cm outside them and a garment's slack says where its
                    // cloth is beyond that (HumanSkirt)
                    Cap("thigh_l", "calf_l", 0.055f), Cap("thigh_r", "calf_r", 0.055f),
                    Cap("calf_l", "foot_l", 0.055f), Cap("calf_r", "foot_r", 0.055f),       // (boots are thick)
                    Cap("foot_l", "foot_l", 0.055f, Heel("foot_l")), Cap("foot_r", "foot_r", 0.055f, Heel("foot_r")),
                    Cap("foot_l", "ball_l", 0.05f), Cap("foot_r", "ball_r", 0.05f),
                };
                Debug.Log($"[HumanSetup] skirt ring: {cols.Count} columns");
            }
        }

        /// <summary>HumanSpringChain per spring in human_rig.json (the cape): bind rotations, the tip extrapolated
        /// from the last two links, collision capsules on the spine, pelvis and legs.</summary>
        static void AddSpringChains(GameObject root, Dictionary<string, Transform> boneMap)
        {
            var json = JsonUtility.FromJson<JRig>(File.ReadAllText(Path.GetFullPath(RigJson)));
            foreach (var s in json.springs ?? new JSpring[0])
            {
                var bones = s.bones.Select(b => boneMap.TryGetValue(b, out var t) ? t : null).ToArray();
                if (bones.Length < 2 || bones.Any(b => b == null)) { Debug.LogWarning("[HumanSetup] spring chain: bones missing"); continue; }
                var last = bones[bones.Length - 1];
                var tipWorld = last.position + (last.position - bones[bones.Length - 2].position);
                HumanSpringChain.Capsule Cap(string a, string b, float r) =>
                    new HumanSpringChain.Capsule { a = boneMap.TryGetValue(a, out var ta) ? ta : null, b = boneMap.TryGetValue(b, out var tb) ? tb : null, radius = r };
                var chain = root.AddComponent<HumanSpringChain>();
                chain.bones = bones;
                chain.restLocal = bones.Select(b => b.localRotation).ToArray();
                chain.tipLocal = last.InverseTransformPoint(tipWorld);
                chain.colliders = new[]
                {
                    Cap("spine_01", "neck_01", 0.13f), Cap("pelvis", "spine_01", 0.15f),
                    Cap("thigh_l", "calf_l", 0.09f), Cap("thigh_r", "calf_r", 0.09f),
                    Cap("calf_l", "foot_l", 0.065f), Cap("calf_r", "foot_r", 0.065f),
                };
                Debug.Log($"[HumanSetup] spring chain {string.Join(",", s.bones)}");
            }
        }

        /// <summary>HumanHelperBones on the prefab root, from human_rig.json's helpers; rest rotations read from
        /// the bind pose (call before anything poses the model).</summary>
        static void AddHelperBones(GameObject root, Dictionary<string, Transform> boneMap)
        {
            var json = JsonUtility.FromJson<JRig>(File.ReadAllText(Path.GetFullPath(RigJson)));
            var list = new List<HumanHelperBones.Helper>();
            var facingT = root.GetComponentInChildren<Animator>(true)?.transform;
            foreach (var h in json.helpers ?? new JHelper[0])
            {
                if (!boneMap.TryGetValue(h.name, out var bone) || !boneMap.TryGetValue(h.source, out var src))
                {
                    Debug.LogWarning($"[HumanSetup] helper {h.name}: bone or source {h.source} missing");
                    continue;
                }
                // the source's axis: toward its child joint (the calf for a thigh)
                Vector3 AxisOf(Transform t)
                {
                    foreach (Transform c in t)
                        if (c.localPosition.sqrMagnitude > 1e-6f) return t.InverseTransformDirection(c.position - t.position).normalized;
                    return Vector3.up;
                }
                var axis = AxisOf(src);
                Transform mate = null;
                if (!string.IsNullOrEmpty(h.mate)) boneMap.TryGetValue(h.mate, out mate);
                Transform baseBone = null, raiseSrc = null;
                if (!string.IsNullOrEmpty(h.baseBone)) boneMap.TryGetValue(h.baseBone, out baseBone);
                if (!string.IsNullOrEmpty(h.raiseOf)) boneMap.TryGetValue(h.raiseOf, out raiseSrc);
                list.Add(new HumanHelperBones.Helper
                {
                    bone = bone, source = src, counter = h.drive == "counter", factor = h.f,
                    restLocal = bone.localRotation, sourceRestLocal = src.localRotation,
                    restRel = Quaternion.Inverse((baseBone != null ? baseBone : src.parent).rotation) * bone.rotation,
                    baseBone = baseBone, raiseSource = raiseSrc,
                    hang = h.hang == "front" ? 1 : h.hang == "back" ? 2 : 0,
                    hangRest = facingT != null
                        ? Quaternion.Inverse(facingT.rotation) * (src.parent.rotation * src.localRotation * axis) : Vector3.down,
                    raiseRestLocal = raiseSrc != null ? raiseSrc.localRotation : Quaternion.identity,
                    raiseAxis = raiseSrc != null ? AxisOf(raiseSrc) : Vector3.up,
                    factorBack = h.fBack, factorRaised = h.raiseTo > h.raiseFrom ? h.fRaised : h.f,
                    raiseFrom = h.raiseFrom, raiseTo = h.raiseTo,
                    sourceAxis = axis,
                    mate = mate, mateRestLocal = mate != null ? mate.localRotation : Quaternion.identity,
                    mateAxis = mate != null ? AxisOf(mate) : Vector3.up,
                });
            }
            var hb = root.AddComponent<HumanHelperBones>();
            hb.helpers = list.ToArray();
            var anim = root.GetComponentInChildren<Animator>(true);
            hb.facing = anim != null ? anim.transform : root.transform;
            Debug.Log($"[HumanSetup] {list.Count} helper bones");
        }

        /// <summary>Rig data in model space. The Blender -> model mapping is fitted (least squares) from the
        /// rest bone heads, so no axis convention is assumed.</summary>
        static HumanRigData BuildRigData(Transform model, Dictionary<string, Transform> boneMap, out Transform[] bones)
        {
            var json = JsonUtility.FromJson<JRig>(File.ReadAllText(Path.GetFullPath(RigJson)));
            int n = json.bones.Length;
            var names = json.bones.Select(b => b.name).ToArray();
            var index = new Dictionary<string, int>();
            for (int i = 0; i < n; i++) index[names[i]] = i;
            bones = names.Select(b => boneMap.TryGetValue(b, out var t) ? t : null).ToArray();
            // fit u = M b + t over bones present in both
            var B = new List<Vector3>();
            var U = new List<Vector3>();
            for (int i = 0; i < n; i++)
                if (bones[i] != null)
                {
                    B.Add(new Vector3(json.bones[i].rest[0], json.bones[i].rest[1], json.bones[i].rest[2]));
                    U.Add(model.InverseTransformPoint(bones[i].position));
                }
            var bc = B.Aggregate(Vector3.zero, (a, v) => a + v) / B.Count;
            var uc = U.Aggregate(Vector3.zero, (a, v) => a + v) / U.Count;
            Matrix4x4 A = Matrix4x4.zero, S = Matrix4x4.zero;
            for (int i = 0; i < B.Count; i++)
            {
                var b = B[i] - bc; var u = U[i] - uc;
                for (int r = 0; r < 3; r++)
                    for (int c = 0; c < 3; c++) { A[r, c] += u[r] * b[c]; S[r, c] += b[r] * b[c]; }
            }
            S[3, 3] = 1; A[3, 3] = 1;
            var M = A * S.inverse;
            float err = 0;
            for (int i = 0; i < B.Count; i++) err = Mathf.Max(err, (M.MultiplyVector(B[i] - bc) + uc - U[i]).magnitude);
            Debug.Log($"[HumanSetup] Blender->model fit: max error {err * 1000f:0.0} mm; rows {M.GetRow(0)} {M.GetRow(1)} {M.GetRow(2)}");

            var data = AssetDatabase.LoadAssetAtPath<HumanRigData>(RigAsset);
            if (data == null) { data = ScriptableObject.CreateInstance<HumanRigData>(); AssetDatabase.CreateAsset(data, RigAsset); }
            data.bones = names;
            data.parents = json.bones.Select(b => string.IsNullOrEmpty(b.parent) ? -1 : index[b.parent]).ToArray();
            data.keys = json.keys.Select(k => new HumanRigData.KeyDelta
            {
                key = k.key,
                bones = k.bones.Select(d => index[d.bone]).ToArray(),
                deltas = k.bones.Select(d => M.MultiplyVector(new Vector3(d.d[0], d.d[1], d.d[2]))).ToArray(),
            }).ToArray();
            data.tallRatio = json.heightRatios.tall;
            data.shortRatio = json.heightRatios.@short;
            data.hipsIndex = index[json.hipsBone];
            EditorUtility.SetDirty(data);
            AssetDatabase.SaveAssets();
            return data;
        }

        // ------------------------------------------------------------------ prefab

        static int LodOf(string name)
        {
            int i = name.LastIndexOf("_L", System.StringComparison.Ordinal);
            return i > 0 && int.TryParse(name.Substring(i + 2), out var l) ? l : 0;
        }

        static GameObject BuildPrefab(Mats mats, AnimatorController male, AnimatorController female)
        {
            var root = new GameObject("Human");
            var model = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(BodyFbx), root.transform);
            PrefabUtility.UnpackPrefabInstance(model, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
            model.name = "Model";
            var boneMap = new Dictionary<string, Transform>();
            foreach (var t in model.GetComponentsInChildren<Transform>(true)) boneMap[t.name] = t;

            SkinnedMeshRenderer Smr(string n) => boneMap.TryGetValue(n, out var t) ? t.GetComponent<SkinnedMeshRenderer>() : null;
            var heads = new[] { Smr("Head"), Smr("Head_L1"), Smr("Head_L2") };
            var bodies = new[] { Smr("Body"), Smr("Body_L1"), Smr("Body_L2") };
            foreach (var h in heads) if (h) h.sharedMaterials = new[] { mats.skin, mats.eye };
            foreach (var b in bodies) if (b) b.sharedMaterial = mats.body;

            // hair, beards, brows and garments are not in the prefab: each piece is cut out into a HumanPiece (its
            // meshes per LOD, materials, the skeleton bones by name) that HumanFace makes when it is worn. The prefab
            // keeps the empty containers: one per LOD for hair, one "Clothes" for every garment LOD.
            var hairRoots = new Transform[3];
            for (int l = 0; l < 3; l++)
            {
                hairRoots[l] = new GameObject(l == 0 ? "Hair" : $"HairLod{l}").transform;
                hairRoots[l].SetParent(model.transform, false);
            }
            var clothRoot = new GameObject("Clothes").transform;
            clothRoot.SetParent(model.transform, false);
            var cut = new SortedDictionary<string, List<HumanPiece.Lod>>(System.StringComparer.Ordinal);
            void Cut(SkinnedMeshRenderer smr, Material[] materials)
            {
                int lod = LodOf(smr.name);
                string piece = lod == 0 ? smr.name : smr.name.Substring(0, smr.name.LastIndexOf("_L", System.StringComparison.Ordinal));
                if (!cut.TryGetValue(piece, out var lods)) cut[piece] = lods = new List<HumanPiece.Lod>();
                while (lods.Count <= lod) lods.Add(new HumanPiece.Lod());
                lods[lod] = new HumanPiece.Lod
                {
                    name = smr.name, mesh = smr.sharedMesh, materials = materials,
                    bones = smr.bones.Select(b => b != null && boneMap.ContainsKey(b.name) ? b.name : "").ToArray(),
                    rootBone = smr.rootBone != null && boneMap.ContainsKey(smr.rootBone.name) ? smr.rootBone.name : "",
                    bounds = smr.localBounds,
                    position = smr.transform.localPosition, rotation = smr.transform.localRotation, scale = smr.transform.localScale,
                };
            }
            var hair = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(HairFbx));
            PrefabUtility.UnpackPrefabInstance(hair, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
            foreach (var smr in hair.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                Cut(smr, Enumerable.Repeat(mats.hair, smr.sharedMesh.subMeshCount).ToArray());
            Object.DestroyImmediate(hair);
            var cfg = HumanFaceConfig.Load(AssetDatabase.LoadAssetAtPath<TextAsset>(ConfigPath));
            var clothFbxs = ClothFbxs();
            if (clothFbxs.Length == 0) Debug.LogWarning($"[HumanSetup] no {Models}/Human_Cloth_*.fbx: no garments");
            foreach (var clothPath in clothFbxs)
            {
                var cloth = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(clothPath));
                PrefabUtility.UnpackPrefabInstance(cloth, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
                foreach (var smr in cloth.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    string g = smr.name.Substring("Cloth_".Length).Split('_')[0];      // Cloth_<G>_<build>[_L<n>]
                    var kind = cfg.FindGarment(g)?.material;
                    var mat = kind == "leather" ? mats.leather : kind == "quilt" ? mats.quilt : kind == "mail" ? mats.mail
                            : kind == "plate" ? mats.plate : mats.cloth;
                    Cut(smr, Enumerable.Repeat(mat, smr.sharedMesh.subMeshCount).ToArray());
                }
                Object.DestroyImmediate(cloth);
            }
            WritePieces(cut);

            var all = model.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            foreach (var smr in all)
            {
                smr.updateWhenOffscreen = false;
                smr.skinnedMotionVectors = false;
            }

            var hf = root.AddComponent<HumanFace>();
            hf.config = AssetDatabase.LoadAssetAtPath<TextAsset>(ConfigPath);
            hf.head = heads[0];
            hf.hairRoot = hairRoots[0];
            hf.lowerLods = new[]
            {
                new HumanFace.LodSet { head = heads[1], hairRoot = hairRoots[1] },
                new HumanFace.LodSet { head = heads[2], hairRoot = hairRoots[2], minPaintedBrows = 0.8f },
            };
            hf.bodies = bodies;
            hf.clothRoot = clothRoot;
            hf.pieces = cut.Keys.ToArray();
            hf.modelRoot = model.transform;
            hf.animator = model.GetComponent<Animator>();
            // our clips are in place (height and XZ baked into the pose); only the turns carry root yaw, so root
            // motion just makes Turn_L90/R90 rotate the model. Games that steer rotation themselves turn it off.
            if (hf.animator != null) hf.animator.applyRootMotion = true;
            hf.maleController = male;
            hf.femaleController = female;
            AddHelperBones(root, boneMap);
            AddSpringChains(root, boneMap);
            AddSkirts(root, boneMap);
            // hand sockets from the rest skeleton (and the shield's on the left forearm), then the stand-in props
            // shown while their states play
            var socketR = AddHandSocket(boneMap, "r");
            AddHandSocket(boneMap, "l");
            var socketShield = AddShieldSocket(boneMap);
            var preview = root.AddComponent<HumanToolPreview>();
            preview.animator = hf.animator;
            string sword = string.Join(",", SwordStates);
            preview.tools = new[]
            {
                new HumanToolPreview.StateTool { state = "Chop", tool = BuildHelperAxe(socketR) },
                new HumanToolPreview.StateTool { state = "Hammer", tool = BuildHelperHammer(socketR) },
                new HumanToolPreview.StateTool { state = sword, tool = BuildHelperSword(socketR) },
                new HumanToolPreview.StateTool { state = sword, tool = BuildHelperShield(socketShield) },
                new HumanToolPreview.StateTool { state = string.Join(",", TwoHandStates), tool = BuildHelperGreatsword(socketR) },
                new HumanToolPreview.StateTool { state = string.Join(",", SpearStates), tool = BuildHelperSpear(socketR) },
            };
            hf.rig = BuildRigData(model.transform, boneMap, out var bones);
            hf.bones = bones;
            hf.restLocal = bones.Select(b => b != null ? b.localPosition : Vector3.zero).ToArray();
            hf.restToParent = bones.Select(b => b != null && b.parent != null
                ? b.parent.worldToLocalMatrix * model.transform.localToWorldMatrix : Matrix4x4.identity).ToArray();

            // LODGroup: portrait up close, LOD1 mid distance, LOD2 for the colony camera (~40 m)
            var lods = new List<Renderer>[3] { new List<Renderer>(), new List<Renderer>(), new List<Renderer>() };
            foreach (var smr in all) lods[LodOf(smr.name)].Add(smr);
            var group = root.AddComponent<LODGroup>();
            group.SetLODs(new[] { new LOD(0.25f, lods[0].ToArray()), new LOD(0.07f, lods[1].ToArray()), new LOD(0.004f, lods[2].ToArray()) });
            group.RecalculateBounds();
            hf.seed = 1;                                   // its face, not applied: that would make pieces in the prefab
            hf.face = HumanFaceGenerator.Random(hf.Config, 1);
            if (hf.animator != null) hf.animator.runtimeAnimatorController = hf.face.sex >= 0 ? male : female;
            var prefab = PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
            Object.DestroyImmediate(root);
            return prefab;
        }

        /// <summary>one HumanPiece asset per piece in Resources/HumanPieces (updated in place, so references and
        /// .meta files stay); pieces the models no longer have are deleted</summary>
        static void WritePieces(SortedDictionary<string, List<HumanPiece.Lod>> cut)
        {
            EnsureFolder(PieceDir);
            var keep = new HashSet<string>();
            AssetDatabase.StartAssetEditing();
            try
            {
                foreach (var kv in cut)
                {
                    string path = $"{PieceDir}/{kv.Key}.asset";
                    keep.Add(path);
                    var asset = AssetDatabase.LoadAssetAtPath<HumanPiece>(path);
                    bool fresh = asset == null;
                    if (fresh) asset = ScriptableObject.CreateInstance<HumanPiece>();
                    asset.lods = kv.Value.ToArray();
                    if (fresh) AssetDatabase.CreateAsset(asset, path);
                    else EditorUtility.SetDirty(asset);
                }
                foreach (var guid in AssetDatabase.FindAssets("t:HumanPiece", new[] { PieceDir }))
                {
                    var path = AssetDatabase.GUIDToAssetPath(guid);
                    if (!keep.Contains(path)) AssetDatabase.DeleteAsset(path);
                }
            }
            finally { AssetDatabase.StopAssetEditing(); }
            AssetDatabase.SaveAssets();
            HumanFace.ClearPieceCache();
            Debug.Log($"[HumanSetup] {cut.Count} pieces ({cut.Values.Sum(l => l.Count(x => x.mesh != null))} renderers) in {PieceDir}");
        }

        /// <summary>Socket_R / Socket_L under the hand bone, from the rest skeleton (the same geometry
        /// hum_anim.Rig uses, so a tool here sits in the fists the clips close): origin in the hole the curled
        /// fingers make (1.6 cm back from the middle knuckle, 1.6 cm into the palm - hum_anim.Rig.fist, fitted to
        /// the finger wrap at GRIP_CURL), +Y the grip axis (little-finger knuckle -> index knuckle: a held handle,
        /// toward the tool's head), +Z the knuckles' way (wrist -> middle knuckle, square to the handle).</summary>
        static Transform AddHandSocket(Dictionary<string, Transform> boneMap, string s)
        {
            string o = s == "r" ? "l" : "r";
            if (!boneMap.TryGetValue($"hand_{s}", out var hand) || !boneMap.TryGetValue($"hand_{o}", out var other)
                || !boneMap.TryGetValue($"index_01_{s}", out var index) || !boneMap.TryGetValue($"pinky_01_{s}", out var pinky)
                || !boneMap.TryGetValue($"middle_01_{s}", out var middle) || !boneMap.TryGetValue($"middle_02_{s}", out var middle2))
            {
                Debug.LogWarning($"[HumanSetup] hand_{s} bones missing: no socket");
                return null;
            }
            Vector3 h = hand.position;
            var n = Vector3.Cross(index.position - h, pinky.position - h).normalized;
            var outward = (h - other.position).normalized;                // the back of the hand faces out at rest
            var dorsal = Vector3.Dot(n, outward) > 0 ? n : -n;
            var up = (index.position - pinky.position).normalized;
            var fwd = middle.position - h;
            fwd = (fwd - up * Vector3.Dot(up, fwd)).normalized;
            var socket = new GameObject(s == "r" ? "Socket_R" : "Socket_L").transform;
            var finger = (middle2.position - middle.position).normalized;
            socket.SetPositionAndRotation(middle.position - finger * 0.016f - dorsal * 0.016f, Quaternion.LookRotation(fwd, up));
            socket.SetParent(hand, true);
            return socket;
        }

        /// <summary>Socket_Shield for a strapped shield (hum_anim._shield_arm): 55% of the way from the elbow to the
        /// wrist and 6 cm out over the back of the forearm, +Y the back of the forearm (the shield's face), +Z along
        /// the forearm toward the hand. Parented to the left hand, not the forearm: the clips keep that wrist
        /// straight, and Humanoid gives the forearm bone only part of the forearm's twist (Lower Arm Twist), so a
        /// shield on it would turn half as far as the clip turns it.</summary>
        static Transform AddShieldSocket(Dictionary<string, Transform> boneMap)
        {
            if (!boneMap.TryGetValue("lowerarm_l", out var fore) || !boneMap.TryGetValue("hand_l", out var hand)
                || !boneMap.TryGetValue("hand_r", out var other) || !boneMap.TryGetValue("index_01_l", out var index)
                || !boneMap.TryGetValue("pinky_01_l", out var pinky))
            {
                Debug.LogWarning("[HumanSetup] left arm bones missing: no shield socket");
                return null;
            }
            Vector3 h = hand.position;
            var n = Vector3.Cross(index.position - h, pinky.position - h).normalized;
            var dorsal = Vector3.Dot(n, (h - other.position).normalized) > 0 ? n : -n;   // (as AddHandSocket)
            var axis = (h - fore.position).normalized;
            dorsal = (dorsal - axis * Vector3.Dot(axis, dorsal)).normalized;
            var socket = new GameObject("Socket_Shield").transform;
            socket.SetPositionAndRotation(Vector3.Lerp(fore.position, h, 0.55f) + dorsal * 0.06f, Quaternion.LookRotation(axis, dorsal));
            socket.SetParent(hand, true);
            return socket;
        }

        static Material HelperMat(string name, Color color, float smooth, float metal = 0f)
        {
            var path = $"{Materials}/{name}.mat";
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat != null) return mat;
            mat = new Material(Shader.Find("Universal Render Pipeline/Lit")) { name = name };
            mat.SetColor("_BaseColor", color);
            mat.SetFloat("_Smoothness", smooth);
            mat.SetFloat("_Metallic", metal);
            AssetDatabase.CreateAsset(mat, path);
            return mat;
        }

        static Transform NewProp(Transform socket, string name)
        {
            var t = new GameObject(name).transform;
            t.SetParent(socket, false);
            return t;
        }

        static void PropPart(Transform prop, PrimitiveType type, string name, Vector3 pos, Vector3 scale, Material mat)
        {
            var g = GameObject.CreatePrimitive(type);
            g.name = name;
            Object.DestroyImmediate(g.GetComponent<Collider>());
            g.GetComponent<MeshRenderer>().sharedMaterial = mat;
            g.transform.SetParent(prop, false);
            g.transform.localPosition = pos;
            g.transform.localScale = scale;
        }

        /// <summary>A round rod along the socket's +Y from y0 to y1.</summary>
        static void Rod(Transform prop, string name, float y0, float y1, float r, Material mat) =>
            PropPart(prop, PrimitiveType.Cylinder, name, new Vector3(0, (y0 + y1) / 2, 0), new Vector3(2 * r, (y1 - y0) / 2, 2 * r), mat);

        // The combat stand-ins match weapons_helper.py's in Blender (the clips were checked against those): the
        // handle along the socket's +Y, a blade's edge the knuckles' way (+Z).

        /// <summary>One-handed sword: a 75 cm blade from 6 cm above the fist, cross guard, grip, pommel.</summary>
        static GameObject BuildHelperSword(Transform socket)
        {
            if (socket == null) return null;
            var metal = HelperMat("M_HelperMetal", new Color(0.62f, 0.62f, 0.66f), 0.6f, 0.8f);
            var wood = HelperMat("M_HelperProp", new Color(0.45f, 0.30f, 0.17f), 0.25f);
            var p = NewProp(socket, "HelperSword");
            PropPart(p, PrimitiveType.Cube, "Blade", new Vector3(0, 0.435f, 0), new Vector3(0.008f, 0.75f, 0.045f), metal);
            PropPart(p, PrimitiveType.Cube, "Guard", new Vector3(0, 0.055f, 0), new Vector3(0.025f, 0.02f, 0.17f), metal);
            Rod(p, "Grip", -0.07f, 0.05f, 0.015f, wood);
            PropPart(p, PrimitiveType.Cube, "Pommel", new Vector3(0, -0.08f, 0), new Vector3(0.03f, 0.03f, 0.03f), metal);
            p.gameObject.SetActive(false);
            return p.gameObject;
        }

        /// <summary>Two-handed sword in the right (upper) fist: a 1 m blade, the grip running down past the left
        /// fist 17 cm below (hum_anim.GREAT_HANDS).</summary>
        static GameObject BuildHelperGreatsword(Transform socket)
        {
            if (socket == null) return null;
            var metal = HelperMat("M_HelperMetal", new Color(0.62f, 0.62f, 0.66f), 0.6f, 0.8f);
            var wood = HelperMat("M_HelperProp", new Color(0.45f, 0.30f, 0.17f), 0.25f);
            var p = NewProp(socket, "HelperGreatsword");
            PropPart(p, PrimitiveType.Cube, "Blade", new Vector3(0, 0.57f, 0), new Vector3(0.01f, 1.0f, 0.055f), metal);
            PropPart(p, PrimitiveType.Cube, "Guard", new Vector3(0, 0.06f, 0), new Vector3(0.03f, 0.025f, 0.26f), metal);
            Rod(p, "Grip", -0.23f, 0.06f, 0.016f, wood);
            PropPart(p, PrimitiveType.Cube, "Pommel", new Vector3(0, -0.24f, 0), new Vector3(0.035f, 0.035f, 0.035f), metal);
            p.gameObject.SetActive(false);
            return p.gameObject;
        }

        /// <summary>Spear in the right (rear) fist: 2 m, the butt 40 cm behind it, the left fist 32 cm up the shaft
        /// (hum_anim.SPEAR_HANDS), a leaf head.</summary>
        static GameObject BuildHelperSpear(Transform socket)
        {
            if (socket == null) return null;
            var metal = HelperMat("M_HelperMetal", new Color(0.62f, 0.62f, 0.66f), 0.6f, 0.8f);
            var wood = HelperMat("M_HelperProp", new Color(0.45f, 0.30f, 0.17f), 0.25f);
            var p = NewProp(socket, "HelperSpear");
            Rod(p, "Shaft", -0.40f, 1.55f, 0.016f, wood);
            PropPart(p, PrimitiveType.Cube, "Head", new Vector3(0, 1.66f, 0), new Vector3(0.008f, 0.22f, 0.05f), metal);
            p.gameObject.SetActive(false);
            return p.gameObject;
        }

        /// <summary>Round shield, 58 cm, on Socket_Shield: the disc's face along the socket's +Y, a boss.</summary>
        static GameObject BuildHelperShield(Transform socket)
        {
            if (socket == null) return null;
            var metal = HelperMat("M_HelperMetal", new Color(0.62f, 0.62f, 0.66f), 0.6f, 0.8f);
            var boards = HelperMat("M_HelperShield", new Color(0.40f, 0.24f, 0.12f), 0.2f);
            var p = NewProp(socket, "HelperShield");
            PropPart(p, PrimitiveType.Cylinder, "Board", Vector3.zero, new Vector3(0.58f, 0.0075f, 0.58f), boards);
            PropPart(p, PrimitiveType.Sphere, "Boss", new Vector3(0, 0.008f, 0), new Vector3(0.12f, 0.06f, 0.12f), metal);
            p.gameObject.SetActive(false);
            return p.gameObject;
        }

        /// <summary>The blade's roll round the handle from the knuckles (hum_anim.AXE_ROLL, which is -42 in
        /// Blender's right-handed axes: the import mirrors one axis, so the angle's sign flips here).</summary>
        const float AxeRoll = 42f;

        /// <summary>A placeholder axe (primitives) in the right-hand socket, hidden until Chop plays.</summary>
        static GameObject BuildHelperAxe(Transform socket)
        {
            if (socket == null) return null;
            var mat = AssetDatabase.LoadAssetAtPath<Material>($"{Materials}/M_HelperProp.mat");
            if (mat == null)
            {
                mat = new Material(Shader.Find("Universal Render Pipeline/Lit")) { name = "M_HelperProp" };
                mat.SetColor("_BaseColor", new Color(0.45f, 0.30f, 0.17f));
                mat.SetFloat("_Smoothness", 0.25f);
                AssetDatabase.CreateAsset(mat, $"{Materials}/M_HelperProp.mat");
            }
            var axe = new GameObject("HelperAxe").transform;
            axe.SetParent(socket, false);
            axe.localRotation = Quaternion.AngleAxis(AxeRoll, Vector3.up);
            void Part(PrimitiveType type, string name, Vector3 pos, Vector3 scale)
            {
                var g = GameObject.CreatePrimitive(type);
                g.name = name;
                Object.DestroyImmediate(g.GetComponent<Collider>());
                g.GetComponent<MeshRenderer>().sharedMaterial = mat;
                g.transform.SetParent(axe, false);
                g.transform.localPosition = pos;
                g.transform.localScale = scale;
            }
            // handle 0.76 m: from past the left fist (16 cm below) up to the head
            Part(PrimitiveType.Cylinder, "Handle", new Vector3(0, 0.14f, 0), new Vector3(0.032f, 0.38f, 0.032f));
            // head: a slab, the edge toward +Z (the way it strikes)
            Part(PrimitiveType.Cube, "Head", new Vector3(0, 0.47f, 0.045f), new Vector3(0.022f, 0.10f, 0.17f));
            axe.gameObject.SetActive(false);
            return axe.gameObject;
        }

        /// <summary>hum_anim.HAMMER_ROLL (-12 in Blender's axes; the import mirrors an axis, so the sign flips).</summary>
        const float HammerRoll = 12f;

        /// <summary>A placeholder hammer in the right-hand socket, hidden until Hammer plays: the head 28 cm up
        /// the handle (hum_anim.HAMMER_HEAD), its face toward +Z.</summary>
        static GameObject BuildHelperHammer(Transform socket)
        {
            if (socket == null) return null;
            var mat = AssetDatabase.LoadAssetAtPath<Material>($"{Materials}/M_HelperProp.mat");
            var ham = new GameObject("HelperHammer").transform;
            ham.SetParent(socket, false);
            ham.localRotation = Quaternion.AngleAxis(HammerRoll, Vector3.up);
            void Part(PrimitiveType type, string name, Vector3 pos, Vector3 scale, Quaternion rot)
            {
                var g = GameObject.CreatePrimitive(type);
                g.name = name;
                Object.DestroyImmediate(g.GetComponent<Collider>());
                g.GetComponent<MeshRenderer>().sharedMaterial = mat;
                g.transform.SetParent(ham, false);
                g.transform.localPosition = pos;
                g.transform.localRotation = rot;
                g.transform.localScale = scale;
            }
            // handle: from 6 cm below the fist up into the head
            Part(PrimitiveType.Cylinder, "Handle", new Vector3(0, 0.12f, 0), new Vector3(0.028f, 0.18f, 0.028f), Quaternion.identity);
            // head: a short cylinder across the handle, the face toward +Z (the way it strikes)
            Part(PrimitiveType.Cylinder, "Head", new Vector3(0, 0.28f, 0.01f), new Vector3(0.045f, 0.06f, 0.045f), Quaternion.Euler(90f, 0f, 0f));
            ham.gameObject.SetActive(false);
            return ham.gameObject;
        }

        // ------------------------------------------------------------------ scene

        static void BuildScene(GameObject prefab)
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.95f, 0.88f);
            sun.intensity = 1.6f;
            sun.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(28, 160, 0);
            var fill = new GameObject("Fill").AddComponent<Light>();
            fill.type = LightType.Directional;
            fill.color = new Color(0.75f, 0.82f, 1f);
            fill.intensity = 0.6f;
            fill.shadows = LightShadows.None;
            fill.transform.rotation = Quaternion.Euler(15, -40, 0);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.55f, 0.6f, 0.7f);
            RenderSettings.ambientEquatorColor = new Color(0.45f, 0.43f, 0.4f);
            RenderSettings.ambientGroundColor = new Color(0.25f, 0.22f, 0.2f);

            var mat = new Material(GraphicsSettings.currentRenderPipeline.defaultMaterial) { color = new Color(0.36f, 0.37f, 0.4f) };
            AssetDatabase.CreateAsset(mat, $"{Materials}/M_Backdrop.mat");
            var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ground.name = "Ground";
            ground.transform.localScale = new Vector3(3, 1, 3);
            ground.GetComponent<Renderer>().sharedMaterial = mat;

            var creator = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            creator.name = "Creator";
            creator.GetComponent<HumanFace>().Randomize(4);

            var lineup = new GameObject("Lineup").transform;
            lineup.position = new Vector3(0, 0, -3f);
            for (int i = 0; i < 10; i++)
            {
                var h = (GameObject)PrefabUtility.InstantiatePrefab(prefab, lineup);
                h.name = $"Human_{i:00}";
                h.transform.localPosition = new Vector3((i - 4.5f) * 0.85f, 0, 0);
                h.GetComponent<HumanFace>().Randomize(100 + i);
            }

            var camGo = new GameObject("Camera");
            camGo.tag = "MainCamera";
            var cam = camGo.AddComponent<Camera>();
            cam.fieldOfView = 25;
            cam.nearClipPlane = 0.05f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.3f, 0.32f, 0.36f);
            var ui = camGo.AddComponent<HumanCreatorUI>();
            ui.target = creator.GetComponent<HumanFace>();
            ui.lineup = lineup;
            ui.cam = cam;
            ui.libraries = AllLibraries();
            var hc = creator.GetComponent<HumanFace>().head.bounds.center;
            cam.transform.position = hc + new Vector3(0.2f, 0, 0.75f);
            cam.transform.LookAt(hc);
            EditorSceneManager.SaveScene(scene, ScenePath);
        }

        static HumanClipLibrary[] AllLibraries() =>
            AssetDatabase.FindAssets("t:HumanClipLibrary")
                .Select(g => AssetDatabase.LoadAssetAtPath<HumanClipLibrary>(AssetDatabase.GUIDToAssetPath(g)))
                .Where(l => l != null).OrderBy(l => l.title).ToArray();

        /// <summary>A HumanClipLibrary from the folder selected in the Project window: every Humanoid clip under
        /// it, split by sex where the path or name says so ("/Male/" "/Female/", "...M@" "...F@" prefixes - how
        /// animation packs such as Kevin Iglesias' lay them out), one state per clip named "[folder] clip"
        /// (the "Human?@" prefix dropped so both sexes share names). The open showcase's clip browser gets it.</summary>
        [MenuItem("Tools/Humans/Build Clip Library From Folder")]
        static void BuildLibraryFromSelection()
        {
            var path = Selection.activeObject != null ? AssetDatabase.GetAssetPath(Selection.activeObject) : null;
            if (string.IsNullOrEmpty(path) || !AssetDatabase.IsValidFolder(path))
            {
                Debug.LogWarning("[HumanSetup] select a folder of Humanoid clips in the Project window first");
                return;
            }
            BuildLibrary(path, Path.GetFileName(path));
        }

        public static HumanClipLibrary BuildLibrary(string folder, string title)
        {
            const string dir = Anim + "/Libraries";
            if (!AssetDatabase.IsValidFolder(dir)) AssetDatabase.CreateFolder(Anim, "Libraries");
            var bySex = new Dictionary<string, List<(string state, AnimationClip clip)>> { ["M"] = new(), ["F"] = new() };
            var names = new List<string>();
            foreach (var guid in AssetDatabase.FindAssets("t:AnimationClip", new[] { folder }))
            {
                var file = AssetDatabase.GUIDToAssetPath(guid);
                foreach (var clip in AssetDatabase.LoadAllAssetsAtPath(file).OfType<AnimationClip>())
                {
                    if (clip.name.StartsWith("__preview__") || !clip.humanMotion) continue;
                    string rel = file.Replace('\\', '/');
                    int at = clip.name.IndexOf('@');
                    string pre = at > 0 ? clip.name.Substring(0, at) : "";
                    bool female = rel.Contains("/Female/") || pre.EndsWith("F");
                    bool male = rel.Contains("/Male/") || pre.EndsWith("M");
                    string cat = Path.GetFileName(Path.GetDirectoryName(file));
                    string state = $"[{cat}] {(at > 0 ? clip.name.Substring(at + 1) : clip.name)}".Replace('.', '_');
                    foreach (var sx in female && !male ? new[] { "F" } : male && !female ? new[] { "M" } : new[] { "M", "F" })
                    {
                        var list = bySex[sx];
                        string unique = state;
                        for (int k = 2; list.Any(e => e.state == unique); k++) unique = $"{state} ({k})";
                        list.Add((unique, clip));
                        if (!names.Contains(unique)) names.Add(unique);
                    }
                }
            }
            AnimatorController Controller(string sx)
            {
                if (bySex[sx].Count == 0) return null;
                var cpath = $"{dir}/{title}_{sx}.controller";
                AssetDatabase.DeleteAsset(cpath);
                var ac = AnimatorController.CreateAnimatorControllerAtPath(cpath);
                var sm = ac.layers[0].stateMachine;
                int k = 0;
                foreach (var (state, clip) in bySex[sx].OrderBy(e => e.state))
                {
                    var st = sm.AddState(state, new Vector3(300 + 250 * (k / 40), 50 * (k % 40), 0));
                    st.motion = clip;
                    k++;
                }
                return ac;
            }
            var lpath = $"{dir}/{title}.asset";
            var lib = AssetDatabase.LoadAssetAtPath<HumanClipLibrary>(lpath);
            if (lib == null) { lib = ScriptableObject.CreateInstance<HumanClipLibrary>(); AssetDatabase.CreateAsset(lib, lpath); }
            lib.title = title;
            lib.male = Controller("M");
            lib.female = Controller("F");
            names.Sort(System.StringComparer.Ordinal);
            lib.states = names.ToArray();
            EditorUtility.SetDirty(lib);
            AssetDatabase.SaveAssets();
            var ui = Object.FindFirstObjectByType<HumanCreatorUI>();
            if (ui != null && !Application.isPlaying)
            {
                ui.libraries = AllLibraries();
                EditorUtility.SetDirty(ui);
                EditorSceneManager.MarkSceneDirty(ui.gameObject.scene);
                EditorSceneManager.SaveScene(ui.gameObject.scene);
            }
            Debug.Log($"[HumanSetup] clip library '{title}': {bySex["M"].Count} male, {bySex["F"].Count} female clips -> {lpath}");
            return lib;
        }

        [MenuItem("Tools/Humans/Render Checks")]
        public static void RenderChecks()
        {
            Directory.CreateDirectory(OutDir);
            var creator = GameObject.Find("Creator")?.GetComponent<HumanFace>();
            var lineup = GameObject.Find("Lineup");
            var cam = Camera.main;
            if (creator == null || cam == null) { Debug.LogWarning("[HumanSetup] open Humans_Showcase first"); return; }
            var c = creator.head.bounds.center + Vector3.up * 0.01f;
            foreach (var (name, yaw) in new[] { ("creator_front", 0f), ("creator_34", 30f) })
            {
                cam.transform.position = c + Quaternion.Euler(4, yaw, 0) * new Vector3(0, 0, 0.75f);
                cam.transform.LookAt(c);
                Render(cam, OutDir, name + ".png", 800, 800);
            }
            var bc = creator.transform.position + Vector3.up * 0.9f;
            cam.transform.position = bc + Quaternion.Euler(6, 25, 0) * new Vector3(0, 0, 4.2f);
            cam.transform.LookAt(bc);
            Render(cam, OutDir, "creator_body.png", 700, 900);
            if (lineup != null)
            {
                var lc = lineup.transform.position + Vector3.up * 0.9f;
                cam.transform.position = lc + new Vector3(0, 0.6f, 11f);
                cam.transform.LookAt(lc);
                Render(cam, OutDir, "lineup.png", 1800, 600);
            }
        }

        public static void Render(Camera cam, string dir, string file, int w, int h)
        {
            var rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            foreach (var smr in Object.FindObjectsByType<SkinnedMeshRenderer>(FindObjectsSortMode.None))
                smr.forceMatrixRecalculationPerRender = true;
            var req = new RenderPipeline.StandardRequest { destination = rt };
            if (RenderPipeline.SupportsRenderRequest(cam, req)) RenderPipeline.SubmitRenderRequest(cam, req);
            else { cam.targetTexture = rt; cam.Render(); cam.targetTexture = null; }
            var prev = RenderTexture.active;
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = prev;
            File.WriteAllBytes(Path.Combine(dir, file), tex.EncodeToPNG());
            Object.DestroyImmediate(tex);
            rt.Release();
        }
    }
}
