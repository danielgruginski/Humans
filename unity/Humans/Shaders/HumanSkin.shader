// Human skin: painted masks coloured per character (same maths as hum_material.py in Blender).
// Per-character values come from a MaterialPropertyBlock (HumanFace), so every head shares one material.
Shader "Humans/Skin"
{
    Properties
    {
        [NoScaleOffset] _MaskA ("Mask A (blush, lips, shading, lash)", 2D) = "black" {}
        [NoScaleOffset] _MaskB ("Mask B (stubble, age, freckles, brows)", 2D) = "black" {}
        [NoScaleOffset] _MaskC ("Mask C (hairline, beard area)", 2D) = "black" {}
        _Tone ("Skin tone", Color) = (0.81, 0.59, 0.44, 1)
        _Lip ("Lip", Color) = (0.74, 0.47, 0.40, 1)
        _Hair ("Hair (brows, stubble, hairline)", Color) = (0.23, 0.15, 0.09, 1)
        _Lash ("Lash line", Color) = (0.19, 0.15, 0.13, 1)
        _Blush ("Blush", Range(0, 1)) = 0.6
        _Freckles ("Freckles", Range(0, 1)) = 0
        _Stubble ("Stubble", Range(0, 1)) = 0
        _Age ("Age lines", Range(0, 1.2)) = 0
        _Brows ("Painted brows", Range(0, 1)) = 0.25
        _Scalp ("Hairline tint", Range(0, 1)) = 0
        _BeardShadow ("Beard shadow", Range(0, 1)) = 0
        _Smoothness ("Smoothness", Range(0, 1)) = 0.45
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" "Queue" = "Geometry" }

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
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
            #pragma multi_compile_fragment _ _LIGHT_COOKIES
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #pragma multi_compile_instancing

            #include "HumanCommon.hlsl"

            TEXTURE2D(_MaskA); SAMPLER(sampler_MaskA);
            TEXTURE2D(_MaskB); SAMPLER(sampler_MaskB);
            TEXTURE2D(_MaskC); SAMPLER(sampler_MaskC);
            CBUFFER_START(UnityPerMaterial)
                half4 _Tone, _Lip, _Hair, _Lash;
                half _Blush, _Freckles, _Stubble, _Age, _Brows, _Scalp, _BeardShadow, _Smoothness;
            CBUFFER_END

            static const half SHADE_MAX = 1.25;
            static const half3 BLUSH_TINT = half3(1.0, 0.55, 0.50);
            static const half3 FRECKLE_TINT = half3(0.70, 0.48, 0.36);

            half4 frag(HVaryings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                half4 a = SAMPLE_TEXTURE2D(_MaskA, sampler_MaskA, i.uv.xy);
                half4 b = SAMPLE_TEXTURE2D(_MaskB, sampler_MaskB, i.uv.xy);
                half4 c = SAMPLE_TEXTURE2D(_MaskC, sampler_MaskC, i.uv.xy);
                half3 hair = _Hair.rgb;
                half3 col = _Tone.rgb;
                col = lerp(col, col * BLUSH_TINT, a.r * _Blush);
                col = lerp(col, col * FRECKLE_TINT, b.b * _Freckles);
                col = lerp(col, lerp(col, hair, 0.6) * 0.75, b.r * _Stubble);
                col = lerp(col, _Lip.rgb, a.g * 0.8);
                col *= 1 - b.g * _Age * 0.25;
                col = lerp(col, hair * 0.8, b.a * _Brows);
                col = lerp(col, _Lash.rgb, a.a);
                col *= a.b * SHADE_MAX;
                col = lerp(col, lerp(col, hair * 0.9, 0.75), c.r * _Scalp);
                col = lerp(col, lerp(col, hair * 0.8, 0.5), c.g * _BeardShadow);
                return HumanShade(i, col, _Smoothness);
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On ZTest LEqual ColorMask 0
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
            ZWrite On ColorMask R
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
            ZWrite On
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
