using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// Per-key bone deltas for the human skeleton, converted to the model's space by HumanSetup from
    /// export/human_rig.json. At runtime each bone moves by sum(weight_k * delta_k) and the (residual) blend
    /// shapes add the rest of the shape, so skeleton and body agree for every character.
    /// </summary>
    public class HumanRigData : ScriptableObject
    {
        [Serializable]
        public class KeyDelta
        {
            public string key;
            public int[] bones;          // indices into `bones`
            public Vector3[] deltas;     // model space, metres
        }

        public string[] bones;           // parents before children
        public int[] parents;            // -1 for the root
        public KeyDelta[] keys;
        public float tallRatio = 1.2f;   // uniform scale at height +1
        public float shortRatio = 0.9f;  // uniform scale at height -1
        public int hipsIndex;

        public float HeightScale(float height) =>
            height >= 0 ? 1f + (tallRatio - 1f) * height : 1f + (1f - shortRatio) * height;
    }
}
