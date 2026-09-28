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

#endif
