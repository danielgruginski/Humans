# Handoff

## Working agreements

- Daniel asked for faces first (2026-09-27): stylised, several different faces, good enough that players will
  look at them in a zoom-in menu. Hair, beards and eyebrows followed the same day.
- He chose MPFB2 (installed as a Blender extension, preferences saved). Style: stylised, matching the goblins.
- Keep Blender work visible: scene **Faces** in `blender/humans.blend`.

## Conventions that bite

- Garments are built over `BodyFrame.co` = the torso Taubin-smoothed (`co_raw` is the real body), plus
  1200 more Taubin steps within 6 cm of each breast/pec apex, and `round_apex` smooths each garment's own
  shell there: a garment (1.5-3 cm edges) puts one vertex on a conical tip and its normal reads as a nipple.
- Body builds (`hum_builds.py`): 3 per sex (Slim/Strong/Heavy). Body keys (sex/weight/muscle macros, body
  sliders, neck width) are set by the build only; face keys are head-only, residual, and faded to zero at the
  head's neck edge (`neck_fade`: by height *and* by distance to the edge ring - the ring rises 4 cm from
  throat to nape, and height alone left ancestry/age keys opening the nape seam by up to 11 mm).
  Garments are built once per build in build space (`BuildSpace`, `build_wardrobe`) and stored at rest
  (`to_rest`), named `Cloth_<Garment>_<Tag>[_L1|_L2]`; Unity shows only the face's build's garments.
- `hum_hair.bind_keys` strips an object's modifiers, Armature included: after rebinding hair/head LODs run
  `hum_build.skin_all`, or Unity gets rootBone-less hair lying at the character's feet (all hair and brows
  vanished once). Reload `hum_hair` and `hum_build` first: a stale `skin_all` in the Blender session made all
  hair rigid on `head` again and long hair sank through the back when walking (Daniel caught it). Check:
  Hair_Long's low vertices should be ~0.4 head / 0.6 neck_01, 3 vertex groups.
- Plate: pieces read what's built before them (`_under`), so GARMENTS order is build order: the arming
  doublet, then the coif (under the plates), cuirass, pauldrons (over cuirass + coif), arms, gauntlets
  (over arms + gloves), legs, sabatons (over boots), helm (over the coif). Plate hides only regions fully
  inside a closed plate: hiding the doublet's belly/chest or the leggings' shin_up opened holes at the flanks
  and behind the knees.
- `HumanFaceConfig.Load` caches by TextAsset; a reimported JSON is the same object, so the first rebuild after
  adding garments used the old list (Gothic plates got the cloth material). `HumanSetup.RebuildAll` now calls
  `HumanFaceConfig.ClearCache()` first.
- A full wardrobe rebuild is ~170 garments x 3 LODs, ~9 min: over MCP run `build_wardrobe(tags=[t], names=...)`
  in ~40 s chunks and stamp what's done (a custom property) so the next call resumes.
- In play mode, `HumanFace.Start` (randomOnStart) can overwrite an outfit set in the same frame: set
  test outfits a frame later.
- Hair colour fades (ombre, sunkissed) use CapCut.y = height within the style (0 top .. 1 lowest ends),
  not the per-clump Clump.y: per clump, short clumps near the crown went fully tip-coloured and read as
  pale "ghost" flakes among dark roots (Daniel spotted it from below). Hair shader is double-sided too.
- Head hair grows with `HeadFrame.face_guard()`: under the mouth and in front of the ears a clump can't
  move toward the middle or forward, and it stops hugging below the chin. Without it, Long's front clumps
  were pulled onto the throat and hung as a stray strand under the chin (seen from below).
- Head hair below the skull: `face_guard` keeps clumps from tucking in below the widest level of the back of
  the skull (a curtain, not a sleeve around the neck) and 2.5 cm off the body; `hair_weights` blends head ->
  neck_01 -> spine_03 by height (rigid on the head, long hair sank into the shoulders when animated);
  `smooth_keys_spatial` blurs the hair's key offsets over 2 cm (the Surface Deform bind to the head's neck
  edge tore a gap at the nape for some faces). Beards/brows keep exact keys and rigid head weights.
- Render scripts that switch off `HumanCreatorUI` (for clean shots) must switch it back on: once it got
  saved disabled in Humans_Showcase and the creator panel vanished for Daniel.

- `hum_cloth` imports `hum_armor` and copies its `ARMOR` dict into `GARMENTS`: after reloading
  `hum_armor`, reload `hum_cloth` too or the old recipes are still used.
- A part of a garment may carry a 6th tuple item `{bone: weight}`: uniform weights for a stiff plate.
- `capcut` 0 means "no cap" (both shaders): a cap's own cut must be > 0.

- Garment layers: `hide` = body regions a garment clips on the body; `cover` = regions it clips on inner
  garments (only for tight shells; skirts part when walking, the jerkin sits far enough out). Garment faces
  that touch a margin region (collar, wrist, ankle, hand) never get clipped, or necklines fray.
