using System;
using System.Collections.Generic;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// One character's face in "creator" terms (what a character creator edits and a save file stores).
    /// ToKeyWeights turns it into blend-shape weights (0..100) by key name; the same names exist on the head
    /// and on every hair/beard/brow piece that the key moves.
    /// Colours are sRGB (as picked); the shaders receive them linearised by SetColor.
    /// </summary>
    [Serializable]
    public class HumanFaceData
    {
        [Serializable]
        public class SliderValue
        {
            public string name;
            [Range(-1, 1)] public float value;
            public SliderValue(string name, float value) { this.name = name; this.value = value; }
        }

        [Serializable]
        public class GarmentColor
        {
            public string garment;
            public Color color;
            public GarmentColor(string garment, Color color) { this.garment = garment; this.color = color; }
        }

        public int seed;

        [Header("Body macros (they shape the face)")]
        [Range(-1, 1)] public float sex;        // -1 feminine .. +1 masculine
        [Range(0, 1)] public float age;         // 0 young adult .. 1 old
        [Range(-1, 1)] public float weight;     // -1 thin .. +1 heavy
        [Range(-1, 1)] public float muscle;     // -1 slight .. +1 muscular
        public Vector3 ancestry = new Vector3(1f / 3, 1f / 3, 1f / 3);   // african, asian, european (sum 1)
        [Range(-1, 1)] public float height;     // -1 short .. +1 tall (a uniform scale of the whole character)

        [Tooltip("Body build tag (config builds: MSlim, MStrong, MHeavy, FSlim, FStrong, FHeavy)")]
        public string build = "MSlim";

        [Header("Face sliders")]
        public List<SliderValue> sliders = new List<SliderValue>();

        [Header("Styles (empty = none)")]
        public string hairStyle = "Swept";
        public string beardStyle = "";
        public string browStyle = "Normal";

        [Header("Skin")]
        public Color tone = new Color(0.81f, 0.59f, 0.44f);
        public Color lip = new Color(0.74f, 0.47f, 0.40f);
        public Color lash = new Color(0.19f, 0.15f, 0.13f);
        [Range(0, 1)] public float blush = 0.6f;
        [Range(0, 1)] public float freckles;
        [Range(0, 1)] public float stubble;
        [Range(0, 1.2f)] public float ageLines;
        [Range(0, 1)] public float paintedBrows = 0.25f;
        [Range(0, 1)] public float hairlineTint = 1f;
        [Range(0, 1)] public float beardShadow;

        [Header("Body underclothes")]
        public Color cloth = new Color(0.85f, 0.81f, 0.72f);
        [Range(0, 1)] public float chestBand;

        [Header("Outfit (garment names from the config; one per slot)")]
        public List<GarmentColor> outfit = new List<GarmentColor>();

        [Header("Eyes")]
        public Color iris = new Color(0.36f, 0.52f, 0.66f);

        [Header("Hair (multi-colour)")]
        public Color hairRoot = new Color(0.23f, 0.15f, 0.09f);
        public Color hairTip = new Color(0.23f, 0.15f, 0.09f);
        public Color hairStreak = new Color(0.6f, 0.1f, 0.1f);
        [Range(0, 1)] public float streaks;
        [Range(0, 1)] public float ombre;
        public string hairLook = "natural";
        public Color beardColor = new Color(0.23f, 0.15f, 0.09f);
        public Color browColor = new Color(0.2f, 0.13f, 0.08f);

        public bool Wears(string garment)
        {
            foreach (var g in outfit) if (g.garment == garment) return true;
            return false;
        }

        /// <summary>The armour set worn ("" = none): the outfit is then exactly the set's pieces.</summary>
        public string armorSet = "";

        /// <summary>Put on a complete armour set (replacing all clothes); "" takes it off (plain clothes back).</summary>
        public void SetArmorSet(HumanFaceConfig cfg, string name, Func<string, Color> groupColour)
        {
            var set = cfg.FindArmorSet(name);
            outfit.Clear();
            armorSet = set != null ? name : "";
            if (set == null) return;
            foreach (var p in set.pieces) outfit.Add(new GarmentColor(p, groupColour(cfg.ArmorGroup(p))));
        }

        /// <summary>A set with the first colour of each group's palette (the plates take the second).</summary>
        public void SetArmorSet(HumanFaceConfig cfg, string name) =>
            SetArmorSet(cfg, name, g =>
            {
                var pal = cfg.GroupPalette(g);
                return HumanFaceConfig.Hex(pal[(g == "Plates" ? 2 : 0) % pal.Length]);
            });

        public IEnumerable<string> GarmentNames { get { foreach (var g in outfit) yield return g.garment; } }

        /// <summary>Put on a garment (replacing whatever was in its slot and anything it can't be worn with),
        /// or take it off (color null).</summary>
        public void SetGarment(HumanFaceConfig cfg, string garment, Color? color)
        {
            var def = cfg.FindGarment(garment);
            var slot = def?.slot;
            outfit.RemoveAll(g => g.garment == garment || (slot != null && cfg.FindGarment(g.garment)?.slot == slot) ||
                                  (color.HasValue && cfg.Excludes(garment, g.garment)));
            if (color.HasValue) outfit.Add(new GarmentColor(garment, color.Value));
            // companions come and go with their garment (the cloak's hood)
            if (def?.companions != null)
                foreach (var c in def.companions) SetGarment(cfg, c, color);
        }

        public float GetSlider(string name)
        {
            foreach (var s in sliders) if (s.name == name) return s.value;
            return 0f;
        }

        public void SetSlider(string name, float value)
        {
            foreach (var s in sliders) if (s.name == name) { s.value = value; return; }
            sliders.Add(new SliderValue(name, value));
        }

        /// <summary>Blend-shape weights (Unity scale 0..100; correctives may be negative).</summary>
        public Dictionary<string, float> ToKeyWeights(HumanFaceConfig cfg)
        {
            var w = new Dictionary<string, float>();
            void Put(string k, float v) { if (Mathf.Abs(v) > 1e-4f) w[k] = v; }
            // the build fixes the body keys (sex, weight, muscle, body sliders); the face is free
            var bd = cfg.FindBuild(build);
            float bsex = sex, bweight = weight, bmuscle = muscle;
            if (bd != null)
            {
                float m = 0, fm = 0;
                foreach (var k in bd.keys) { if (k.key == "Masculine") m = k.w; if (k.key == "Feminine") fm = k.w; }
                bsex = m - fm;
                bweight = 0; bmuscle = 0;
            }
            float sex_ = bsex, weight_ = bweight, muscle_ = bmuscle;

            float masc = Mathf.Max(sex_, 0), fem = Mathf.Max(-sex_, 0);
            Put("Masculine", masc);
            Put("Feminine", fem);
            float young = age < 0.12f ? (0.12f - age) / 0.12f * 0.8f : 0f;
            float old = age >= 0.12f ? (age - 0.12f) * 0.75f : 0f;
            Put("Young", young);
            Put("Old", old);
            Put("Heavy", Mathf.Max(weight_, 0));
            Put("Thin", Mathf.Max(-weight_, 0));
            Put("Muscular", Mathf.Max(muscle_, 0));
            Put("Slight", Mathf.Max(-muscle_, 0));
            var anc = Normalised(ancestry);
            Put("AncAfrican", anc.x);
            Put("AncAsian", anc.y);
            Put("AncEuropean", anc.z);
            // correctives for macro interactions (feminine counts as negative masculine for the ancestry ones)
            var val = new Dictionary<string, float>
            {
                ["Masculine"] = masc, ["Feminine"] = fem, ["Old"] = old,
                ["AncAfrican"] = anc.x, ["AncAsian"] = anc.y, ["AncEuropean"] = anc.z,
            };
            foreach (var c in cfg.correctives)
            {
                float a = c.a == "Masculine" && c.b.StartsWith("Anc") ? sex_ : (val.TryGetValue(c.a, out var va) ? va : 0);
                float b = val.TryGetValue(c.b, out var vb) ? vb : 0;
                Put(c.name, a * b);
            }
            foreach (var s in cfg.sliders)
            {
                float v = Mathf.Clamp(GetSlider(s.name), -1, 1);
                if (v > 0) Put(s.name + "_Pos", v);
                else if (v < 0 && s.hasNeg) Put(s.name + "_Neg", -v);
            }
            if (bd != null)
            {
                foreach (var k in new List<string>(w.Keys)) if (cfg.IsBodyKey(k)) w.Remove(k);
                foreach (var k in bd.keys) w[k.key] = k.w;
            }
            var keys = new List<string>(w.Keys);
            foreach (var k in keys) w[k] *= 100f;
            return w;
        }

        /// <summary>Only the body keys (the build): body meshes and the skeleton.</summary>
        public static Dictionary<string, float> BodyOnly(HumanFaceConfig cfg, Dictionary<string, float> all)
        {
            var w = new Dictionary<string, float>();
            foreach (var kv in all) if (cfg.IsBodyKey(kv.Key)) w[kv.Key] = kv.Value;
            return w;
        }

        public static Vector3 Normalised(Vector3 a)
        {
            a = Vector3.Max(a, Vector3.zero);
            float s = a.x + a.y + a.z;
            return s > 1e-5f ? a / s : new Vector3(1f / 3, 1f / 3, 1f / 3);
        }

        public HumanFaceData Clone() => JsonUtility.FromJson<HumanFaceData>(JsonUtility.ToJson(this));
    }
}
