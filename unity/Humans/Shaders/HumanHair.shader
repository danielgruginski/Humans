// Human hair, beards and brows: solid clumps, multi-colour (root/tip ombre + coherent streaks).
//   t  = uv1.y (root -> tip), id = uv1.x (per clump, varies smoothly with position)
//   c  = lerp(root, tip, smoothstep(0.25, 1, o) * ombre)   o = uv2.y: 0 top of the style .. 1 its lowest ends
//   c  = lerp(c, streak, id < streaks)
// Double-sided: thin or folded clumps seen from behind would otherwise open holes (Blender draws both sides,
// so it never showed there); back faces get flipped normals.
//   hidden under a cap: CapCut (uv2.x) > _CapCut (0 = no cap)
//   c *= strand.r * lerp(0.7, 1, smoothstep(0, 0.3, t)) * (1 - EDGE_DARK * vertexColor.r)
Shader "Humans/Hair"
{
    Properties
    {
        _Strands ("Strands", 2D) = "white" {}
        _HairRoot ("Root", Color) = (0.23, 0.15, 0.09, 1)
        _HairTip ("Tip", Color) = (0.23, 0.15, 0.09, 1)
        _HairStreak ("Streak", Color) = (0.6, 0.1, 0.1, 1)
        _Streaks ("Streak fraction", Range(0, 1)) = 0
        _Ombre ("Ombre", Range(0, 1)) = 0
        _EdgeDark ("Clump edge darkening", Range(0, 1)) = 0.35
        _Smoothness ("Smoothness", Range(0, 1)) = 0.45
        _CapCut ("Cap cut (0 = no cap)", Float) = 0
        _HoodCut ("Under a hood (0/1)", Float) = 0
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" "Queue" = "Geometry" }

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            Cull Off
            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex HumanVert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile _ _LIGHT_LAYERS
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #pragma multi_compile_instancing

            #include "HumanCommon.hlsl"

            TEXTURE2D(_Strands); SAMPLER(sampler_Strands);
            CBUFFER_START(UnityPerMaterial)
                float4 _Strands_ST;
                half4 _HairRoot, _HairTip, _HairStreak;
                half _Streaks, _Ombre, _EdgeDark, _Smoothness;
                float _CapCut, _HoodCut;
            CBUFFER_END

            half4 frag(HVaryings i, bool front : SV_IsFrontFace) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                i.normalWS = front ? i.normalWS : -i.normalWS;
                if (_CapCut > 0 && i.cap.x > _CapCut) discard;
                if (_HoodCut > 0.5 && i.cap.z > 0) discard;
                half t = i.uv.w;
                half id = i.uv.z;
                half3 col = lerp(_HairRoot.rgb, _HairTip.rgb, smoothstep(0.25, 1.0, i.cap.y) * _Ombre);
                col = lerp(col, _HairStreak.rgb, 1.0 - step(_Streaks, id));
                col *= SAMPLE_TEXTURE2D(_Strands, sampler_Strands, i.uv.xy * _Strands_ST.xy + _Strands_ST.zw).r;
                col *= lerp(0.7, 1.0, smoothstep(0.0, 0.3, t));
                col *= 1.0 - _EdgeDark * i.color.r;
                return HumanShade(i, col, _Smoothness);
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On ZTest LEqual ColorMask 0 Cull Off
            HLSLPROGRAM
            #pragma vertex ShadowPassVertex
            #pragma fragment ShadowPassFragment
            #pragma multi_compile_instancing
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #include "Packages/com.unity.render-pipelines.universal/Shaders/ShadowCasterPass.hlsl"
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On ColorMask R Cull Off
            HLSLPROGRAM
            #pragma vertex DepthOnlyVertex
            #pragma fragment DepthOnlyFragment
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/Shaders/DepthOnlyPass.hlsl"
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On Cull Off
            HLSLPROGRAM
            #pragma vertex DepthNormalsVertex
            #pragma fragment DepthNormalsFragment
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/DepthNormalsPass.hlsl"
            ENDHLSL
        }
    }
}