- Unity culls back faces, Blender doesn't: open sheets (pauldrons, stud domes) vanished in Unity until the
  Cloth shader went `Cull Off` with flipped back-face normals.

- Garments: `hum_cloth.build_garment` rests the rig and zeroes the *body* keys only. Other garments keep
  the preview character's key values, so re-run `hum_faces.apply_face` before comparing garments in a render.
- Blender shows back faces, Unity culls them: check garment winding (normals out) - skirts were inside-out
  once and looked fine in Blender. `vertex_ao` uses the normals too.
- Body hide regions are per face (the "Region" UV, written by `hum_cloth.write_regions` before `body_lods`,
  which copy it). Hidden regions must stay well inside each garment; collar, wrist and ankle are margin
  regions only long garments hide.

- Body keys are residuals over bone movement: a Blender preview of a face must also pose the bones
  (`hum_faces.apply_face` does it via `hum_rig.pose_for_keys`). Keys alone look wrong for macros.
- Corrective keys combine as `ab - a - b + 2*base` (for vertices *and* joints). With `+base` once, the
  rest shape still matched, but the corrective moved the skeleton 1.4 m.
- MPFB height 1.0 is a 2.3 m giant; height is handled as a uniform scale instead of a key.

- EEVEE misreads Attribute(OBJECT) values when a material reads many object properties (11 broke the lips):
  scalars are packed into `hum_amt1..3` vectors (`hum_material.set_props` does it).
