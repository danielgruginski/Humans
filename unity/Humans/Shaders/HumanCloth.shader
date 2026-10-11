// Human garments (same maths as hum_material.cloth_material in Blender):
//   c = colour * pattern(uv) * lerp(0.5, 1, AO) * (1 - 0.18 * hem)      AO, hem = vertex colour r, g ("ClothData")
// One material per fabric (M_HumanCloth = weave, M_HumanLeather = grain); the colour is per renderer
// (MaterialPropertyBlock _Color, set by HumanFace).
//   c = lerp(c, _Metal * lerp(0.5, 1, AO), vertex colour b)                studs and buckles: iron
// _Triplanar (mail, the skeleton's bone): the pattern is projected in 3D from each vertex's rest position (uv2, uv3.x),
// so the rings are one size everywhere; trims (uv3.y = 1) keep their flat UV.
// Double-sided (open sheets like shoulder plates and hems seen from inside): back faces get flipped normals.
// Layering: uv1.x = body region under the face; bit (region) of _Hide set = covered by an outer garment.
// Torn (the undead, per renderer): _Tatter 0..1 over the tatter texture (R holes, G dirt, B fray), projected in 3D from
// the rest position like the mail: holes where R + fray < _Tatter * holes (hems tear first), a dark frayed rim, dirt;
// _TatterCut 1 cuts the holes out (a skeleton's rags: the bones show; the depth and shadow passes clip them too),
// 0 paints the skin (_Skin) in them, shadowed under the cloth's edge (a zombie). Same maths as hum_material._tatter.
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
        [NoScaleOffset] _TatterTex ("Tatter (holes, dirt, fray)", 2D) = "white" {}
        _Tatter ("Torn (undead)", Range(0, 1)) = 0
        _TatterCut ("Cut the holes (0/1)", Float) = 0
        _Skin ("Skin under the holes", Color) = (0.55, 0.6, 0.5, 1)
        _TatterTile ("Tatter tile (m)", Float) = 0.6
        _TatterHoles ("Hole area at torn 1", Float) = 0.17
        _TatterFray ("Fray", Float) = 0.22
        _TatterHem ("Hems tear first", Float) = 0.6
        _TatterRim ("Frayed rim", Float) = 0.035
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" "Queue" = "Geometry" }

        HLSLINCLUDE
        #include "HumanCommon.hlsl"

        TEXTURE2D(_Pattern); SAMPLER(sampler_Pattern);
        TEXTURE2D(_TatterTex); SAMPLER(sampler_TatterTex);
        CBUFFER_START(UnityPerMaterial)
            float4 _Pattern_ST;
            half4 _Color, _Metal, _Skin;
            half _MetalSmoothness;
            half _HemDark, _Smoothness;
            float _Hide, _Triplanar, _TriTile;
            half _Tatter, _TatterCut;
            float _TatterTile, _TatterHoles, _TatterFray, _TatterHem, _TatterRim;
        CBUFFER_END

        // blend weights of a 3D projection from the rest position's own surface (not the posed one)
        float3 RestWeights(float3 rp)
        {
            float3 rn = cross(ddx(rp), ddy(rp));
            float rl = length(rn);
            float3 tw = rl > 1e-12 ? pow(abs(rn / rl), 6) : float3(0, 0, 1);
            return tw / max(tw.x + tw.y + tw.z, 1e-5);
        }

        // d > 0 inside a hole (in hole-field units); dirt 0..1
        void Tatter(HVaryings i, float3 tw, out half d, out half dirt)
        {
            float3 q = i.cap.xyz / _TatterTile;
            half3 t = SAMPLE_TEXTURE2D(_TatterTex, sampler_TatterTex, q.yz).rgb * tw.x
                    + SAMPLE_TEXTURE2D(_TatterTex, sampler_TatterTex, q.xz).rgb * tw.y
                    + SAMPLE_TEXTURE2D(_TatterTex, sampler_TatterTex, q.xy).rgb * tw.z;
            half h = t.r + (t.b - 0.5) * _TatterFray - i.color.g * _TatterHem * _Tatter;
            d = _Tatter > 0 ? _Tatter * _TatterHoles * (1 + _TatterCut) - h : -1;
            dirt = smoothstep(0.3, 0.9, t.g);
        }

        // regions an outer layer covers, and a skeleton's rags' holes
        void ClothClip(HVaryings i)
        {
            clip(0.5 - fmod(floor(_Hide / exp2(round(i.uv.z))), 2.0));
            if (_TatterCut > 0.5 && _Tatter > 0)
            {
                half d, dirt;
                Tatter(i, RestWeights(i.cap.xyz), d, dirt);
                clip(-d);
            }
        }
        ENDHLSL

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

            half4 frag(HVaryings i, bool front : SV_IsFrontFace) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                i.normalWS = front ? i.normalWS : -i.normalWS;
                clip(0.5 - fmod(floor(_Hide / exp2(round(i.uv.z))), 2.0));
                half3 pat = SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, i.uv.xy * _Pattern_ST.xy + _Pattern_ST.zw).rgb;
                float3 rp = i.cap.xyz;
                float3 tw = RestWeights(rp);
                float3 q = rp / _TriTile;
                half3 tri = SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.yz).rgb * tw.x
                          + SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.xz).rgb * tw.y
                          + SAMPLE_TEXTURE2D(_Pattern, sampler_Pattern, q.xy).rgb * tw.z;
                pat = lerp(pat, tri, step(0.5, _Triplanar) * (1 - step(0.5, i.cap.w)));
                half3 col = _Color.rgb * pat;
                col *= lerp(0.5, 1.0, i.color.r);
                col *= 1.0 - _HemDark * i.color.g;
                col = lerp(col, _Metal.rgb * lerp(0.5, 1.0, i.color.r), i.color.b);
                half smooth = lerp(_Smoothness, _MetalSmoothness, i.color.b);
                // torn and dirty (the undead)
                half d = -1, dirt = 0;
                UNITY_BRANCH if (_Tatter > 0) Tatter(i, tw, d, dirt);   // a uniform: the living skip the taps
                half on = step(0.001, _Tatter);
                half hole = step(0, d) * on;
                clip(0.5 - hole * _TatterCut);
                half rim = step(-_TatterRim, d) * (1 - hole) * on;
                col = lerp(col, col * half3(0.5, 0.45, 0.36), dirt * _Tatter * 0.9);
                col *= 1 - 0.55 * rim;
                half3 skin = _Skin.rgb * lerp(0.2, 0.6, smoothstep(0, 0.1, d));
                col = lerp(col, skin, hole);
                smooth = lerp(smooth, 0.3, hole);
                return HumanShade(i, col, smooth);
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On ZTest LEqual ColorMask 0 Cull Off
            HLSLPROGRAM
            #pragma vertex ShadowVert
            #pragma fragment ShadowFrag
            #pragma multi_compile_instancing
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            float3 _LightDirection;
            float3 _LightPosition;

            HVaryings ShadowVert(HAttributes v)
            {
                HVaryings o = HumanVert(v);
            #if _CASTING_PUNCTUAL_LIGHT_SHADOW
                float3 l = normalize(_LightPosition - o.positionWS);
            #else
                float3 l = _LightDirection;
            #endif
                o.positionCS = ApplyShadowClamping(TransformWorldToHClip(ApplyShadowBias(o.positionWS, o.normalWS, l)));
                return o;
            }

            half4 ShadowFrag(HVaryings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                ClothClip(i);
                return 0;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On ColorMask R Cull Off
            HLSLPROGRAM
            #pragma vertex HumanVert
            #pragma fragment DepthFrag
            #pragma multi_compile_instancing

            half DepthFrag(HVaryings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                ClothClip(i);
                return i.positionCS.z;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On Cull Off
            HLSLPROGRAM
            #pragma vertex HumanVert
            #pragma fragment DepthNormalsFrag
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"

            void DepthNormalsFrag(HVaryings i, bool front : SV_IsFrontFace, out half4 outNormalWS : SV_Target0
            #ifdef _WRITE_RENDERING_LAYERS
                , out uint outRenderingLayers : SV_Target1
            #endif
            )
            {
                UNITY_SETUP_INSTANCE_ID(i);
                ClothClip(i);
                float3 n = NormalizeNormalPerPixel(front ? i.normalWS : -i.normalWS);
                outNormalWS = half4(n, 0.0);
            #ifdef _WRITE_RENDERING_LAYERS
                outRenderingLayers = EncodeMeshRenderingLayer();
            #endif
            }
            ENDHLSL
        }
    }
}
