// Human garments (same maths as hum_material.cloth_material in Blender):
//   c = colour * pattern(uv) * lerp(0.5, 1, AO) * (1 - 0.18 * hem)      AO, hem = vertex colour r, g ("ClothData")
// One material per fabric (M_HumanCloth = weave, M_HumanLeather = grain); the colour is per renderer
// (MaterialPropertyBlock _Color, set by HumanFace).
//   c = lerp(c, _Metal * lerp(0.5, 1, AO), vertex colour b)                studs and buckles: iron
// _Triplanar (mail): the pattern is projected in 3D from each vertex's rest position (uv2, uv3.x), so the
// rings are one size everywhere; trims (uv3.y = 1) keep their flat UV.
// Double-sided (open sheets like shoulder plates and hems seen from inside): back faces get flipped normals.
// Layering: uv1.x = body region under the face; bit (region) of _Hide set = covered by an outer garment.
Shader "Humans/Cloth"
{
    Properties
    {
        _Pattern ("Pattern (grey, tiling)", 2D) = "white" {}
        _Color ("Colour", Color) = (0.6, 0.5, 0.4, 1)
        _HemDark ("Hem darkening", Range(0, 1)) = 0.18
        _Smoothness ("Smoothness", Range(0, 1)) = 0.15
        _Hide ("Hidden regions (bit mask)", Float) = 0
        _Triplanar ("3D pattern (0/1)", Float) = 0
        _TriTile ("3D pattern tile (m)", Float) = 0.24
        _Metal ("Iron (studs)", Color) = (0.68, 0.68, 0.7, 1)
        _MetalSmoothness ("Iron smoothness", Range(0, 1)) = 0.6
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

            TEXTURE2D(_Pattern); SAMPLER(sampler_Pattern);
            CBUFFER_START(UnityPerMaterial)
                float4 _Pattern_ST;
                half4 _Color, _Metal;
                half _MetalSmoothness;
                half _HemDark, _Smoothness;
                float _Hide, _Triplanar, _TriTile;
            CBUFFER_END

            half4 frag(HVaryings i, bool front : SV_IsFrontFace) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                i.normalWS = front ? i.normalWS : -i.normalWS;
                clip(0.5 - fmod(floor(_Hide / exp2(round(i.uv.z))), 2.0));
                half3 pat = SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, i.uv.xy * _Pattern_ST.xy + _Pattern_ST.zw).rgb;
                float3 rp = i.cap.xyz;
                float3 rn = cross(ddx(rp), ddy(rp));
                float rl = length(rn);
                float3 tw = rl > 1e-12 ? pow(abs(rn / rl), 6) : float3(0, 0, 1);
                tw /= max(tw.x + tw.y + tw.z, 1e-5);
                float3 q = rp / _TriTile;
                half3 tri = SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.yz).rgb * tw.x
                          + SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.xz).rgb * tw.y
                          + SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.xy).rgb * tw.z;
                pat = lerp(pat, tri, step(0.5, _Triplanar) * (1 - step(0.5, i.cap.w)));
                half3 col = _Color.rgb * pat;
                col *= lerp(0.5, 1.0, i.color.r);
                col *= 1.0 - _HemDark * i.color.g;
                col = lerp(col, _Metal.rgb * lerp(0.5, 1.0, i.color.r), i.color.b);
                return HumanShade(i, col, lerp(_Smoothness, _MetalSmoothness, i.color.b));
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
