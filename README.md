# Humans

Faces for the human characters: one stylised head with face sliders as shape keys, painted as masks
that a skin shader colours per character, plus hairstyles, beards and eyebrows as solid stylised clumps
that carry the same shape keys (so they fit every face) and support multi-colour hair.

Built on **MPFB 2.0.17** (MakeHuman for Blender, from extensions.blender.org). MPFB's base mesh and
targets are CC0, so the exported heads can ship. The add-on code itself is GPL, but we only use its output.

Blender file: `blender/humans.blend`, scene **Faces** (cameras `Cam_Front`, `Cam_34`, `Cam_Side`).
The MPFB source human is hidden in the `HUM_Work` collection.

## Rebuild

```python
import sys; sys.path.insert(0, r"E:\Unity\Projects\GameArtGeneration\Humans\src")
import hum_build
hum_build.show()          # Faces scene on screen (own call)
hum_build.build_all()     # head + eyes + UVs + masks + materials + 98 shape keys + all hair (~17 s)
hum_build.build_hair()    # only the hair/beard/brow objects (~9 s)

import hum_export
hum_export.export_all()    # export/Human_Head.fbx, Human_Hair.fbx, human_face_config.json (+ Textures/)

import hum_faces
hum_faces.apply_face(bpy.data.objects["Head"], hum_faces.random_face(4))    # one random character
hum_faces.lineup(bpy.data.objects["Head"], range(1, 9), views=("Front", "34"))   # renders/lineup.png
hum_faces.slider_sheet(bpy.data.objects["Head"], ["EyeTilt", "NoseWidth"])      # -1 / 0 / +1 per slider
```

