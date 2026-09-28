// Human eye: front-projected eyeball mask, iris colour per character.
Shader "Humans/Eye"
{
    Properties
    {
        [NoScaleOffset] _EyeMask ("Eye mask (iris, pupil, iris dark, sclera)", 2D) = "black" {}
        _Iris ("Iris", Color) = (0.36, 0.52, 0.66, 1)
        _Smoothness ("Smoothness", Range(0, 1)) = 0.72
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
                half _Smoothness;
            CBUFFER_END

            half4 frag(HVaryings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                half4 m = SAMPLE_TEXTURE2D(_EyeMask, sampler_EyeMask, i.uv.xy);
                half3 col = half3(0.86, 0.84, 0.80) * m.a;
                half3 iris = lerp(_Iris.rgb, _Iris.rgb * 0.25, m.b);
                col = lerp(col, iris, m.r);
                col = lerp(col, half3(0.005, 0.005, 0.005), m.g);
                return HumanShade(i, col, _Smoothness);
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
