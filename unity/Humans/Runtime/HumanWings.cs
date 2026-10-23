using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// The wings (2026-10-23: the demons', imps' and angels' DemonWings / AngelWings garments, skinned to two chains
    /// of helper bones off spine_03 - xh_wing_l/r_0 root, _1 elbow, _2 wrist; hum_helpers.WING in Blender, where they
    /// stay rigid). After the Animator each chain goes back to its bind rotations and is turned about the
    /// character's frame: a slow breathing sway, wing beats (<see cref="flap"/>: 0 at rest .. 1 full beats, the elbow
    /// and wrist following the root a little later, so the beat travels out along the wing) and folding
    /// (<see cref="fold"/>: swept back and down along the back). A game sets flap (flying, attacking) and fold
    /// (walking indoors, resting); <see cref="demo"/> beats now and then on its own for test scenes. HumanFace runs
    /// it only while a wings-slot garment is worn; HumanSetup fills it from human_rig.json's "wings".
    /// </summary>
    [DefaultExecutionOrder(150)]
    public class HumanWings : MonoBehaviour
    {
        [Tooltip("Left wing: root, elbow, wrist")] public Transform[] left = Array.Empty<Transform>();
        [Tooltip("Right wing: root, elbow, wrist")] public Transform[] right = Array.Empty<Transform>();
        public Quaternion[] restLeft = Array.Empty<Quaternion>(), restRight = Array.Empty<Quaternion>();
        [Tooltip("The character's frame (the Animator's transform)")] public Transform facing;

        [Range(0f, 1f), Tooltip("Wing beats: 0 at rest .. 1 full beats (flying, attacking)")] public float flap;
        [Range(0f, 1f), Tooltip("0 half raised (rest) .. 1 folded down along the back")] public float fold;
        [Tooltip("Beats per second")] public float beatRate = 1.5f;
        [Tooltip("How far the root swings up and down at full beats (deg)")] public float beatAngle = 36f;
        [Tooltip("The breathing sway at rest (deg)")] public float breathAngle = 3f;
        [Tooltip("Beat now and then on its own (test scenes; a game drives flap)")] public bool demo;

        float phase, beat, breath, demoClock;

        void OnDisable() => Rest();

        void Rest()
        {
            for (int i = 0; i < left.Length && i < restLeft.Length; i++) if (left[i] != null) left[i].localRotation = restLeft[i];
            for (int i = 0; i < right.Length && i < restRight.Length; i++) if (right[i] != null) right[i].localRotation = restRight[i];
        }

        void LateUpdate() => Pose(Time.deltaTime);

        /// <summary>Advance by dt and pose both wings (editor tools that sample a clip call it after sampling).</summary>
        public void Pose(float dt)
        {
            float target = flap;
            if (demo)
            {
                demoClock = (demoClock + dt) % 7f;
                target = Mathf.Max(target, demoClock < 2.6f ? 1f : 0f);       // 2.6 s of beats every 7 s
            }
            beat = Mathf.MoveTowards(beat, target, dt * 2.5f);
            phase = (phase + dt * beatRate * Mathf.PI * 2f) % (Mathf.PI * 2f);
            breath = (breath + dt * 0.35f * Mathf.PI * 2f) % (Mathf.PI * 2f);
            Rest();
            var f = facing != null ? facing : transform;
            PoseChain(left, f, 1f);
            PoseChain(right, f, -1f);
        }

        void PoseChain(Transform[] b, Transform f, float side)
        {
            if (b.Length < 3 || b[0] == null || b[1] == null || b[2] == null) return;
            Vector3 up = f.up, back = -f.forward;
            float rise = breathAngle * Mathf.Sin(breath) + beat * beatAngle * Mathf.Sin(phase) - fold * 30f;
            // the root: swept back when folding (about the character's up), then raised or lowered about the axis
            // across the wing (its direction x up: + turns the wing's tip up)
            Vector3 d = b[1].position - b[0].position;
            if (fold > 0f)
            {
                float sweep = Vector3.SignedAngle(Vector3.ProjectOnPlane(d, up), back, up);
                b[0].rotation = Quaternion.AngleAxis(sweep * 0.55f * fold, up) * b[0].rotation;
                d = b[1].position - b[0].position;
            }
            b[0].rotation = Quaternion.AngleAxis(rise, Vector3.Cross(d, up).normalized) * b[0].rotation;
            // the elbow and the wrist follow later in the beat (the beat travels out), and fold down
            float bend1 = beat * beatAngle * 0.55f * Mathf.Sin(phase - 0.8f) - fold * 55f;
            Vector3 d1 = b[2].position - b[1].position;
            b[1].rotation = Quaternion.AngleAxis(bend1, Vector3.Cross(d1, up).normalized) * b[1].rotation;
            float bend2 = beat * beatAngle * 0.6f * Mathf.Sin(phase - 1.5f) - fold * 60f;
            Vector3 d2 = b[2].position - b[1].position;
            b[2].rotation = Quaternion.AngleAxis(bend2, Vector3.Cross(d2, up).normalized) * b[2].rotation;
        }
    }
}