| Script | Does |
|---|---|
| `hum_mpfb.py` | Creates the MPFB source human; sets macros (gender, age, weight, muscle, race) and detail targets; reads back vertex positions |
| `hum_head.py` | Cuts the head at a neck edge loop; stylisation (`STYLE`: bigger eyes, smaller nose/mouth, rounder cranium); fits eyeballs to MPFB's eye helpers; anchors every state at the neck ring; builds the Head mesh |
| `hum_uv.py` | Seams (face island, ears, back of head, MPFB's small islands), minimum-stretch unwrap, face at 1.8x texel density, pack |
| `hum_paint.py` | Per-texel masks from baked positions/normals + vertex AO/cavity; eye mask |
| `hum_material.py` | Blender preview of the skin and eye shaders (per-character colours are object properties) |
| `hum_faces.py` | Slider list, macro keys, corrective keys, random face generator, lineup and slider sheets |
| `hum_scene.py` | Cameras, renders, contact sheets |
| `hum_rig.py` | MPFB game_engine skeleton rebuilt from its JSON (bone ends = joint-helper centroids, so they exist for any state), MPFB weights by source vertex, residual keys, pose preview, weight transfer to LODs |
| `hum_body.py` | Body = MPFB body minus the head faces (shares the neck ring), body masks (blush, painted shorts, chest band, shading, freckles) |
| `hum_cloth.py` | Villager garments: offset shells over the body (edge loops straightened), lofted skirts (convex envelope, flare, folds), footwear from convex section tubes + voxel remesh, body regions to hide, binding to the body keys, skinning, L1/L2 |
| `hum_armor.py` | Leather armour on the same machinery: Jerkin (torso shell with clean armholes/neckline, overlapping flared hip bands, lofted two-plate pauldrons), Bracers; round iron studs (metal flag, removed at L1/L2) |
| `hum_lod.py` | LOD1 (mid distance) and LOD2 (colony camera): decimated heads and coarser pieces (`hum_styles.lod_recipe`), all bound to the full head's keys; collections `HUM_LOD1`, `HUM_LOD2`; names end in `_L1`/`_L2` (not `_LOD`, which Unity's importer auto-detects) |
| `hum_export.py` | FBX export (-Z forward, Y up, FBX_SCALE_ALL, vertex colours linear) and the JSON config the C# generator reads |
| `hum_hair.py` | Grooming engine: hairline and beard regions, cap shell, clump growth (hugs the scalp, released below the hairline), tube meshes, `bind_keys` (Surface Deform -> the head's shape keys) |
| `hum_styles.py` | Recipes: `HAIR` (Buzz, Crop, Curly, Swept, SidePart, Long, Ponytail, Bun, Mohawk), `BEARD` (Short, Full, Goatee, ChinStrap, Mustache), `BROWS` (Normal, Thin, Bushy, Straight) |

## Head

- **Mesh:** MPFB head topology cut at the neck + two eyeballs: 4,766 verts, 9,480 tris (head 8.4k, eyes 1.1k).
  This is the close-up (portrait / zoom-in menu) version. An in-game version for the 40 m colony camera is still to do.
- **Shape keys (98):**
  - 45 face sliders. Two-sided ones are `<Name>_Pos` / `<Name>_Neg`: eyes, brows, nose, mouth, chin, cheeks,
    face shape, head, ears (incl. `EarPointed`), neck.
  - Macros: `Masculine`, `Feminine`, `Old`, `Young`, `Heavy`, `Thin`, `Muscular`, `Slight`, `AncAfrican`,
    `AncAsian`, `AncEuropean` (ancestry weights sum to 1; all zero = the even mix).
  - Correctives `X_A_B` (weight = w_A * w_B; for gender x ancestry, feminine counts as negative masculine).
- **Eyes** move with the sliders: they are refitted to MPFB's eye helper in every captured state.
- Every key is anchored at the neck ring. Body macros change height in MPFB; the skeleton will carry that,
  so the head keys only change shape.

## Textures (1024², `export/Textures`)

| Texture | R | G | B | A |
|---|---|---|---|---|
| `T_Head_MaskA` | blush zones | lips | shading (x1.25) | lash line + lid crease |
| `T_Head_MaskB` | stubble | age lines | freckles | brows |
| `T_Eye_Mask` (256²) | iris | pupil | iris darkening | sclera shade |

Skin colour (linear), per character: `tone`, `lip` (defaults to tone x (0.82, 0.56, 0.54)), `hair`, `lash`,
`blush`, `freckles`, `stubble`, `age`, `brows`; eyes: `iris`. The formula is in the `hum_material.py` docstring,
and the Unity shader must use the same one.

## Hair, beards, brows

Every style is its own object in the `HUM_Hair` collection (`Hair_<style>`, `Beard_<style>`,
`Brows_<style>`), built on the neutral head and then bound to it: each gets the head's shape keys that
move it (43-74 of the 98, same names). Keys that don't move a piece are left out, so look keys up by name.

- **Cap:** an offset shell of the skin inside the hairline/beard region. Its rim sinks 0.8 mm under the
  skin, so there is no visible edge. Buzz, Short beard and ChinStrap are cap only.
- **Clumps:** flattened tapered tubes, 6 sides (beards 5, brows 4). Roots are closed into the skin.
  Clumps hug the scalp until they pass below the hairline at the back; ponytail tails hang free below the chin.
- **Portrait budget:** hair 3.4k (Buzz) to 20k (Long) tris, beards 3.4k-16k, brows 1.3k-1.9k.
  Colony-camera versions still to do.

Hair shader (`hum_material.hair_material`, same maths needed in Unity). `Clump.y` = root->tip,
`Clump.x` = clump id (smoothly varying with position, uniformly distributed):

    c = lerp(root, tip, smoothstep(0.25, 1, t) * ombre)
    c = lerp(c, streak, id < streaks)                 # dyed streaks / two-tone (streaks = 0.5)
    c = c * strand.r * lerp(0.7, 1, smoothstep(0, 0.3, t))

Per-object properties: `hum_hair_root`, `hum_hair_tip`, `hum_hair_streak`, `hum_streaks`, `hum_ombre`
(`hum_material.set_hair_props`). The random generator picks looks: natural, sun-kissed tips, dyed ombre,
streaks, two-tone (`hum_faces.DYES`). Texture: `T_Hair_Strands` (256², tiles along the clump UVs).

## Hair details (after the iteration pass)

- Shading normals of clumps are 70% the head's normal: a hairdo lights as one mass. Clump sides are darkened by
  the shader through the vertex colour `HairData.r` (1 at a clump's side edges).
- Clumps collide with a copy of the head whose ears are smoothed into domes, but only for styles that cover the
  ears (`cover_ears`: Long, SidePart). Other styles collide with the real skin and end at the ear.
- Roots start on the real skin and are closed into it. Spines are smoothed after growing, and ring frames are
  smoothed along each clump (no twists).
- Beards: the lips are cut out with MPFB's lip group. Length is concentrated at the chin, cheeks are short, and
  under the jaw drifts toward the chin. `sideburns=True` adds a strip in front of the ear up to the hair
  (Full, Wizard, ChinStrap, ShortSideburns).
- Skin `T_Head_MaskC`: R = hairline band (the cap edge fades into the skin), G = beard area (shadow under
  beards). Neither reaches down the neck.

## Unity (MedievalSetting, `Assets/Humans`)

```
powershell -ExecutionPolicy Bypass -File tools\install_to_unity.ps1 -Project E:\Unity\Projects\MedievalSetting
```
then **Tools > Humans > Rebuild Prefab and Showcase** (renders go to `MedievalSetting/Logs/HumanSetup`).

- `Prefabs/Human.prefab`: `HumanFace` + Head (SkinnedMeshRenderer, 98 blend shapes, skin + eye submeshes) +
  Hair (20 pieces: `Hair_*`, `Beard_*`, `Brows_*`, one active per kind). The FBXs import as MeshRenderers
  (no rig), so the setup swaps them for bone-less SkinnedMeshRenderers.
- Shaders `Humans/Skin`, `Humans/Eye`, `Humans/Hair` (URP 17, Forward+): the same maths as the Blender preview.
  Per-character colours are sent with MaterialPropertyBlocks, so all humans share three materials. Eyes
  receive no shadows.
- `HumanFaceData`: creator values (sex, age, weight, muscle, ancestry, 45 sliders, styles, colours).
  `ToKeyWeights` turns them into blend-shape weights. `HumanFaceGenerator.Random(cfg, seed)` is the C# port of
  `random_face`, and reads the exported config.
- Scene `Scenes/Humans_Showcase`: a creator head with a test panel (`HumanCreatorUI`: reroll, body macros,
  styles, colours incl. multi-colour looks, all sliders; right-drag orbits, the wheel zooms) and a lineup
  of 10 random humans.
- Head import: normals and blend-shape normals calculated at 180 deg (60 deg creased nostrils and lids).
  Hair import: Blender's normals kept, no blend-shape normals.

## LODs

| | LOD0 (portrait) | LOD1 (mid) | LOD2 (colony camera) |
|---|---|---|---|
| Head (with eyes) | 9,480 | 1,894 | 662 |
| Hair | 3.0k-19k | 0.4k-2.8k | 0.2k-0.85k |
| Beard | 7k-25k | 0.46k-2k | 0.14k-0.34k (shell only) |
| Brows | 1.3k-1.9k | 0.5k-0.7k | none (painted brows at 0.8) |

Each LOD carries the face keys, so one `HumanFace` drives all three. In Unity the prefab holds containers
LOD0/LOD1/LOD2, each with a head and a Hair folder, under a LODGroup (transitions at 0.15, 0.04, 0.002 of screen height).

## Body and rig

- **Coordinates:** every captured state goes through `hum_head.full_coords`: MPFB, then face
  stylisation, then body stylisation (`BODY_STYLE`: body x0.92 below the shoulders about the neck, hands
  x1.12, feet x1.06), then feet on the ground. Head, body and joints all come from these same coords.
- **Skeleton:** MPFB `game_engine` (53 bones, Unreal-style names; Unity's Humanoid mapper takes them). No
  jaw or eye bones yet. The eyes and hair are rigid on `head`.
- **Keys are residuals:** key = MPFB shape - W * (bone deltas of that key). At runtime the bones move by
  sum(w_k * delta_k) (`human_rig.json`) and the blend shapes add the rest, so the shape is exact in the rest
  pose and the joints sit where MPFB puts them (knees and shoulders bend in the right place). Checked in
  Blender: bones + residual keys = MPFB shape with 0 error for single keys, sums and correctives.
- **Height** is not a key: it is a uniform scale of the whole character (height +1 = x1.206, -1 = x0.895,
  from MPFB's height 0.75/0.25), so Humanoid animation keeps the feet on the ground.
- **Hips:** a Humanoid Animator places the hips at the base avatar's height, so `HumanFace` lifts the model by
  the pelvis delta while animated (e.g. -5 cm for a feminine body).
- **Body sliders** (MPFB detail targets, same residual pipeline): ArmMuscle, ShoulderMuscle, LegMuscle,
  ChestMuscle, BackMuscle, VShape, ShoulderWidth, Waist, Hips, Bust, Belly (`hum_faces.BODY_SLIDERS`). They
  are no longer free: they, the sex/weight/muscle macros and NeckWidth are fixed per **body build** (below).
- **Body builds** (`hum_builds.py`): 3 per sex - Slim, Strong, Heavy (tags MSlim ... FHeavy; odds 0.4/0.3/0.3).
  A build sets `BODY_KEYS` on the body, skeleton and head; every other key (face sliders, age, ancestry and
  their correctives) is head-only, residual, and fades to zero at the head's neck edge (`neck_fade`), so any
  face meets any build's neck. Garments are built once per build as an exact fit (`BuildSpace`,
  `build_wardrobe`), stored at rest and named `Cloth_<Garment>_<Tag>`; no body keys on garments.
  Why: layered armour following ~90 keys through approximate bindings kept poking through.
  Config: `builds` (keys per build), `bodyKeys`. Unity: `HumanFaceData.build`, the creator's Sex + Build
  pickers, `HumanFace` shows only the face's build's garments.
- **Body:** 18.3k tris (L1 5.5k, L2 2.6k), 49 keys (macros, correctives, neck, body sliders). `T_Body_MaskA` (blush, shorts,
  shading, chest band) + `T_Body_MaskB` (freckles). Shader `Humans/Body`: tone, cloth colour, blush,
  freckles, chest band (feminine by default).

Unity: `Human_Body.fbx` (Humanoid, avatar from the model) carries HumanRig, Body*, Head*. Garments ship as one
FBX per outfit family (`Human_Cloth_Clothes|Leather|PaddedMail|Cloak|Plate|Gothic|Ornate|BlackKnight.fbx`,
`hum_export.cloth_family`); HumanSetup loads every `Human_Cloth_*.fbx`, the install script drops stale ones. `Human_Hair.fbx`
(Generic) is re-bound to the body's skeleton by bone name. `Data/HumanRigData.asset` holds the key deltas in
model space; the Blender-to-model mapping is fitted from the rest bones, not assumed. The showcase has a
creator (Portrait/Body/Lineup views, the 11 motions, height, underclothes) and 10 walking humans.

## Animations (our own, shippable)

`src/hum_anim.py` authors 13 clips procedurally on the deform rig: a pose is world-space rotation deltas per
bone + a pelvis offset, legs/arms solved with two-bone IK and pole vectors, keyed as local quaternions
(rotations + pelvis location only, so a clip is build-independent and retargets as Humanoid). 30 fps, in place.

| Clip | Frames | Loop | Notes |
|---|---|---|---|
| Idle / Idle_Look / Idle_Shift | 120 / 150 / 180 | yes | breathing, glance round, weight shift |
| Walk / Run | 30 / 22 | yes | 1.35 / 3.6 m/s (`human_clips.json` speed) |
| Turn_L90 / Turn_R90 | 30 | no | root yaw kept as root motion |
| Chop / Hammer | 48 / 30 | yes | two-handed overhead chop; one-handed hammer onto an anvil at waist height |
| Sit_Down / Sit_Idle / Stand_Up | 36 / 120 / 36 | idle only | seat height 0.46 m |
| Death | 54 | no | falls back, held |

`hum_anim.build_clips()` + `export_clips()` write `export/Anims/Human@<clip>.fbx` (armature + a sibling empty:
with a lone armature Unity collapses `HumanRig` into the file root and the copied avatar no longer matches) and
`export/human_clips.json`. HumanSetup imports them as Humanoid with the body's avatar (Copy From Other), loops
and root locks from the JSON, and builds one shared `Animation/Humans_Motion.controller` (both sexes).

Int `Motion`: 0 Idle, 1 Walk, 2 Run, 3 Chop, 4 Hammer, 5 Sit (Sit_Down -> Sit_Idle; leaving 5 plays Stand_Up),
6 Death (held until 0), 7 Turn_L90, 8 Turn_R90 (play once and hold until Motion changes), 9 Idle_Look,
10 Idle_Shift. The prefab's Animator has root motion on: the in-place clips don't move it, the turns rotate it
~87 deg (the 0.2 s blend in eats a few); a game that steers rotation itself turns root motion off.

**Helper bones** (`src/hum_helpers.py`, Unity `HumanHelperBones`): six extra deform bones the clips never key,
driven after the Animator so any Humanoid clip works.

| Helper | Sits at / child of | Drive | Takes |
|---|---|---|---|
| `xh_deltoid_l/r` | shoulder joint / clavicle | half the upper arm's turn | the shoulder and armpit (no collapse overhead) |
| `xh_glute_l/r` | hip joint / pelvis | half the thigh's turn | hip crease, buttocks, plate tassets |
| `xh_skirt_l/r` | hip joint / pelvis | 80% of the thigh's forward swing, 50% back, 100% seated | a skirt's panel, hips to knees (hanging faces only) |
| `xh_skirtback_l/r` | behind the buttocks / pelvis | as xh_skirt | the panel's back half (folds under the seat instead of swinging down through it) |
| `xh_hem_l/r` | knee of the skirt panel / xh_skirt | 25% of the thigh's swing forward, 60% back, 10% seated | skirts below the knee |
| `xh_cape_0..2` | down the back of a cape / spine_03 | spring chain (`HumanSpringChain`) | cloaks and the Black Knight's cape below the shoulder blades |

The cape chain's nodes ride spine joints plus fixed offsets (`head_off`/`tail` in `HELPERS`, strategy "OFFSET" in
`hum_rig.Skeleton.ends`), so they take those joints' per-build offsets. At runtime `HumanSpringChain` (Verlet, 60 Hz,
pulled toward the hanging pose, gravity, damping, capsules on spine/pelvis/legs) swings the cape; in Blender it is
rigid. Cape weights are closed-form (`hum_cloak.cape_weights`: spine by height, shoulder caps on the arms, the back
on the chain), smoothed over the mesh so the folded rim follows its edge. Big stiff pieces on the shoulder
(pauldron shells) put their arm weight on the deltoid helper, graded down the arm: the shell turns a quarter as far
as the arm, the lames below follow it.

**In-place edits keep the build fit.** Garments are stored at rest (built shape - W @ dJ(build)); any in-place
weight change must move them by (W_old - W_new) @ dJ - `hum_helpers.rest_shift` (used by `apply_to_object` and
`hum_cloak.reskin`). Helpers that sit on their host's joint need nothing.

One formula for all (Blender `hum_helpers.drive`, Unity `HumanHelperBones`): the helper's world rotation turns f
of the way its source turns past the source's parent; the parent only places it. Skirt helpers pick f by the swing
(forward / back, measured along the model's facing) and by how raised *both* thighs are (the less raised: seated
75 deg each, running 69 / -33), so sitting and running get different skirts. Skirt rows are recognised by the
garment's Region UV (hanging faces = region 0), so a shirt tail under trousers stays a shell.
A helper copies its host's joint, so it shares the host's per-key joint deltas (residual body keys stay valid).
Weights: `hum_helpers.redistribute` splits the host's weight by position along the limb (skirt rows below the
knee go wholly to the two hems, blended left/right across the skirt's width); it runs inside `hum_rig.skin`, is
idempotent, and gives each stiff piece (plates, studs) one averaged row so it still never bends.
`apply_to_object` re-splits an existing mesh in place (no rebuild). human_rig.json carries the helper table;
HumanSetup reads the bind rotations into the prefab's `HumanHelperBones`. Names avoid Humanoid auto-mapping words.
Capes (Cloak, KnightCape) never get hem weight (only rows with thigh weight are skirts); instead
`hum_cloak.shoulder_share` puts the cloth over each shoulder cap on that arm (long ramps, little on the back
panel), so raised arms lift the cloak rather than passing through it; `hum_cloak.reskin` re-weights in place.

**Hands and tools.** `Pose.fingers(s, fist)` blends relaxed -> fist per joint (`HAND_RELAXED/HAND_FIST/THUMB_ROOT`).
Two-handed tools go through `_handle_hands`: both fists close round one rigid handle (the hole the fingers make
at `GRIP_CURL`, fitted from the finger wrap), each hand turns the least from its forearm, the elbow is searched
round the shoulder-wrist line to keep the wrist inside Humanoid's limits (twist 90, flex 80, deviation 40 - past
those Unity clamps and the grip comes apart) and the upper arm under `ARM_RAISE` (135: higher folds the armpits);
a handle out of reach slides in rather than stretching the arms. Keys are `spline()`d (flow / stop / hit).
The prefab has `Socket_R` / `Socket_L` under the hand bones (HumanSetup.AddHandSocket, same geometry): origin in
the fist hole, +Y along the handle toward the tool head, +Z where the knuckles face. Props parent there; the axe
is rolled `AXE_ROLL` (-42 in Blender = +42 in Unity, the import mirrors an axis) so its blade leads the chop.
`HumanToolPreview` shows the placeholder `HelperAxe` while Chop plays and `HelperHammer` while Hammer plays
(showcase only). The hammer uses the same grip solver one-handed (`hands=(("r", 0.0),)`), its handle angles
(`HAMMER_PSI`) searched for the least wrist strain, and the elbow angle keyed and splined (`HAMMER_ELBOW`) so the
solver can't hop between two equally good elbows mid-swing; `HAMMER_ROLL` = -12 (Unity +12).

