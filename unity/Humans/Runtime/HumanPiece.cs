using System;
using UnityEngine;

namespace Humans
{
    /// <summary>
    /// One wearable piece (a hairstyle, a beard, brows, a garment for one build: Hair_X, Beard_X, Brows_X,
    /// Cloth_Garment_Build) as HumanSetup cut it out of the imported models: per LOD the mesh, its materials and the
    /// skeleton bones it is skinned to, by name. The prefab carries none of them: HumanFace makes a piece's renderers
    /// when someone wears it, loading it from Resources/HumanPieces, so only what is worn is in memory.
    /// </summary>
    public class HumanPiece : ScriptableObject
    {
        public const string Folder = "HumanPieces";

        [Serializable]
        public class Lod
        {
            [Tooltip("The renderer's name (the piece's name, with _L1 / _L2 below LOD0)")]
            public string name;
            public Mesh mesh;
            public Material[] materials = new Material[0];
            [Tooltip("The skinning bones by name (empty: a bone the skeleton does not have)")]
            public string[] bones = new string[0];
            public string rootBone;
            public Bounds bounds;
            public Vector3 position;
            public Quaternion rotation = Quaternion.identity;
            public Vector3 scale = Vector3.one;
        }

        [Tooltip("By LOD index; an entry without a mesh: the piece has no such LOD (brows at LOD2)")]
        public Lod[] lods = new Lod[0];

        public Lod At(int lod) => lod >= 0 && lod < lods.Length && lods[lod] != null && lods[lod].mesh != null ? lods[lod] : null;
    }
}
