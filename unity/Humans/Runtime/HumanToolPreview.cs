using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Shows a tool in the hand while the animator plays the state that uses it (the helper axe during Chop).
    /// The tools sit in the hand sockets HumanSetup adds under the hand bones: Socket_R / Socket_L, origin at the
    /// fist centre, +Y along the held handle (toward the tool's head), +Z where the knuckles face (a tool's
    /// striking side). A game parents its own props to the same sockets; this component is only for previews.
    /// </summary>
    public class HumanToolPreview : MonoBehaviour
    {
        [Serializable]
        public class StateTool
        {
            [Tooltip("Animator state name on layer 0")]
            public string state;
            public GameObject tool;
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
                bool on = cur.IsName(t.state) || (animator.IsInTransition(0) && next.IsName(t.state));
                if (t.tool.activeSelf != on) t.tool.SetActive(on);
            }
        }
    }
}
