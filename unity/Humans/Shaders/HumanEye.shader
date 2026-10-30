// Human eye: front-projected eyeball mask, iris colour per character. _Milk (the undead): the iris fades toward a
// pale grey and the pupil into it (hum_material.eye_material).
// The mask carries the lids' shadow; a small fixed highlight on the iris keeps the eye alive whatever the lights do.
Shader "Humans/Eye"
{
    Properties
    {
        [NoScaleOffset] _EyeMask ("Eye mask (iris, pupil, iris dark, sclera)", 2D) = "black" {}
        _Iris ("Iris", Color) = (0.36, 0.52, 0.66, 1)
        _Smoothness ("Smoothness", Range(0, 1)) = 0.72
        _Milk ("Clouded (undead)", Range(0, 1)) = 0
        _Catchlight ("Highlight on the iris", Range(0, 1)) = 0.75
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
            // no shadow keywords on purpose: stylised eyes stay out of the brow/lid shadow (else they read as holes)
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #pragma multi_compile_instancing

            #include "HumanCommon.hlsl"

            TEXTURE2D(_EyeMask); SAMPLER(sampler_EyeMask);
            CBUFFER_START(UnityPerMaterial)
                half4 _Iris;
                half _Smoothness, _Milk, _Catchlight;
            CBUFFER_END

            static const half3 EYE_CORNER = half3(0.62, 0.34, 0.31);       // the mask's B outside the iris
            static const half3 CATCH_DIR = half3(-0.20, 0.20, 0.96);        // view space, up and to the left

            half4 frag(HVaryings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                half4 m = SAMPLE_TEXTURE2D(_EyeMask, sampler_EyeMask, i.uv.xy);
                half3 col = half3(0.72, 0.70, 0.66) * m.a;
                col = lerp(col, EYE_CORNER, m.b);
                half3 iris = lerp(_Iris.rgb, _Iris.rgb * 0.25, m.b);
                iris = lerp(iris, half3(0.62, 0.64, 0.60), _Milk * 0.55);
                col = lerp(col, iris, m.r);
                col = lerp(col, half3(0.005, 0.005, 0.005), m.g * (1 - 0.85 * _Milk));
                half4 c = HumanShade(i, col, _Smoothness);
                half3 n = NormalizeNormalPerPixel(i.normalWS);
                half spot = smoothstep(0.9965, 0.9985, dot(TransformWorldToViewDir(n), normalize(CATCH_DIR))) * m.r * (1 - _Milk);
                c.rgb += spot * _Catchlight * saturate(GetMainLight().color + SampleSH(n));
                return c;
            }
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