- LOD object names end in `_L1`/`_L2`, not `_LOD1`: Unity's FBX importer treats `_LOD<n>` as its own LOD
  convention (and warns when there's no `_LOD0`).
- Reload `hum_export` too before exporting (`hum_build.reload()` doesn't): a stale module exported only the full head.
- Unity imports these FBXs (no rig) as MeshRenderers even with blend shapes; `HumanSetup.ToSkinned` converts them.
- Colours in C# are sRGB; `SetColor` linearises. Colour maths in the generator runs in linear space (`.linear`/`.gamma`).

- Hair modules import each other (`hum_styles` does `from hum_hair import ...`): reload hum_hair first
  (`hum_build.reload()` does it in order), otherwise stale functions survive.
- The Bash tool breaks on heredocs with quotes in them; write patch scripts to a file instead.

- `mesh.materials.clear()` resets every face to slot 0. Use `hum_paint.set_materials` (replaces slots in place).
  Before this fix, the eyeball UV disc was baked over the face island.
- Eyeball UVs are a front projection that overlaps the head UV square. They must stay on material slot 1,
  which the bakes skip.
- MPFB macros move the whole head (height). Keys are anchored at the neck ring (`rig.neck_ref`).
- MPFB targets are strong at 1.0. Random faces soft-clamp sliders to about ±0.7, and nose, chin and head
  length get less spread (`hum_faces.SPREAD`).
- Old + feminine + thin gives a long, hooked nose. That comes from MPFB's macro, not the sliders.
- Blender 4.4 `uv.unwrap(method='MINIMUM_STRETCH')` is used, with a fallback to CONFORMAL.

## State (2026-09-27)

Done: head + eyes, stylisation, UVs, paint masks, preview shader, 98 keys, random faces, lineups
(`renders/lineup_v5.png`, `lineup_v5b.png`) and a slider sheet (`renders/sliders.png`).

- 2026-09-27 (later): Daniel asked for hair, beards and eyebrows ("bonus points" for multi-colour hair).
  Done as solid stylised clumps + caps, 9 hairstyles, 5 beards, 4 brow sets, all bound to the face keys;
  root/tip ombre and position-coherent streaks. Renders: `renders/lineup_hair_a.png`, `lineup_hair_b.png`,
  `hair_colors.png`.

- 2026-09-27 (later still): hair iteration (unified normals, edge darkening, ear domes, beard v2 with
  sideburns, no neckbeard) and the first Unity install in MedievalSetting (prefab, 3 URP shaders,
  C# generator, showcase + creator panel). Verified: setup renders, play mode with no console errors.

- 2026-09-27 (night): Daniel chose "mildly stylised" and "body + rig only" (painted underclothes, clothing
  later). Beards were fixed again after his notes: the sideburn is a smooth rise of the beard's top edge,
  there's no mustache over the mouth, and the chin strap is a jawline band. Body, rig, residual keys,
  height scale and Unity Humanoid are done; walking verified in play mode.
- 2026-09-27 (late night): "plain medieval villager clothes to start". Shirt, Tunic, Dress, Trousers,
  Boots, Shoes, Belt, Apron (`hum_cloth.py`), each with L1/L2, bound to the body keys, skinned, dyeable,
  hiding the body regions under it. In Unity: `Human_Cloth.fbx`, `Humans/Cloth` shader, outfit in
  `HumanFaceData`/generator/creator UI. Verified walking in play mode (lineup + colony-distance view).

- 2026-09-27 (later): "fix the tunic poke-through, once the clothes are correct, start leather armor".
  Tunic skirt now skins like the body under it (skirt_shell) and garments layer: each garment has a Region
  UV and outer layers clip what they cover on inner ones (`cover`, shader `_Hide`). Leather armour added
  (`hum_armor.py`): Jerkin (cuirass + 3 studded hip bands + two-plate pauldrons) and Bracers, iron studs as
  metal (ClothData.b), dropped at L1/L2. ~27% of random faces get armour. Cloth shader is double-sided.

- 2026-09-27 (later): "fix the pauldrons, then add a leather cap and more armor". Armour is modular now:
  Jerkin, Pauldrons (own garment; each plate has uniform weights, so it turns with the arm and never
  bends), Bracers, Greaves (stiff on the calf), Cap (bound to the head keys like hair, rigid on `head`).
  Hair under a cap: every hair piece has a "CapCut" UV (height above the cap rim); the hair shader hides
  what's above `_CapCut` (0 = no cap). Verified walking in Unity.
- 2026-09-27 (later): "armor has to cover everything ... it can cover completely the clothes and disable
  them ... Also, niples are showing on the clothes". Full coverage set: Coat (sleeves to the wrist, stand
  collar open at the throat, split skirt panels), Leggings (knee guards), Gloves (gauntlet cuff), Boots,
  Hood (cap + aventail over ears, neck and nape; hides the hair). They take the clothes' slots / exclude
  them; Jerkin, Pauldrons, Bracers, Greaves layer on top. Random armoured characters always get the full
  set. Nipples: garments are built over a Taubin-smoothed torso (`BodyFrame.smooth_anatomy`) and tops,
  coat and jerkin smooth their key offsets (`smooth_keys`).
- 2026-09-27 (later): Daniel found partial armour (jerkin/pauldrons over a shirt and trousers: the coat and
  leggings sat in the "Outer"/"Legs" clothing slots, easy to miss) and asked for variety. Armour is now worn
  only as complete sets (`hum_armor.ARMOR_SETS`, config `armorSets`, `HumanFaceData.armorSet`): "Leather"
  (Leggings, Coat, Cuirass, Gloves, Boots, Hood) and "Studded Leather" (StuddedLeggings, StuddedCoat, Jerkin,
  Pauldrons, Bracers, Greaves, Gloves, Boots, Hood). The creator's Outfit section has an Armour selector
  (colours: leather / plates / boots) and hides the clothing slots while armour is on; armour pieces never
  appear in clothing slots. Studs were sunk into the leather (cast() flipped normals inward): fixed.
- 2026-09-27 (later): "add a cloak with a hood". `hum_cloak.py`: Cloak (slot cloak, layer 5, over clothes
  or armour; hull of torso + legs + arms hanging down + a shoulder ball for pauldrons, open in front below an
  iron clasp; collar on neck/spine, lower half skinned like a skirt) and CloakHood (a companion garment:
  added/removed with the cloak via `companions`, never offered on its own; hides hair, replaces Cap/Hood).
  ~20 % of random characters get one (`random_cloak`, palette `cloaks`). Recut as a cape after Daniel's
  review ("the cloak should just not cover the arms"): collar -> over the shoulder tops -> behind the arms
  from the armpits down (span 172 -> 118 -> 78 deg from the back); hull includes the arms hanging and swung
  back 30 deg; skinned to the spine/pelvis only. No cloth simulation (see README). Creator: "Cloak" slot, also shown
  under armour. `HumanFaceConfig.WornArmorSet` tolerates swapped headgear.
- 2026-09-27 (later): cloak hood reworked after Daniel's notes ("close at the neck", "only parts of the hair
  disabled", "more triangular", "hoods are more like a prism on the sideways"): the hood is the convex hull of
  the head (+2 cm) and a seam from the forehead over the crown to a point behind it (`_hood_crown`), sliced
  into rings; face open from the hairline to the chin, closed at the throat, hem tucked in the cloak collar.
  Hair is cut only where the hood covers it (HoodCut UV = uv3; fringe and face-framing locks stay).
  Garment key offsets are also blurred over 3 cm (`smooth_keys_spatial`): nipples came back through the
  sliders otherwise.
- Then "start the other armor types": sets Padded (Gambeson, PaddedLeggings, PaddedCoif, Gloves, Boots) and
  Mail (Gambeson + Hauberk, MailChausses, MailCoif, Gloves, Boots); materials M_HumanQuilt (T_Cloth_Quilt) and
  M_HumanMail (T_Cloth_Mail); colours per group (Leather, Plates, Padding, Mail, Boots).
- Then Daniel's armour notes (mail through the cloak, collar tabs, pattern stretching, bare nape) and "we need
  additional details that will help ease these transitions, where there are seams": garment UVs are now
  per panel (`cloth_face_uvs`: each face takes the torso or one limb's mapping; whole pattern repeats around
  the body/limb, so the wrap seam is invisible) and a raised binding strip covers every torso/sleeve seam
  (`seam_trim`, darker via the hem channel, flat spot of the pattern). The cloak's hull includes the armour
  built before it (`_worn_under`); coifs lie over the gambeson/hauberk (`over=`); hood/coif collars take the
  body radius at each vertex's own height (no tab); headgear hems ride spine_03.
- Then "the problem in the neck still persists, at least when animating. The hood also does not flow with the
  animations": headgear below the jaw now takes the body's key offsets and every vertex takes the bone weights
  of the skin under it (head or body, smoothed; `_skin_weights_under`, `_body_follow`), so capes ride the
  neck, collarbones and shoulders. Region 15 "neck" added to the body; hoods and coifs hide neck + collar
  (the body's nape bent through the coif when walking even with matching weights).
- Then "the rings have no size consistency" + "the hood part ... should be more of an oval": every garment
  has UV layers RestXY/RestZ (rest position, metres; RestZ.y = 1 on seam trims) and Humans/Cloth has
  `_Triplanar`/`_TriTile`: mail is projected in 3D from the rest position (24 rings per 0.24 m tile), so ring
  size is the same on every panel and still sticks to the cloth when animated. Hood/coif capelets are an
  oval through their widest points. Also: hum_armor was missing `import bpy`, so the previous round's
  headgear skin weights never built - fixed and rebuilt.
- Coif/hood capes reduced after "this is the area I meant to be reduced" (the flat bib on the chest): the hem
  height follows the angle round the neck (short rounded dip in front, high over the shoulders, deepest at
  the back), small flare, the plan-view oval only at 45 %, coif drops 0.06 / 0.07 m.

- 2026-09-27 (evening): "Do you think the variable body sizes are making the armor production harder?" ->
  "yes, go with 4 builds per sex" / "or even less if apropriate": 3 builds per sex (MSlim/MStrong/MHeavy,
  FSlim/FStrong/FHeavy, odds 0.4/0.3/0.3). Every garment is an exact fit per build, no body keys on
  garments; face sliders stay free. Creator: Sex + Build pickers replace the body sliders. Then Daniel:
  "leather armor has nipples in them" - breast apex rounding (frame + garment, see Conventions); and a nape
  crack for some faces (neck fade). Verified in play mode: all builds x 4 armour sets + clothes + cloak,
  8 hair styles front/back, headgear, nape. Renders in MedievalSetting `Logs/HumanSetup/` (nip3_sheet,
  nape_sheet, hs_sheet, builds_lineup).

- 2026-09-27 (evening): "start the plate armor. Make it something extensible, we will want to have better
  looking armor in the game". `hum_plate.py` (style + frame/support/grid primitives + pieces, see README
  "Plate armour") and a Plate set on all 6 builds; Unity shader `Humans/Plate` (metallic PBR, hammered steel,
  polish/trim/strap channels), material M_HumanPlate; mail and plate share the "Steel" colour group.
  Verified walking on every build, LOD0-2. Renders: MedievalSetting `Logs/HumanSetup/pl_sheet.png`,
  `lod_sheet.png`, `cf_sheet.png`.

- Then "keep working on the armor": gorget (draped on a height field), oval couters/poleyns with fan wings,
  rolled beads curling back onto the plate (they read as wire hoops before), arming doublet hem under the
  fauld (its cut edge showed), plate LODs (per-plate weights, beads dropped), and a second style "Gothic"
  (fluting, brass trim, sallet) as set "Gothic Plate". Renders: `Logs/HumanSetup/cmp_sheet.png`,
  `gp_sheet.png`, `gp_portrait.png`.

- Then Daniel's fantasy references ("can we also have armor like these ones?"), "start with the black knight",
  "criticise the result, then iterate": bodysuit under-layer (body shader), Black Knight set, ornament channel +
  Flux filigree, closed horned helm. Critique rounds: wallpaper ornament -> etched border bands on big plates only;
  round bucket helm -> keel, brow, narrow jaw, head hidden; soft edges -> gold beads, bigger spikes, sharper points.
  Also fixed: plain Plate/Gothic showed ornament (no uv4 on their meshes). Renders: `Logs/HumanSetup/cmp3_sheet.png`,
  `bkl_sheet.png`, `bk_portrait.png`.

- Then "finish the armor first, then animations": Black Knight claws, flaring pauldrons, back-hung cape, skirt
  dropped on Daniel's call ("keeps getting in the way"); Ornate Plate (etched damask); ornament texture array +
  modes + per-slice scale; garments split into per-family FBXs (largest 39 MB; was one ~200 MB file). Renders:
  `Logs/HumanSetup/fin_sheet.png`, `ns_sheet.png`.

- Then "go ahead with that animation list": our own 13 clips (`hum_anim.py`, README "Animations"), replacing the
  Kevin Iglesias clips (licensed, can't ship in a sold pack). Humanoid via the body avatar, one shared
  `Humans_Motion` controller. Verified in play mode on villagers and all four plate sets (Walk/Run/Chop/Hammer/
  Sit/Death/Turns). Fixed on the way: clip FBXs need a sibling empty (avatar hierarchy), turns held instead of
  re-triggering, plate cuirass no longer hides the pelvis region (a hole at the back of the thigh over the
  bodysuit when running). Unity renders in play mode must come a frame after changing a pose (skinning runs in
  the player loop, not in `Camera.Render`).

- Then "they are keeping the hands in a claw stance ... clutched fists when running, relaxing when idle, walking"
  and "the chop motion is robotic": hands are now a relaxed-to-fist blend with per-joint angles (knuckle, middle,
  tip; cascade index -> pinky; thumb root swings alongside the index when relaxed, folds over it in a fist) -
  `Pose.fingers(s, fist, spread)`, presets `HAND_RELAXED/HAND_FIST/THUMB_ROOT`. Idle/walk relaxed, run clenched,
  tools gripped. Chop and Hammer keys go through `spline()` (cubic Hermite: flow / stop / hit keys) instead of
  easing to a halt at every key, and the chop is keyed in polar form round the shoulders (an arc; the straight
  grip path dragged the hands past the face and slowed them mid-swing). Downswing now accelerates 0 -> 7.6 m/s
  into the log. Renders: `renders/anim_chop_strip.png`, `anim_hands_unity.png`, `anim_hands_blender.png`.

- Then "build a helper axe so we can see the chop" / "stretching the arms too much" / "the hands don't properly
  grab the axe, and the axilas are getting stretch artifacts": hand sockets + HelperAxe in the prefab; the chop's
  fists now close round one rigid handle (fitted finger hole, reach-aware, elbow search inside Humanoid wrist
  limits), elbows bent through the lift, axe cocked behind the shoulders, upper arms <= 135 (armpits no longer
  tear), blade leads within 20 degrees, head ~20 m/s at impact. Renders: `renders/anim_chop_grip_unity.png`,
  `anim_chop_axe_blender.png`. Blender helper: scratchpad `axe_helper.py` (removed after renders so no export
  picks it up).

- Then "you can build the helper bones now": xh_deltoid / xh_glute / xh_hem (README "Helper bones"), added to the
  live armature and every skinned mesh in place (1196 objects, 654 with helper weights, ~40 s) - no rebuild.
  Checked: Unity avatar mapping unchanged; chop armpits clean on shirts and leather; long dresses hang from the
  knees seated and stay one A-line mid-stride (a sharp left/right split parted them into tubes - fixed).
  Renders `renders/helpers_*.png`.

- Then "reskin the cloak ... the arms clip the cloak" and "sitting stance also has hands clipping": cloak and
  KnightCape shoulders ride the arms (and no longer hang from the knee hems); seated palms rest flat on the thighs
  12 cm off the bone (thickest build's thigh 9.9 cm + cloth + palm), blended in without the old pop.
  `export_clips` now resets bone offsets first (a build preview had baked 3 cm offsets into the sit clips:
  Unity "Copied Avatar Rig Configuration mis-match"). Small teeth remain on the cloak's rim at the shoulder with
  the arms fully up.

- Then "go ahead with the plans": cape spring chain (xh_cape_0..2 + HumanSpringChain; capes trail when running,
  settle when idle), pauldron shells on the deltoid helper (no longer riding up round the helm), cloak rim teeth
  smoothed (weights averaged over the mesh), Hammer rebuilt on the grip solver with a helper hammer (wrists inside
  Humanoid limits, head lands on the anvil, the free hand moved off the strike path). Found and fixed: the earlier
  in-place re-weights had shifted dresses / cloaks off their builds by up to 2.6 cm (garments are stored at rest
  = built - W @ dJ): repaired, and `hum_helpers.rest_shift` now guards every in-place edit. LOD objects now carry
  `at_rest` too.

- Then "the way people sit when in dress is weird" and "can you fix this bulge?" (a running dress): skirt helpers
  (xh_skirt, xh_skirtback) carry the skirt panel as one piece - seated it lies over the lap and folds under the
  seat, the hem hangs from the knees; striding it follows the knee forward but not the thigh back, and the hem
  hangs from the panel, not the leg (a running knee-lift had carried the lower skirt up in a flap). Helper drive
  unified to one follow formula. Shirt tails were caught as skirts (white patch at the crotch) - skirts now come
  from the Region UV's hanging faces. Renders `renders/dress_*.png`.

- Then "keep working" (QA in play mode with `HumanQA`: Lineup / Dress / Pose / Release / Shot - pose on one
  frame, shoot on a later one): skirt panels bent forward stuck out behind like tails - the skirt helpers now
  use a "hang" drive (hang straight down in the character's frame unless the thigh pushes into the panel;
  `hum_helpers._hang`, mirrored in HumanHelperBones). xh_hemback (back hem, on the back panel, half-follows the
  calf) stops the trailing heel poking out of a running skirt. The spring chain only runs while a cloak-slot
  garment is worn (HumanFace).
- Then "the cloak also has issues, that hole makes no sense" / "something is wrong at the positioning of the
  cloak" / "head is disjointed from body" / "cloak should not be used with armor": the cloak's hull included
  every garment of the build, so plate gorgets and pauldrons made every cloak a stiff ring at chin height,
  18-24 cm out - from above a ring-shaped gap round the hood, from the front flaps on the chin. Now the Cloak
  excludes pauldrons, gorgets and plate (`hum_cloak.bulky`, added to its `excludes` at export - they collided
  anyway) and fits clothes, gambesons and mail; its collar tucks 1.2 cm inside the hood (tall builds' collar
  is above the body mesh's neck: the first ring below with points stands in). CloakHood no longer hides the
  neck/collar body regions: seen from below that was a hole in the throat under the hood. Renders
  `renders/_tmp/cloak_v2_*.png`, `cloak_below.png`.

- Then "the skirts ... are lifting too much, in an unnatural way" (the rigid panels: whole quarters turned with
  the thighs, the back hem flipped with the calf) -> Daniel chose a physics skirt. The 8 panel helpers are gone;
  a skirt ring replaces them (`hum_helpers.RING`): 12 columns round the hips, each `xh_skirtNN_hip` (hip ring ->
  3 cm outside the legs at knee height) + `_knee` (-> the hem) + a weightless `_hem` tip. Weights: two
  neighbouring columns by azimuth, hip link above the knee, knee link below, at most 4 bones a row (Unity
  skins with 4 and had dropped up to 14-23% of skirt rows' weight - Blender and Unity moved differently).
  Unity `HumanSkirt` (execution order 150) simulates the knee/hem points (Verlet, 60 Hz): target = hanging in
  the character's frame, seated = carried by the thighs (stiffness 1, the old lap drape); leg capsules push
  one-sidedly by ring slice (a leg inside a column's 30 deg slice must not reach past that column's cloth),
  out and up (`lift`), both links elastic (`elastic`, `elasticHip`: the running feet are further apart than a
  dress's hem is wide - Daniel's point - so it stretches and rises). Each garment's slack (how far its cloth
  stands outside each column, per build: `hum_helpers.ring_slack`, exported as `skirtSlack`) sets where a
  leg starts pushing; HumanFace passes the tightest worn skirt's, and runs HumanSkirt only while a garment
  with `hangs` is worn. The leg margin (`thickness`, boots) is capped per column by its rest gap (a margin
  wider than the gap flew the tight sides of a dress up standing still). Blender previews only hang /
  follow the thighs seated (no simulation): check running skirts in Unity.
- Then "everything that has a skirt like item ... broking into pieces": the ring only took skirt rows with some
  pelvis weight, but `skirt_shell` garments (Tunic, Coat, Jerkin and what's built on them: Hauberk, Cuirass,
  StuddedCoat, Gambeson) weight their skirts' sides like trousers - half of each skirt hung from the ring, half
  followed the legs, torn apart. Now every hanging row the legs carry goes on the ring, and stiff pieces on a
  skirt (studs, rivets) take the nearest ring row (they floated off the cloth). Seated, a short skirt stood
  up over the lap like a tray (the rigid link turned the cloth's outward offset up with it): the seated target
  now aims so the cloth, not the chain, lands on the thigh.
- Then "any chance we could align these textures? from the gambeson": skirt panels without their own UVs
  (Coat, StuddedCoat, Gambeson, Jerkin, Cuirass, Hauberk) were mapped round each thigh (their nearest body
  part), so the quilting channels restarted at the waist. `cloth_face_uvs(..., group)` now maps skirt parts
  with the torso's projection (build_garment), and `hum_cloth.remap_skirt_uvs` re-mapped the built ones in place
  (their hanging faces, every build and LOD, in build space) - the channels run on down from the body.
- Tried and reverted ("the front lifts too much on the short skirts", then "forget it, now the thighs show
  through"): colliding only as far down as a short skirt's cloth reaches, a 3D thigh rule letting the cloth
  rest on a raised thigh, a 1.5 cm margin on thighs and lift for hems only brought the fronts down to 45-65 deg
  but let the thighs through. Daniel prefers the lift to clipping: a raised knee stands a short skirt's front
  up to ~80 deg, and that's accepted.
- Then "we need to work on attack animations" (his picks: one-handed + shield, two-handed, spear; stand-in
  weapons; bow already exists in the Goblins project): 10 combat clips (README "Combat"), Unity states 11-20,
  stand-in sword / shield / greatsword / spear. Checked numerically in Blender (blade vs body and shield per
  frame, wrist strain and frame-to-frame turns) and in Unity (fists on the handle, play-mode sheets in villager
  clothes and every armour set). The combat clips use a capped-twist `_hold` and splined elbow/twist hints; Chop
  and Hammer are untouched (their keys were tuned on the old hold).
- Then "this kind of hand positioning (the right hand) is wrong, wrists are not supposed to bend that much": the
  first pass only kept Humanoid's limits and every sword hand sat bent 40-70 deg (the raised block worst). The
  rest pose is palm-down, so a thumb-up grip is already +90 twist (Humanoid's limit) and the solver bent the
  wrist for the rest. Now `wrist_comfort` (bend ~30, twist cheap up to thumb-up) drives the combat solver, and
  every strained key's blade and fist were re-searched: held poses bend <= ~25 deg, strikes ~20-30.
  Standard for future clips: comfortable wrists, checked with tools/combat_qa/strain_check.py.
- Then "link me back to kevin iglesias animations ... test how they look with the new bones": clip libraries
  (README "Trying other clip packs"); "Kevin Iglesias" built in MedievalSetting and wired into the showcase.

- 2026-10-03 (MedievalSetting session, Daniel: "go with option 2"): the prefab no longer carries the pieces. It was
  the whole creator - 1,324 objects, 1,196 skinned renderers (every garment x 6 builds x 3 LODs, every hair /
  beard / brows) - copied for every character, with every mesh loaded. HumanSetup now cuts each piece into a
  `HumanPiece` (Resources/HumanPieces, 398) and `HumanFace` makes a worn piece's renderers on demand (README
  "Unity"). Checked in the game: 5 villagers + player 763 objects (was 6,624), outfits, hair under hoods,
  forced LOD1, re-dressing the player in armour, the game's silhouette tag (pieces take the body's
  renderingLayerMask); showcase lineup renders unchanged.

- 2026-10-04: **orcs** (Daniel: "branch off the humanoids to build orcs ... the next threat"; look: the human painted
  green, tusks, pointy ears, taller, more muscular; both sexes; models + a test fight). A face preset (`hum_orcs.py`,
  README "Orcs") + the Tusks beard style, exported in the config and applied by `HumanFaceGenerator.ApplyPreset`;
  no new body geometry, so every garment and armour set fits. In MedievalSetting: `CreatureDef.facePreset`, orc
  warrior / brute / archer and an "orc" group, an encounter on the bandit road (Game README). Checked in play mode.
  Renders: `renders/orc_lineup.png`; Unity `MedievalSetting/Logs/Orcs`.

- 2026-10-05: **wizard's robes** (Daniel: "What about some robes for the wizard? Where could the player get those?
  Maybe the wizard trainer in the second town also sells wizardry equipment?" -> "go ahead with the robes").
  `hum_robe.py` (README "Wizard's robes"): Robe + RobeTrim on all six builds, three sets (Apprentice, Journeyman,
  Magister) with their own colours and kept off random people (config `armorSets[].colours`, `noRandom`; C#
  `ArmorSet.Colour`, `SetArmorSet`, the generator's filter). Only `Human_Cloth_Robes.fbx`, the config and the
  scripts were installed in MedievalSetting (no full re-export), then Rebuild Prefab and Showcase. In the game:
  three robe items, Old Wren sells the apprentice's, Magister Vane the others and the staves, and wears the
  magister's (Game README). Checked in play mode: Vane in the tower, the shop rows, the player in the apprentice's
  robe. Renders `renders/robe_*.png`, `renders/robe_unity_*.png`.

## Open / next

- Robes: no hood (the first proposal had one up or down) and a sash rather than a rope belt. Looking down into
  the neckline from close above shows a thin dark line of the robe's inside between skin and binding (any shell
  garment's; at the game camera it reads as the collar's shadow). The shared torso/sleeve seam binding runs over
  the shoulders as on every sleeved garment.

- Orcs: more of an orc look would need geometry the human lacks (a heavier jaw and brow in the mesh, lower ears,
  broader hands); the preset is as far as sliders go. Grey hair in the Buzz cap reads as a knitted cap; brows are
  faint on dark green skin at the game camera.

- **Combat clips are work in progress** (Daniel, 2026-09-28: "the quality of the animations was not good ... the
  amplitude of the movement was wrong, and the sword swing wasn't having the blade in the direction of the cut").
  He has let go of building our own animations: don't push this further unless he asks. To pick it up again,
  key the swing arcs from reference (full shoulder/hip rotation, larger arcs), key the edge direction along the
  cut (the grip frame's +Z), and only then fix wrists.
- Combat: in the spear lunge the front skirt column rides up over the forward thigh and, from behind, reads as a
  stiff flap out to the side (the ring's lift at its most extreme); long dresses flare wide over the split
  stance. The slash's elbow still drops ~50 deg in the frame of the hit, and one frame there (and one in the
  wind-up) passes Humanoid's twist / deviation limit a little: a clamped frame could show the sword a few degrees
  off in Unity. Edge alignment of the blades is free (least strain), not keyed. No hit
  events/curves on the clips yet (a game needs the impact time: Slash 0.50, Overhead 0.56, TwoHand 0.54 / 0.58,
  Thrust 0.45, Jab 0.30 normalized).

- Skirt ring: tuned on the Run clip by eye (stiffness 0.15, stretch 3, lift 0.5, elastic 1.35 / 1.25,
  thickness 0.05); the back hem kicks out in a pointed flap at the top of the heel kick. HumanHelperBones still
  carries the old panels' hang / raise code (unused now).
- Coifs (Padded/Mail/Plate) and the leather Hood still hide the neck and collar regions - likely the same hole
  from a low camera; check from below and drop the hide if nothing pokes through.
- Chop: the elbow angle isn't keyed yet (the hammer's is) - fine now, but key it if a pop shows up.
- Sitting: long dresses and skirts sweep out level from the knees (skirt weighted to the thighs); the cloak and
  cape pass through the (absent) seat. A skirt-front helper bone would fix the dresses.
- Clips: Hammer still uses the old one-hand IK (no socket alignment / wrist limits) - give it the chop's grip
  treatment and a helper hammer; Run could lean more; turns rotate ~87 deg.

- Plate: a visor (the bascinet takes one); steel reflects the showcase's blue sky strongly (a
  reflection probe in the real scenes will change the look); tassets at the back look like a ragged fringe
  in profile; new slots `gauntlets`, `sabatons`, `helm` aren't in the creator's clothing slots (only via sets).
- Human_Cloth.fbx is now ~152 MB with two plate styles (per build x 3 LODs); splitting it per set would keep
  imports quicker as styles are added.

- Shirts and the padded gambeson still show the breasts' cone shape on female builds (no nipple point any
  more); armour could be built over a "bridged" chest (fill under/between the breasts) if Daniel wants.
- Human_Cloth.fbx is ~92 MB (6 builds x ~28 garments x 3 LODs); fine for now, could drop LOD0 stud meshes.
- `HumanCreatorUI.showBody` is unused (warning) since the body sliders went.

- Next armour: plate (breastplate, pauldrons, vambraces, gauntlets, greaves, sabatons, helmet).
- Seam trims only cover torso/sleeve seams; leg/torso (trousers) seams are hidden by tunics/skirts so far.

- Cloak: a soft vertical fold down the centre back; single sheet (no lining colour). Hood a bit bulky from
  the side. Optional later: Unity Cloth (or spring bones on a few cape bones) for the portrait view only.

- Studded coat skirt: studs cluster unevenly where rays hit the flared panels at a slant; a UV-grid placement
  would be tidier. StuddedCoat LOD0 is 9k tris (studs), L2 590.
- Plate should follow the same set pattern (padded and mail are done).

- Hidden hair under a cap still casts shadows in Unity (URP's stock ShadowCaster pass doesn't clip); it
  lands inside the cap, so it hasn't shown, but a custom shadow pass would be exact.
- Tall styles (Bun, Mohawk) vanish entirely under a cap; the bun could be kept by raising its CapCut.
- Clothing: boots have a small lump at the inner ankle bone; the shirt collar edge is slightly stepped
  under a tunic in close-ups.

- Daniel's feedback on the look (Blender lineups + Unity `Humans_Showcase`).
- LODs done (README): at the colony camera a head with hair and beard is at most ~1.9k tris.
  Human_Hair.fbx is 61 MB (LOD0 pieces dominate).
- Unity: blend-shape bounds are the base mesh's (re-check with extreme sliders).
- One eye white showed dark specks in a Unity close-up (creator_34): not investigated yet.
- No jaw or eye bones yet (talking and blinking need them, or keys driven from MPFB expressions).
- Painted underclothes (shorts, chest band) still show where no garment covers them (by design).
- In-game head (~2k tris) with the same keys (Surface Deform transfer), and fewer eye segments.
- Unity: FBX export, skin/eye shader (URP) with the mask formula, `HumanFace` component that composes the
  keys at spawn and bakes the mesh.
- Eye bones: eye pivots move with the sliders, so the bone positions must be derived per face.
- Blink / talk keys (MPFB has expression targets), mouth interior and teeth.
- Body: the neck ring must match the body's neck ring for the same macros.
- Hair: colony-camera LODs (cap + a few big clumps); the white Goatee still hangs clumps beside the mouth
  corners that can read as fangs; ponytail tips are flat when seen from below; long hair will need the
  body/shoulders to collide with.
- Beards on the jaw need jaw-bone weights once the face rig exists (talking).