## Clothing (villager set)

- **Garments** (`hum_cloth.GARMENTS`): slot, fabric, hidden body regions, recipe.
  - Shirt (top), Tunic (outer), Dress (top), Trousers (legs), Boots/Shoes (feet), Belt, Apron.
  - Shells are offset copies of body faces, smoothed with the offset restored. Their open edges are
    straightened along the loop, so hems and cuffs are clean.
  - Skirts are lofted rings around the body's convex envelope (no dip between the legs) with flare and
    folds; they hang from the torso (pelvis/thigh weights).
  - The apron is the dress skirt's front, pushed 1.2 cm out.
  - Footwear is a foot tube (convex sections, so a toe box instead of toes) plus a shaft tube outside the
    trousers, fused by a voxel remesh, cut open at the top, with a flat sole and smoothed key deltas.
- **Keys and skin:** Surface Deform to the body (nearest-point fallback), weights transferred from the
  body; skirt parts bind to torso faces only. LODs (0.4 / 0.18) bind to their own LOD0 garment.
- **Hiding skin:** the body has a per-face "Region" UV (uv1.x). `Humans/Body` clips faces whose bit is set
  in `_Hide`, which is the union of the worn garments' regions. Collar, wrist and ankle are margin regions.
- **Colours:** `Humans/Cloth` = colour x tiling pattern (T_Cloth_Weave / T_Cloth_Leather) x AO (vertex
  colour r) x hem darkening (g). One material per fabric; colour per renderer (MaterialPropertyBlock).
