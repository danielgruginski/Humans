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

        [Tooltip("Strand hair and beards: the tint it lays on the skin in the head's UVs, fading out past its edge")]
        public Texture2D edge;

        /// <summary>How thick the piece is round a limb (HumanClothPush: the cloth pushed off that limb clears it), from
        /// its LOD0 at setup - the meshes aren't readable in a build.</summary>
        [Serializable]
        public class LimbFit
        {
            public string bone;                           // the limb's bone (upper arm, forearm, hand, thigh, shin)
            [Tooltip("Radius near the bone's joint and near the far end (rest metres)")] public float ra, rb;
            [Tooltip("The build's offset of the bone: the piece's rest positions (uv2/uv3, Blender axes) less its mesh's")]
            public Vector3 offset;
            public int count;                             // vertices that ride the bone (0: it has none)
        }
        public LimbFit[] limbs = new LimbFit[0];

        /// <summary>Strand-card hair as HumanHairSim simulates it, from the LOD's mesh at setup (the meshes aren't readable
        /// in a build): a particle per card row - its mesh vertices, its strand (consecutive particles, root first), its
        /// skinning. Positions are not stored: they come from the GPU skinning when bound (the face's keys in them).</summary>
        [Serializable]
        public class HairSim
        {
            public int[] vertStart = new int[0];          // particle p's vertices: vertList[vertStart[p] .. vertStart[p + 1])
            public int[] vertList = new int[0];
            public int[] parent = new int[0];             // -1: a strand's root
            public float[] path = new float[0];           // the distance from its root along the strand (m, rest)
            public float[] hold = new float[0];           // its strand's length lying on the head from the root (m): held
                                                          // there like the root, followed loosely past it
            public string[] bones = new string[0];        // the bones it is skinned to, by name
            public Matrix4x4[] bindposes = new Matrix4x4[0];
            public int[] skinI = new int[0];              // 4 a particle, into bones
            public Vector4[] skinW = new Vector4[0];
            public bool Valid => parent.Length > 0 && vertStart.Length == parent.Length + 1;
        }

        /// <summary>A worn piece's points the simulated hair stays off (one a 2 cm cell of its LOD's mesh), with their body
        /// region (uv1.x: points hidden by an outer layer are skipped) and skinning; positions from the GPU skinning.</summary>
        [Serializable]
        public class SimLayer
        {
            public int[] verts = new int[0];
            public int[] region = new int[0];
            public string[] bones = new string[0];
            public Matrix4x4[] bindposes = new Matrix4x4[0];
            public int[] skinI = new int[0];
            public Vector4[] skinW = new Vector4[0];
            public bool Valid => verts.Length > 0 && skinW.Length == verts.Length;
        }

        [Tooltip("By LOD: the hair's simulation data (empty: not simulated)")] public HairSim[] hairSim = new HairSim[0];
        [Tooltip("By LOD: this piece as a layer simulated hair stays off")] public SimLayer[] simLayers = new SimLayer[0];

        public HairSim HairAt(int lod) => lod >= 0 && lod < hairSim.Length && hairSim[lod] != null && hairSim[lod].Valid ? hairSim[lod] : null;
        public SimLayer LayerAt(int lod) => lod >= 0 && lod < simLayers.Length && simLayers[lod] != null && simLayers[lod].Valid ? simLayers[lod] : null;

        public Lod At(int lod) => lod >= 0 && lod < lods.Length && lods[lod] != null && lods[lod].mesh != null ? lods[lod] : null;
    }
}
