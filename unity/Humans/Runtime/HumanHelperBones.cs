using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Drives the helper bones (xh_*) after the Animator, so they work under any Humanoid clip (Humanoid never
    /// animates bones outside the avatar). Each helper sits on a main joint and carries part of the skin there:
    /// <list type="bullet">
    /// Every helper's world rotation turns <c>factor</c> of the way its source turns past the source's parent:
    /// <item>share: xh_deltoid: half
    /// the upper arm, keeps the armpit and shoulder from collapsing; xh_glute: half the thigh, the hip crease and
    /// tassets)</item>
    /// <item>skirt: a share whose factor rises to factorRaised as the source is raised (xh_skirt: a skirt's panel
    /// between hips and knees follows most of the thigh's swing, all of it when sitting)</item>
    /// <item>xh_hem: at the knee of the skirt panel (child of xh_skirt), follows a little of the thigh's swing: the
    /// skirt below the knee hangs from it</item>
    /// </list>
    /// HumanSetup fills the list from human_rig.json (hum_helpers.HELPERS in Blender, the same formulas).
    /// </summary>
    [DefaultExecutionOrder(100)]
    public class HumanHelperBones : MonoBehaviour
    {
        [Serializable]
        public class Helper
        {
            public Transform bone;
            public Transform source;
            public bool counter;
            [Range(0f, 1f)] public float factor = 0.5f;
            [Tooltip("The helper's local rotation in the bind pose")]
            public Quaternion restLocal = Quaternion.identity;
            [Tooltip("The helper's bind rotation relative to its base (the source's parent unless baseBone is set)")]
            public Quaternion restRel = Quaternion.identity;
            [Tooltip("The source's local rotation in the bind pose")]
            public Quaternion sourceRestLocal = Quaternion.identity;
            [Tooltip("The factor while the source swings back (factor is for forward); = factor for no difference")]
            public float factorBack = 0.5f;
            [Tooltip("The factor once the source is raised (degrees from its bind direction) past raiseTo")]
            public float factorRaised;
            public float raiseFrom, raiseTo;
            [Tooltip("The source's axis (toward its child joint), in its own space")]
            public Vector3 sourceAxis = Vector3.up;
            [Tooltip("Skirt panels: 1 front, 2 back - hang in the character's frame unless the source (followed by factor) pushes further forward / back")]
            public int hang;
            [Tooltip("The source's rest axis in the facing transform's space (the hanging direction)")]
            public Vector3 hangRest = Vector3.down;
            [Tooltip("Optional: turn on top of this bone instead of the source's parent (xh_hemback: the hanging hem)")]
            public Transform baseBone;
            [Tooltip("Optional: measure 'raised' on this bone instead of the source (xh_hemback: the thigh)")]
            public Transform raiseSource;
            public Quaternion raiseRestLocal = Quaternion.identity;
            public Vector3 raiseAxis = Vector3.up;
            [Tooltip("Optional: the other thigh - 'raised' is then the less raised of the two (sitting lifts both)")]
            public Transform mate;
            public Quaternion mateRestLocal = Quaternion.identity;
            public Vector3 mateAxis = Vector3.up;
        }

        public Helper[] helpers = Array.Empty<Helper>();
        [Tooltip("The character's facing (the animated model: root-motion turns rotate it, not this root)")]
        public Transform facing;

        void LateUpdate()
        {
            foreach (var h in helpers)
            {
                if (h.bone == null || h.source == null || h.source.parent == null || h.bone.parent == null) continue;
                // the source's own turn (past its parent), in world space
                var turn = h.source.rotation * Quaternion.Inverse(h.source.parent.rotation * h.sourceRestLocal);
                float f = h.factor, raisedK = 0f;
                if (h.factorBack != h.factor)                        // skirts: less when the thigh swings back
                {
                    var rest = h.source.parent.rotation * h.sourceRestLocal * h.sourceAxis;
                    float swing = Vector3.Dot(h.source.rotation * h.sourceAxis - rest, (facing != null ? facing : transform).forward);
                    float u = Mathf.Clamp01((swing + 0.05f) / 0.1f);
                    f = Mathf.Lerp(h.factorBack, h.factor, u * u * (3f - 2f * u));
                }
                if (h.raiseTo > h.raiseFrom)                         // xh_skirt: all of the thigh's turn once raised
                {
                    var rs = h.raiseSource != null ? h.raiseSource : h.source;
                    var rRest = h.raiseSource != null ? h.raiseRestLocal : h.sourceRestLocal;
                    var rAxis = h.raiseSource != null ? h.raiseAxis : h.sourceAxis;
                    float raised = Vector3.Angle(rs.rotation * rAxis, rs.parent.rotation * rRest * rAxis);
                    if (h.mate != null && h.mate.parent != null)
                        raised = Mathf.Min(raised, Vector3.Angle(h.mate.rotation * h.mateAxis,
                                                                 h.mate.parent.rotation * h.mateRestLocal * h.mateAxis));
                    float u = Mathf.Clamp01((raised - h.raiseFrom) / (h.raiseTo - h.raiseFrom));
                    raisedK = u * u * (3f - 2f * u);
                    f = Mathf.Lerp(f, h.factorRaised, raisedK);
                }
                // f of the source's turn, in world space, whatever the helper hangs from (its parent only places it)
                if (h.hang != 0 && facing != null)
                {
                    // hang in the character's frame unless the thigh pushes into the panel
                    var r = h.source.parent.rotation * h.sourceRestLocal * h.sourceAxis;
                    var ct = Quaternion.Slerp(Quaternion.identity, turn, h.factor) * r;
                    var ch = facing.rotation * h.hangRest;
                    float sgn = Vector3.Dot(ct - ch, facing.forward) * (h.hang == 1 ? 1f : -1f);
                    float w = Mathf.Clamp01((sgn + 0.03f) / 0.06f);
                    var dir = Vector3.Lerp(ch, ct, w * w * (3f - 2f * w)).normalized;
                    if (raisedK > 0f)
                        dir = Vector3.Lerp(dir, Quaternion.Slerp(Quaternion.identity, turn, h.factorRaised) * r, raisedK).normalized;
                    h.bone.rotation = Quaternion.FromToRotation(r, dir) * h.source.parent.rotation * h.restRel;
                    continue;
                }
                var part = Quaternion.Slerp(Quaternion.identity, turn, f);
                h.bone.rotation = part * (h.baseBone != null ? h.baseBone.rotation : h.source.parent.rotation) * h.restRel;
            }
        }
    }
}