- **Budget** (LOD2, colony camera): shirt 384, trousers 242, boots 618, dress 608 tris; a dressed villager
  is about 4.6k tris including head, hair and body.
- **Unity:** `Human_Cloth.fbx` (Generic) is re-bound by bone name under `Model/Clothes`. `HumanFace.clothRoot`
  switches garments on by `face.outfit` (garment + sRGB colour, one per slot). `HumanFaceGenerator.RandomOutfit`
  ports `hum_faces.random_outfit`. The creator UI has a per-slot garment and colour picker and "Random outfit".

## Leather armour and layering

- **Layers:** Shirt/Dress/Trousers 1, Tunic/Boots/Shoes 2, Jerkin/Bracers/Belt/Apron 3. Every garment carries a
  per-face Region UV like the body; `cover` lists what it clips on lower layers (`HumanFace` sets
  `_Hide` per garment via `HumanFaceConfig.LayerHideMask`). Necklines step down by layer (shirt at the
  neck, tunic 1.5 cm, jerkin 2.5 cm off it).
- **Jerkin** (`slot` armor, excludes Belt and Apron): stiff cuirass 2.2 cm out; three hip bands, each flaring
  over the next, studded along the lower edge; pauldrons of two overlapping curved plates with studs.
  **Bracers**: forearm guards with a stud row. Palette `armorLeather`; iron `_Metal` (vertex colour b).
