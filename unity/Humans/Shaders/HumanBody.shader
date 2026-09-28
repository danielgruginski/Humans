// Human body: skin + painted underclothes (same maths as hum_material.body_material in Blender).
//   c = tone; c = lerp(c, c*BLUSH, A.r*blush); c = lerp(c, c*FRECKLE, B.r*freckles)
//   c = lerp(c, cloth, saturate(A.g + A.a*top)); c *= A.b * SHADE_MAX
// Regions under garments are clipped: uv1.x = region id (per face), bit (id) of _Hide set = hidden.
Shader "Humans/Body"
{
    Properties
    {
        [NoScaleOffset] _MaskA ("Mask A (blush, shorts, shading, chest band)", 2D) = "black" {}
        [NoScaleOffset] _MaskB ("Mask B (freckles)", 2D) = "black" {}
        _Tone ("Skin tone", Color) = (0.81, 0.59, 0.44, 1)
        _Cloth ("Underclothes", Color) = (0.85, 0.81, 0.72, 1)
        _Blush ("Blush", Range(0, 1)) = 0.5
        _Freckles ("Freckles", Range(0, 1)) = 0
        _Top ("Chest band", Range(0, 1)) = 0
        _Smoothness ("Smoothness", Range(0, 1)) = 0.4
        _Hide ("Hidden regions (bit mask)", Float) = 0
        _Suit ("Bodysuit (0/1)", Float) = 0
        _SuitColor ("Bodysuit colour", Color) = (0.12, 0.12, 0.13, 1)
        [NoScaleOffset] _SuitPattern ("Bodysuit weave", 2D) = "white" {}
        _SuitTile ("Bodysuit weave tiling", Float) = 30
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
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #pragma multi_compile_instancing

            #include "HumanCommon.hlsl"

            TEXTURE2D(_MaskA); SAMPLER(sampler_MaskA);
            TEXTURE2D(_MaskB); SAMPLER(sampler_MaskB);
            TEXTURE2D(_SuitPattern); SAMPLER(sampler_SuitPattern);
            CBUFFER_START(UnityPerMaterial)
                half4 _Tone, _Cloth, _SuitColor;
                half _Blush, _Freckles, _Top, _Smoothness, _Suit;
                float _Hide, _SuitTile;
            CBUFFER_END

            static const half SHADE_MAX = 1.25;
            static const half3 BLUSH_TINT = half3(1.0, 0.55, 0.50);
            static const half3 FRECKLE_TINT = half3(0.70, 0.48, 0.36);

            half4 frag(HVaryings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                float region = round(i.uv.z);
                clip(0.5 - fmod(floor(_Hide / exp2(region)), 2.0));
                half4 a = SAMPLE_TEXTURE2D(_MaskA, sampler_MaskA, i.uv.xy);
                half4 b = SAMPLE_TEXTURE2D(_MaskB, sampler_MaskB, i.uv.xy);
                half3 col = _Tone.rgb;
                col = lerp(col, col * BLUSH_TINT, a.r * _Blush);
                col = lerp(col, col * FRECKLE_TINT, b.r * _Freckles);
                half cloth = saturate(a.g + a.a * _Top);
                col = lerp(col, _Cloth.rgb, cloth);
                // a bodysuit (the under-layer of fantasy armour): the whole body in a dark woven cloth
                half weave = SAMPLE_TEXTURE2D(_SuitPattern, sampler_SuitPattern, i.uv.xy * _SuitTile).r;
                col = lerp(col, _SuitColor.rgb * lerp(0.7, 1.0, weave), _Suit);
                cloth = max(cloth, _Suit);
                col *= a.b * SHADE_MAX;
                return HumanShade(i, col, lerp(_Smoothness, 0.2, cloth));
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
