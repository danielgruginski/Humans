// Shared forward pass for the human skin, eye and hair shaders (URP 17, Forward+).
// Each shader defines its UnityPerMaterial CBUFFER and a fragment that computes albedo/smoothness,
// then calls HumanShade().
#ifndef HUMAN_COMMON_INCLUDED
#define HUMAN_COMMON_INCLUDED

#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

struct HAttributes
{
    float4 positionOS : POSITION;
    float3 normalOS   : NORMAL;
    float2 uv0        : TEXCOORD0;   // head: mask UVs; hair: strand texture UVs
    float2 uv1        : TEXCOORD1;   // hair "Clump" UVs: x = clump id, y = root -> tip
    float2 uv2        : TEXCOORD2;   // hair "CapCut": x = height above a cap's rim, y = ombre (0 top .. 1 lowest ends)
    float2 uv3        : TEXCOORD3;   // hair "HoodCut": x > 0 = under a cloak's hood
    float2 uv4        : TEXCOORD4;   // plate "Ornament": x = etched/inlaid ornament weight
                                     // cloth: uv2 = rest position xy, uv3 = (rest z, 1 = flat trim)
    half4  color      : COLOR;       // hair "HairData": r = clump edge
    UNITY_VERTEX_INPUT_INSTANCE_ID
};

struct HVaryings
{
    float4 positionCS : SV_POSITION;
    float3 positionWS : TEXCOORD0;
    half3  normalWS   : TEXCOORD1;
    float4 uv         : TEXCOORD2;   // xy = uv0, zw = uv1
    half4  color      : TEXCOORD3;
    half   fogFactor  : TEXCOORD4;
    float4 cap        : TEXCOORD5;   // hair: CapCut.xy, HoodCut.x; cloth: rest position, trim flag
    float2 orn        : TEXCOORD6;   // plate: ornament weight
    UNITY_VERTEX_INPUT_INSTANCE_ID
    UNITY_VERTEX_OUTPUT_STEREO
};

HVaryings HumanVert(HAttributes v)
{
    HVaryings o = (HVaryings)0;
    UNITY_SETUP_INSTANCE_ID(v);
    UNITY_TRANSFER_INSTANCE_ID(v, o);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
    VertexPositionInputs p = GetVertexPositionInputs(v.positionOS.xyz);
    VertexNormalInputs n = GetVertexNormalInputs(v.normalOS);
    o.positionCS = p.positionCS;
    o.positionWS = p.positionWS;
    o.normalWS = n.normalWS;
    o.uv = float4(v.uv0, v.uv1);
    o.color = v.color;
    o.cap = float4(v.uv2, v.uv3);
    o.orn = v.uv4;
    o.fogFactor = ComputeFogFactor(p.positionCS.z);
    return o;
}

// The undead's rot (hum_undead, hum_material._rot in Blender): rot mask R blotches, G and B the two wound sets,
// A hollows; rot 0 (the living) leaves the colour alone. wet: how much of a wound is there (glossier).
static const half3 ROT_TINT = half3(0.55, 0.50, 0.52);
static const half ROT_HOLLOW = 0.6;
static const half3 WOUND_RIM = half3(0.30, 0.10, 0.08);
static const half3 WOUND_CORE = half3(0.06, 0.012, 0.01);

half3 HumanRot(half3 col, half4 r, half rot, half2 wounds, out half wet)
{
    col = lerp(col, col * ROT_TINT, r.r * rot);
    col *= 1 - ROT_HOLLOW * r.a * rot;
    half w = max(r.g * wounds.x, r.b * wounds.y) * step(0.001, rot);
    wet = smoothstep(0.12, 0.45, w);
    col = lerp(col, WOUND_RIM, wet);
    col = lerp(col, WOUND_CORE, smoothstep(0.5, 0.85, w));
    return col;
}

half4 HumanShadePBR(HVaryings i, half3 albedo, half metallic, half smoothness, half occlusion);

half4 HumanShade(HVaryings i, half3 albedo, half smoothness)
{
    return HumanShadePBR(i, albedo, 0, smoothness, 1);
}