- **Random:** `random_armor` gives ~30% of men and ~12% of women a jerkin (70% of them with bracers).
- **Short skirts:** the tunic skirt blends to the body's weights away from the centre line (`skirt_shell`),
  so striding thighs no longer poke through; long skirts keep the hanging pelvis/thigh weights.

### Modular armour (second pass)

| Piece | Slot | Notes |
|---|---|---|
| Jerkin | armor | cuirass + three studded hip bands; excludes Belt and Apron |
| Pauldrons | shoulders | two plates per shoulder; upper plate 0.7 upperarm + 0.3 clavicle, lower plate upperarm only |
| Bracers | bracers | forearm guards with studs |
| Greaves | shins | curved shin plates 3.1 cm out (clear of boot shafts), knee lip, studs; calf only |
| Cap | head | dome + lofted studded band + crest; rim over the brows, above the ears, at the nape |

- **Cap and hair:** `hum_armor.write_cap_coords` writes a "CapCut" UV on every hair/beard/brow piece
  (x = height above the rim line). `Humans/Hair` discards fragments with CapCut > `_CapCut`; `HumanFace`
  sets `_CapCut` from the worn garments (`capCut` in the config). Hair rooted under the rim (long hair,
  ponytails, the back of curly styles) shows below the band.
- **Random:** a jerkin-wearer gets pauldrons 60%, bracers 70%, greaves 40%, cap 50%.
- **Budget (LOD2):** pauldrons 146, greaves 112, cap 110 tris; a fully armoured villager (body 2.6k, head+hair up to 1.9k, clothes+armour ~2.7k) is ~7k at the
  colony camera.

