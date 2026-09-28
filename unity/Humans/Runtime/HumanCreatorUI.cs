using System.Collections.Generic;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Test panel for the showcase scene: a small character creator (IMGUI).
    /// Right-drag orbits the camera around the face, the scroll wheel zooms (the "zoom-in view" test).
    /// Mouse input comes from IMGUI events, so it works with either input handling setting.
    /// </summary>
    public class HumanCreatorUI : MonoBehaviour
    {
        public HumanFace target;
        public Transform lineup;
        public Camera cam;
        public float distance = 0.75f;
        public float yaw = 20f, pitch = 4f;

        enum View { Portrait, Body, Lineup }
        View view = View.Portrait;
        Vector2 scroll;
        bool showSliders = true, showBody = true;
        string hairName = "brown", dyeName = "crimson";
        float toneT = 0.4f;
        int lineupSeed = 100;
        static readonly string[] Looks = { "natural", "sunkissed", "ombre", "streaks", "twotone" };

        HumanFaceConfig Cfg => target.Config;

        void Start()
        {
            if (target != null && target.face != null && target.face.sliders.Count == 0) target.Randomize(target.seed);
            RerollLineup();
            PlaceCamera();
        }

        void LateUpdate() => PlaceCamera();

        Vector3 Pivot()
        {
            if (view == View.Body && target != null)
                return target.transform.position + Vector3.up * 0.9f * (target.modelRoot ? target.modelRoot.localScale.y : 1f);
            if (view == View.Lineup && lineup != null)
            {
                var b = new Bounds(lineup.position, Vector3.zero);
                foreach (var r in lineup.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
                return b.center;
            }
            return target != null && target.head != null ? target.head.bounds.center + Vector3.up * 0.01f : Vector3.up * 1.55f;
        }

        void PlaceCamera()
        {
            if (cam == null) return;
            var rot = Quaternion.Euler(pitch, 180f + yaw, 0);
            var d = view == View.Lineup ? Mathf.Max(distance * 4f, 9f) : view == View.Body ? Mathf.Max(distance, 3.6f) : distance;
            cam.transform.position = Pivot() - rot * Vector3.forward * d;
            cam.transform.rotation = rot;
        }

        void RerollLineup()
        {
            if (lineup == null) return;
            int i = 0;
            foreach (var hf in lineup.GetComponentsInChildren<HumanFace>()) hf.Randomize(lineupSeed + i++);
        }

        void OnGUI()
        {
            var e = Event.current;
            if (e.type == EventType.MouseDrag && e.button == 1) { yaw += e.delta.x * 0.4f; pitch = Mathf.Clamp(pitch + e.delta.y * 0.3f, -40, 60); }
            if (e.type == EventType.ScrollWheel && e.mousePosition.x > 340) distance = Mathf.Clamp(distance * (1 + e.delta.y * 0.05f), 0.25f, 6f);
            if (target == null) return;

            GUILayout.BeginArea(new Rect(10, 10, 330, Screen.height - 20), GUI.skin.box);
            scroll = GUILayout.BeginScrollView(scroll);
            var f = target.face;
            bool changed = false;

            GUILayout.Label($"<b>Human faces</b>   seed {target.seed}", Rich());
            GUILayout.BeginHorizontal();
            if (GUILayout.Button("<")) { target.Randomize(target.seed - 1); Sync(); }
            if (GUILayout.Button("Random")) { target.Randomize(Random.Range(0, 100000)); Sync(); }
            if (GUILayout.Button(">")) { target.Randomize(target.seed + 1); Sync(); }
            GUILayout.EndHorizontal();
            GUILayout.BeginHorizontal();
            if (GUILayout.Toggle(view == View.Portrait, "Portrait", GUI.skin.button)) view = View.Portrait;
            if (GUILayout.Toggle(view == View.Body, "Body", GUI.skin.button)) view = View.Body;
            if (GUILayout.Toggle(view == View.Lineup, "Lineup", GUI.skin.button)) view = View.Lineup;
            GUILayout.EndHorizontal();
            for (int m = 0; m < Motions.Length; m++)
            {
                if (m % 6 == 0) GUILayout.BeginHorizontal();          // six motion buttons per row
                if (GUILayout.Toggle(motion == m, Motions[m], GUI.skin.button)) { if (motion != m) { motion = m; SetMotion(); } }
                if (m % 6 == 5 || m == Motions.Length - 1) GUILayout.EndHorizontal();
            }
            if (view == View.Lineup && GUILayout.Button("Reroll lineup")) { lineupSeed += 10; RerollLineup(); }
            GUILayout.Label("right-drag: orbit   wheel: zoom");

            GUILayout.Space(6);
            GUILayout.Label("<b>Body</b>", Rich());
            changed |= BuildGui(f);
            changed |= Slider("Age", ref f.age, 0, 1);
            changed |= Slider("Short / Tall", ref f.height, -1, 1);
            var anc = f.ancestry;
            bool ac = false;
            ac |= Slider("Ancestry: African", ref anc.x, 0, 1);
            ac |= Slider("Ancestry: Asian", ref anc.y, 0, 1);
            ac |= Slider("Ancestry: European", ref anc.z, 0, 1);
            if (ac) { f.ancestry = anc; changed = true; }

            GUILayout.Space(6);
            GUILayout.Label("<b>Styles</b>", Rich());
            changed |= Cycle("Hair", ref f.hairStyle, WithNone(target.Styles("Hair_")));
            changed |= Cycle("Beard", ref f.beardStyle, WithNone(target.Styles("Beard_")));
            changed |= Cycle("Brows", ref f.browStyle, target.Styles("Brows_"));

            if (Cfg.garments != null && Cfg.garments.Length > 0) changed |= OutfitGui(f);

            GUILayout.Space(6);
            GUILayout.Label("<b>Colours</b>", Rich());
            if (Slider("Skin tone", ref toneT, 0, 1)) { SetTone(toneT); changed = true; }
            var hairNames = new List<string>(); foreach (var c in Cfg.hairColors) hairNames.Add(c.name);
            var dyeNames = new List<string>(); foreach (var c in Cfg.dyes) dyeNames.Add(c.name);
            var irisNames = new List<string>(); foreach (var c in Cfg.irisColors) irisNames.Add(c.name);
            bool hc = false;
            hc |= Cycle("Hair colour", ref hairName, hairNames);
            hc |= Cycle("Look", ref f.hairLook, new List<string>(Looks));
            if (f.hairLook != "natural" && f.hairLook != "sunkissed") hc |= Cycle("Dye", ref dyeName, dyeNames);
            if (hc) { SetHairColours(); changed = true; }
            string iris = Nearest(Cfg.irisColors, f.iris);
            if (Cycle("Eyes", ref iris, irisNames)) { f.iris = Cfg.IrisColor(iris); changed = true; }
            changed |= Slider("Stubble", ref f.stubble, 0, 1);
            changed |= Slider("Freckles", ref f.freckles, 0, 1);
            changed |= Slider("Age lines", ref f.ageLines, 0, 1.2f);
            changed |= Slider("Blush", ref f.blush, 0, 1);
            if (Cfg.cloths != null && Cfg.cloths.Length > 0)
            {
                var clothNames = new List<string>(Cfg.cloths);
                string cl = NearestHex(Cfg.cloths, f.cloth);
                if (Cycle("Underclothes", ref cl, clothNames)) { f.cloth = HumanFaceConfig.Hex(cl); changed = true; }
            }
            bool band = f.chestBand > 0.5f;
            bool nb = GUILayout.Toggle(band, " Chest band");
            if (nb != band) { f.chestBand = nb ? 1 : 0; changed = true; }

            GUILayout.Space(6);
            var bodyNames = new HashSet<string>(Cfg.bodySliders ?? new string[0]) { "NeckWidth" };   // set by the build
            showSliders = GUILayout.Toggle(showSliders, " Face sliders", GUI.skin.button);
            if (showSliders)
                foreach (var s in Cfg.sliders)
                {
                    if (bodyNames.Contains(s.name)) continue;
                    float v = f.GetSlider(s.name);
                    if (Slider(s.name, ref v, s.hasNeg ? -1 : 0, 1)) { f.SetSlider(s.name, v); changed = true; }
                }

            GUILayout.EndScrollView();
            GUILayout.EndArea();
            if (changed) target.Apply();
        }

        /// <summary>Outfit: one garment per slot (or none) and its colour from the villager palettes.</summary>
        bool OutfitGui(HumanFaceData f)
        {
            bool changed = false;
            GUILayout.Space(6);
            GUILayout.BeginHorizontal();
            GUILayout.Label("<b>Outfit</b>", Rich());
            if (GUILayout.Button("Random outfit", GUILayout.Width(110)))
            {
                f.outfit = HumanFaceGenerator.RandomOutfit(Cfg, new HumanFaceGenerator.Rng(Random.Range(0, 100000)), f.sex >= 0);
                f.armorSet = Cfg.WornArmorSet(f);
                changed = true;
            }
            GUILayout.EndHorizontal();

            // armour: a complete set that replaces the clothes (never loose pieces over clothes)
            if (Cfg.armorSets != null && Cfg.armorSets.Length > 0)
            {
                var sets = new List<string> { "" };
                foreach (var s in Cfg.armorSets) sets.Add(s.name);
                string set = f.armorSet ?? "";
                if (Cycle("Armour", ref set, sets))
                {
                    if (set == "")
                    {
                        f.armorSet = "";                  // armour off: back to villager clothes
                        f.outfit = HumanFaceGenerator.RandomOutfit(Cfg, new HumanFaceGenerator.Rng(Random.Range(0, 100000)), f.sex >= 0, false);
                    }
                    else
                        f.SetArmorSet(Cfg, set);
                    changed = true;
                }
                if (!string.IsNullOrEmpty(f.armorSet))
                {
                    foreach (var group in new[] { "Padding", "Steel", "Blackened", "Suit", "Leather", "Plates", "Cloth", "Boots" })
                        changed |= ArmorColour(f, group, g => Cfg.ArmorGroup(g) == group && !Cfg.FindGarment(g).companion
                                                                && Cfg.FindGarment(g).slot != "cloak", Cfg.GroupPalette(group));
                    changed |= SlotGui(f, "cloak");        // a cloak goes over armour too
                    return changed;                       // no clothing slots under armour
                }
            }
            var slots = new List<string>();
            foreach (var g in Cfg.garments) if (!slots.Contains(g.slot) && !SlotIsArmorOnly(g.slot)) slots.Add(g.slot);
            foreach (var slot in slots) changed |= SlotGui(f, slot);
            return changed;
        }

        /// <summary>One slot: garment (or none) and its colour. Companion-only garments never show up.</summary>
        bool SlotGui(HumanFaceData f, string slot)
        {
            bool changed = false;
            var options = new List<string> { "" };
            foreach (var g in Cfg.garments)
                if (g.slot == slot && !Cfg.IsArmorPiece(g.name) && !g.companion) options.Add(g.name);
            if (options.Count < 2) return false;
            string worn = "";
            foreach (var o in f.outfit)
            {
                var d = Cfg.FindGarment(o.garment);
                if (d?.slot == slot && !d.companion) worn = o.garment;
            }
            string pick = worn;
            if (Cycle(char.ToUpper(slot[0]) + slot.Substring(1), ref pick, options))
            {
                if (pick == "") f.SetGarment(Cfg, worn, null);
                else f.SetGarment(Cfg, pick, HumanFaceConfig.Hex(Palette(pick)[0]));
                changed = true;
                worn = pick;
            }
            if (worn == "") return changed;
            var pal = Palette(worn);
            Color cur = Color.white;
            foreach (var o in f.outfit) if (o.garment == worn) cur = o.color;
            string hex = NearestHex(pal, cur);
            if (Cycle("   colour", ref hex, new List<string>(pal)))
            {
                f.SetGarment(Cfg, worn, HumanFaceConfig.Hex(hex));
                changed = true;
            }
            return changed;
        }

        bool SlotIsArmorOnly(string slot)
        {
            foreach (var g in Cfg.garments) if (g.slot == slot && !Cfg.IsArmorPiece(g.name)) return false;
            return true;
        }

        /// <summary>One colour for a group of armour pieces.</summary>
        bool ArmorColour(HumanFaceData f, string label, System.Predicate<string> group, string[] pal)
        {
            Color cur = Color.white;
            bool any = false;
            foreach (var o in f.outfit) if (group(o.garment)) { cur = o.color; any = true; break; }
            if (!any || pal == null) return false;
            string hex = NearestHex(pal, cur);
            if (!Cycle(label, ref hex, new List<string>(pal))) return false;
            var c = HumanFaceConfig.Hex(hex);
            foreach (var o in f.outfit) if (group(o.garment)) o.color = c;
            return true;
        }

        string[] Palette(string garment)
        {
            var g = Cfg.FindGarment(garment);
            if (g?.slot == "cloak" && Cfg.cloaks != null) return Cfg.cloaks;
            if (g?.layer >= 3 && g.material == "leather" && Cfg.armorLeather != null) return Cfg.armorLeather;
            if (g?.material == "leather") return Cfg.leather;
            var all = new List<string>(Cfg.linen);
            all.AddRange(Cfg.wool);
            return all.ToArray();
        }

        /// <summary>Sex and build (the body comes in fixed builds; garments are made for each).</summary>
        bool BuildGui(HumanFaceData f)
        {
            if (Cfg.builds == null || Cfg.builds.Length == 0) return Slider("Feminine / Masculine", ref f.sex, -1, 1);
            var cur = Cfg.FindBuild(f.build) ?? Cfg.builds[0];
            bool changed = false;
            string sex = cur.sex == "M" ? "Masculine" : "Feminine";
            if (Cycle("Sex", ref sex, new List<string> { "Masculine", "Feminine" }))
            {
                string want = sex == "Masculine" ? "M" : "F";
                foreach (var b in Cfg.builds) if (b.sex == want && b.name == cur.name) { f.build = b.tag; break; }
                f.sex = want == "M" ? Mathf.Abs(f.sex) + 0.01f : -Mathf.Abs(f.sex) - 0.01f;
                changed = true;
                cur = Cfg.FindBuild(f.build);
            }
            var names = new List<string>();
            foreach (var b in Cfg.builds) if (b.sex == cur.sex) names.Add(b.name);
            string n = cur.name;
            if (Cycle("Build", ref n, names))
            {
                foreach (var b in Cfg.builds) if (b.sex == cur.sex && b.name == n) f.build = b.tag;
                changed = true;
            }
            return changed;
        }

        void Sync()
        {
            var f = target.face;
            hairName = Nearest(Cfg.hairColors, f.hairRoot);
            float best = 1e9f;
            for (int i = 0; i <= 40; i++)
            {
                var c = ToneAt(i / 40f);
                float d = Mathf.Abs(c.r - f.tone.r) + Mathf.Abs(c.g - f.tone.g) + Mathf.Abs(c.b - f.tone.b);
                if (d < best) { best = d; toneT = i / 40f; }
            }
        }

        Color ToneAt(float t)
        {
            var tones = Cfg.skinTones;
            float x = t * (tones.Length - 1);
            int i = Mathf.Min(Mathf.FloorToInt(x), tones.Length - 2);
            return Color.Lerp(HumanFaceConfig.Hex(tones[i]).linear, HumanFaceConfig.Hex(tones[i + 1]).linear, x - i).gamma;
        }

        void SetTone(float t)
        {
            var f = target.face;
            f.tone = ToneAt(t);
            var k = Cfg.shader.lipFromTone;
            var lin = f.tone.linear;
            f.lip = new Color(lin.r * k[0], lin.g * k[1], lin.b * k[2]).gamma;
        }

        void SetHairColours()
        {
            var f = target.face;
            var root = Cfg.HairColor(hairName).linear;
            var dye = Cfg.DyeColor(dyeName).linear;
            f.hairRoot = root.gamma; f.hairTip = root.gamma; f.hairStreak = root.gamma; f.streaks = 0; f.ombre = 0;
            switch (f.hairLook)
            {
                case "sunkissed": f.hairTip = new Color(root.r + (1 - root.r) * 0.35f, root.g + (1 - root.g) * 0.35f, root.b + (1 - root.b) * 0.35f).gamma; f.ombre = 0.8f; break;
                case "ombre": f.hairTip = dye.gamma; f.ombre = 1; break;
                case "streaks": f.hairStreak = dye.gamma; f.streaks = 0.3f; break;
                case "twotone": f.hairStreak = dye.gamma; f.streaks = 0.5f; break;
            }
            f.beardColor = f.hairRoot;
            f.browColor = (root * 0.8f).gamma;
        }

        static string Nearest(HumanFaceConfig.NamedColor[] list, Color c)
        {
            string best = list[0].name; float bd = 1e9f;
            foreach (var n in list)
            {
                var x = HumanFaceConfig.Hex(n.hex);
                float d = Mathf.Abs(x.r - c.r) + Mathf.Abs(x.g - c.g) + Mathf.Abs(x.b - c.b);
                if (d < bd) { bd = d; best = n.name; }
            }
            return best;
        }

        static List<string> WithNone(List<string> l) { l.Insert(0, ""); return l; }

        // values of the animator's "Motion" int (HumanSetup.BuildControllers)
        static readonly string[] Motions = { "Idle", "Walk", "Run", "Chop", "Hammer", "Sit", "Death", "Turn L", "Turn R", "Look", "Shift" };
        int motion;

        void SetMotion()
        {
            var all = new List<Animator>();
            if (target != null && target.animator != null) all.Add(target.animator);
            if (lineup != null) all.AddRange(lineup.GetComponentsInChildren<Animator>());
            foreach (var a in all) if (a.runtimeAnimatorController != null) a.SetInteger("Motion", motion);
        }

        static string NearestHex(string[] hexes, Color c)
        {
            string best = hexes[0]; float bd = 1e9f;
            foreach (var h in hexes)
            {
                var x = HumanFaceConfig.Hex(h);
                float d = Mathf.Abs(x.r - c.r) + Mathf.Abs(x.g - c.g) + Mathf.Abs(x.b - c.b);
                if (d < bd) { bd = d; best = h; }
            }
            return best;
        }

        static GUIStyle rich;
        static GUIStyle Rich() => rich ??= new GUIStyle(GUI.skin.label) { richText = true };

        static bool Slider(string label, ref float v, float lo, float hi)
        {
            GUILayout.BeginHorizontal();
            GUILayout.Label(label, GUILayout.Width(140));
            float n = GUILayout.HorizontalSlider(v, lo, hi, GUILayout.Width(120));
            GUILayout.Label(n.ToString("0.00"), GUILayout.Width(36));
            GUILayout.EndHorizontal();
            if (Mathf.Abs(n - v) < 1e-5f) return false;
            v = n;
            return true;
        }

        static bool Cycle(string label, ref string value, List<string> options)
        {
            if (options.Count == 0) return false;
            int i = Mathf.Max(0, options.IndexOf(value ?? ""));
            GUILayout.BeginHorizontal();
            GUILayout.Label(label, GUILayout.Width(90));
            bool ch = false;
            if (GUILayout.Button("<", GUILayout.Width(24))) { i = (i + options.Count - 1) % options.Count; ch = true; }
            GUILayout.Label(string.IsNullOrEmpty(options[i]) ? "(none)" : options[i], GUILayout.Width(120));
            if (GUILayout.Button(">", GUILayout.Width(24))) { i = (i + 1) % options.Count; ch = true; }
            GUILayout.EndHorizontal();
            if (ch) value = options[i];
            return ch;
        }
    }
}
