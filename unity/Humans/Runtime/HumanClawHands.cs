using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Hands with claws (2026-10-24, the ghoul's GhoulClaws: 8-12 cm talons rigid on the fingers' last bones; Daniel:
    /// "the ghoul has the fist clutched in some animations, making the nails pierce the hand to the other side"): after
    /// the Animator, each finger joint's bend away from the open hand of the bind pose is held to <see cref="limit"/>
    /// (proximal, middle, last joint; the thumb's scaled by <see cref="thumbScale"/>), so a clip's fist becomes a claw
    /// and the talons stay in front of the palm. HumanSetup fills the joints (disabled); HumanFace switches it on while a
    /// garment in the `claws` slot is worn. Limits from MedievalSetting's GhoulCheck "Ghoul Claws" (every talon vertex
    /// against its hand, through the ghoul's clips).
    /// </summary>
    [DefaultExecutionOrder(150)]
    public class HumanClawHands : MonoBehaviour
    {
        [Tooltip("Per hand (left, then right): thumb, index, middle, ring, pinky, each joint 01..03")]
        public Transform[] joints = new Transform[0];
        [Tooltip("The joints' local rotations in the bind pose (the open hand)")]
        public Quaternion[] rest = new Quaternion[0];
        [Tooltip("Most a joint may bend from the open hand, degrees: proximal, middle, last")]
        public Vector3 limit = new Vector3(40f, 40f, 20f);     // 2026-10-24: 1 of 900 sampled frames left (0.7 cm, a thumb)
        [Range(0, 1)] public float thumbScale = 0.75f;

        void LateUpdate() => Apply();

        /// <summary>Hold the fingers to the limits now (LateUpdate does it every frame; edit-mode tools that sample a
        /// clip themselves call it after sampling).</summary>
        public void Apply()
        {
            for (int i = 0; i < joints.Length && i < rest.Length; i++)
            {
                if (joints[i] == null) continue;
                bool thumb = (i / 3) % 5 == 0;
                Clamp(joints[i], rest[i], (thumb ? thumbScale : 1f) * limit[i % 3]);
            }
        }

        /// <summary>Turn t back toward its rest rotation until it is at most maxDeg away (about the same axis).</summary>
        public static void Clamp(Transform t, Quaternion rest, float maxDeg)
        {
            var rel = Quaternion.Inverse(rest) * t.localRotation;
            rel.ToAngleAxis(out float ang, out var axis);
            if (ang > 180f) ang -= 360f;
            if (Mathf.Abs(ang) <= maxDeg || float.IsNaN(axis.x) || axis.sqrMagnitude < 1e-8f) return;
            t.localRotation = rest * Quaternion.AngleAxis(Mathf.Sign(ang) * maxDeg, axis);
        }
    }
}