### Full-coverage leather armour

Everything but the face is covered. The armour replaces the clothes (same slots, or `excludes`).

| Piece | Slot / layer | Notes |
|---|---|---|
| Leggings | legs / 1 | the trousers' fit + 3 mm (boots and greaves still fit over them), domed knee guards (thigh/calf 50/50, stiff) |
| Coat | outer / 2 | torso and sleeves to the wrist at 1.6 cm (+0.6 cm down the arm), studded closure, stand collar open in front (beards), front and back skirt panels to above the knee (split at the hips) |
| Boots | feet / 2 | the villager boots |
| Gloves | hands / 3 | 3.5 mm shell over hand and fingers + flared gauntlet cuff over the sleeve and bracers |
| Hood | head / 4 | the cap + an aventail: a smooth convex bell over head, ears and the body's neck/trapezius, head -> neck weights; hides the hair (beard and brows stay) |
| Jerkin, Pauldrons, Bracers, Greaves | optional, layers 3-4 | over the coat |

- Random armoured characters (~30 % of men, ~12 % of women) get the full set, plus a jerkin (70 %),
  pauldrons (60 %), bracers (40 %) and greaves (50 %).
- LOD2 (colony camera): coat 590, leggings 309, gloves 405, hood 316, boots 618 tris.
- **No nipples on garments:** `BodyFrame.smooth_anatomy` Taubin-smooths the torso before any shell is
  built and rounds each breast/pec apex (1200 weighted Taubin steps within 6 cm); `round_apex` smooths each
  garment shell there too, since a coarse garment vertex on a conical tip reads as a nipple.

