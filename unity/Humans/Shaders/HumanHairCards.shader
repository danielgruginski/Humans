// Strand-card hair (the hair spike, 2026-10-29; Blender side hum_cards.py): cards carrying a strand atlas instead of
// solid clumps, lit as hair - a soft wrapped diffuse plus two highlights along the strands (Kajiya-Kay: the primary
// white and shifted toward the tips, the secondary tinted by the hair and broken up per strand).
//   atlas _Cards (linear): r shade, g strand id, a coverage (cut at _Cutoff)
//   uv0 atlas UVs (cards) / tiling strand UVs (cap), uv1 Clump (x id, y root -> tip), uv2 CapCut (x height above a cap's
//   rim, y ombre), uv3 HoodCut (x > 0 under a hood; y on the cap: across the parting, in its half widths), uv4 Guide
//   (x the card row's strand-sim particle, -1 = the cap, -2 = a card left out of the sim, -3 = one that is a curl's coil;
//   y on the cap: how far its border dissolves)
//   the cap shell (guide < 0) is opaque on the old tiling _Strands texture, so no skin shows between the cards
//   c = lerp(root, tip, smoothstep(0.25, 1, o) * ombre); c = lerp(c, streak, id < streaks); c *= shade * root shadow
// Simulated (HumanHairSim, _HairSimOn): _HairSim holds per particle its target, its position and the rotation between
// them (3 float4s); a vertex is carried by its row's particle: p' = pos + rot(p - target), its normal and strand
// direction rotated alike. Every pass does it, so shadows and depth follow the swinging hair.
// The strand direction is the mesh's bitangent (Mikktspace tangents from uv0: +v runs root -> tip on a card).
Shader "Humans/HairCards"
{
    Properties
    {
        _Cards ("Strand atlas", 2D) = "white" {}
        _Strands ("Cap strands", 2D) = "white" {}
        _HairRoot ("Root", Color) = (0.23, 0.15, 0.09, 1)
        _HairTip ("Tip", Color) = (0.23, 0.15, 0.09, 1)
        _HairStreak ("Streak", Color) = (0.6, 0.1, 0.1, 1)
        _Streaks ("Streak fraction", Range(0, 1)) = 0
        _Ombre ("Ombre", Range(0, 1)) = 0
        _Cutoff ("Coverage cut", Range(0.05, 0.95)) = 0.5
        _Wrap ("Diffuse wrap", Range(0, 1)) = 0.35
        _RootShadow ("Root shadow", Range(0, 1)) = 0.35
        _Spec1 ("Primary highlight", Range(0, 2)) = 0.06
        _Spec1Tint ("Primary tint (hair colour)", Range(0, 1)) = 0.9
        _Exp1 ("Primary exponent", Range(4, 600)) = 300
        _Shift1 ("Primary shift", Range(-1, 1)) = -0.08
        _Spec2 ("Secondary highlight", Range(0, 2)) = 0.25
        _Exp2 ("Secondary exponent", Range(4, 400)) = 28
        _Shift2 ("Secondary shift", Range(-1, 1)) = 0.15
        _ShiftJitter ("Shift per strand", Range(0, 1)) = 0.6
        _CapShade ("Cap shell shade (under the cards)", Range(0, 1)) = 0.6
        _CapCut ("Cap cut (0 = no cap)", Float) = 0
        _HoodCut ("Under a hood (0/1)", Float) = 0
    }

    HLSLINCLUDE
    #include "HumanCommon.hlsl"

    TEXTURE2D(_Cards); SAMPLER(sampler_Cards);
    TEXTURE2D(_Strands); SAMPLER(sampler_Strands);
    CBUFFER_START(UnityPerMaterial)
        float4 _Cards_ST, _Strands_ST;
        half4 _HairRoot, _HairTip, _HairStreak;
        half _Streaks, _Ombre, _Cutoff, _Wrap, _RootShadow;
        half _Spec1, _Spec1Tint, _Exp1, _Shift1, _Spec2, _Exp2, _Shift2, _ShiftJitter, _CapShade;
        float _CapCut, _HoodCut;
    CBUFFER_END

    StructuredBuffer<float4> _HairSim;      // 3 a particle: target (world), position (world), rotation (quaternion)
    float _HairSimOn;

    struct HCAttributes
    {
        float4 positionOS : POSITION;
        float3 normalOS   : NORMAL;
        float4 tangentOS  : TANGENT;
        float2 uv0        : TEXCOORD0;
        float2 uv1        : TEXCOORD1;
        float2 uv2        : TEXCOORD2;
        float2 uv3        : TEXCOORD3;
        float2 uv4        : TEXCOORD4;
        UNITY_VERTEX_INPUT_INSTANCE_ID
    };

    struct HCVaryings
    {
        float4 positionCS : SV_POSITION;
        float3 positionWS : TEXCOORD0;
        half3  normalWS   : TEXCOORD1;
        half3  strandWS   : TEXCOORD2;
        float4 uv         : TEXCOORD3;   // xy uv0, zw uv1 (id, root -> tip)
        float4 cap        : TEXCOORD4;   // CapCut.xy, HoodCut.x, 1 = the cap shell
        half   fogFactor  : TEXCOORD5;
        half2  capx       : TEXCOORD6;   // the cap shell: x how far its border dissolves (Guide.y: 1 on it .. 0 inside; a
                                         // card: 1 = a curl's coil),
                                         // y its signed distance across the parting in half widths (HoodCut.y)
        UNITY_VERTEX_INPUT_INSTANCE_ID
        UNITY_VERTEX_OUTPUT_STEREO
    };

    float3 QRot(float4 q, float3 v)
    {
        float3 t = 2.0 * cross(q.xyz, v);
        return v + q.w * t + cross(q.xyz, t);
    }

    // world position, normal and strand direction, carried by the strand sim when it runs
    void HairWorld(HCAttributes v, out float3 p, out float3 n, out float3 s)
    {
        VertexNormalInputs ni = GetVertexNormalInputs(v.normalOS, v.tangentOS);
        p = TransformObjectToWorld(v.positionOS.xyz);
        n = ni.normalWS;
        s = ni.bitangentWS;
        UNITY_BRANCH if (_HairSimOn > 0.5 && v.uv4.x > -0.5)
        {
            uint k = (uint)(v.uv4.x + 0.5) * 3;
            float3 t = _HairSim[k].xyz;
            float3 x = _HairSim[k + 1].xyz;
            float4 q = _HairSim[k + 2];
            p = x + QRot(q, p - t);
            n = QRot(q, n);
            s = QRot(q, s);
        }
    }

    HCVaryings HairVert(HCAttributes v)
    {
        HCVaryings o = (HCVaryings)0;
        UNITY_SETUP_INSTANCE_ID(v);
        UNITY_TRANSFER_INSTANCE_ID(v, o);
        UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
        float3 p, n, s;
        HairWorld(v, p, n, s);
        o.positionWS = p;
        o.positionCS = TransformWorldToHClip(p);
        o.normalWS = n;
        o.strandWS = s;
        o.uv = float4(v.uv0, v.uv1);
        bool shell = v.uv4.x < -0.5 && v.uv4.x > -1.5;     // -1: the cap; -2, -3: cards that aren't simulated (a bun, a curl)
        o.cap = float4(v.uv2, v.uv3.x, shell ? 1.0 : 0.0);
        // (x on a card: 1 a curl, -1 a card standing off the head - a bun's, a crest's - lit from whichever side shows)
        o.capx = shell ? half2(v.uv4.y, v.uv3.y) : half2(v.uv4.x < -2.5 ? 1.0 : v.uv4.x < -1.5 ? -1.0 : 0.0, 99.0);
        o.fogFactor = ComputeFogFactor(o.positionCS.z);
        return o;
    }

    // the atlas texel (the cap: opaque, its tiling strands); discards what a cap, a hood or the coverage cut hides
    half4 HairTexel(HCVaryings i, bool parting = true)
    {
        if (_CapCut > 0 && i.cap.x > _CapCut) discard;
        if (_HoodCut > 0.5 && i.cap.z > 0) discard;
        half4 a;
        UNITY_BRANCH if (i.cap.w > 0.5)
        {
            half r = SAMPLE_TEXTURE2D(_Strands, sampler_Strands, i.uv.xy * _Strands_ST.xy + _Strands_ST.zw).r;
            // the shell's border thins out along its own strands into the skin (its hard edge read as a wig line)
            clip(r * 0.6 + (1.0 - i.capx.x) * 1.3 - 0.75);
            // the parting: the scalp shows through a line down the middle, its edge ragged along the strands. Not in
            // the shadow pass: the shell still shades the scalp there (lit, the line read as a bright painted stripe)
            if (parting) clip(abs(i.capx.y) - 1.0 + (r - 0.5) * 0.5);
            a = half4(r, 0.5, 0.5, 1);
        }
        else
            a = SAMPLE_TEXTURE2D(_Cards, sampler_Cards, i.uv.xy * _Cards_ST.xy + _Cards_ST.zw);
        clip(a.a - _Cutoff);
        return a;
    }
    ENDHLSL

    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "TransparentCutout" "Queue" = "AlphaTest" }

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            Cull Off
            HLSLPROGRAM
            #pragma target 4.5
            #pragma vertex HairVert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile _ _LIGHT_LAYERS
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            half StrandSpec(float3 t, float3 h, half e)
            {
                half th = dot(t, h);
                return smoothstep(-1.0, 0.0, th) * pow(sqrt(saturate(1.0 - th * th)), e);
            }

            half4 frag(HCVaryings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                half4 a = HairTexel(i);
                // a card stands for a layer of hair: both its faces are lit with its outward normal (off the head).
                // Flipped on the back face, the far side's cards showing over the crown faced away from the light and
                // read as a halo of dark wires
                float3 n = normalize(i.normalWS);
                float3 v = GetWorldSpaceNormalizeViewDir(i.positionWS);
                half px = distance(_WorldSpaceCameraPos, i.positionWS) * 2.0
                        / (abs(UNITY_MATRIX_P._m11) * _ScreenParams.y);         // a pixel's width there, m
                // a curl's coil lit by its own normal (out from its path) is half dark sides. Close up they are its
                // roundness; once a pixel holds a curl's worth (under 1 mm of hair .. 3 mm), each is a dark speck, and light
                // hair went grainy. There its cards face the viewer and wrap the light: the curl's average, not one side
                if (i.capx.x < -0.5 && i.cap.w < 0.5 && dot(n, v) < 0.0) n = -n;
                half curlFar = saturate(i.capx.x) * (1.0 - i.cap.w) * smoothstep(0.001, 0.003, px);
                n = normalize(lerp(n, dot(n, v) < 0.0 ? -n : n, curlFar) + v * 0.5 * curlFar);
                half wrapAmt = lerp(_Wrap, 1.0, curlFar);
                half t = i.uv.w;
                half id = i.uv.z;
                half3 col = lerp(_HairRoot.rgb, _HairTip.rgb, smoothstep(0.25, 1.0, i.cap.y) * _Ombre);
                col = lerp(col, _HairStreak.rgb, 1.0 - step(_Streaks, id));
                half3 hue = col / max(max(col.r, col.g), max(col.b, 1e-3));   // the hair's colour at full brightness
                // dark hair is seen by its shine: the primary stronger and whiter the darker the hair (at the brown
                // tuning the black looked matte). Linear: a mid brown is ~0.06, black ~0.001
                half dark = 1.0 - saturate(dot(col, half3(0.3, 0.59, 0.11)) / 0.02);
                half spec1 = _Spec1 * (1.0 + 0.8 * dark);   // (2.5x on black: its front locks went grey)
                half tint1 = _Spec1Tint * (1.0 - 0.5 * dark);
                col *= a.r * lerp(0.9, 1.1, a.g);
                half ao = lerp(1.0 - _RootShadow, 1.0, smoothstep(0.0, 0.3, abs(t)));    // (a shell's t can be < 0)
                // the shell lies under the cards: it reads as depth (uv1.y past 1 on a shell lightens it: short hair,
                // where more of it shows - at full _CapShade a crop's whorl read as a dark disc)
                half shell = lerp(_CapShade, 1.0, saturate(t - 1.0));
                // below 0 it darkens it - curls, between which only shadow shows - while a pixel is under 1 mm of
                // hair; at 3 mm it is lit as the hair's mass (from the game camera the dark gaps took over: blonde
                // curls read as a dark head with blonde specks)
                if (t < 0.0) shell = lerp(_CapShade * (1.0 + t), 1.0, smoothstep(0.001, 0.003, px));
                ao *= lerp(1.0, shell, i.cap.w);
                col *= ao;

                // diffuse only (ambient, every light, shadows, SSAO): the shine is the strand highlights below. The
                // shared PBR path's reflection (a flat card's Fresnel, strongest at grazing) turned the underside and
                // the crown's edge silver-grey
                InputData d = (InputData)0;
                d.positionWS = i.positionWS;
                d.positionCS = i.positionCS;
                d.normalWS = n;
                d.viewDirectionWS = v;
                d.shadowCoord = TransformWorldToShadowCoord(i.positionWS);
                d.fogCoord = InitializeInputDataFog(float4(i.positionWS, 1.0), i.fogFactor);
                d.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(i.positionCS);
                d.bakedGI = SampleSH(n);
                d.shadowMask = half4(1, 1, 1, 1);
                SurfaceData sd = (SurfaceData)0;
                sd.albedo = col;
                sd.occlusion = ao;
                sd.alpha = 1;
                half4 c = UniversalFragmentBlinnPhong(d, sd);

                Light L = GetMainLight(TransformWorldToShadowCoord(i.positionWS), i.positionWS, half4(1, 1, 1, 1));
                half ndl = dot(n, L.direction);
                half wrap = saturate((ndl + wrapAmt) / (1.0 + wrapAmt)) - saturate(ndl);   // light past the terminator
                half lit = L.distanceAttenuation * L.shadowAttenuation;
                c.rgb += col * L.color * wrap * lit;
                float3 s = normalize(i.strandWS);
                float3 hv = normalize(L.direction + v);
                half j = (a.g - 0.5) * _ShiftJitter;
                half s1 = StrandSpec(normalize(s + n * (_Shift1 + j)), hv, _Exp1);
                half s2 = StrandSpec(normalize(s + n * (_Shift2 + j)), hv, _Exp2) * smoothstep(0.3, 0.7, a.g);
                // only the lit side of the hair shines, and the smooth shell under the cards barely (a highlight there
                // spread into blown-out patches)
                // deeper strands (the atlas's darker shade) shine less: straight hanging hair has the same strand
                // direction everywhere, and an even highlight over it read as silver sheets (from below above all).
                // The primary is narrow (_Exp1 300) and jittered per strand (0.6): a flat lock catches it in streaks,
                // not all over (black locks read grey). It is weak and tinted toward the hair's colour, the shine mostly
                // the hair-coloured secondary:
                // a whole lock of parallel strands (the front locks on the chest) catches the primary all over - white
                // it read lavender-grey on brown, at 0.14 still a pale beige ombre below the head's shadow
                half3 spec = (s1 * spec1 * lerp(1.0, hue, tint1) + s2 * _Spec2 * col * 2.5)
                           * smoothstep(-0.1, 0.5, ndl) * lit * ao * (1.0 - 0.8 * i.cap.w) * lerp(0.25, 1.0, a.r * a.r);
                // (a curl from afar: each coil's highlight is a bright speck, on black hair above all)
                c.rgb += spec * L.color * lerp(1.0, 0.25, curlFar);
                c.rgb = MixFog(c.rgb, d.fogCoord);
                return c;
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On ZTest LEqual ColorMask 0 Cull Off
            HLSLPROGRAM
            #pragma target 4.5
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW

            float3 _LightDirection;
            float3 _LightPosition;

            HCVaryings vert(HCAttributes v)
            {
                HCVaryings o = HairVert(v);
            #if _CASTING_PUNCTUAL_LIGHT_SHADOW
                float3 ld = normalize(_LightPosition - o.positionWS);
            #else
                float3 ld = _LightDirection;
            #endif
                float4 cs = TransformWorldToHClip(ApplyShadowBias(o.positionWS, o.normalWS, ld));
            #if UNITY_REVERSED_Z
                cs.z = min(cs.z, UNITY_NEAR_CLIP_VALUE);
            #else
                cs.z = max(cs.z, UNITY_NEAR_CLIP_VALUE);
            #endif
                o.positionCS = cs;
                return o;
            }

            half4 frag(HCVaryings i) : SV_Target
            {
                HairTexel(i, false);                         // hidden hair (under a cap or a hood) casts no shadow
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
            #pragma target 4.5
            #pragma vertex HairVert
            #pragma fragment frag
            #pragma multi_compile_instancing
            half frag(HCVaryings i) : SV_Target
            {
                HairTexel(i);
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
            #pragma target 4.5
            #pragma vertex HairVert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #pragma multi_compile_fragment _ _GBUFFER_NORMALS_OCT
            half4 frag(HCVaryings i, bool front : SV_IsFrontFace) : SV_Target
            {
                HairTexel(i);
                float3 n = normalize(front ? i.normalWS : -i.normalWS);
            #if defined(_GBUFFER_NORMALS_OCT)
                float2 oct = saturate(PackNormalOctQuadEncode(n) * 0.5 + 0.5);
                return half4(PackFloat2To888(oct), 0.0);
            #else
                return half4(n, 0.0);
            #endif
            }
            ENDHLSL
        }
    }
}
