using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Humans.EditorTools
{
    /// <summary>
    /// Contact sheets for checking clips against outfits, in play mode on the showcase (Humans_Showcase): dress
    /// the lineup, freeze everyone at a clip phase, render one tile per character (the others hidden).
    /// Pose() and Shot() must run on different frames: skinning happens in the player loop, not in Camera.Render.
    /// </summary>
    public static class HumanQA
    {
        /// <summary>The showcase lineup (not the creator), left to right.</summary>
        public static Animator[] Lineup() =>
            Object.FindObjectsByType<HumanFace>(FindObjectsSortMode.None)
                .Where(f => f.name.StartsWith("Human_") && f.animator != null)
                .OrderBy(f => f.name).Select(f => f.animator).ToArray();

        /// <summary>Armour set (or null to keep the outfit) per lineup character.</summary>
        public static void Dress(params string[] sets)
        {
            var row = Lineup();
            for (int i = 0; i < row.Length && i < sets.Length; i++)
            {
                if (string.IsNullOrEmpty(sets[i])) continue;
                var hf = row[i].GetComponentInParent<HumanFace>();
                hf.face.SetArmorSet(hf.Config, sets[i]);
                hf.Apply();
            }
        }

        /// <summary>Everyone frozen in `state` at normalized `phase` (Motion set so the controller stays there).</summary>
        public static void Pose(string state, float phase)
        {
            int motion = System.Array.IndexOf(HumanSetup.MotionStates, state);
            if (state == "Sit_Idle") motion = 5;
            foreach (var a in Lineup())
            {
                a.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                if (motion >= 0) a.SetInteger("Motion", motion);
                a.Play(state, 0, phase);
                a.speed = 0f;
            }
        }

        /// <summary>Back to playing.</summary>
        public static void Release()
        {
            foreach (var a in Lineup()) { a.speed = 1f; a.cullingMode = AnimatorCullingMode.CullUpdateTransforms; }
        }

        /// <summary>One tile per lineup character, the camera `dist` m off the hips along `view` (model space: +z
        /// in front, +x the character's left), `rows` rows. Saved as PNG at `path`.</summary>
        public static void Shot(string path, Vector3 view, float dist = 2.6f, int tile = 300, int rows = 2, float height = 0f)
        {
            var row = Lineup();
            int cols = Mathf.CeilToInt(row.Length / (float)rows);
            var sheet = new Texture2D(tile * cols, (int)(tile * 1.3f) * rows, TextureFormat.RGB24, false);
            int th = (int)(tile * 1.3f);
            var go = new GameObject("_qacam");
            var cam = go.AddComponent<Camera>();
            cam.fieldOfView = 32f;
            cam.nearClipPlane = 0.05f;
            var rt = new RenderTexture(tile, th, 24) { antiAliasing = 4 };
            cam.targetTexture = rt;
            var all = Object.FindObjectsByType<HumanFace>(FindObjectsSortMode.None).SelectMany(f => f.GetComponentsInChildren<Renderer>(true)).ToList();
            for (int i = 0; i < row.Length; i++)
            {
                var a = row[i];
                foreach (var r in all) r.forceRenderingOff = true;
                foreach (var r in a.GetComponentsInParent<HumanFace>()[0].GetComponentsInChildren<Renderer>(true)) r.forceRenderingOff = false;
                var c = a.GetBoneTransform(HumanBodyBones.Hips).position + Vector3.up * height;
                cam.transform.position = c + a.transform.TransformDirection(view.normalized) * dist;
                cam.transform.LookAt(c);
                cam.Render();
                RenderTexture.active = rt;
                sheet.ReadPixels(new Rect(0, 0, tile, th), (i % cols) * tile, (rows - 1 - i / cols) * th);
            }
            foreach (var r in all) r.forceRenderingOff = false;
            sheet.Apply();
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllBytes(path, sheet.EncodeToPNG());
            RenderTexture.active = null;
            cam.targetTexture = null;
            Object.DestroyImmediate(rt);
            Object.DestroyImmediate(go);
            Object.DestroyImmediate(sheet);
        }
    }
}
