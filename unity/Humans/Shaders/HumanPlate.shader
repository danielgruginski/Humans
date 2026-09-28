// Plate armour (same maths as hum_material.plate_material in Blender). Vertex colour "ClothData":
//   r = AO, g = polish (rolled edges, rivets: brighter, smoother), b = LOD detail flag, a = material
//   (1 steel, 0.5 trim, 0 leather strap).
//   steel = _Color * pattern(rest position, triplanar) , metallic, smoothness lerp(_Smoothness, _PolishSmoothness, polish)
//   trim  = _Trim (brass), metallic;   strap = _Strap (leather), not metallic
// The pattern (hammer marks, brushing) is projected in 3D from each vertex's rest position (uv2, uv3.x), so
// it is the same scale on every plate and sticks to the plate when animated.
// Double-sided (open plates are seen from inside); region clip like Humans/Cloth.
// Ornament (uv4.x = weight, 0 outside each plate's panel; uv4.y = pattern, a slice of the _Ornament array): a
// tiling filigree mask in the plate's
// own UVs, inlaid in _Inlay (gold) and raised by a screen-space bump from the mask (_OrnRelief metres).
Shader "Humans/Plate"
{
    Properties
    {
        _Pattern ("Hammered steel (grey, tiling)", 2D) = "white" {}
        _Color ("Steel tint", Color) = (0.56, 0.57, 0.6, 1)
        _TriTile ("Pattern tile (m)", Float) = 0.3
        _Smoothness ("Smoothness", Range(0, 1)) = 0.5
        _PolishSmoothness ("Polished edge smoothness", Range(0, 1)) = 0.82
        _Polish ("Polished edge brightening", Range(0, 1)) = 0.25
        _Trim ("Trim (brass)", Color) = (0.78, 0.6, 0.3, 1)
        _Strap ("Straps (leather)", Color) = (0.2, 0.12, 0.07, 1)
        _Hide ("Hidden regions (bit mask)", Float) = 0
        _Ornament ("Ornament masks (filigree, tiling; one slice per pattern)", 2DArray) = "" {}
        _OrnTile ("Ornament tiles per UV unit (0.25 m)", Float) = 2.5
        _OrnTiles ("Scale per pattern slice (0..3)", Vector) = (1, 0.5, 1, 1)
        _Inlay ("Inlay (gold)", Color) = (0.86, 0.64, 0.3, 1)
        _OrnRelief ("Ornament relief (m)", Float) = 0.0012
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
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BLENDING
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BOX_PROJECTION
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #pragma multi_compile_instancing

            #include "HumanCommon.hlsl"

            TEXTURE2D(_Pattern); SAMPLER(sampler_Pattern);
            TEXTURE2D_ARRAY(_Ornament); SAMPLER(sampler_Ornament);
            CBUFFER_START(UnityPerMaterial)
                float4 _Pattern_ST;
                half4 _Color, _Trim, _Strap, _Inlay;
                half _Smoothness, _PolishSmoothness, _Polish;
                float _Hide, _TriTile, _OrnTile, _OrnRelief;
                float4 _OrnTiles;
            CBUFFER_END

            half4 frag(HVaryings i, bool front : SV_IsFrontFace) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                i.normalWS = front ? i.normalWS : -i.normalWS;
                clip(0.5 - fmod(floor(_Hide / exp2(round(i.uv.z))), 2.0));
                float3 rp = i.cap.xyz;
                float3 rn = cross(ddx(rp), ddy(rp));
                float rl = length(rn);
                float3 tw = rl > 1e-12 ? pow(abs(rn / rl), 6) : float3(0, 0, 1);
                tw /= max(tw.x + tw.y + tw.z, 1e-5);
                float3 q = rp / _TriTile;
                half pat = SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.yz).r * tw.x
                         + SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.xz).r * tw.y
                         + SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.xy).r * tw.z;
                half ao = i.color.r, polish = i.color.g, kind = i.color.a;
                // ornament: height from the filigree mask, bumped in screen space (Mikkelsen surface gradient)
                // uv4.y = pattern slice + 10 * mode (0 gold inlay, 1 etched: bright lines on a darkened ground)
                float ormode = floor(i.orn.y / 10 + 0.01);
                float oslice = round(i.orn.y - 10 * ormode);
                float stile = _OrnTiles[(uint)clamp(oslice, 0, 3)];     // each pattern at its own scale
                float hraw = SAMPLE_TEXTURE2D_ARRAY(_Ornament, sampler_Ornament, i.uv.xy * _OrnTile * stile, oslice).r;
                float h = hraw * saturate(i.orn.x);
                float3 N = normalize(i.normalWS);
                float3 dpdx = ddx(i.positionWS), dpdy = ddy(i.positionWS);
                float3 r1 = cross(dpdy, N), r2 = cross(N, dpdx);
                float det = dot(dpdx, r1);
                float3 grad = sign(det) * (ddx(h) * r1 + ddy(h) * r2) * _OrnRelief;
                float3 Nb = abs(det) * N - grad;
                i.normalWS = dot(Nb, Nb) > 1e-20 ? normalize(Nb) : N;
                half inlay = smoothstep(0.35, 0.65, h) * (1 - ormode);
                half etch = saturate(i.orn.x) * ormode;             // etched: the ground darkens, lines stay bright
                half trim = step(0.25, kind) * step(kind, 0.75);
                half strap = step(kind, 0.25);
                half3 steel = _Color.rgb * pat;
                steel = lerp(steel, saturate(steel * 1.3 + 0.04), polish * _Polish);
                steel = lerp(steel, _Inlay.rgb * lerp(0.8, 1.0, pat), inlay);
                steel *= lerp(1.0, lerp(0.55, 1.1, smoothstep(0.25, 0.6, hraw)), etch);
                half3 col = lerp(steel, _Trim.rgb * lerp(0.85, 1.0, pat), trim);
                col = lerp(col, _Strap.rgb * lerp(0.8, 1.0, pat), strap);
                half metallic = 1 - strap;
                half smooth = lerp(_Smoothness * lerp(0.85, 1.0, pat), _PolishSmoothness, max(polish, inlay * 0.6));
                smooth = lerp(smooth, 0.3, strap);
                return HumanShadePBR(i, col, metallic, smooth, lerp(0.35, 1.0, ao));
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
