using System;
using System.Collections.Generic;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Random characters, a port of hum_faces.random_face (Blender). Distributions, biases and palettes come
    /// from the exported config; the colour maths runs in linear space like the Blender version.
    /// </summary>
    public static class HumanFaceGenerator
    {
        static readonly string[] FaceShapes = { "FaceSquare", "FaceRound", "FaceOval", "FaceTriangle", "FaceInvTriangle", "FaceDiamond" };
        static readonly string[] Looks = { "natural", "sunkissed", "ombre", "streaks", "twotone" };
        static readonly float[] LookWeights = { 50, 20, 12, 12, 6 };

        public static HumanFaceData Random(HumanFaceConfig cfg, int seed)
        {
            var rng = new Rng(seed);
            var f = new HumanFaceData { seed = seed };

            bool masc = rng.Value() < 0.5;
            float sex = rng.Range(0.55f, 0.95f);
            f.sex = masc ? sex : -sex;
            float age = rng.Beta(1.6, 2.6);
            f.age = age;
            f.weight = Mathf.Clamp(rng.Gauss(0, 0.45f), -1, 1);
            f.muscle = Mathf.Clamp(rng.Gauss(0, 0.4f), -1, 1);
            var anc = new Vector3(rng.Gamma(0.6), rng.Gamma(0.6), rng.Gamma(0.6));
            anc /= anc.x + anc.y + anc.z;
            f.ancestry = anc;

            f.sliders.Clear();
            foreach (var s in cfg.sliders)
            {
                float bias = (masc ? s.mascBias : s.femBias) + (s.name == "MouthCorners" ? 0.25f : 0f);
                float v = rng.Gauss(bias * sex, 0.3f) * s.spread;
                if (s.name.StartsWith("Face") && !s.hasNeg && Array.IndexOf(FaceShapes, s.name) >= 0)
                    v = rng.Value() < 0.35 ? Mathf.Abs(rng.Gauss(0, 0.25f)) : 0f;
                if (s.name == "EarPointed" || s.name == "ChinCleft" || s.name == "Belly")
                    v = Mathf.Max(0, rng.Gauss(-0.2f, 0.4f));
                v = 0.7f * (float)Math.Tanh(v / 0.7f);          // random faces stay off the extremes
                if (!s.hasNeg) v = Mathf.Max(0, v);
                f.sliders.Add(new HumanFaceData.SliderValue(s.name, v));
            }

            // skin tone leans on ancestry but keeps its own spread
            int n = cfg.skinTones.Length;
            float t = Mathf.Clamp01(0.15f * anc.z + 0.45f * anc.y + 0.85f * anc.x + rng.Gauss(0, 0.12f)) * (n - 1);
            int i = Mathf.FloorToInt(t);
            var c0 = HumanFaceConfig.Hex(cfg.skinTones[i]).linear;
            var c1 = HumanFaceConfig.Hex(cfg.skinTones[Mathf.Min(i + 1, n - 1)]).linear;
            var toneLin = Color.Lerp(c0, c1, t - i);
            float dark = t / (n - 1);
            f.tone = toneLin.gamma;
            f.lip = Mul(toneLin, cfg.shader.lipFromTone).gamma;

            string hair;
            if (age > 0.6f && rng.Value() < 0.7) hair = rng.Pick("grey", "white", "ash");
            else if (dark > 0.45f) hair = rng.Pick("black", "black", "dark_brown");
            else hair = rng.Pick("black", "dark_brown", "brown", "brown", "auburn", "red", "blond", "ash");
            string iris = dark > 0.5f ? rng.Pick("dark_brown", "brown", "brown", "amber")
                                      : rng.Pick("brown", "dark_brown", "hazel", "green", "blue", "blue", "grey");
            f.iris = cfg.IrisColor(iris);
            f.blush = rng.Range(0.35f, 0.8f) * (1 - 0.5f * dark);
            f.freckles = dark < 0.3f && (hair == "red" || hair == "auburn" || rng.Value() < 0.2) ? rng.Range(0.4f, 1f) : 0f;
            f.stubble = masc && rng.Value() < 0.6 ? rng.Range(0.2f, 0.55f) : 0f;
            f.ageLines = Mathf.Max(0, (age - 0.4f) / 0.6f) * 1.1f;
            f.paintedBrows = 0.25f;

            // styles
            var hw = new List<(string, float)>();
            foreach (var h in cfg.hairStyles)
            {
                float w = masc ? h.masc : h.fem;
                if (h.name == "Curly") w *= 1 + 3 * anc.x;
                if (h.name == "" && masc && age > 0.5f) w = 0.35f;
                hw.Add((h.name, w));
            }
            f.hairStyle = rng.Weighted(hw);
            if (masc)
            {
                var bw = new List<(string, float)>();
                foreach (var b in cfg.beardStyles) bw.Add((b.name, b.w));
                f.beardStyle = rng.Weighted(bw);
                if (f.beardStyle != "" && age > 0.5f && rng.Value() < 0.4) f.beardStyle = age < 0.8f ? "Full" : "Wizard";
            }
            else f.beardStyle = "";
            var brw = new List<(string, float)>();
            foreach (var b in cfg.browStyles) brw.Add((b.name, masc ? b.masc : b.fem));
            f.browStyle = rng.Weighted(brw);

            // hair colours (linear maths, stored sRGB)
            var root = cfg.HairColor(hair).linear;
            string look = Looks[rng.WeightedIndex(LookWeights)];
            if ((hair == "grey" || hair == "white") && look != "natural") look = "natural";
            f.hairLook = look;
            var tip = root; var streak = root; float streaks = 0, ombre = 0;
            string dye = cfg.dyes[rng.Int(cfg.dyes.Length)].name;
            switch (look)
            {
                case "sunkissed": tip = Lighten(root, 0.35f); ombre = 0.8f; break;
                case "ombre": tip = cfg.DyeColor(dye).linear; ombre = 1f; break;
                case "streaks": streak = cfg.DyeColor(dye).linear; streaks = rng.Range(0.18f, 0.35f); break;
                case "twotone": streak = cfg.DyeColor(dye).linear; streaks = 0.5f; break;
            }
            f.hairRoot = root.gamma; f.hairTip = tip.gamma; f.hairStreak = streak.gamma;
            f.streaks = streaks; f.ombre = ombre;
            f.beardColor = (rng.Value() < 0.8 ? root : new Color(root.r * 1.35f + 0.004f, root.g * 1.35f + 0.004f, root.b * 1.35f + 0.004f)).gamma;
            f.browColor = (root * 0.8f).gamma;
            f.hairlineTint = f.hairStyle == "" || f.hairStyle == "Mohawk" ? 0f : 1f;
            f.beardShadow = f.beardStyle is "Full" or "Wizard" or "Short" or "ShortSideburns" or "ChinStrap" ? 0.5f : 0f;
            if (cfg.cloths != null && cfg.cloths.Length > 0) f.cloth = HumanFaceConfig.Hex(cfg.cloths[rng.Int(cfg.cloths.Length)]);
            f.height = Mathf.Clamp(rng.Gauss(0, 0.35f), -1, 1);
            f.chestBand = masc ? 0f : 1f;
            f.outfit = RandomOutfit(cfg, rng, masc);
            // body build (garments exist per build)
            if (cfg.builds != null && cfg.builds.Length > 0)
            {
                var opts = new List<(string, float)>();
                foreach (var b in cfg.builds) if (b.sex == (masc ? "M" : "F")) opts.Add((b.tag, b.odds));
                if (opts.Count > 0) f.build = rng.Weighted(opts);
            }
            f.armorSet = cfg.WornArmorSet(f);
            f.sex = masc ? Mathf.Abs(f.sex) : -Mathf.Abs(f.sex);
            return f;
        }

        /// <summary>Lay a preset (the config's, e.g. "Orc") over a face (port of hum_orcs.orc_face): its sliders, skin,
        /// eyes, hair, beard, brows and height, rolled from the seed; false when the config has no such preset.</summary>
        public static bool ApplyPreset(HumanFaceConfig cfg, HumanFaceData f, string preset, int seed)
        {
            var p = cfg?.FindPreset(preset);
            if (p == null) return false;
            var rng = new Rng(seed * 31 + 7);
            bool masc = f.sex >= 0f;
            f.sex = masc ? Mathf.Max(f.sex, p.sexMin) : Mathf.Min(f.sex, -p.sexMin);
            if (p.sliders != null)
                foreach (var s in p.sliders)
                {
                    float m = masc || s.name.StartsWith("Ear") ? s.mean : s.mean * p.femScale;
                    float v = Mathf.Clamp(s.jitter > 0f ? rng.Gauss(m, s.jitter) : m, -1f, 1f);
                    var cs = Array.Find(cfg.sliders, x => x.name == s.name);
                    if (cs != null && !cs.hasNeg) v = Mathf.Max(0f, v);
                    var have = f.sliders.Find(x => x.name == s.name);
                    if (have != null) have.value = v;
                    else f.sliders.Add(new HumanFaceData.SliderValue(s.name, v));
                }
            if (p.tones != null && p.tones.Length > 0)
            {
                var toneLin = HumanFaceConfig.Hex(p.tones[rng.Int(p.tones.Length)]).linear;
                f.tone = toneLin.gamma;
                f.lip = Mul(toneLin, cfg.shader.lipFromTone).gamma;
            }
            if (p.irises != null && p.irises.Length > 0) f.iris = HumanFaceConfig.Hex(p.irises[rng.Int(p.irises.Length)]);
            f.blush = rng.Range(p.blushMin, p.blushMax);
            f.freckles = 0f;
            f.stubble = 0f;
            if (p.hairColors != null && p.hairColors.Length > 0)
            {
                var c = cfg.HairColor(p.hairColors[rng.Int(p.hairColors.Length)]);
                if (c != Color.magenta)
                {
                    f.hairRoot = f.hairTip = f.hairStreak = c;
                    f.streaks = 0f; f.ombre = 0f; f.hairLook = "natural";
                    f.browColor = (c.linear * 0.8f).gamma;
                }
            }
            if (p.hairStyles != null && p.hairStyles.Length > 0) f.hairStyle = p.hairStyles[rng.Int(p.hairStyles.Length)] ?? "";
            if (p.brows != null && p.brows.Length > 0) f.browStyle = p.brows[rng.Int(p.brows.Length)];
            if (!string.IsNullOrEmpty(p.beard))
            {
                f.beardStyle = p.beard;
                f.beardColor = HumanFaceConfig.Hex(p.beardColor);
                f.beardShadow = 0f;
            }
            if (p.heightMax > p.heightMin || p.heightMax > 0f) f.height = rng.Range(p.heightMin, p.heightMax);
            f.hairlineTint = f.hairStyle == "" || f.hairStyle == "Mohawk" ? 0f : 1f;
            return true;
        }

        /// <summary>Port of hum_faces.random_outfit. Men: shirt + trousers (+ tunic, belt); women: dress
        /// (+ apron, belt) or sometimes shirt + trousers; boots or shoes. Colours sRGB.</summary>
        public static List<HumanFaceData.GarmentColor> RandomOutfit(HumanFaceConfig cfg, Rng rng, bool masc, bool allowArmor = true)
        {
            var o = new List<HumanFaceData.GarmentColor>();
            if (cfg.garments == null || cfg.linen == null) return o;
            Color Pick(string[] pal) => HumanFaceConfig.Hex(pal[rng.Int(pal.Length)]);
            void Add(string g, Color c) => o.Add(new HumanFaceData.GarmentColor(g, c));
            if (masc || rng.Value() < 0.15)
            {
                Add("Shirt", Pick(cfg.linen));
                Add("Trousers", Pick(cfg.wool));
                if (rng.Value() < 0.55) Add("Tunic", Pick(cfg.wool));
                if (rng.Value() < 0.6) Add("Belt", Pick(cfg.leather));
            }
            else
            {
                var dress = new string[cfg.wool.Length + 1];
                cfg.wool.CopyTo(dress, 0);
                dress[cfg.wool.Length] = cfg.linen[0];
                Add("Dress", Pick(dress));
                if (rng.Value() < 0.5) Add("Apron", Pick(cfg.linen));
                if (rng.Value() < 0.4) Add("Belt", Pick(cfg.leather));
            }
            Add(rng.Value() < 0.6 ? "Boots" : "Shoes", Pick(cfg.leather));
            // now and then full leather armour (replaces the clothes; covers everything but the face)
            // (not the sets kept off random people: the wizard's robes)
            var randomSets = cfg.armorSets == null ? null : Array.FindAll(cfg.armorSets, s => !s.noRandom);
            if (allowArmor && cfg.armorLeather != null && randomSets != null && randomSets.Length > 0 && rng.Value() < (masc ? 0.3 : 0.12))
            {
                var set = randomSets[rng.Int(randomSets.Length)];
                var colours = new Dictionary<string, Color>();
                o.Clear();
                foreach (var p in set.pieces)
                {
                    var g = cfg.ArmorGroup(p);
                    if (!colours.TryGetValue(g, out var c)) colours[g] = c = set.Colour(g) ?? Pick(cfg.GroupPalette(g));
                    Add(p, c);
                }
            }
            // now and then a hooded cloak over clothes or armour
            if (cfg.cloaks != null && cfg.FindGarment("Cloak") != null && rng.Value() < 0.2)
            {
                var c = Pick(cfg.cloaks);
                o.RemoveAll(g => g.garment == "Cap" || g.garment == "Hood");
                Add("Cloak", c);
                Add("CloakHood", c);
            }
            return o;
        }

        static Color Mul(Color c, float[] k) => new Color(c.r * k[0], c.g * k[1], c.b * k[2], 1);
        static Color Lighten(Color c, float k) => new Color(c.r + (1 - c.r) * k, c.g + (1 - c.g) * k, c.b + (1 - c.b) * k, 1);

        /// <summary>Small deterministic RNG with the distributions random_face uses.</summary>
        public class Rng
        {
            readonly System.Random r;
            public Rng(int seed) { r = new System.Random(seed); }
            public double Value() => r.NextDouble();
            public int Int(int max) => r.Next(max);
            public float Range(float a, float b) => a + (float)r.NextDouble() * (b - a);
            public string Pick(params string[] xs) => xs[r.Next(xs.Length)];

            public float Gauss(float mu, float sigma)
            {
                double u1 = 1.0 - r.NextDouble(), u2 = r.NextDouble();
                return mu + sigma * (float)(Math.Sqrt(-2 * Math.Log(u1)) * Math.Cos(2 * Math.PI * u2));
            }

            public float Gamma(double shape)
            {
                if (shape < 1) return Gamma(shape + 1) * (float)Math.Pow(r.NextDouble(), 1.0 / shape);
                double d = shape - 1.0 / 3, c = 1 / Math.Sqrt(9 * d);
                while (true)
                {
                    double x = Gauss(0, 1), v = 1 + c * x;
                    if (v <= 0) continue;
                    v = v * v * v;
                    double u = r.NextDouble();
                    if (u < 1 - 0.0331 * x * x * x * x || Math.Log(u) < 0.5 * x * x + d * (1 - v + Math.Log(v)))
                        return (float)(d * v);
                }
            }

            public float Beta(double a, double b) { float x = Gamma(a), y = Gamma(b); return x / (x + y); }

            public int WeightedIndex(float[] w)
            {
                float sum = 0; foreach (var x in w) sum += x;
                float p = (float)r.NextDouble() * sum;
                for (int i = 0; i < w.Length; i++) { p -= w[i]; if (p <= 0) return i; }
                return w.Length - 1;
            }

            public string Weighted(List<(string name, float w)> items)
            {
                var w = new float[items.Count];
                for (int i = 0; i < w.Length; i++) w[i] = items[i].w;
                return items[WeightedIndex(w)].name;
            }
        }
    }
}