### Armour sets

Armour is only worn as a complete set (it replaces the clothes; the creator hides clothing slots under it):

| Set | Pieces |
|---|---|
| Leather | Leggings, Coat, Cuirass (plain boiled leather + hip bands), Gloves, Boots, Hood |
| Studded Leather | StuddedLeggings, StuddedCoat (rivet rings over torso, sleeves and skirt), Jerkin (studded), Pauldrons, Bracers, Greaves, Gloves, Boots, Hood |

Colours: one for the leather, one for the plates over it (cuirass/jerkin, pauldrons, bracers, greaves), one
for the boots. `hum_armor.ring_studs` places rivets in staggered rings around a limb or the spine axis.

### Hooded cloak

`hum_cloak.py`: **Cloak** (wool, shoulders to mid-calf, iron clasp at the throat, open in front, over clothes or
any armour set) and **CloakHood** (a loose pointed hood with a short capelet; face open, hair hidden). The hood
is a *companion*: `SetGarment("Cloak", colour)` adds it, removing the cloak removes it. LOD2: cloak ~370,
hood ~280 tris.

Cloak cut: a cape - over the shoulder tops, then behind the arms (they stay free). No cloth simulation:
Unity's Cloth runs per character on the CPU (too heavy for a colony of dozens), ignores the blend shapes
the body sliders drive, and doesn't follow LOD switches. If the portrait view needs motion later, a
cheap option is two or three spring bones down the back of the cape, or Cloth on the LOD0 cape only.

### Padded and Mail sets

| Set | Pieces |
|---|---|
| Padded | PaddedLeggings, Gambeson (quilted coat, split skirt), PaddedCoif (round hood), Gloves, Boots |
| Mail | MailChausses, Gambeson, Hauberk (mail, sleeves to the wrist, knee-length split skirt, 3.6 cm out), MailCoif (round hood with a shoulder cape), Gloves, Boots |

Patterns `T_Cloth_Quilt` (4 stitched channels per tile) and `T_Cloth_Mail` (24 staggered rings per tile)
from `hum_paint.armour_textures`. The coifs are `hum_cloak._cloak_hood(peak=False, ...)`. Colours: one per
group (`hum_faces.armour_group` / `HumanFaceConfig.ArmorGroup`): Leather, Plates (leather plates), Padding,
Steel (mail and plate), Boots.

### Plate armour (`hum_plate.py`) - built to be extended

Two sets from the same builders (two styles):
- **Plate** (style "Munition", plain): PaddedLeggings, ArmingDoublet (the gambeson without its skirt, hem
  under the fauld), Gloves, Boots, PlateCoif (mail, worn *under* the plates), PlateCuirass (breastplate with
  a medial ridge, backplate, three fauld lames, two tassets a side, side straps), PlateGorget (upright
  collar + two lames draped over chest, back and shoulders), PlatePauldrons (domed cop + 3 lames), PlateArms
  (rerebrace open on the inside, couter = oval cup + fan wing, closed vambrace), PlateGauntlets (cuff + hand
  plate over the leather gloves), PlateLegs (cuisse, poleyn = oval cup + wing, closed greave with a ridge),
  PlateSabatons (4 lames + toe cap over the boots), PlateHelm (open-faced bascinet, crest, rolled rim,
  aventail rivets).
- **Gothic Plate** (style "Gothic"): the same pieces fluted (crisp ridges), brass-trimmed beads and rivets, a
  stronger ridge and a fluted **sallet** with a tail over the nape; shares PlateCoif and the under-layers.