// Metallic PBR (plate armour); HumanShade is the non-metal case.
half4 HumanShadePBR(HVaryings i, half3 albedo, half metallic, half smoothness, half occlusion)
{
    InputData d = (InputData)0;
    d.positionWS = i.positionWS;
    d.positionCS = i.positionCS;
    d.normalWS = NormalizeNormalPerPixel(i.normalWS);
    d.viewDirectionWS = GetWorldSpaceNormalizeViewDir(i.positionWS);
    d.shadowCoord = TransformWorldToShadowCoord(i.positionWS);
    d.fogCoord = InitializeInputDataFog(float4(i.positionWS, 1.0), i.fogFactor);
    d.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(i.positionCS);
    d.bakedGI = SampleSH(d.normalWS);
    d.shadowMask = half4(1, 1, 1, 1);

    SurfaceData s = (SurfaceData)0;
    s.albedo = albedo;
    s.metallic = metallic;
    s.smoothness = smoothness;
    s.occlusion = occlusion;
    s.alpha = 1;

    half4 c = UniversalFragmentPBR(d, s);
    c.rgb = MixFog(c.rgb, d.fogCoord);
    return c;
}


// Skin (2026-10-18, after "they look like plastic figurines"): a matte, weakly reflective surface with a little light
// scattered past the shadow edge. Needs _SPECULAR_SETUP defined before this file (Humans/Skin, Humans/Body):
//   - specular = the reflectance at normal incidence (skin ~0.028; lower = less glare), taken as is, so the grazing
//     rim and the environment reflection scale with it, not with a fixed 0.04;
//   - smoothness broken up a little across the surface (value noise in UV space, so it stays on the body as it moves):
//     a perfectly even sheen is what reads as a moulded figure;
//   - scatter: the main light wrapped past the terminator in a warm tint (a cheap stand-in for subsurface light).
static const half SKIN_WRAP = 0.5;
static const half3 SKIN_SCATTER_TINT = half3(1.0, 0.42, 0.30);

half HumanNoise(float2 p)
{
    float2 c = floor(p), f = frac(p);
    f = f * f * (3.0 - 2.0 * f);
    #define HN_HASH(q) frac(sin(dot(q, float2(127.1, 311.7))) * 43758.5453)
    half n = lerp(lerp(HN_HASH(c), HN_HASH(c + float2(1, 0)), f.x), lerp(HN_HASH(c + float2(0, 1)), HN_HASH(c + float2(1, 1)), f.x), f.y);
    #undef HN_HASH
    return n;
}

half4 HumanShadeSkin(HVaryings i, half3 albedo, half smoothness, half specular, half scatter, half breakup)
{
    InputData d = (InputData)0;
    d.positionWS = i.positionWS;
    d.positionCS = i.positionCS;
    d.normalWS = NormalizeNormalPerPixel(i.normalWS);
    d.viewDirectionWS = GetWorldSpaceNormalizeViewDir(i.positionWS);
    d.shadowCoord = TransformWorldToShadowCoord(i.positionWS);
    d.fogCoord = InitializeInputDataFog(float4(i.positionWS, 1.0), i.fogFactor);
    d.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(i.positionCS);
    d.bakedGI = SampleSH(d.normalWS);
    d.shadowMask = half4(1, 1, 1, 1);

    half n = HumanNoise(i.uv.xy * 160.0) * 0.6 + HumanNoise(i.uv.xy * 47.0) * 0.4;
    SurfaceData s = (SurfaceData)0;
    s.albedo = albedo;
    s.specular = specular.xxx;
    s.smoothness = saturate(smoothness + (n - 0.5) * breakup);
    s.occlusion = 1;
    s.alpha = 1;
    half4 c = UniversalFragmentPBR(d, s);

    Light L = GetMainLight(d.shadowCoord, d.positionWS, d.shadowMask);
    half ndl = dot(d.normalWS, L.direction);
    half wrap = saturate((ndl + SKIN_WRAP) / (1.0 + SKIN_WRAP)) - saturate(ndl);
    half lit = L.distanceAttenuation * lerp(1.0, L.shadowAttenuation, 0.5);   // the band lies where the body shades itself
    c.rgb += albedo * SKIN_SCATTER_TINT * L.color * (wrap * lit * scatter);
    c.rgb = MixFog(c.rgb, d.fogCoord);
    return c;
}

#endif
