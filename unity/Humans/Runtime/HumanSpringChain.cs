using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// A cape's spring chain (xh_cape_0..2, down the back of a cloak or cape): Verlet points along the links,
    /// pulled toward the hanging pose, with gravity, damping and collision capsules on the spine, pelvis and legs;
    /// the links then turn to follow the points. Runs after the Animator and HumanHelperBones, at a fixed 60 Hz,
    /// so the cape trails when the character runs or turns and settles back when it stops.
    /// HumanSetup fills it from human_rig.json (hum_helpers.CAPE in Blender, where the chain is rigid).
    /// </summary>
    [DefaultExecutionOrder(200)]
    public class HumanSpringChain : MonoBehaviour
    {
        [Serializable]
        public struct Capsule
        {
            public Transform a, b;
            public float radius;
        }

        [Tooltip("The links, from the one hanging off the spine down")]
        public Transform[] bones = Array.Empty<Transform>();
        [Tooltip("Their local rotations in the bind pose")]
        public Quaternion[] restLocal = Array.Empty<Quaternion>();
        [Tooltip("The last link's tip, in its own space")]
        public Vector3 tipLocal = new Vector3(0, 0.25f, 0);

        [Range(0f, 1f), Tooltip("Pull toward the hanging pose per step")] public float stiffness = 0.06f;
        [Range(0f, 1f), Tooltip("Velocity lost per step")] public float damping = 0.12f;
        [Tooltip("Scale of gravity on the points")] public float gravity = 0.6f;
        [Tooltip("Cloth thickness kept off the colliders")] public float thickness = 0.03f;
        public Capsule[] colliders = Array.Empty<Capsule>();

        const float Step = 1f / 60f;
        Vector3[] pos, prev, target;
        float acc;
        bool live;

        void OnEnable() { live = false; }

        void OnDisable()                                                // back to hanging (no cape worn)
        {
            for (int i = 0; i < bones.Length && i < restLocal.Length; i++)
                if (bones[i] != null) bones[i].localRotation = restLocal[i];
        }

        void LateUpdate()
        {
            int n = bones.Length;
            if (n == 0 || restLocal.Length != n || bones[0] == null) return;
            if (target == null || target.Length != n + 1)
            {
                target = new Vector3[n + 1];
                pos = new Vector3[n + 1];
                prev = new Vector3[n + 1];
                live = false;
            }
            // the hanging pose: the links at rest on whatever the animation did to the spine
            for (int i = 0; i < n; i++) bones[i].localRotation = restLocal[i];
            for (int i = 0; i < n; i++) target[i] = bones[i].position;
            target[n] = bones[n - 1].TransformPoint(tipLocal);
            if (!live || (pos[0] - target[0]).sqrMagnitude > 4f)       // first frame or a teleport
            {
                Array.Copy(target, pos, n + 1);
                Array.Copy(target, prev, n + 1);
                acc = 0f;
                live = true;
            }
            acc = Mathf.Min(acc + Time.deltaTime, 4 * Step);
            while (acc >= Step)
            {
                acc -= Step;
                Simulate(n);
            }
            // turn each link so its child point lands on the simulated one
            for (int i = 0; i < n; i++)
            {
                var from = (i + 1 < n ? bones[i + 1].position : bones[i].TransformPoint(tipLocal)) - bones[i].position;
                var to = pos[i + 1] - bones[i].position;
                if (from.sqrMagnitude > 1e-8f && to.sqrMagnitude > 1e-8f)
                    bones[i].rotation = Quaternion.FromToRotation(from, to) * bones[i].rotation;
            }
        }

        void Simulate(int n)
        {
            pos[0] = prev[0] = target[0];
            var g = Physics.gravity * (gravity * Step * Step);
            for (int i = 1; i <= n; i++)
            {
                var v = (pos[i] - prev[i]) * (1f - damping);
                prev[i] = pos[i];
                pos[i] += v + g;
                pos[i] += (target[i] - pos[i]) * stiffness;
            }
            for (int it = 0; it < 2; it++)
            {
                for (int i = 1; i <= n; i++)                            // links keep their length
                {
                    float len = (target[i] - target[i - 1]).magnitude;
                    var d = pos[i] - pos[i - 1];
                    pos[i] = pos[i - 1] + (d.sqrMagnitude > 1e-10f ? d.normalized : (target[i] - target[i - 1]).normalized) * len;
                }
                for (int i = 1; i <= n; i++)                            // and stay out of the body
                    foreach (var c in colliders)
                    {
                        if (c.a == null || c.b == null) continue;
                        Vector3 a = c.a.position, ab = c.b.position - a;
                        float t = Mathf.Clamp01(Vector3.Dot(pos[i] - a, ab) / Mathf.Max(ab.sqrMagnitude, 1e-8f));
                        var q = a + ab * t;
                        var d = pos[i] - q;
                        float r = c.radius + thickness;
                        if (d.sqrMagnitude < r * r)
                            pos[i] = q + (d.sqrMagnitude > 1e-10f ? d.normalized : -transform.forward) * r;
                    }
            }
        }
    }
}