- **Black Knight** (style "BlackKnight", fantasy): blackened steel close over a **Bodysuit** (no geometry: the body
  shader paints the body as dark woven cloth, `_Suit`), pointed plackart/fauld/tassets/pauldron lames, flaring
  pauldrons with spike crests, spiked vambraces, clawed gauntlets (a plate on every finger segment, rigid on its
  bone), a closed helm (keeled visor, brow ridge, narrow jaw, eye slit with a dark liner, horns) that hides the
  whole head (`hides_head`), gold beads, **gold-inlaid acanthus filigree** in an etched band inside each large
  plate, and a KnightCape hung from the backplate under the pauldrons (`_back_cape`). (A long skirt was tried
  and dropped: it bunched between the legs.)
- **Ornate Plate** (style "Ornate", fantasy): bright steel over the bodysuit, every large plate **etched** with
  damask (bright raised lines on a darkened ground, `ornament_mode=1`) inside a plain rim, gold beads.
Wearing plate excludes the cloak.

Ornament channel: plate parts carry `orn` per vertex (`Grid.panel`: a band `ornament_band` in from each plate's
edge, only on plates over ~12 cm; x style.ornament), written as UV layer "Ornament" (Unity uv4): x = weight,
y = pattern slice + 10 x mode (0 gold inlay, 1 etched). `Humans/Plate` samples `T_Plate_Ornament`, a
**Texture2DArray** (a vertical strip of 512 px slices: 0 acanthus, 1 damask; `_OrnTiles` = scale per slice), and
raises it with a screen-space bump (`_OrnRelief`). Slices: `pipeline/filigree.py` (Flux-dev; seeds 4101, 4103) ->
`pipeline/tex_seamless.py` -> `pipeline/filigree_strip.py`. A new pattern = a new slice + `ornament_pattern`. **Every plate mesh needs the Ornament layer** (zeros if plain): a mesh without
uv4 reads leftovers and plain plate showed gold.

How it's built (read the module docstring first):
- **Support:** a plate follows the convex support radius, around a bone or the spine, of the body *and of
  every garment built before it for that build* (`_under`), plus a standoff. So plates bridge hollows (one
  smooth breastplate over any bust, no nipples, no breast cone) and never dip into what they cover. Build
  order = `PLATE` dict order: each piece reads the ones before it.
- **Grid:** one plate is a (row, column) grid over (t along the axis, angle around it). Every column has its
  own t range (shaped outlines: neck scoop, armholes). Radial offsets make ridges, domes and flutes;
  `roll()` curls an edge into a bead; `rivets()` and `strap()` place details by (t, angle).
- **Rigid:** every plate has uniform weights (lames blend two bones). Articulation is overlapping lames, as
  on real armour. LODs: `plate_lod_weights` gives each decimated piece its plate's weights, and beads, rims
  and rivets are dropped before decimating (they fold over otherwise).
- **Vertex data (ClothData):** r AO, g polish, b LOD detail, a material (1 steel, 0.5 trim, 0 leather).
  Shader `Humans/Plate`: metallic PBR, hammered steel (`T_Plate_Steel`) projected from rest position,
  polished edges, brass trim and leather straps from the channels. Blender preview: `hum_material.plate_material`.

To make better-looking armour:
- **New look:** add a `PlateStyle` to `STYLES` (ridge, fluting `flutes`/`flute_depth`, bead size `roll`,
  rivets, `trim=True` for brass beads/rivets, `straps`, `helm` "bascinet"/"sallet"/"closed", `helm_tail`,
  `horns`, `point`, `spikes`, `pauldron_lames`, `cuisses`, `ornament`, `group`, and what it stands off:
  `under_torso`/`under_legs`/`under_hands`), then
  `PLATE.update(plate_garments("<Style>", "<Prefix>", coif="PlateCoif"))` and a set in `PLATE_SETS` - that
  is all "Gothic" took. Everything else (Unity config, material, colours, LODs) follows.
- **New piece or shape:** write a builder from `Frame`/`Support`/`Grid` (see `_pauldrons` for lames, `_cop`
  for a cup + wing, `_gorget` for a plate draped on a height field, `_helm` for a dome), then register it in
  `plate_garments` (dict order = build order).
- **Richer surfaces:** extend `Humans/Plate` and `plate_material` together: etching masks by rest position,
  per-style patterns, a trim colour from the palette.

Budget (MStrong, whole character incl. body/head/hair): 7.4k tris at LOD2, 17.5k at LOD1. Plate LOD2:
cuirass 491, legs 330, arms 207, helm 197, pauldrons 158, gauntlets 79.

