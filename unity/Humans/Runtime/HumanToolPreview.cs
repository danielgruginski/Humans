using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Shows a tool in the hand while the animator plays a state that uses it (the helper axe during Chop, the
    /// sword and shield through the sword states). The tools sit in the sockets HumanSetup adds under the hand
    /// bones: Socket_R / Socket_L, origin at the fist centre, +Y along the held handle (toward the tool's head),
    /// +Z where the knuckles face (a tool's striking side); a shield on Socket_Shield (left forearm, +Y its
    /// face). A game parents its own props to the same sockets; this component is only for previews.
    /// </summary>
    public class HumanToolPreview : MonoBehaviour
    {
        [Serializable]
        public class StateTool
        {
            [Tooltip("Animator state name(s) on layer 0, comma-separated")]
            public string state;
            public GameObject tool;
            [NonSerialized] string[] names;

            public bool Plays(AnimatorStateInfo info)
            {
                if (names == null)
                {
                    names = (state ?? "").Split(',');
                    for (int i = 0; i < names.Length; i++) names[i] = names[i].Trim();
                }
                foreach (var n in names)
                    if (info.IsName(n)) return true;
                return false;
            }
        }

        public Animator animator;
        public StateTool[] tools = Array.Empty<StateTool>();

        void LateUpdate()
        {
            if (animator == null || !animator.isActiveAndEnabled || animator.runtimeAnimatorController == null) return;
            var cur = animator.GetCurrentAnimatorStateInfo(0);
            var next = animator.GetNextAnimatorStateInfo(0);
            foreach (var t in tools)
            {
                if (t.tool == null) continue;
                bool on = t.Plays(cur) || (animator.IsInTransition(0) && t.Plays(next));
                if (t.tool.activeSelf != on) t.tool.SetActive(on);
            }
        }
    }
}
