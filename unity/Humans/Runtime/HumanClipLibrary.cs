using UnityEngine;

namespace Humans
{
    /// <summary>
    /// A set of other Humanoid clips to try on the humans in the showcase (HumanCreatorUI's clip browser): per-sex
    /// controllers with one unconnected state per clip, and the state names (the same name in both controllers when
    /// a clip exists for both sexes). Built by Tools > Humans > Build Clip Library From Folder; the helper bones,
    /// skirt ring and cape chain run after the Animator, so they work on any clip here too.
    /// </summary>
    [CreateAssetMenu(menuName = "Humans/Clip Library")]
    public class HumanClipLibrary : ScriptableObject
    {
        public string title;
        public RuntimeAnimatorController male, female;
        public string[] states = System.Array.Empty<string>();

        /// <summary>The controller for a face's sex (HumanFace.face.sex: >= 0 male), the other if one is missing.</summary>
        public RuntimeAnimatorController For(float sex) =>
            sex >= 0 ? (male != null ? male : female) : (female != null ? female : male);
    }
}
