using UnityEngine;

namespace Humans
{
    /// <summary>
    /// What HumanHairSim needs that no worn piece carries (Resources/HumanHairSimData, made at setup by
    /// HumanHairCardsSpike.Install): the compute shader (so builds include it) and the body and head as layers the hair
    /// stays off, per LOD (Body / Body_L1, Head / Head_L1; one mesh per LOD serves every build: the build's keys are in
    /// the GPU skinning the layer's positions come from).
    /// </summary>
    public class HumanHairSimData : ScriptableObject
    {
        public const string Path = "HumanHairSimData";
        public ComputeShader shader;
        public HumanPiece.SimLayer[] body = new HumanPiece.SimLayer[0];
        public HumanPiece.SimLayer[] head = new HumanPiece.SimLayer[0];

        static HumanHairSimData loaded;
        static bool tried;

        public static HumanHairSimData Get()
        {
            if (loaded == null && !tried)
            {
                tried = true;
                loaded = Resources.Load<HumanHairSimData>(Path);
            }
            return loaded;
        }

        public static void ClearCache() { loaded = null; tried = false; }

        public HumanPiece.SimLayer Body(int lod) => lod >= 0 && lod < body.Length && body[lod] != null && body[lod].Valid ? body[lod] : null;
        public HumanPiece.SimLayer Head(int lod) => lod >= 0 && lod < head.Length && head[lod] != null && head[lod].Valid ? head[lod] : null;
    }
}
