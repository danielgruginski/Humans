using System;
using System.Collections.Generic;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Mirror of export/human_face_config.json, written by the Blender pipeline (hum_export.py).
    /// Blender is the single source of truth for the slider list, palettes and style weights.
    /// </summary>
    [Serializable]
    public class HumanFaceConfig
    {
        [Serializable] public class Slider { public string name; public bool hasNeg; public float spread = 1, femBias, mascBias; }
        [Serializable] public class Corrective { public string name, a, b; }
        [Serializable] public class NamedColor { public string name, hex; }
        [Serializable] public class SexWeighted { public string name; public float masc, fem; }
        [Serializable] public class Weighted { public string name; public float w; }
        /// <summary>A garment: slot (one garment per slot), layer, fabric ("cloth"/"leather"), body regions it
        /// hides, and the regions it covers on inner garments (only where it is a tight shell, not skirts).</summary>
        [Serializable] public class Garment { public string name, slot, material; public int layer; public int[] hide, cover; public string[] excludes; public float capCut; public bool hidesHair, hoodCut, hidesFaceHair, hidesHead; public string group;
            public string[] companions; public bool companion;       // companion: worn only with another garment
            public bool hangs;                                            // has a skirt on the ring (HumanSkirt)
            public SkirtSlack[] skirtSlack; }
        /// <summary>How far a garment's skirt stands outside each ring column, per build (hum_helpers.ring_slack).</summary>
        [Serializable] public class SkirtSlack { public string build; public float[] hip, knee; }

        /// <summary>Per ring column, the tightest worn skirt's slack (the cloth a leg reaches first): hip link, knee
        /// link. 1 (no cloth) where nothing worn hangs.</summary>
        public void SkirtSlackOf(IEnumerable<string> worn, string build, float[] hip, float[] knee)
        {
            for (int i = 0; i < hip.Length; i++) hip[i] = 1f;
            for (int i = 0; i < knee.Length; i++) knee[i] = 1f;
            foreach (var n in worn)
            {
                var g = FindGarment(n);
                if (g?.skirtSlack == null) continue;
                foreach (var sl in g.skirtSlack)
                {
                    if (sl.build != build) continue;
                    for (int i = 0; i < hip.Length && i < sl.hip.Length; i++) hip[i] = Mathf.Min(hip[i], sl.hip[i]);
                    for (int i = 0; i < knee.Length && i < sl.knee.Length; i++) knee[i] = Mathf.Min(knee[i], sl.knee[i]);
                }
            }
        }

        /// <summary>A worn garment has a skirt (HumanSkirt runs).</summary>
        public bool Skirted(IEnumerable<string> worn)
        {
            foreach (var n in worn) if (FindGarment(n)?.hangs == true) return true;
            return false;
        }
        /// <summary>A body build: the body's key weights (fixed); garments exist once per build (Cloth_G_Tag).</summary>
        [Serializable] public class KeyWeight { public string key; public float w; }
        [Serializable] public class Build { public string tag, sex, name; public float odds; public KeyWeight[] keys; }
        public Build[] builds;
        public string[] bodyKeys;

        public Build FindBuild(string tag)
        {
            if (builds != null) foreach (var b in builds) if (b.tag == tag) return b;
            return null;
        }

        HashSet<string> bodyKeySet;
        public bool IsBodyKey(string key)
        {
            bodyKeySet ??= new HashSet<string>(bodyKeys ?? new string[0]);
            return bodyKeySet.Contains(key);
        }

        /// <summary>A complete armour set: worn as a whole, it replaces the clothes.</summary>
        [Serializable] public class ArmorSet { public string name; public string[] pieces; }
        [Serializable] public class ShaderConsts { public float shadeMax; public float[] blushTint, freckleTint, lipFromTone; public float edgeDark; }

        public Slider[] sliders;
        public string[] macros;
        public Corrective[] correctives;
        public string[] skinTones;
        public NamedColor[] hairColors, irisColors, dyes;
        public string[] cloths;
        public string[] bodySliders, muscleSliders;
        public SexWeighted[] hairStyles, browStyles;
        public Weighted[] beardStyles;
        public ShaderConsts shader;
        public Garment[] garments;
        public string[] linen, wool, leather, armorLeather, cloaks, padding, steel, blackened, suit;   // palettes (sRGB hex)

        /// <summary>Colour group of an armour-set piece (one colour per group): Leather, Plates (leather
        /// plates), Padding, Steel (mail and plate armour), Boots or Cloth.</summary>
        public string ArmorGroup(string garment)
        {
            if (garment == "Boots") return "Boots";
            var gg = FindGarment(garment);
            if (!string.IsNullOrEmpty(gg?.group)) return gg.group;     // a style's own group (Blackened, Suit)
            if (IsPlate(garment)) return "Plates";
            switch (FindGarment(garment)?.material)
            {
                case "leather": return "Leather";
                case "quilt": return "Padding";
                case "mail":
                case "plate": return "Steel";
                default: return "Cloth";
            }
        }

        public string[] GroupPalette(string group)
        {
            switch (group)
            {
                case "Boots": return leather;
                case "Padding": return padding ?? linen;
                case "Steel": return steel ?? wool;
                case "Blackened": return blackened ?? steel ?? wool;
                case "Suit": return suit ?? wool;
                case "Cloth": return wool;
                default: return armorLeather;
            }
        }
        public ArmorSet[] armorSets;

        public ArmorSet FindArmorSet(string name)
        {
            if (armorSets != null) foreach (var s in armorSets) if (s.name == name) return s;
            return null;
        }

        /// <summary>The armour set this outfit is ("" = none). Headgear may be swapped (a cloak's hood).</summary>
        public string WornArmorSet(HumanFaceData f)
        {
            if (armorSets == null) return "";
            foreach (var s in armorSets)
                if (Array.TrueForAll(s.pieces, p => f.Wears(p) || FindGarment(p)?.slot == "head")) return s.name;
            return "";
        }

        /// <summary>True for garments that only exist as parts of armour sets.</summary>
        public bool IsArmorPiece(string garment)
        {
            if (armorSets == null || garment == "Boots") return false;
            foreach (var s in armorSets) if (Array.IndexOf(s.pieces, garment) >= 0) return true;
            return false;
        }

        /// <summary>Plates worn over the coat (second armour colour).</summary>
        public static bool IsPlate(string garment) =>
            garment is "Jerkin" or "Cuirass" or "Pauldrons" or "Bracers" or "Greaves";

        /// <summary>True if a and b can't be worn together (either one lists the other in "excludes").</summary>
        public bool Excludes(string a, string b)
        {
            var ga = FindGarment(a); var gb = FindGarment(b);
            return (ga?.excludes != null && Array.IndexOf(ga.excludes, b) >= 0) ||
                   (gb?.excludes != null && Array.IndexOf(gb.excludes, a) >= 0);
        }

        static HumanFaceConfig cached;
        static TextAsset cachedSource;

        /// <summary>Forget the parsed config: a reimported JSON keeps the same TextAsset object, so the editor
        /// setup calls this before rebuilding (new garments were missing from the first rebuild otherwise).</summary>
        public static void ClearCache() { cached = null; cachedSource = null; }

        public static HumanFaceConfig Load(TextAsset json)
        {
            if (json == null) throw new ArgumentNullException(nameof(json), "HumanFaceConfig: no config TextAsset");
            if (cached != null && cachedSource == json) return cached;
            cached = JsonUtility.FromJson<HumanFaceConfig>(json.text);
            cachedSource = json;
            return cached;
        }

        public static Color Hex(string hex) => ColorUtility.TryParseHtmlString(hex, out var c) ? c : Color.magenta;

        public Color HairColor(string name) => Find(hairColors, name);
        public Color IrisColor(string name) => Find(irisColors, name);
        public Color DyeColor(string name) => Find(dyes, name);

        static Color Find(NamedColor[] list, string name)
        {
            foreach (var c in list) if (c.name == name) return Hex(c.hex);
            return Color.magenta;
        }

        public Garment FindGarment(string name)
        {
            if (garments != null) foreach (var g in garments) if (g.name == name) return g;
            return null;
        }

        /// <summary>Bit mask of the body regions hidden by these garments (Humans/Body _Hide).</summary>
        public int HideMask(IEnumerable<string> garmentNames)
        {
            int m = 0;
            foreach (var n in garmentNames)
            {
                var g = FindGarment(n);
                if (g?.hide != null) foreach (var r in g.hide) m |= 1 << r;
            }
            return m;
        }

        /// <summary>True if a worn garment covers the hair entirely (a hood).</summary>
        public bool HidesHair(IEnumerable<string> worn)
        {
            foreach (var n in worn) if (FindGarment(n)?.hidesHair == true) return true;
            return false;
        }

        /// <summary>A closed helm: no hair, beard or brows show.</summary>
        public bool HidesFaceHair(IEnumerable<string> worn)
        {
            foreach (var n in worn) if (FindGarment(n)?.hidesFaceHair == true) return true;
            return false;
        }

        /// <summary>A closed helm hides the whole head (the face can't be seen; its chin showed below).</summary>
        public bool HidesHead(IEnumerable<string> worn)
        {
            foreach (var n in worn) if (FindGarment(n)?.hidesHead == true) return true;
            return false;
        }

        /// <summary>The worn bodysuit's colour (the body shader paints the body as cloth), or null.</summary>
        public Color? SuitColor(List<HumanFaceData.GarmentColor> outfit)
        {
            foreach (var o in outfit) if (FindGarment(o.garment)?.material == "suit") return o.color;
            return null;
        }

        public bool HoodCut(IEnumerable<string> worn)
        {
            foreach (var n in worn) if (FindGarment(n)?.hoodCut == true) return true;
            return false;
        }

        /// <summary>Hair cut height of the worn headgear (0 = none).</summary>
        public float CapCut(IEnumerable<string> worn)
        {
            float c = 0;
            foreach (var n in worn) { var g = FindGarment(n); if (g != null) c = Mathf.Max(c, g.capCut); }
            return c;
        }

        /// <summary>Regions of `garment` covered by the worn garments on higher layers.</summary>
        public int LayerHideMask(string garment, IEnumerable<string> worn)
        {
            var g = FindGarment(garment);
            if (g == null) return 0;
            int m = 0;
            foreach (var n in worn)
            {
                var h = FindGarment(n);
                if (h?.cover != null && h.layer > g.layer) foreach (var r in h.cover) m |= 1 << r;
            }
            return m;
        }

        public IEnumerable<string> SliderNames { get { foreach (var s in sliders) yield return s.name; } }
    }
}
