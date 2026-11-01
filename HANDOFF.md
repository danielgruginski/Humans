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
- Keys added after the build (the orcs') go through `hum_faces.add_keys` + `hum_orcs.propagate_keys`, never
  `add_shape_keys` (it clears every key). New sliders are appended to `SLIDERS` and marked `PRESET_ONLY` unless
  every human should roll them: a rolled slider is a random draw, and a new draw shifts every seeded face after it
  (the game's named NPCs would all change). The C# generator skips `presetOnly` sliders the same way.
- The undead's shapes live in `hum_undead.DEFORMS` (hum_faces' `_bound` pulls them in on first use). A garment with a
  `make` (the Skeleton) builds its own LODs in `build_wardrobe`; `builds` limits it to those build names. The skeleton's
  rays start inside the body and go out (a cast back from outside met the arms first and the ribs reached out to them);
  the body ends at the neck, so its BVH includes the head's skin for the cervical spine.
- Blender image pixels changed in a session need `img.update()` before EEVEE shows them.
- Unity: `HumanSetup.ConfigureModel` reimports a model only when a setting changes. Reimporting every ~600 MB of cloth
  FBX on each rebuild ran the editor out of memory once (after a 2-day editor session), killing the rebuild.
- `hum_orcgear` sets `hum_plate.STYLES["Orc"]` when imported: reloading hum_plate drops it, so reload hum_orcgear (and
  then hum_cloth) after hum_plate; its builds hold the style object (`hum_orcgear.STYLE`), not a lookup.
- `HumanRig` carries the Hum_Idle action: a preview poses the arms down (not the A pose) until it is cleared.
- Saving after many garment rebuilds printed "Shapekey ... has an invalid 'from' pointer, it will be deleted": the
  replaced garments' orphaned key blocks, dropped on save (harmless).

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
- Eyeballs (fixed 2026-10-06): `_eye_unit` used to wind inward. Blender draws both sides, so it looked fine there,
  but Unity culled the eyes' front half and drew the inside of the back half, whose front-projected UVs repeat the
  iris: a hollow eye that "followed the camera", dark specks, and no eyes at all on orcs. Faces now wind outward.
  The shipped head was patched in place (`hum_head.retemplate_eyes`: the eyes are an affine image of the template in
  every key, so the map is fitted per key and applied to a new template, keys stay exact). Don't make the template
  much denser: Unity's area-and-angle weighted normals broke on tiny triangles round the front pole (a 4-degree first
  ring flipped the pupil normals). `hum_paint.IRIS_SCALE` 0.72 (the iris filled the opening once the real front
  showed) and the sclera is shaded toward the lids.
- Eye pass (2026-10-30, Daniel: faces look ugly, "something in the eyes"). Before: ball R 18.2 mm, opening 26 x 7.8 mm,
  iris 16.9 mm with a quarter hidden by each lid, gaze 4.6 deg down + 2.4 deg out per eye, unshaded whites. Now: ball
  R 15.5 (`hum_head.EYE_BALL`, `EYE_SHIFT`; `eye_verts` looks straight ahead), opening 28.2 x 10.8 mm (STYLE
  `eye-scale-incr` 0.5, `eye-height2-incr` 0.1), iris 14 mm (`IRIS_SCALE` 0.70), about 77% of it showing, IPD 61.4 mm.
  Measure with front ray casts (`hum_eyes.opening`): the opening is not a mesh boundary. `hum_paint` draws lash, crease
  and rim along the real lid margin (`Face.lid`, `lid_a`); `Face.eye` keeps the old helper sphere so brows, cheeks and
  crow's feet stay put. `Humans/Eye`: darker sclera, pink corners (`EYE_CORNER`, also in `hum_material`), lid shadow in
  T_Eye_Mask, a fixed catchlight (`_Catchlight`). T_Eye_Mask stays 256 (HumanSetup sets its import max).
  The shipped head was patched in place, no rebuild: `hum_eyes.patch(head)` (one run, guard `head["eye_pass"]`) and
  `retarget(old_targets)` add a constant skin delta to the basis and every key on Head + LODs and refit the eyes per key;
  the basis matches a fresh `all_coords` to 0.00016 mm. Install: Human_Body.fbx + the 3 masks + HumanEye.shader, reimport;
  Human.prefab references the fbx by fileID, so no prefab rebuild. Shots: `renders/eyes_unity_before_after*.png`.
  Left: the band 6-10 mm under the eye is real-time light on the lower lid, which faces down (surface recedes 3.5 mm
  over 11 mm); the painted fill (`lid_a["under"]`, +24%) only takes the edge off. MPFB `eye-bag-*` targets barely change
  it. Next idea: push the skin 1-2 mm forward in that band (a skin delta, same patch method). Also a dark sliver at the
  inner corners, visible only in close-ups.
- Mouth pass (2026-10-30, after the eyes). Before: 41.5 mm wide, upper lip 3.8 mm over the lower, seam 7.3 mm deep, a
  pout; a 0.5 mm slit from x 18 mm out and a corner vertex spiking down showed the dark inside as black hooks. Now: 46 mm
  wide, thinner upper lip with a bow and philtrum, less overhang (STYLE mouth targets), the corners about 1 mm above the
  middle. `hum_head.lip_seal` closes the slit in every built state (`LIP_LIFT`, vertex numbers on +x; rays through the
  seam 3 of 4600). `hum_paint`: one soft shaded line along the seam (`lip_seam`, `F.lip_xs/zs`), a shadow in each corner,
  light on the lower lip. `hum_mouth.py` holds the in-place patches (`seal`, `beards`: Beard_* and LODs follow the skin's
  move by nearest vertices, up to 3.3 mm). Basis matches a fresh `all_coords` to 0.00006 mm. Small dark ticks remain at
  the corners in extreme close-ups (faces the light can't reach; Unity preview's weak ambient overstates them).
  Shots: `renders/mouth_unity_before_after.png`.
- Nose pass (2026-10-30, after the mouth). Before: a triangle from the front, a beak in profile (STYLE `nose-volume-decr`
  0.55 + `nose-point-width-decr` 0.45), no wings, black slits in the nostrils. Now: MPFB's own rounder nose (only
  `nose-scale-vert-decr` stays), the tip 4 mm back. `hum_head.nose_form` runs in every built state: `NOSE_FORM` pushes a
  lobe out and creases its edge on each side (the wings), `_nostril_pits` replaces MPFB's folded pouch with a relaxed skin
  (`nostril_rings`, rings out from vertex 2548) and a pit `NOSTRIL_PIT` 1 mm deep. Keep the pit shallow: at 3.5 mm its
  walls go edge-on to the view and face away from the light, and the black slits come back; the mask was smooth and
  there were no back faces, so it was lighting on those walls, not paint. `hum_paint` makes the dark: NOSTRIL (MaskB's
  attribute bake, the free channel of `_hum_b`) into `shade`, a soft line in the crease, a little light on the tip. Nothing
  above 15 mm over the tip moved. Applied in place like the mouth (constant delta on Head, keys, LODs, Beard_*: the
  basis matches a fresh `all_coords` to 0.00006 mm); a full rebuild gives the same shape. Face sliders still narrow the
  nose a lot: `FEM_BIAS` NoseWidth -0.35, NoseTipWidth -0.3 (seed 2 rolls -0.62, -0.48). Shots: `renders/nose_before_after.png`.
- Face types (2026-10-30, Daniel's "random preset faces"). Sliders rolled alone made forty small unrelated changes, so every random face read alike. `hum_faces.FACE_TYPES` (12: Plain, Rugged, Long, Hawk, Round, Fine, Broad, Pinched, Snub, Severe, Soft, Jaw; odds per sex) adds a type's slider means at 0.75-1.2 strength, each face slider's own noise is x0.55 (FACE_NOISE), FACE_FLESH / FACE_OLD tie cheeks and neck to the Heavy/Thin roll and lips, lids and lobes to age. The type has its own RNG stream (seed * 1000003 + 12345), the main stream's draws are unchanged, so hair, clothes and body stay per seed; every NPC's face itself changes. C#: `HumanFaceGenerator.Random(cfg, seed, forceType)`, `FaceTypeOf`; config `faceTypes` + slider `flesh`/`old`, patched in both JSONs without a full re-export. Means can be tuned in the JSON with no recompile. FEM_BIAS narrowed nose eased (NoseWidth -0.2, NoseTipWidth -0.12). Test gotcha: re-rolling one prefab instance many times in one command drew stale pieces (hoods, brows) in some frames though the active pieces were right: use a new instance per shot. Sheets: renders/face_types_*.png.
- LOD neck (2026-10-30). Two causes, neither from the face passes. The gap: head and body LODs are decimated apart, their neck rims are different polylines, up to 2 mm apart: `hum_lod.neck_flap` adds a flap under the head's rim, 8 mm down and 3 mm in, inside the neck, with its rim vertex's keys and weights (Head_L1 +22 verts, Head_L2 +14). The V notch: Body_L2 had 10 cm "chest" triangles from the neck ring down the back (a face's region is its vertices' majority), hidden under any shirt: `hum_lod.neck_regions` makes a face touching the neck region neck (8 faces on Body_L2, none on L1) and `_sink` takes their far corners 5 mm in, or they poked through a dress at the shoulder. Both run in head_lod / body_lods on a rebuild; applied in place here. bmesh moves an extruded vertex twice in shape keys, so neck_flap writes keys with numpy. Sheets: renders/lod_neck_before_after.png, lod_neck_after.png.
- Skin detail (2026-10-31). `src/hum_skin.py` paints T_Head_MaskD (R warm, G cool, B gold, A grain 0.5 = none), run by `hum_paint.bake_head_masks`; object-space noise, so no UV seams, faded to nothing down the neck. HumanSkin.shader + hum_material apply it (WARM/COOL/GOLD_TINT, GRAIN: keep both in step). Age spots go into MaskB's age channel. Crow's feet removed on Daniel's word ("side eye wrinkles look bad"). The shader's _MaskD defaults to black, whose alpha reads as grain: a material on Humans/Skin without the texture comes out wrong (M_HumanSkin is the only one). His call: keep it as is, one material on every LOD (he floated LOD0-only or dropping it: at the game camera it can't be seen, renders/skin_unity_game_camera.png). Checked in Unity in preview shots (renders/skin_unity_faces.png, skin_unity_presets.png: orc, zombie, ghoul, elf, demon, giant, lich); ghoul through GhoulCheck.Ghoul (M + F, body, rags, claws: renders/skin_unity_ghoul.png) and the dwarf too; not play-tested. Gotcha for test shots: `ApplyPreset` alone on a random person keeps an outfit with no pieces in the preset's build, whose regions still hide the body: a floating head. Dress through HumanActor, as the game does.
- Re-exporting Human_Hair.fbx: the pieces in Resources/HumanPieces store bone lists by name, and the old fbx (2026-10-24)
  had 102 bones against today's 131. A skinned mesh whose bone list doesn't match its bindposes draws NOTHING, no error.
  The mouth pass rewrote the lists on the 23 hair/beard/brow pieces in place (bones from the fbx's renderers). Four test
  scenes keep saved hair renderers with the old lists and show no hair until rebuilt: Creatures_Test, Riders_Clips,
  Riders_Test (and Humans_Showcase, rebuilt 2026-10-30 with the new `Tools/Humans/Rebuild Showcase Only`: scene alone,
  stops if other scenes are open or unsaved. It also saves faces, so it needs this after a change to the face rules). `hum_export.export_hair` also takes every piece in HUM_Hair,
  now including the strand cards that ship in Human_HairCards.fbx (178 MB instead of 88): export the old 65 by name until
  the spike joins it.
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
  3 cm outside the legs at knee height; split by `_mid` since 2026-10-28, below) + `_knee` (-> the hem) + a weightless
  `_hem` tip. Weights: two
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
  Cost (2026-10-12, MedievalSetting's bandit road at 12-40 fps, the profiler: HumanSkirt.LateUpdate 30.7 ms of a 40 ms
  frame for 17 people; the belt, tunic, jerkin, gambeson and hauberk all hang, so nearly everyone runs it): the leg
  capsules are now read once a frame (they were read per column, point and pass: thousands of transform reads a
  step), at most two steps a frame (it had caught up to four, so a slow frame made the next slower), and it rests
  while none of the character's skinned meshes is drawn (off screen and out of the shadows; it starts afresh when
  seen). Installed into MedievalSetting by copying the script. The same evening `HumanSpringChain` (the cape's links:
  the same pattern, much smaller -- 3 links against 6 capsules, about 300 transform reads a frame per cloak, on screen
  or not, catching up to four steps) got the same treatment: only while drawn, the capsules read once a frame, the
  link lengths once a frame, at most two steps.
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

- 2026-10-10: **the undead** (Daniel: "do the same [as the orcs], but with zombies and skeletons"; his picks: rotting
  villagers, models + the Unity install; README "The undead"). Undead builds + six new preset-only keys (in place),
  all 65 human garments built for MUndead/FUndead, rot masks, torn clothes in the cloth shader, the Zombie and Skeleton
  presets, the skeleton garment (`hum_skeleton`). Exported (every cloth family + Human_Cloth_Undead.fbx), installed in
  MedievalSetting, prefab rebuilt (685 pieces); checked in Unity in edit mode and walking (Logs/Undead). Pushed as 2730c31.
  Daniel later said he expected the zombies first and had been eyeing an Asset Store pack; the skeleton is fine "if it is
  low poly" (8.5k / 3.4k / 2.0k).

- 2026-10-11: **zombie clips** (Daniel: "can you give them animations like limping or having a hard time walking? also,
  slam attacks for zombies, or bite attacks, Skeletons could use the human animations though" - he raised own clips
  again himself, for the zombies). `hum_zombie_anim.py`: Idle, Limp, Shamble, Slam, Bite (README "Zombie clips"),
  exported, Humans_Motion states 21-25, checked in Unity play mode (frozen frames). Pushed with the undead (2730c31).
  Later that day, when they became game creatures (MedievalSetting's Shepherd Downs and the Hollow Barrow): Limp and
  Shamble re-timed to 40 frames at 0.75 / 0.85 m/s, the speeds the game moves them at, so their feet do not slide
  (Shamble's shuffle lifts 4 cm); re-exported and copied to MedievalSetting.

- 2026-10-12: **rags** (Daniel: "another clothing option for humans - rags. This will also be used to improve the zombie
  clothing, naturally"). `hum_rags.py` (README "Rags"): RagShirt, RagTunic, RagTrousers on all ten builds, cut ragged
  in the geometry and torn on the living too (ClothData alpha = 1 - rag; HumanCloth `_TatterRagTile`, a coarser hole
  field: fewer, bigger rips). Exported `Human_Cloth_Rags.fbx` + config, installed in MedievalSetting with the shader
  (prefab rebuilt, 30 rag pieces); its zombies and barrow skeletons wear them, and the character maker has two rag
  outfits. Iterations Daniel didn't see: the shirt tucked under the trousers (offset grows by the hips), straight
  edges (cut after the shell), an "underwear" hem following the crotch (a skirt-loft tail), crenellated steps
  (`_tear_hem` moves vertices), regular teeth (random widths and notches), many small rips (RAG 0.32, tile x5),
  the tunic's torso ending just above its skirt (a ring of what is under showed; now 4 cm below the hips).
  Unity renders (the game's undead outfits, front mirrored, and from a game-like height): `renders/undead_rags_*.png`.

## Humanoids test scene (2026-10-31)
MedievalSetting `Assets/Game/HumanoidsTest/Humanoids_Test.unity` shows every human def, random people, the races, the goblins and the troll, built from GameRules (Tools > Game > Checks > Build Humanoids Test Scene; Humanoids Test Renders checks each unit, Logs/HumanoidsTest/). It plays bought clips and stays in Assets/Game, so the itch packs never carry it; the pack's own scene, with no animations, is `Humanoids_Catalog` (built by `itch/_tools/unity/HumanoidsPack.cs`). `HumanFace` no longer lifts its model for a build: the moved bones already keep the feet down (the game's `HumanLift` may still sink builds in play, see POLISH.md). Not played yet; POLISH.md has what it found. Its sheets run the cloth sims; Humanoids Cloth Poke counts leg mesh edges through hanging cloth (Logs/HumanoidsTest/cloth_poke_L0.txt, cloth_poke_clips_L0.txt; `own: true` runs this pipeline's clips instead, cloth_poke_clips_own_L0.txt). The count skips what arm bones move: by distance alone, hands by the thigh or on the lap counted as legs, which inflated the first figures (262 held was really 64, own idles' 400 were all fingers). Idle held: 9469 bare -> 64 with the sim, 101 of 105 units clean. Whole clips, worst moment of each: own 6421 (403 of 532 clean; idles clean), bought about 20500 (264 of 524 clean); both still cross on deaths and knockdowns, sitting (own) and long hems on the feet. `HumanClothPush` now pushes a hanging garment off the feet too (no prefab change: foot -> ball, no rest), which cleared most robes' and dresses' hems; the blind Prior's shoe still catches the trim (cause not looked into). Sitting still puts a thigh through a robe just under the belt; shrinking the thigh's rest capsule when seated changed nothing, so it was taken out (cause not found).

## Skull pass (2026-10-31)
Daniel: "the skull for liches and skeletons ... looks weird". It was one long ellipsoid with a small block for a face, rods for the brow and arches, a thin strap of a jaw, and tiny teeth under the maxilla. `Skel.skull` is rewritten, measured off the same head: the vault is three bones (parietals, frontal, occipital) with flatter sides, capped at 2.64 x its half width (the head's full length read as an egg from the game camera); a solid mask round tapered, tilted orbits; temples carved behind them; cheekbones as a plate with a buttress down to the molars; a ribbon arch standing free; a pear-shaped nasal opening with a septum (LOD0); a maxilla that stops above the teeth; a square-chinned mandible with broad rami; 12 + 12 tapered teeth (LOD1 merges pairs, LOD2 threes, so far away the mouth isn't a hole); a smaller light further back in the orbit. Triangles 9.0k / 3.5k / 2.2k (were 8.5k / 3.4k / 2.0k). `LichCrown` re-fits itself: rebuild it after the Skeleton. The crown stands up to 9 mm off the skull (13 mm on the female), from `hum_lich.ring`'s support measure, which is unchanged.

- `decimate_mirrored`: over the whole mesh the collapses chewed one orbit's rim and folded triangles there, on one build and not the other, which rendered as black slits. Now one side is decimated, edges folded past 135 degrees collapse, and it is mirrored. Blender's own Decimate symmetry left dents along the midline, so it isn't used. FUndead L2 keeps 2 non-manifold edges (no visible effect).
- `HumanSetup` set every texture in Assets/Humans/Textures on each rebuild, and its `path.Contains("Strands")` caught Textures/HairEdge/*Strands.png (256 px clamp became 1024 px repeat). It skips HairEdge now; the 21 metas were restored from git.
- Checked in Unity preview shots only (Logs/Skull, male, female, lich, close up and at the game camera), not in play and not with helmets or hoods on. Installed: Human_Cloth_Undead.fbx, HumanSetup.cs, Rebuild Prefab Only. The itch humanoids pack still has the old skull. Blender scene `SkullPass` holds old and new side by side.

## Hood pass (2026-11-01)
Picked from my list of graphics fixes, Blender only because another session had the Unity editor. POLISH.md: cloth hoods make a face look long; the Cloak's and ElvenCape's collars ride up to the chin.

- `hood_profile` (shared by CloakHood and the coifs): the opening reached 11 cm over the eyes, near the top of the skull, and was 62 deg wide, a tall pointed slot. Now 7.5 cm over the eyes, 68 deg, flat over the brow and closing round the jaw. `HoodCut.x` on all 108 hair and beard pieces rewritten to match. Don't use `hum_armor.write_cap_coords` to refresh it on its own: it zeroes `HoodCut.y`, the strand styles' parting.
- The hood's crown had a real hole: the fan on top was wound against the rows (in Unity, backface culled), and the rows under the seam were long slivers (now a small fan, 12 mm lower, `peak` hoods only). A closed ring's two ends could round to different weld cells, which left a slit on some builds (now one point). All 48 hoods and coifs: 3368 tris, no open edges on the crown.
- `_cloak`: the collar sat level all round at neck + 5 cm, above the chin on every male build (up to 3 cm on dwarves), and the clasp with it. Now it falls in front to 1 cm over the hood's hem (`_hood_hem_front`), sides and back as before. `_collar_clear` replaces nothing in the hull: it moves the collar rows out to what really lies under them, and raises the back and side rows over the traps (cleared the orcs' shirt patches). Two more collar rows: Cloak 2540 -> 2740 tris. The hood's collar is capped 5 cm past its neck ring (`peak` only; it spread in points on orcs). **Build CloakHood before Cloak**: the cape reads the hood, and `GARMENTS` lists Cloak first.
- Left: on orcs the wide neck hole shows the shirt between the hood's collar and the cape, and the collar's edge is a little ragged; the opening shows the ear tips from straight in front. The leather `Hood` has its own cap + aventail and doesn't make a face long, so it wasn't touched.
- Checked in Blender only (scene `HoodPass`, plain materials, rest pose: `HP_Old` / `HP_New` rows, pairs in `HP_Sheet`; `renders/hood_pass_*.png`), every build for the hood and cape, LOD1 and LOD2 on MSlim, hair by faces kept on four styles. **Not in Unity, not animated.**
- **Exported but NOT installed** (Unity was in use): `export/Human_Cloth_Cloak.fbx`, `_Elven`, `_PaddedMail`, `_Plate`, `Human_Hair.fbx`. To finish: copy them to MedievalSetting Assets/Humans/Models, Tools > Humans > Rebuild Prefab Only, look at the game camera. `itch/_tools/unity/HumanoidsPack.cs` `SoftHoods` can then lose its hoods, and POLISH.md its line.

## Curves pass (2026-11-01)
Daniel: "the default female body is kind of stale, can you make it curvier? Like a prettier silluette?", then "larger breasts? Nothing major". Blender only, another session had the Unity editor.

- Waist and Hips can't do it. `Waist_Neg` moves the belly and back (11 mm in depth, 3 mm from the side), `Hips_Pos` keeps the widest point at the crotch and grows the shelf on top of the seat. `hum_curves.py` adds a body key, **`Curves_Pos`** (`@curves`, PRESET_ONLY): `PROFILE` gives what the silhouette gains per height, measured on FSlim, placed by the hip and chest bones. `bust_delta` adds upper fullness and all-round volume. No joint deltas, no key on the head. A deform runs before `full_coords` grounds the body, so its absolute heights are wrong there: keep them relative to a bone (the first cut's bust landed 1.9 cm off for this reason).
- Builds: FSlim `Curves_Pos` 1.0, FStrong and FHeavy 0.85, all three `Bust_Pos` 0.42 (was 0.16). The races' female builds and all male builds keep their bodies. FSlim from the front: waist 21.8 -> 20.0 cm, hip 34.6 -> 34.8 cm, ratio 0.63 -> 0.57, the hip's widest point up from the crotch to the hip; the bust stands 1.9 cm further forward.
- Rebuilt in Blender timers (`bpy.app.timers`, a few garments per tick): FSlim 72, FStrong 71, FHeavy 70 garments with LODs, 25 min. **Capes last**: `_cloak` reads every garment under it, so CloakHood, Cloak, KnightCape, ElvenCape go after the rest of the wardrobe.
- `hum_cards.build_fit` on the draped hair (LongStrands, LongThinStrands, SidePartStrands; LOD0 + L1): rows inside the body or shirt on the three builds ~300 -> 0, it adds `Curves_Pos` to the pieces itself. Clear `_BUILD_FIELDS` for changed builds first. Its blur also moved the men's long hair up to 2 cm (no new clipping; MOrc improved). `hum_orcs.propagate_keys` needs the window on scene `Faces`: from another scene it fails with "surface deform bind failed".
- Checked in Blender only (scene `CurvePass`, plain materials, rest pose; `renders/curves_*.png`): chest clearance over the breast's apex on 18 torso garments on all three builds, at least 3 mm (Shirt) and no nipples through. LOD1 and LOD2 by ray count: LOD1 Shirt 1 mm; a few chest vertices past the cloth at the side of the bust on the LOD2 Shirt (FHeavy 3 of 43, FStrong 1, and FOrc 1 on an unchanged build) and at the side of the LOD1 PlateCuirass (FSlim 2 of 98). Left as they are. **Not in Unity, not animated.** Motion may show new leg and hip crossings: run Humanoids Cloth Poke.
- **Exported but NOT installed**: `export/Human_Body.fbx`, `Human_Hair.fbx`, every `Human_Cloth_*.fbx` written 2026-11-01 (BlackKnight, Cloak, Clothes, Elven, Gothic, Leather, Ornate, PaddedMail, Plate, Rags, Robes, Wings), `human_face_config.json`, `human_rig.json`. This set includes the hood pass. Install them together, the new body in old clothes pokes through: copy to MedievalSetting Assets/Humans/Models, Tools > Humans > Rebuild Prefab Only, look at the game camera.
- The itch humanoids pack and the Items pack's armour drops still have the old body; the armour icons too.

## Open / next

- Zombie clips: not in the game yet - zombies aren't creatures; a creature would take them through a clip set
  (CreatureAnim's BeastAnimationSet-style pools: Idle, Walk = Limp or Shamble, Slam, Bite; Hit and Death from the
  human clips). A long dress flares up when the slam doubles the zombie over (the skirt ring pushed by the deep knee
  bend). The reaching arms are straight-ish IK (no wrist/finger animation beyond the claw); the bite has no jaw (no
  jaw bone).
- Undead: from the game camera the zombies' painted holes read as light speckles more than tears (2026-10-12: the
  rags answer it for the game's zombies - big rips, torn hems; whole clothes on a zombie still speckle); the hunch is mild under the walk clip (no zombie clips: bought Humanoid packs
  would carry the shamble); skeletons in full shirts still show a body's volume (rags, belts, mail and helms read better
  than whole clothes; the game's skeletons wear rags since 2026-10-12). No game creatures
  yet (that comes with the barrows/crypts).

- Rags: the tunic's skirt top stands ~8 mm off its torso, so from above you see a little into the ring (the plain
  Tunic's too); over a RagShirt a thin pale line of the shirt's tail shows there, like a waistband. The cuts are one
  seeded shape per garment (every rag shirt has the same short right sleeve): a second seed would be another garment
  (RagShirt2) or a per-character mirror.

- Robes: no hood (the first proposal had one up or down) and a sash rather than a rope belt. Looking down into
  the neckline from close above shows a thin dark line of the robe's inside between skin and binding (any shell
  garment's; at the game camera it reads as the collar's shadow). The shared torso/sleeve seam binding runs over
  the shoulders as on every sleeved garment.

- Orcs (2026-10-10, Daniel: "what about working on the orcs in blender?"): the Orc builds and shapes are done
  (README "Orcs"); the orc gear too ("go ahead with the orc armour": README "Orc gear", `hum_orcgear`), installed and
  worn by the game's orcs. Next on the list: crude orc weapons and the horn-blower's war horn in the Weapons kit.
  Open: no asymmetric pauldron (one big spiked one); the mantle can't go over a breastplate (it would need to stand
  off what is worn under it, like the plates' `_under`); orc gear exists for the Orc builds only. Grey hair in the Buzz cap reads as a
  knitted cap; brows are faint on dark green skin at the game camera. Orcs use the humans' clips (no stoop).

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
  thickness 0.05). 2026-10-27 (Daniel: skirts "kicked back" when moving): a leg's push no longer turns into speed
  (`kick` 0.3: Verlet had flung the cloth on past the heel) and a heel just below the knee point moves that point
  too (`drape` 1, a segment collision: the hem had swung out round it at up to 5x the push). Walking, the pointed
  flap at toe-off is gone (back hem 0.63 -> 0.50 m behind the hips at most); running, the hem no longer flips to
  hip height, but a long dress still stands out behind like a bustle (the run's stride is longer than the dress;
  a 25-40 deg cap on the back columns was tried: little gain, feet through the cloth). HumanHelperBones still
  carries the old panels' hang / raise code (unused now).
- Cape chain (2026-10-27, "the way cloaks hang is weird"): the cloak's cut stands off the back like a shell (the
  hull takes in arms swung back 30 deg; the chain's tail is 36 cm behind the pelvis). HumanSpringChain now turns
  each link `drape` 0.75 of the way to hanging straight down, fading back to the cut between `trail` 1.8 and
  3.4 m/s (so it still streams out at a run), and keeps the cape outside a worn skirt's ring (a dress poked through).
- Cape re-cut (2026-10-27, same evening): the hull takes in the arms hanging only (`hum_cloak.ARM_SWING`, also
  hum_plate `_back_cape`), flare 0.07 -> 0.045, 1 cm closer below the shoulders, and no wings in `_worn_under` (the
  angels' folded wings had stood MSlim's cloak 4 cm further off). Cloak (12 builds), ElvenCape (6) and KnightCape (12)
  rebuilt: the back now lies over the outermost garment it must clear (the hauberk: ~5 cm off a tunic, 8-10 cm off
  bare skin) - seat 0.33-0.37 -> 0.19-0.21 m behind the spine line, hem 0.40 -> 0.28; from behind 0.70 -> 0.61 m wide
  (KnightCape 0.86 -> 0.62). xh_cape_0..2 moved onto the new back line (y only, so the weights didn't change;
  `hum_helpers.sync_bones` now moves offset helpers too). Exported Human_Body.fbx (new `hum_export.export_body`),
  Human_Cloth_Cloak/Elven/BlackKnight.fbx (the only families weighted to the chain) and human_rig.json; config
  unchanged. Unity HumanSpringChain: `drape` 1 now means the hanging pose keeps the cut's link directions as on an
  upright body (`facing` + `restDirs`, set by HumanSetup) instead of turning with the torso - rigid on spine_03 the
  walk's sway swung the hem 6-12 cm side to side like a board; it fades to `stream` 20 deg back at a run (`trail`);
  the spine/pelvis capsules (`torso`) never push a point further out than the cut (their radii are wider than the
  close cut); a skirt's ring pushes the chain straight back (it had shoved it sideways at a walk). Checks:
  MedievalSetting Logs/ClothMotion `cut0_*` (before), `cut2_*` (after), `*_views_*` (6 angles incl. from below);
  Blender scene CloakCut in humans.blend (old red, new blue, per build). Open: a long dress's hem still swings 0.5 m
  behind at a walk and lifts the cape with it (the skirt sim); the arm swinging back passes beside / under the side
  panel (no poke-through seen in the walk or run strips). MedievalSetting's Riders_Test / Riders_Clips scenes hold
  baked (unpacked) humans with the old chain bones and bind data; their chains are off (no cloak) - re-make them if a
  rider ever wears one.
- Cape side chains (2026-10-27, night; Daniel: "when the arm swings backwards it clips over the cloak"): two more
  chains, `hum_helpers.CAPE_SIDES` xh_cape_l/r_0..2, at `CAPE_SIDE_X` 0.24 out (the game's clips hang the hands 26-29 cm
  out and swing them up to 12 / 29 cm behind the root at a walk), same heights and hosts as the centre (so the in-place
  re-weight shifts nothing). `hum_cloak.with_chain` splits the cape from the centre (|x| < 4 cm) to the side chain
  (|x| > 24 cm, the edges); `top_bones` caps cape rows at 4 bones (they reached 6). `sync_bones` added the bones (108),
  `reskin` re-weighted all 90 cape meshes in place; exported Body, Cloak/Elven/BlackKnight, rig json (`springs` with
  `side`). Unity: one HumanSpringChain per spring; a side chain also gets upper arm / forearm / hand capsules with
  `pushBack` (push the point straight back, so a hand just outside the chain lifts the cape over it rather than pressing
  it in); HumanFace / LookPreview / ClothMotionCheck handle all chains. The upright drape is now taken in spine_03's
  frame without its lean (`upLocal`, `backLocal`, `restDirs` in that space; `facing` gone): it keeps the torso's
  twist (the side panels had stayed put while a combat stance turned the torso) and never turns a link forward into a
  back bent forward. Checked: game-camera close-ups (MedievalSetting Logs/ClothMotion `gamecam_centre.png` = sides
  rigid vs `gamecam_sides.png`: the walking man's arms no longer bulge through the sides, the running arm no longer
  lies over the cape), `cut3_*` strips and views. Open: deep attack lunges (attack_1h clip 1) bend the back through the
  cape at the belt and the tunic shows (the 3-link chain is straight between shoulder blades and waist; link-middle
  collisions were tried and didn't help); a raised elbow in the combat stance shows over the cape's shoulder from a high
  camera (legit, above it). The creator's "cloak in the wrong spot" didn't reproduce (renders match the game).
- 2026-10-28 (Daniel's in-game shots: club + shield, the right elbow through the cape's side in the combat stance):
  the side chains start higher, root at the top of the shoulder blades (z 1.20 rest), first point at elbow height
  (0.98), then 0.64 and the tip 0.30 (`_CAPE_SIDE`); the old first point at the waist was 15 cm below a bent elbow, so
  the straight panel above it was pierced. `with_chain` now takes each chain's own heights (where it takes the spine
  part over, and its link blend). Arm capsules 3 cm over the limb (0.085 / 0.075 / 0.075): an elbow out in the combat
  stance passes the chain further out. Exported Body, Cloak/Elven/BlackKnight, rig json; installed, Rebuild Prefab Only.
  Check (combat stance + shield-guard layer, steep camera behind; arm drawn over the cape, frames): heavy man 29 -> 4,
  woman 5 -> 0, runs 8 -> 6 and 10 -> 1 against the side chains held still; the strong man's elbow stays out beside the
  cape's edge in that stance (outside it, not through). MedievalSetting Logs/ClothMotion/compare/arm_combat.png.
- Cape grid (2026-10-28, Daniel: "any chance we could increase the number of bones on the clothes?"): the three chains
  became `hum_helpers.CAPE_COLUMNS`, five columns (the middle, 12 and 24 cm out each side: xh_cape_*, _lm_*, _l_*,
  _rm_*, _r_*) of four links each (16, 18, 24, 30 cm: 1.18 -> 1.02 (elbow height) -> 0.84 -> 0.60 -> 0.30 m at rest), the
  nodes on the cloak's back line (`_CAPE_Y`, the builds' mean per column). `CAPE_SIDES` / `CAPE_SIDE_X` are gone.
  `with_chain` shares a row between the columns either side by x and between the links by height; `top_bones` keeps
  4 bones with the arm's (upperarm, deltoid) favoured x3 - the 4-bone cap had dropped the arm share at the cape's side
  from 0.085 to 0.016. Rig json `springs` carry `tip` (the last link against the one before: HumanSetup had
  extrapolated the tail 6 cm high). Unity: one HumanSpringChain per column; every column off the middle gets its
  side's arm capsules (`pushBack`); `neighbours` + `stretch` 1.15 keep columns from parting (a pushed column drags the
  next). Check: the combat-stance count (arm drawn over the cape) is 17 frames of 41 on the heavy man against 4 with
  three chains, but the renders look the same (edge frames along the cape's border); runs and walks unchanged. Open:
  attack_1h's lunge still bends the back through the cape at the belt.
- Skirt ring in three links (2026-10-28, Daniel: "skirts could also have at least 3 links, with different sizes, the
  links closer to the waist are smaller"): `xh_skirtNN_mid` between the hip pivot and the knee point, 40% of the way
  down (`RING_MID`, offsets from the thigh on the column's side, so it takes the thigh's per-build delta): links 14 /
  22 / 32 cm in front, 13 / 19 / 32 behind; the knee link is the mid link's child now (`sync_bones` re-parents). Weights
  (`redistribute`): hip link above the mean mid height, a 10 cm band to the mid link, the old knee band below - still
  at most 4 ring bones a row (all 545 skirted meshes re-weighted in place, `rest_shift` keeping the build fit).
  `ring_slack` measures three links (hip at the mid joint's height, mid at knee height, knee at the hem); config
  `skirtSlack` has `hip`, `mid`, `knee` (the old `hip` value is the new `mid`). Blender `_ring`: the mid link turns with
  the hip link seated. Unity HumanSkirt: three Verlet points per column (mid, knee, hem), each link elastic
  (`elasticHip` for both upper links), the neighbours' limit and `kick` on all three; a leg still pushes the hips-to-knee
  line as one link turning round the hips (the mid point rides along at its share) and the knee link with `drape`, so
  the cloth session's tuning holds - only the cloth's own swing bends the mid joint. `SlackDown`: a short skirt (a
  tunic, no cloth at the mid link) uses its hem's slack there. HumanSpringChain keeps the cape off all three links.
  Exported Body (131 bones), Clothes, Elven, Leather, Orc, PaddedMail, Rags, Robes (every family with a ring skirt),
  rig json, config; installed, Rebuild Prefab Only; the avatar's mapping is unchanged. Cloth Motion (FSlim dress): walk
  0.49 / 0.27 m behind the hips (2 links: 0.50 / 0.26), run 0.54 / 0.38 (0.55 / 0.39), highest hem the same - the
  strips look alike (MedievalSetting Logs/ClothMotion `skirt3_*`, sheet `skirt3_vs_before.png`). Still as before: the
  get_up clip lifts the legs out of a dress lying down (the ring hangs in the character's frame).
- Cloak shoulders (2026-10-28 evening, Daniel: "the cloak has bones on the shoulder area? Because I think that is the
  area that is failing to move when the arms move, causing some clipping issues"). Two causes, both fixed:
  (1) the cut: `_worn_under` left out every under-garment point more than 2 cm past the shoulder joint (the arms are
  the hanging-arm proxy's), the shoulder caps too, so a tunic's sleeve top stuck out through the cloak's side over the
  deltoid even at rest (MStrong, MHeavy, FSlim, MSlim...; ray test from the shoulder joint). The caps (within
  max(11 cm, 0.55 x the joint's x) of the joint, from 5 cm below it up) are in the hull now; Cloak (12 builds) and
  ElvenCape (6) rebuilt (`build_wardrobe`, the window on the Faces scene). MOrc keeps 3 cap points (1 cm).
  (2) the weights: the cloth on the shoulders and the upper arm followed the arm ~55-70% (shoulder_share capped at
  0.85, then 6 smoothing passes) and never the clavicle, while the sleeve under it does both. `reskin` now gives the
  arm share - and the cloth lying on the shirt above the cape grid's roots (within 7-10 cm: the cloak is cut to clear
  mail) - the build's own Shirt rows at each vertex's nearest point (`under_rows`, `smoothed_cape_weights`: spine and
  grid smoothed 6 passes, the arm share 2; `top_bones` also favours the clavicles). KnightCape re-weighted the same
  way (not rebuilt; strips over the Black Knight set look as before). Check, MStrong in the tunic outfit (Unity, shirt
  and tunic points above 1 m that lie outside the cloak, mean per frame; old -> new): rest 0.4 -> 0, walk 1.9 -> 0.1,
  run 25 -> 24, combat stance + shield 54 -> 7, attack_1h 37/116/54/39 -> 24/37/9/24, above 1.25 m none left (old up to
  63). Sheet: MedievalSetting Logs/ClothMotion/shoulder_fit_before_after.png. Cloth Motion numbers unchanged. Left: the
  run's arm swinging back still shows at the back of the shoulder; MOrc's tunic collar shows behind the neck at rest.
  Gotcha: after an FBX swap whose meshes use other bones, Rebuild Prefab - the pieces kept the old bone lists and
  skinned garbage.
- Thighs through a tunic's front (same report: "frames where the thighs are raising beyond the part of the long shirt"):
  not fixed. The pokes sit just below the belt (0.67-0.77 m), on rows 100% on the hip links: a thigh raised past ~50 deg
  (run, attack lunges) comes up in front of the ring's pivots, and links turning round a fixed pivot can't clear it.
  Tried and taken out: the mid joint riding the thighs (no effect, even with no slack) and sliding the pivots out by the
  thigh capsule's reach (parted the front columns into a slit with the thigh in it: more pokes). Next idea: the tunic
  rows just under the belt take a share of the thigh in front (a partial, local return of the panels Daniel rejected).
- Buffers (same evening, Daniel: "making the arms and thighs a tad larger when calculating the cloak"): HumanSetup's
  arm capsules on the side cape columns 8.5/7.5 -> 10.5/9.5 cm and the skirt ring's thigh capsules 5.5 -> 7 cm. The
  cape and every skirt hang exactly as before at rest (Cloth Motion: same cape tip, dress, robe and mail idle numbers;
  hems rise 4-5 cm more at a run). His outfit, poking points per frame: arms run 24 -> 19, attacks 24/37/9/24 ->
  19/26/6/20, combat stance 7 (unchanged: not the simulated part); thighs run 3.7 -> 3.2, attacks 7.4/10.4/4.1/8.0 ->
  6.2/8.8/3.8/7.2. A fatter hanging-arm proxy in the cut (6 -> 7.5 cm) changed no vertex: below the armpits the cloak
  wraps only behind the arms (CLOAK_SPAN) and the shoulder caps are the sleeve tops now - not kept.
- Shields (same evening, Daniel's screenshots of a run with the plank shield): the clipping he still saw was the shield
  on the forearm through the cloak's side - the cape knew the arm only. MedievalSetting PlayerModel.ShieldCloth (game
  side; player and NPCs both go through SetShield) adds three pushBack capsules down the worn shield's long side to every
  HumanSpringChain (ends are child "ShieldCloth" transforms on the prop; removed with the shield), radius = a sixth of
  its width + 10 cm (a side column carries the cloak's edge ~9 cm out past its point: without it the shield touched the
  cloth but never the point). Plank shield in his outfit, shield vertices inside the cloak per frame, no colliders ->
  installed: standing 60 -> 5.6, walk 29 -> 5.9, attacks 12.7/11.0/3.4/4.6 -> 4.6/6.9/3.3/5.6; the run stays ~19 (its
  back swing reaches the rows that ride the upper arm, not the simulated part). Sheet: MedievalSetting Logs/ClothMotion/shield_cloth_gamecam.png. Any other held
  prop that swings behind (a backpack? a quiver?) would need the same. (The shield numbers here were mis-measured: see
  the metric gotcha below. The renders are right.)
- Push-out on the GPU ("approach A", 2026-10-28, Daniel: "take a step back... proper cloth simulation?"; his order: A,
  then D = our own GPU cloth sim, skipping Unity Cloth and Magica). HumanClothPush (on the prefab, from HumanSetup) +
  Humans/Cloth `ClothPush`: every cloak vertex, and a hanging garment's hanging part (uv1.x = 0), is pushed out of the
  limbs' tapered capsules (upper arm, forearm, hand, thigh, shin; radius = the thickest worn piece's 90th-percentile fit
  round that bone + 6 mm, `HumanPiece.limbs` measured at setup) and the shield's (`SetProp`, from PlayerModel), by how
  much deeper it sits than its rest position (uv2/uv3) lay in the rest capsule - cloth that hugs a limb at rest stays.
  His outfit (MStrong, tunic + cloak + plank shield), points poking out per frame, off -> on: thighs through the tunic
  run 4.5 -> 0.3, combat stance 9.8 -> 0, attack_1h 9.0/12.4/8.8/11.3 -> 0.5/4.7/0.9/0.5; shirt/tunic through the cloak
  run 9.7 -> 1.9, combat stance 6.4 -> 3.0, attacks 11.6/13.8/2.9/11.8 -> 8.9/11.1/3.6/11.2; shield unchanged. Sheets
  (Logs/ClothMotion): pushA_hips_zoom.png (the skirt's dark thigh patches gone), pokes_where_A.png (what is left: red =
  shirt/tunic, yellow = shield, blue = thigh). Left: an arm raised high or swung back comes up through the cloak's
  shoulder cap (the overhead attack, the shield arm in guard); a shield passed through the cape stays on the wrong side
  (a stateless push can't tell); the shield count mostly counts a shield lying over the cloak, which is right.
- **Metric gotcha (cost an afternoon):** `SkinnedMeshRenderer.BakeMesh(m, false)` + `transform.TransformPoint` scales a
  human's skinned positions twice (the Clothes node is at the build's 1.105 scale): up to 16 cm off at the shoulders.
  Skinned-vs-skinned poke counts stayed comparable (both off alike), but anything against a real world position - the
  shield, capsules, a sim - was wrong, and A first looked useless. Use `BakeMesh(m, true)` + `TransformPoint`.
- GPU cloth sim spike ("D", same night, not in the game): Runtime/HumanClothSim.cs + Shaders/HumanClothSim.compute;
  Humans/Cloth draws `_SimOut` (world position + normal per mesh vertex, by SV_VertexID: `HUMAN_VERTEX_ID`, target
  4.5) when `_SimOn` is set, the push-out otherwise. The skinned cloak is the target; particles (welded vertices) follow
  it with a damped offset, keep its edge/bend lengths (Jacobi), stay within a max distance (1 cm on body bones, 12 cm on
  the cape's chains), and are pushed out of HumanClothPush's capsules (`Capsules`) and off the worn layers' nearest
  skinned points (shirt, tunic, trousers, body/head where shown; `BuildLayer` samples 2 cm cells). Skinning matches
  Unity's exactly (0.00 cm). Not wired: HumanSetup/HumanFace don't build or bind it (`BuildCloth`/`BuildLayer` are
  editor-only; a check binds it by hand); per-piece data would go in HumanPiece at setup, the body per build. First
  numbers vs off: run sleeves 9.7 -> 2.4, but combat stance 6.4 -> 13.5 and attacks 11.6/13.8/2.9/11.8 ->
  8.5/11.7/4.1/13.9 - untuned (the layer push and the capsules fight the shoulder rows).
- Sim tuned (same night, Daniel: "let's try it"). MedievalSetting Tools: `ClothPokeCheck.Run(variants)` (editor script
  next to ClothMotionCheck) counts shirt/tunic/shield points out of the cloak per frame for off / A / sim variants, with
  one normal source for all (the welded faces' average: the authored normals alone moved counts by a third). Sum over
  run, combat stance, attack_1h 1 and 3: off 46.2, A 31.7, sim first cut 33.5, sim without capsules 29.6 (the layers do
  the work), now 25.8 = defaults in HumanClothSim: 6 substeps x 4 Jacobi pairs, layer gap 8 mm, deep 6 cm, capsules
  2 cm thinner than the fits (full size they push the cape at rest). Per clip A -> sim: run 3.1 -> 3.6, stance 6.8 ->
  6.1, attacks 10.7/11.2 -> 8.8/7.3. Sheet Logs/ClothMotion/sim_vs_A.png (top A, bottom sim): draws clean. Compute
  normals face the skinned ones (a face wound the other way no longer flips one).
  To try it: play mode, Tools/Game/Checks/Cloth Sim on the Player (Ctrl+Alt+C) - the player's cloak simulated, again:
  back to A; it rebinds when the clothes change (`HumanClothSim.Follow`, editor only: the data is built from the
  meshes). Not in builds yet: the data must move to HumanPiece at setup (and the body per build).
- Daniel's play test (2026-10-29): "I could not see a difference" between A and the sim. Editor.log: the second
  Ctrl+Alt+C bound and ran clean; the first was pressed with no cloak bound yet, and the rebind from LateUpdate failed:
  the Human FBX meshes are not Read/Write, and play mode refuses their vertices inside the player loop (a menu call
  reads them fine). Verdict: the sim buys nothing visible over A at far more cost. PARKED (his call, 2026-10-29): A
  ships; HumanClothSim, the compute and the shader's _SimOn hook stay, off unless the switch adds it. The rebind now
  goes through EditorApplication.delayCall (HumanClothSim.Rebind), so the switch also starts when a cloak is put on
  later. To ship it one day: data into HumanPiece at setup (body per build), NPCs, LODs, a GPU cost check.
- **Upright neck** (2026-10-29, Daniel: "Isn't the neck too forward?"): the rest skeleton's neck_01 leans ~25 deg
  forward of spine_03 (head 24 deg back to keep the face level), and Humanoid takes the avatar's reference pose as
  every muscle's zero; the bought clips nod the neck down (-0.4..-0.5) and the head up (+0.4..+0.5) on top of it, so in
  Kevin idle/walk/run neck_01 -> head leaned 39-44 deg from vertical (20 at rest), the head 9-11 cm ahead of the chest
  (21 running). Fix: `HumanSetup.UprightNeck` (in ConfigureModel for the body, `NeckUpright` 20) stands the avatar's
  reference neck_01 up 20 deg and turns the head back 20, from the model's own rest rotations (never accumulates);
  meshes, bind pose and garments untouched. Kevin clips now 19-22 deg, head 7.5-7.9 cm ahead (18 running), face pitch
  unchanged (within 1 deg). Our clips keep their poses exactly (Walk, Sword_Slash, Sit_Idle, Zombie_Shamble,
  MammothDriver_Idle measured before/after). **Gotcha:** a CopyFromOther clip importer keeps its own copy of the
  avatar's description, refreshed only when sourceAvatar is assigned again - a plain reimport kept the old neck (the 15
  MammothDriver clips, which human_clips.json doesn't list, moved 20 deg until re-assigned); `ReimportAvatarClips`
  re-assigns and reimports every clip under Animation that uses the body's avatar. Applied in MedievalSetting
  (Human_Body.fbx.meta + 43 clip metas; `HumanSetup.ApplyUprightNeck()` does it without a prefab rebuild). Hoods, mail
  coif, plate gorget, dress + cloak checked side by side (Logs/HairCards/neck_collars.png): no new clipping. It helps
  hair too: hair is skinned head -> neck_01 -> spine_03 by height, so the craned neck stretched it; now long hair falls
  on the back and the ponytail hangs at the nape (renders/neck_hair_motion.png). Not play-tested.
- **Hair spike: strand cards** (2026-10-29, Daniel: not happy with the hair, wants "a complete new hair system", a new
  material and hair "physically reacting like cloth"; he picked strand cards over better solid locks). Spike pieces sit
  NEXT TO the clump styles (nothing old changed): Hair_LongStrands, Hair_PonytailStrands (+ _L1, _L2).
  - Blender `src/hum_cards.py` (scene **HairCards** in humans.blend: old | new as collection instances; `gallery()`
    renders renders/hair_cards_gallery.png). The style recipes stay: `hum_styles.hair_spines` (split out of
    hair_parts, same output) gives the guides; a style = the old cap shell + 3 card layers (inner dense, outer locks,
    wisps; `LAYERS`), 3 verts a row (a shallow trough), cards beside the face narrower. Atlas `T_Hair_Cards`
    (`build_atlas`, numpy, 8 columns: base / locks / wisps; R shade, G strand id, A coverage). UVs: UVMap, Clump,
    CapCut, HoodCut, **Guide** (uv4: x = the row's particle, -1 = cap/band; y root -> tip). Gotcha: a FLOAT2 *corner*
    attribute is a UV map in Blender 4.4 (it shifted CapCut to channel 3): the guide is kept as a POINT attribute and
    written as UV 4 after write_cap_coords (`write_guides` asserts the order). `build_all()` (Faces scene active: the
    Surface Deform bind needs the object in the view layer) binds the face keys, skins with hair_weights; L2 = a copy
    of the clump style's L2; `export()` -> export/Human_HairCards.fbx (apart from Human_Hair.fbx).
  - **Ponytail redone** (Daniel: "That ponytail mesh is horrible, we need a new one" - the old tail was a flat fan
    sticking straight back): `tail_parts` = a round bundle from a tie on the hair, out a little then hanging down the
    neck (kept off head/body), fuller below the tie, tapering; rings of cards facing out round the axis (twisting a
    little), a hair-wrapped band over the gather. The L2 copy still has the old tail (40 m away).
  - Unity: shader **Humans/HairCards** (Shaders/HumanHairCards.shader): atlas cut at 0.5 (Install sets mip "preserve
    coverage"), wrapped diffuse + two Kajiya-Kay highlights along the bitangent (Install imports Mikktspace tangents;
    5 of 5,256 card verts off the strand), the cap shell darker (_CapShade) and nearly without highlight, highlights
    only on a card's lit side (first cut blew the crown out white), own ShadowCaster/Depth passes that clip (hidden
    hair no longer casts shadows). Sim **HumanHairSim** (+ .compute): a particle per card row; world-space Verlet
    that damps only the swing relative to the skinned target (damping the world motion acted as a gale: walking hair
    streamed back), a little drag, eased back to the target (strong at the root), strand lengths (Jacobi), max
    distance growing along the strand, kept off the worn layers (HumanClothSim.BuildLayer: body, head, clothes; never
    deeper than the target lies). Substeps adaptive (`maxStep` 1/240 s; at 1/120 s a running crown flew apart) and the
    knobs are per 1/240 s (same motion at any frame rate). The shader moves each vertex by its row's particle
    (`_HairSim`, target / position / rotation) in every pass.
  - Editor: Humans/Editor/HumanHairCardsSpike.cs, **Tools/Humans/Hair Cards Spike/Install** (FBX import, atlas, material
    M_HumanHairCards, pieces into Resources/HumanPieces). HumanSetup's Rebuild deletes pieces it didn't cut: run Install
    again after one. The prefab's HumanFace.pieces list is untouched: `HumanHairCardsSpike.Offer(hf)` adds the spike
    pieces to an instance. MedievalSetting `Tools/Game/Checks/Hair Cards/` (Game/Scripts/Editor/HairCardsCheck.cs):
    Gallery (Logs/HairCards/gallery.png: old | cards, 6 views incl. the game camera), Motion (walk, run, stop; sim off
    / on strips + how far strands trail), Sim on the Player (play mode: puts LongStrands / PonytailStrands on the player
    and simulates it).
  - **Long redone as a drape** (same day, Daniel: "it is not just the material, the mesh is also bad. Improve the mesh
    of the Long style" + thick and thin; "You can use more faces for the hair"): the flow-grown Long hugged the skull
    (a wet helmet), narrowed into a V below the occiput and hung stringy temple locks. `src/hum_drape.py`: strands
    hung under gravity (follow-the-leader lengths, 140 passes) over the head inflated by the hair's `volume` (signed
    distance grids of the ear-domed head and the body, 6 mm cells, ~6 s once per head: cache them on the HeadFrame),
    stiff for 5 cm off the root along the comb direction, kept out of a face zone (in front of the ears, below the
    hairline, nearer the middle than the eye's outer corner), sliding off the shoulders (behind; the front roots in
    front), resting 2 cm off the body (over a shirt: at 1.2 cm the shirt showed through in patches), cut at a ragged
    hem (collarbone at the front, shoulder blades at the back) or where it runs 20 cm out over a shoulder, gathered
    into locks toward the tips, settled. `hum_cards.DRAPED` holds the two variants (volume, spacing, card width,
    clumping, layers): **LongStrands = thick** (3 layers, 21.8k tris L0 / 3.7k L1, 4,912 particles) and
    **LongThinStrands = thin** (flatter, less dense, the same 3 column groups; 14.0k / 2.4k, 2,870; clumped 0.6 on the
    locks' columns it read as wet strings over skin, now 0.25). Cards up to 24 rows (smooth bends). Skinned with
    `draped_weights`: hair_weights, then where the hair lies on the body below the neck the body's own weights there
    (neck, spine_02/03, clavicles - not the arms; 4 bones). Shader: highlights 0.14 / 0.2 and less on deeper strands
    (straight hanging hair has one strand direction: an even highlight read as silver sheets, from below most).
    Sim: hair is pushed at least 2 mm out of any worn layer even where its target lies inside (a cloak, a shirt).
    **Open:** skinned only (no sim: LOD1/LOD2, builds), running still lets the shirt show through at the shoulder blade
    on the side the arm swings back (the shirt follows the arm there; a wider body-weight fade made it worse); the sim
    fixes it, so the cure is the sim on LOD1 and in builds. From the front the hair goes behind the shoulders (the
    slide); thin shows slivers of skin between cards at the sides; a grey sheen from below. Sheets:
    renders/long_gallery_round.png (old / thick / thin), renders/long_motion_round.png (thick skinned / thick sim /
    thin sim).
  - **Sim in builds** (same day, Daniel: "Sim in builds"): no mesh is readable in a build, so nothing the sim needs
    is read from one at runtime any more. Setup (`HumanHairCardsSpike.Install`, ~20 s) stores indices and skinning only:
    `HumanPiece.hairSim[lod]` (a particle's mesh vertices, strand parent, path, 4 bones) for LOD0/LOD1 of the spike
    hair, `HumanPiece.simLayers[lod]` (one vertex a 2 cm cell, region, skinning) on every `Cloth_*` piece, and
    Resources/`HumanHairSimData` (the compute shader, so builds carry it, + Body/Body_L1 and Head/Head_L1 layers). At
    bind the renderers get `vertexBufferTarget |= Raw`; once drawn, `RestHair`/`RestLayer` read Unity's skinned vertex
    buffer (root bone's space at unit scale: TRS(rootBone.position, rotation, 1), measured 0.000 cm vs BakeMesh) and
    undo the skinning with the palette it was drawn with (last frame's in play; a check tool renders the pose it ticks):
    the face and build keys come along. Targets skinned from that rest match Unity's skinning to 0.001 mm. One thread
    a strand runs every substep (`Simulate`): 5 dispatches a frame per run instead of ~40. Lengths are split between
    neighbours (Gauss-Seidel, 3 passes): follow-the-leader (all on the child) fed energy into Verlet and the hair
    exploded into curls when walking. A layer renderer with no skinned buffer (not drawn: boots under a close-up) is
    left out (points moved far), not waited for (it kept the sim from ever starting). `HumanFace.Apply` ends with
    `HumanHairSim.Ensure`: anyone wearing a piece with sim data gets the component (play mode); a run per LOD (0, 1)
    ticks while its hair is visible and within `simDistance` 25 m of Camera.main, restarting on its target when it
    comes back; every 20 frames the worn renderers and face keys are checked and it binds again on a change. Checked in
    edit mode: LOD0 and LOD1 through the build path (no sim-off patches on the back any more, mean 1.2 / 1.7 cm off the
    target). **Not checked:** play mode (Ensure's frame timing) and a real build; no GPU cost measured; no NPC wears
    the spike styles (they are offered per instance, not in Human.prefab's list or the config), so a build only shows
    them through the check menu.
  - **Long round 2** (same day, Daniel: "Do you think the long hair looks good? ... something feels off", then "Rework
    everything necessary"). The critique (renders/long_critique.png): a box hung from the forehead's hairline that hid
    the face in profile, sides cut at the neck while the back went on (a mullet: the 20 cm "reach" cut), a halo of dark
    wires over the crown, hair floating 2 cm off the body, a silver-grey underside, skin slivers in the thin one.
    - Drape (`hum_drape`): roots on the cap shell (recipe cap + 1.5 mm), the clearance growing from there, half of it
      over the top and combed down onto it (`crown_k`, hug); front/top by how far ahead of the crown a point is
      (`front_of`, not the angle round the head: near the top that swung between neighbours - chevrons); the front
      hairline swept back and up the brow, the sides hardly back; below the hairline nothing ahead of the face line
      (temple corner -> just behind the ear's front at the jaw, `face_line`): the profile shows. Roots ahead of the top
      of the head (about the front third) slide off the shoulder in front - locks over the chest - the rest behind; the
      slide only above the armpits. Rests 1.2 cm off the body or 5 mm off a shirt (Cloth_Shirt_FSlim taken back to the
      base body, `unbuild`; an open mesh, so only within 4 cm of the body). Hem: front locks shoulder - 12 cm, back
      shoulder - 17 cm and a 4 cm U by where the tip hangs; also cut where a strand rises or folds past the head; draped
      twice (the second hangs each strand only to its hem + 3 cm: the extra length piled on the hips in zigzags).
      Clumping by arc length with each mate's pull held past its end (a mean over mates "still that long" jumped), never
      across the shoulder split; settling smooths along the strand.
    - Cards (`hum_cards`): rows spread by bent length (`bend` 0.03 m/rad, up to 30 rows; stubs under 3 mm ignored);
      facing off the head near it and off the body where they lie on it (`card_normal_fn`: front locks faced sideways,
      edge-on to the sun, and read mauve); a fill layer under the rest (`FILL`: wide dense cards, sides and back, not
      clumped) so gaps show hair, not skin; thin cards 3 cm wide. Card rows share their bone weights.
    - Bug: the draped styles were never skinned with `draped_weights` - `split("_L")` cut "Hair_LongStrands" at "_Long".
    - Builds: the head's Surface Deform keys (Feminine, Thin, Slight...) carried the front locks 3 cm back into every
      female chest. `draped_keys`: a card row takes the head's key offset while on the head, carries the last one down
      the free hang and takes the body's own key offset where it lies on the body (body keys the head lacks are added).
      `build_fit` then fits every `hum_builds.BUILDS` build as the garments are: its rows (key mix + bone moves) pushed
      out of that build's body and `Cloth_Shirt_<tag>`, the body keys corrected (least squares, the smallest change),
      blurred over 2.5 cm (rows pushed one by one out of the shirt's folds crumpled the tips). Worst build's mean refit
      3.3 cm (thick). The 16 builds' distance grids cache per session (`_BUILD_FIELDS`, kept over a reload); a build of
      both styles takes ~145 s - longer than an MCP call: run it from a `bpy.app.timers` callback that logs to a file.
    - Shader: diffuse only (`UniversalFragmentBlinnPhong`; the shared PBR path's Fresnel turned the underside and the
      crown's edge silver-grey), both faces lit with the outward normal (flipped, the far side's cards over the crown
      faced away from the light: the dark wires), the primary highlight tinted toward the hair colour (`_Spec1Tint`
      0.7: white over a lock of parallel strands read lavender). Install now copies the shader's float defaults onto
      M_HumanHairCards (the saved material had kept its first numbers).
    - Sim: a layer point's plane holds only `disk` 3.5 cm across and not for hair resting more than `inside` 1.5 cm
      behind it (an endless shoulder-top plane lifted the front locks; walking flung them forward). `HairSim.hold`
      (Install, from the prefab head's vertices): a strand's length lying on the head; the follow and max distance
      count from there (by path alone the crown sagged and flapped when running: dark blotches). Run + stop: mean
      1.0 cm (thick) / 0.9 cm (thin) off the target.
    - Now: thick 27.8k tris (L1 4.5k, 6,423 particles), thin 18.4k (L1 2.5k, 3,974). Sheets in renders/:
      long_rework_before_after.png, long_round2_builds_thick/thin.png (9 builds, shirt), long_round2_motion_thick/
      thin.png, long_round2_lod1.png. Open: not play-tested; the sunlit part of the front locks reads a little paler;
      thin hair still lets an ear show from the game camera now and then; alpha edges alias at distance.
    - **Round 3** (same day, Daniel: "Keep working on it"):
      - The part showed a ~4 cm band of bare cap and the hairline the cap's edge: each card's first row was sunk 2 mm
        and its edges dipped from the root, so its first centimetre lay under the cap. Draped cards now start flat
        (`root_sink` 0, the trough growing in over `dip_len` 5 cm). Atlas strands start a little apart (`stagger`,
        their own random stream), so a card's root fades in. Front roots get half the volume (`vol_k`): the temples
        had puffed and rolled.
      - `_fringe`: short wisp cards just in front of the front hairline (a level ray at the HAIRLINE table's height
        - the nearest skin point slid 1.5 cm down the brow). `cap_guides`: the cap's Guide.y = how far its border
        dissolves (1 on it .. 0 a centimetre in); the shader cuts the shell there along its own strand texture.
        Both barely show: in a closer render the hairline already read fine (the head's scalp tint softens it); the
        hard line was mostly the gallery crop's 3x zoom.
      - The pale front locks were the primary highlight: a flat lock of parallel strands catches it all over (with
        it off they were a rich brown). Primary 0.14 -> 0.06, tint 0.9, secondary 0.2 -> 0.25 (hair-coloured), and
        `_Exp1` 120 -> 300 with `_ShiftJitter` 0.6, so a lock catches it in streaks; dark hair gets it stronger and
        whiter (`dark` from the base colour's linear luminance: a mid brown is ~0.06 there, not 0.26 - the first cut
        treated brown as dark). Colour lineup renders/long_round3_colours.png (blonde, black, red, grey, brown).
      - Checked again: 9 builds (long_round3_builds_thick/thin.png), run + stop (long_round3_motion_thick/thin.png,
        0.9 cm mean off target), gallery long_round3_gallery.png. Thick 28.0k tris (L1 4.4k), thin 18.7k (L1 2.5k).
        PonytailStrands shares the material (new shading) but wasn't rebuilt (its cap has no dissolve data yet).
      - **Parting** (Daniel: "Shouldn't we have a line in the middle of the head that divides the hair for each
        side?"): `parting()` gives the cap shell's vertices their signed distance across the line (in half widths,
        `PART_HALF` 1.7 mm, wandering a little front to back, tapering out short of the crown: `part_along`); it rides
        in HoodCut.y (written in `write_guides`; signed, so it interpolates exactly over the shell's centimetre
        triangles) and the shader cuts the shell there with a ragged edge - the scalp shows. Not in the shadow pass:
        lit, the line read as a bright painted stripe. Card roots keep `PART_CLEAR` 4 mm off it, the fringe starts
        7 deg off the middle, and over the top the shell's strand texture runs away from the line (it ran front to
        back there). `part_x` in DRAPED (default 0) for side partings later. renders/long_parting.png.
  - **CropStrands** (2026-10-30, Daniel picked Crop as the next style - the most worn: 37 named NPCs, 16 % of random
    men; the clump Crop was spiky feathers with a jagged fringe). Short hair doesn't hang: `hum_cards.SHORT` +
    `short_parts` / `grow_short` lay strands on the scalp along a flow (no gravity), stepping 5 mm tangent to the head
    and set back at a clearance growing from the cap to the style's `volume` over 2 cm; lengths by region
    (`short_lengths`: top 5.5, fringe 4.5, sides 2, back 3 tapering to a 1.2 cm nape, a little ragged); the fringe stops
    5 cm above the eyes give or take a few mm a strand (one line read as a bowl cut) and short of the ears. Flow
    (`short_flow`): brushed from a whorl at the top of the back (`crown` 5.5 cm behind / 2.5 cm under the top),
    spreading less sideways over the top (`fan`) and spiralling round the whorl (`swirl` 0.9 over 5 cm). Whorl lessons:
    every flow over a head has one (hairy ball); the head's own crown point fanned the top every which way (patchy and
    curly from the game camera), down the back it stared out of the back view, a strong swirl read as a cinnamon roll,
    and cards all running outward from their roots left a disc of bare cap in its middle - `whorl` adds ten short cards
    spiralling over it. Short cards: 1.6 cm wide on 1 cm (2.2 cm read as petals), `v0` 0.35 (the root shadow starts that
    far along: rows of short cards' dark roots read as fish scales; the atlas's soft starts stay - skipped too, root
    edges cut hard), `cap_light` 0.5 (the shell's uv1.y past 1 lightens _CapShade: more of it shows under short hair).
    Install skips the sim for hair no longer than 9 cm (`ShortHair`). 15.8k tris (L1 3.0k; L2 the clump copy).
    MedievalSetting HairCardsCheck's gallery has the Crop pair (on MStrong). Checked: 5 faces / 3 builds (LOD0, LOD1, the
    game camera, behind), brown + black, under Cap / Hood / coifs / CloakHood / PlateHelm
    (renders/crop_lineup.png, crop_compare.png, hair_cards_headgear.png). Not play-tested; not in any NPC config.
  - **SweptStrands** (2026-10-30, the next men's style while Daniel slept: "try to keep going"). The short builder with
    the Swept recipe's own "back" flow (no `crown` in SHORT: `short_flow` falls back to `hum_styles.flow_fn`; its
    whorl lies on the face, none in the hair). Lengths top 8.5, front 10 (the front's hair rides back over the top),
    sides 4.5, back 5.5, nape 2 cm. Two Swept-only keys: `down` (100..140 deg round the head the flow turns straight
    down - a constant "back" projected onto the back of the head wrapped the sides round into a dark knot at the nape)
    and `hem` (strands stop 6 mm under the hairline, ragged -4..+8 mm a strand: they hung on down the neck in a lump).
    19.1k tris (L1 3.0k; L2 the clump copy). HairCardsCheck gallery has the Swept pair. Checked: 5 faces / 3 builds /
    black, brown, blonde, red, grey (LOD0, LOD1, the game camera), under Cap / Hood / coifs / CloakHood / PlateHelm
    (renders/swept_compare2.png, swept_lineup.png, swept_headgear.png; swept_compare.png = the knot). Known: the
    forehead hairline is the head's straight HAIRLINE (shared with every style), crisp on a slicked-back style.
    Not play-tested; not in any NPC config.
  - **PonytailStrands scalp** (2026-10-30, same night): the scalp moved from the clump recipe's guides
    (`style_parts`) to the short builder; the round tail (`tail_parts`) is unchanged and now added by `short_parts`
    for any recipe with a "tail". Strands lie on the scalp along the recipe's "tie" flow and stop at the gather
    (`gather` 9 mm round a point 6 mm out from the skin, as the tail's own gather - on the skin it was out of reach of
    strands lying 5-7 mm out: they circled it to their full 30 cm, a mess round the tie and 200 s builds, now 80 s;
    they also stop once they pass it). `over_ears` lifts them over the ears (the ear stop cut the temples short).
    Cards narrow to 40 % at the tie (full width, converging cards crossed in a patchwork), are flat (`curve` 0.02: the
    short styles' trough dipped the edges of cards lying this close through the shell - wiggly cut lines, a
    wood-grain look) and have no sparse outer layer. The shell's texture runs to the tie (`tie_uv`: polar round it,
    25 tiles round, unwrapped per face so there's no seam; it fell down the sides across the hair) and is nearly as
    light as the cards (`cap_light` 0.85). 20.0k tris (L1 3.6k). Checked: 5 faces / 3 builds (FSlim, FStrong,
    FHeavy) / 5 colours, the game camera, under Cap / Hood / coifs / CloakHood / PlateHelm (the tail hangs out under
    the cap and helm; hoods hide it) - renders/ponytail_check2.png, ponytail_compare.png (before the tie fix),
    ponytail_headgear.png. Motion (HairCardsCheck.Motion, sim): the scalp holds (whole strands within 2 cm of the
    head: `hold` = their length), the tail swings; mean 0.1 cm off target, max 18.2 cm at the run's stop. Not
    play-tested.
  - **Hold fix** (same night): a flick of strands over the gather at the run's bounce (ponytail and bun) was scalp
    hair going free - `HairSimOf`'s on-head test took every other head vertex within 2 cm, and the game head's 5k
    vertices are sparse over the top (hair lying flat on the crown measured up to 3.1 cm away). Now every vertex,
    within 2.5 cm: the bun's scalp has no free particles (was 734), the ponytail's free ones are its tail. LongStrands
    re-checked: mean 0.8 cm off target (was 0.9).
  - **BunStrands** (same night; Bun is worn by 17 configs as often as Ponytail): the ponytail's scalp builder pulled
    to the recipe's crown tie (`gather` 2.8 cm: the bun's foot), then `bun_parts`: three interleaved spirals of cards
    (0.7 turn each, staggered ends) wound three turns over a squat dome (radius 3.4 cm, height 0.75x) from its foot to
    a rosette at the top, facing out from its middle, over a light core shell (drawn like the cap) so nothing shows
    through. The old clump bun was a ball of random great circles (loops of wire). The bun doesn't swing: its cards'
    Guide x is -2 - HairSimOf skips negative guides, and the shader now reads only -1 as the cap shell (-2 = a card
    left out of the sim; HumanHairCards.shader, `shell`). 18.6k tris (L1 3.3k). Motion: max 0.3 cm off target.
    Under every headgear the bun is cut away (CapCut/HoodCut), nothing pokes through. Renders: bun_compare.png,
    bun_headgear.png. Checked on FSlim brown only (not the 5-face lineup). Not play-tested; not in any NPC config.
  - **SidePartStrands** (2026-10-30, Daniel: "Go on" - the next style). SidePart's recipe is the "part" flow that
    covers the ears, Long's own, so it's a DRAPED entry, not a SHORT one: Long's drape with the parting `part_x` 2.8 cm
    off the middle (cut in the cap by `parting()`, passed to `comb_dir` now, and to `_fringe`, which skips the
    parting's few mm and starts 2 deg off the middle) and short. No hem: `length` as SHORT's (top 12, front 10, sides
    7.5, back 8.5, nape 4.5 cm; `ragged` then a fraction, as there) hangs each strand only its own length - the top
    falls over the ears to the lobes, the back to the collar. Locks don't mix across the parting (`clump` groups by
    its side). `cap_light` 0.4 as the short styles'. Two fixes on the way:
    - Behind the parting's end the hair kept splitting along its line: a dark seam down the back, a tuft at the
      crown. `comb_dir` (side partings only; Long's centre one unchanged) fades the sideways comb out between 1 and
      4.5 cm behind the top of the head, and `parting()` turns the shell's texture down the back there too.
    - A strand at the very top folded on itself (the tuft that stayed): the body's distance grid had an "inside" speck
      over the head - the body is open at the neck and a node nearest that rim took its sign at random (-1.6 cm, a
      push of 2.8 cm sideways). `Field.outside_above`: nothing above the body's top is inside. Shared code: Long's
      drape gets it on its next rebuild (not rebuilt yet).
    10.8k tris (L1 1.6k; L2 the clump copy), 2,185 particles; simulated (12 cm > ShortHair). Fitted to the builds,
    worst mean refit 0.5 cm. Checked: 5 faces / 3 builds (MSlim, MStrong, MHeavy) / 5 colours, LOD0 + LOD1, the game
    camera; under Cap / Hood / coifs / CloakHood / PlateHelm (under the cap it shows below the rim, the rest hide it);
    motion (sim) mean 0.0 / max 1.7 cm off target. Renders: sidepart_compare.png, sidepart_lineup.png,
    sidepart_headgear.png. Its shape is a full mop over the ears (as the recipe's cover_ears), not the old style's
    long fringe swept over one eye - the drape keeps hair off the face. Not play-tested; not in any NPC config.
  - **CurlyStrands** (2026-10-30, Daniel: "Curly next"; the clump Curly was a mass of blobby leaves). Ringlets: the
    short builder's strands (top 4, front 3.5, sides 2.8, back 3.5, nape 2 cm), each turned up to 75 deg off the flow
    (`turn`: curls lie every which way, not combed), then wound into a coil round its path (`coil()`: a turn every
    1.6 cm, either hand, radius growing in over its first 8 mm) - a card faces out from the path, so it wraps the
    ringlet as a spiral band with its strands running round it (`_facing`; 6 rows a turn at LOD0, 3 at LOD1, where
    the facing bends 60 % to the scalp's normal: big facets lit round the path showed their undersides as dark
    specks). A layer's 5th item is its coil radius: two layers, 5.5 and 6 mm (4.5/5 left the cap showing). No flat
    fill: its straight strands showed between the curls as slicked patches. The cap is the problem with curls -
    its tiling strand texture read as a combed base under blonde and grey curls:
    - `cap_light` below 0 (only Curly): the shell's uv1.y is negative and HumanHairCards.shader darkens it to
      (1 + uv1.y) of _CapShade (-0.45: 0.33) - the shadow between curls - while a pixel covers under 1 mm of hair, and
      lights it fully (the hair's mass) by 3 mm (`px` from the camera distance, projection and screen height). Dark at
      every distance, the gaps took over from the game camera: blonde read as a dark head with blonde specks, and LOD1
      (lighter) popped. Every other shell has uv1.y >= 0.35: unchanged.
    - Not simulated: the coil cards' guides are -2 (as the bun's). Wound, a 4 cm curl's path is 15 cm, past
      ShortHair - 4,252 particles, motion strips identical to skinned, one curl straying 5.2 cm.
    - Density (Daniel: "some areas are unpopulated"; LOD1 may stay sparse from the top-down camera). Measured with
      blonde curls over a black cap (_CapShade 0 by MaterialPropertyBlock; black / (black + blonde) pixels per view,
      renders/curly_coverage.png). The cause was the roots: `sample_roots` only picks head vertices, sparse over the
      skull, so tighter spacing and `fill` never reached the crown (0.8 spacing: back 18.5 %, top 20 %, whatever the
      density). `scalp_points` samples the scalp's faces instead, for LOD0's coil layers and `fill` only (other styles
      keep `sample_roots`): 4 mm candidates 305 -> 2,110. Now `spacing0` 0.9, `fill` 5 mm (`fill_gaps`: 62 curls),
      front 4.7/3.8 %, 3/4 6.5/5.8, side 8.5/7.8, back 10.3/9.8, top 7.9/6.8, 3/4 back 8.8/8.2 (man/woman).
    - The fringe line is off (`fringe_z` -1, `hem` 6 mm): it cut the temples' curls to 5 mm stubs. `turn` 75 and a whorl
      of 16 broke up the lines running from the whorl. These recipe keys are shared, so LOD1 took them too (3.3k -> 3.6k).
    - Grain from afar: LOD0's coils lit by their own normals (out from the path) are half dark sides; once a pixel holds
      a curl's worth, each is a speck (blonde/grey 12-15 % dark pixels at 9 and 5 m, cap and root shadow not the cause;
      tested by overriding them). The coil cards' guide is now -3 (still out of the sim; a bun stays -2). HumanHairCards.shader
      fades them from 1 to 3 mm a pixel: normal faced to the viewer + bent 0.5 toward it, wrap 1, highlights x 0.25 (they
      were black hair's bright specks: 9.4 -> 1.7 % at 9 m). Now blonde 1.8 % dark at 9 m, 1.6 % at 5 m, LOD1 2.8 / 1.8;
      medians 155 / 158 and 152 / 153, so no pop. Close-ups unchanged: 3 of 1.17M pixels differ at 0.6 m (by at most 12
      summed over rgb), none at 1.2 m. At a 30 deg lens LOD0 lasts to about 12 m (size 1.66, transition 0.25), so these are
      the distances a player sees. LOD1 at 3 m shows dark cap patches, but it isn't drawn that close.
    - Cost: LOD0 went from 6 to 5 card rows a turn, Daniel's pick (`coil` is pitch, rows at LOD0, rows at LOD1): 27.5k tris
      (-13 %) on the head after the eye pass. Coverage front 6.2/5.3 %, 3/4 6.6/5.5, side 9.7/8.7, back 11.6/11.5, top 9.4/8.1,
      3/4 back 9.5/8.4 (man/woman; 6 rows 5.2/4.1, 7.3/6.5, 9.3/8.7, 11.6/10.9, 8.6/7.4, 9.9/9.1): some views worse, some
      better, so root placement moves as much as the rows do. At 0.6 m the coils are visibly more angular and hatched (renders/
      curly_rows_6v5.png, 6 rows left of each pair); at 1.2 m the same to the eye. At 9 and 5 m (curly_rows_distance.png,
      6 / 5 / 6 / 5) dark pixels, under 0.6 x the median: blonde 1.9 / 2.7 % (6 rows 1.5 / 2.6), grey 1.7 / 3.0 (1.0 / 2.0).
      Black's dark and bright figures mean little: its median is 10, but it does show specks on either build.
      Spacing 1.0 gave 24.4k but back 15 %, top 13 %.
    - Comparing renders across runs: the whole figure went darker between two runs (brightness 83 -> 71 at 0.6 m, same
      geometry: 0 silhouette pixels differ), cause not found. It first made 5 rows look much worse than it is: render both
      sides under one lighting and check a non-hair control. The face session also edits the head in the same Blender,
      and hair is fitted to the head: the same 5-row recipe gave 26.9k, 27.3k and 27.5k across its edits, so don't compare
      builds across them. Only Curly is rebuilt on the post-eye-pass head; the others were fitted before it (eye-area skin
      only, so a fringe close to the brows is what to check).
      Untested idea: hair on its own LOD switch, since LOD0 and LOD1 match at 5 m and LOD0 is drawn to about 12 m.
    27.5k tris, close to LongStrands thick (28k); L1 3.7k; L2 the clump copy. Checked: 5 faces / 3 builds /
    5 colours, LOD0 + LOD1 + the game camera (renders/curly_lineup.png, curly_compare.png); LOD0 vs LOD1 at true 1080p
    pixels at 9, 5 and 3 m, black / blonde / grey (curly_lods.png); under Cap / Hood / coifs / CloakHood / PlateHelm
    (curly_headgear.png: curls show under the cap's rim at the nape and a fringe in the coifs' face opening; hood and
    helm hide them). CropStrands + SweptStrands rebuilt after the short-builder refactor: same geometry (tris, verts,
    vertex hash). Not play-tested; not in any NPC config.
  - **MohawkStrands** (2026-10-30, the last style on the list; beards still later). `STAND` + `stand_parts`: strands
    stand off the band and gather (0.85) into locks along the crest, shorter at the band's edges so the front reads as a
    wedge, not a slab. Layers: "mat" (lying on the scalp, brushed back: from behind and above the standing strands point
    at the camera, and the mat is what reads as hair there), two "side", "cross", a fine "side" (L0 only). Out of the sim,
    as the bun (Guide x = -2). 6.6k / 1.7k / 335 tris; old Mohawk's blades lose to it from the side and at the game
    camera. **Own LOD2** (mat + one layer of big cards, built by `stand_parts`), not the clump copy: that one had blades
    floating over grey scalp patches. Renders: renders/mohawk_compare.png, mohawk_final.png (top row L0 x5, L1 x2, L2 x3;
    bottom row 6 hats, then the old L2 at 9 m and 40 m).
    - Weakest view: straight behind, still stringy and dark over the mat (strands end-on). The old one is tidier there.
    - Name: `hairlineTint` is 0 only for the style strings "" and "Mohawk" (HumanFaceGenerator, HumanActor), so a merge
      must treat "MohawkStrands" the same. Renders call `HumanActor.Face(..., "Mohawk", ...)`, then set `face.hairStyle`.
    - Headgear: Cap and Hood cover it; MailCoif and CloakHood show a small front tuft; PlateHelm (open face: capCut 0, no
      hoodCut, no hidesHair) lets the crest poke through. The old Mohawk does all of this too; not changed, in POLISH.md.
  - **Strand brows, hair and beard edges** (2026-10-30, live in the game and the showcase, not play-tested):
    - **Brows** (`BROW_CARDS`, `brow_parts`, Brows_NormalStrands / Thin / Bushy / Straight, through `HumanFace.PieceFor`): the clump
      brows' charcoal came from their material, not their colour. Fine cards rooted over the painted arc, lying on the skin as a
      brow grows: the inner end nearly straight up, leaning outward, the tail out and a little down; lower hairs rising, upper ones
      flatter, so they meet along a ridge. On the head bone with exact keys; no LOD2 (the head's painted brows, as before). Cards
      must be much wider than the strand you want: the coverage cut leaves a 1.8 mm card a scratchy line (first round). Tris L0 / L1:
      Normal 1.8k / 136, Thin 1.2k / 88, Bushy 2.4k / 164, Straight 1.7k / 152.
    - **Edge hairs** (`edge_fringe`, `FRINGE`, every hair and beard at L0 and L1): fine short cards rooted past the piece's edge,
      thinning out over 5 mm, combed like the hair next to them (`cards_part` keeps its rows in `part.rows`), so they run back into
      it. They start where the mask is 0.06, not 0.5: the cap shell reaches past 0.5 and hid the first round's. Not on a beard's
      underside (`n.z < -0.35`). They add 1.5-2.5k tris to a full style at L0.
    - **Soft tint on the skin** (`bake_edges`, export/HairEdge/<piece>.png, 256 px in the head's UVs, copied to
      Assets/Humans/Textures/HairEdge; `HumanPiece.edge`, set by Install; `_HairEdge`, `_BeardEdge`, `_BrowEdge` on Humans/Skin, set by
      `HumanFace.EdgeOf`): 1 under the piece, fading over 9 mm past its edge, by 3D distance, so no UV seams; brows a soft base of
      their own shape, 2.5 mm. No triangles, and it softens LOD1 and LOD2 too. A new style needs `bake_edges(names=[...])`.
    - **Lips:** `H.lip_dist` is unreliable on the lower lip: its vertices are up to a centimetre apart, so a beard came through in
      vertical stripes when the ring shrank. `LIP_LOW_X`/`LIP_LOW` (the lip's measured bottom edge) and `on_lips` now keep the
      beard, the edge hairs and the tint off it; the bare ring under the lip is 0.6 to 2.6 mm.
    - Still rough: the cap shell's cut edge shows small stairs in an extreme close-up (Full's cheek line, Swept's forehead, on
      dark hair above all). That's item 3 of the hair list (soft edges). Renders: renders/brows_before.png, brows_r2.png, edges_r3.png.
  - **Live in the game and the showcase** (2026-10-30, Daniel: "just apply it to the main game, including that scene"): the
    strand styles are now the game's. One rule in `HumanFace.PieceFor`: a plain style wears `<style>Strands` when that piece is
    on the list ("Crop" -> Hair_CropStrands, "Full" -> Beard_FullStrands), else its own (Buzz, Tusks, Horns). So GameRules' NPCs
    and creatures, the face config, the character maker's lists and saved looks all keep the plain names. `Styles()` lists a
    style with strands once, under its plain name; LongThinStrands has no plain twin and shows as itself. Beard shadow is 0 for
    any strand beard (set in HumanFace, whatever the face holds: the generator still writes 0.5 for the old names). Clump pieces
    stay in Resources, unworn (they still count toward the build). `HumanHairCardsSpike.OfferOnPrefab` listed the 17 pieces on
    Human.prefab; HumanSetup keeps them on a rebuild (`hf.pieces`) and no longer deletes `*Strands.asset`. Humans_Showcase
    re-applied + saved (additively, the shared editor's scene untouched). Render: renders/strands_ingame_check.png (men; women;
    Orc, Zombie, Elf, Dwarf, Lich, Giant presets; women's backs).
    - Not play-tested. To watch: cost in crowds. Tris go up by up to 1.5x (Long 28k / 4.4k vs 19k / 2.6k, Curly 27k vs 18k; Crop
      and the beards about even at L0, more at L1), and Swept, SidePart, Long, Ponytail and Bun now run a GPU sim per
      human, visible and within 25 m (`simDistance`), so a pack of zombies or bandits is the worst case. Profile first if FPS drops.
    - `HairCardsCheck` Gallery's "old" row now also shows strands (PieceFor). Its Sim on the Player still works.
  - **Beards** (2026-10-30, redone the same day: Daniel found the first strand beards "weird"): Beard_FullStrands,
    WizardStrands, DwarfStrands, GoateeStrands, MustacheStrands, ShortStrands, ShortSideburnsStrands, ChinStrapStrands beside
    the clump ones, which are untouched (`BEARD_CARDS`, `beard_outline`, `beard_tip`, `beard_card_parts`; Tusks and Horns
    aren't hair). Not the clump recipes any more: they shared the clump stencil (a rectangle on the cheek, straight back cut)
    and hung straight down (a flat curtain from the side). Now an outline drawn in profile on this head, strands combed
    toward the chin and gathered into locks, and cards lit as the beard's volume (`beard_normal`), not the skin under it
    (under the jaw that faces the floor: the beard went black). Out of the sim (Guide -2), rigid on the head with exact keys,
    as the clump beards. Tris (L0 / L1 / L2, with the edge hairs): Full 21.4k / 2.9k / 358, Wizard 25.9k / 3.4k / 358, Dwarf 27.5k / 3.6k / 361,
    Goatee 6.2k / 1.1k / 129, Mustache 3.2k / 570 / 75, Short 18.7k / 3.1k / 339, ShortSideburns 19.7k / 3.2k / 354, ChinStrap
    11.4k / 2.0k / 198. Renders: renders/beards_compare.png (all 8: front, 3/4, side), beards_check.png (other faces and
    colours; headgear + a goatee close-up; L1; L2 at 9 m).
    - **Sideburns** (Daniel: a Short beard stopped as a patch on the cheek): everything but Goatee and Mustache runs up in
      front of the ear into the hair, a band about 2 cm wide (top edge zm + 0.076, the hair's edge there is around z 1.45), not
      a wedge narrowing to nothing. Short differs from ShortSideburns only by its cleaner cheek line now. Sideburn strands
      hang straight (`burn` in `beard_tip`); roots may sit 5 mm from the ear (at 12 mm the band had no strands).
    - **Mustache** (Daniel: "the capilars are not placed in the correct anatomical position"): redrawn from the head's measured
      upper lip, in x and z (`TACHE_X/TOP`, `TACHE_X_LIP/LIP`), shared by Mustache, Goatee, Full, Wizard, Dwarf, Short and
      ShortSideburns. It was a thin band hugging the lip, 5 mm short of the nose and thinning out by x 21 mm (its top edge came
      from the beard's y table, and `F.lip_x` 22.8 mm is narrower than the real corner, 28.2 mm), with hair running almost sideways.
      Now: lip's edge (z +9 mm) up to just under the nose (+20.5 at the middle, +22 under the nostril), falling to the corner.
      `tache_tip`: down and outward from the midline, 20 deg off vertical there, 55 at the corner, on the skin, ending at the
      lip's edge. Its own fine cards in its own pass (`TACHE_SPACING`, `TACHE_WIDTH`): a Full beard's cards are wider than
      the whole upper lip. Render: renders/mustache_check.png (close-ups, from below, L1, L2 at 9 m; other faces).
    - Nothing over the mouth: pointed card roots, because square ones read as teeth. Roots beside the mouth's corners droop
      short and on the skin: free, they stood off the receding chin as stray wires. A goatee's patch is a wedge narrowing up.
    - Still rough: one or two thin
      edge-on wires on Wizard from the side; L2 Dwarf/Wizard read as a beard from the game camera, the short styles barely.
    - Short cards read as leaves (wool): a card's width is capped at half its length, `spread` 0.2 (how round it lights).
    - Headgear: fine, the same cuts as the clump ones (hood_cut beard=True).
    - `beardShadow`: `HumanFaceGenerator` sets 0.5 only for the exact old names, so these get 0, which is right: the skin tint
      is painted to the old stencil (T_Head_MaskB) and would show around the new outline. No face config offers these yet;
      `HumanHairCardsSpike.Offer` adds them to a face's list.
    - Installed Human_HairCards.fbx is now 189 MB. hum_export.export_hair takes everything in HUM_Hair, these too: filter it
      when re-exporting Human_Hair.fbx (see "Re-exporting Human_Hair.fbx").
  - **Fixed for all strand styles** (2026-10-30): (a) LOD2 was bald. The parting clip reads HoodCut.y and the copies had
    no `hair_part`, so 0 read as "on the parting" and the shell was cut away. `lod2_copy` now writes 99. Not seen in game:
    no NPC config uses a spike style yet. (b) Guide -2 cards (bun, crest) lit dark from behind: Cull Off, only far curls
    flipped their normals. The shader now flips them to face the viewer (capx.x = -1). The bun moved under 1% of pixels
    (`3/4` 50 px, back 1,071, top 994, same lights).
  - Numbers (the first cards, before the drape): LongStrands L0 9.4k tris (old Long 19k), L1 1.5k, 1,752 particles; PonytailStrands 8.0k (old 16.6k), 1,400
    particles. Run + stop: strands off their target mean 0.5 cm (Long) / 0.3 cm (Ponytail), a short spike to the 20 cm
    cap at the instant stop. Not done: the other 7 styles, beards, brows; sim data into HumanPiece for builds (editor
    only now, like the cloth sim); LOD1 not simulated; alpha edges alias (no MSAA in the game); no play test yet.
- Unity check: MedievalSetting Tools/Game/Checks/Cloth Motion (ClothMotionCheck) walks a dressed human through
  idle/walk/run in a preview scene and shoots strips into Logs/ClothMotion; the sims have public Tick(dt) /
  HumanHelperBones.Apply() for it.
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
  the side.

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
- Eyes fixed 2026-10-06 (see Conventions, "Eyeballs"): the specks were the inside of the back of the eyeball.
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

- 2026-10-18: **orc mammoth driver** (Daniel: "orc mammoth riders, complete with animations"; his picks: one driver on
  the neck, all clips ours -- he reopened own-made clips for this): `src/hum_ride.py`, scene **Orc_Mammoth** (the
  mammoth, its MammothTack and clips appended from Beasts' beasts.blend; `OrcRider` = a copy of HumanRig on the
  mammoth's `Socket_Driver` at the orc preset's mean height x1.155, bones at the MOrc joints, wearing copies of the
  body, an orc head and the Orc Hide garments, the weapon kit's IronSpear in the right fist). Poses are hum_anim
  Poses on `OrcRig` (the base rig + MOrc joint deltas from export/human_rig.json); the pelvis is keyed against the
  base rest (the Animator's hips). 15 clips `Human@MammothDriver_*`: one per mammoth clip (Idle, Walk, Run, Charge,
  Trumpet, TuskSwipe, Stomp, Graze, Hit, Death, Sleep, Wake) keyed every frame in seat space (torso lag, feet under
  the foot rope, left fist on the rope grip, accents; Death rides the mammoth down and slides off its left side),
  plus Thrust, Flinch (overlays) and Fall. `hum_ride.build_all()`, export from the Faces scene:
  `hum_ride.export_clips()` (registers its clips in `hum_anim.CLIPS` only, not BUILD/human_clips.json). Unity:
  `Beasts.MountedRider`; the game's `RiderSetup` configures the clips and builds the driver in `Riders_Test`.
  Gotcha: Blender 4.4 action slots -- `hum_anim.use` assigns the action's slot (an action keyed on OrcRider otherwise
  exported a T-pose from HumanRig).
  Fixes the same day (Daniel: "the arm is messed up", "he swirls the spear, then thrusts"): every hand goes through
  `hum_anim._handle_hands(cap=True)` (`hum_ride.hold`): a hand turned freely put the rope-grip arm past Humanoid's
  wrist limits (twist 90 / flex 80 / deviation 40) and Unity twisted it. The rope grip's direction is searched once
  per clip (thumb-up on the loop won); the elbow carries frame to frame (`HINT`), with a full search when a hinted
  solve goes over. A fist's grip runs across the forearm (give or take 40 degrees): a spear along the extended arm or
  upright above a vertical forearm can't be held -- the jab now crosses the arm at ~50 degrees, the raised spear
  points forward-up, and `_tilt` leans the weapon up to 45 degrees where nothing else fits. Own clips blend body
  settings and hand targets per frame and solve each frame (key poses alone, or solved arms slerped bone by bone,
  swirled the spear / bent the wrist). All clips within the limits (one Trumpet frame 7 degrees over on flex).
  Then (Daniel: "now the orc trumpet is swirling the spear"): what held it steady, every clip measured for per-frame
  turns of the spear and both forearms (all <= 21 deg, mostly real motion, wrists inside the limits):
  - hands follow on frame to frame (`CHAIN`: the elbow kept as a direction -- an angle from a fixed zero flipped
    when the arm lay along that zero -- and the forearm twist searched near the last; each step away costs), a
    fresh solve only when following on breaks a wrist by more than 6 degrees; loops run a lap first so the seam
    matches;
  - the rope-grip fist is where the grip is at rest, carried by the torso (`GRIP_LOCAL`): tracking the rope through
    the mammoth's head swings asked for poses no wrist gives;
  - weapon poses searched for comfort rather than drawn: the jab cocks low with the arm down-out-back and pushes 24 cm
    along the shaft, the charge's spear is levelled low from the hip (under the arm along the forearm it sat at the
    limits and cycled every frame), the trumpet swings the resting arm up about the shoulder (a spear upright or
    forward overhead needs more forearm twist than Humanoid has); the resting spear is carried by the torso;
  - the falls blend the clinging pose out over 0.2 s; their flailing arms keep their own `CHAIN` keys.
  A comfort search like the ones in this session (arm reach x spear direction, `_handle_hands` full solve, cost
  wrist_comfort + miss) is the way to set any new held-weapon pose.

- 2026-10-20: **matte skin** (Daniel, from a Reddit comment: "increase the roughness and remove the glare, that will make
  them look less like plastic figurines"). `HumanCommon.HumanShadeSkin` (Humans/Skin and Humans/Body define
  `_SPECULAR_SETUP`): the reflectance F0 set directly (`_Specular` 0.025; it scales the grazing rim and the
  environment reflection too), smoothness 0.32 (was 0.45 head / 0.40 body) broken up a little by UV value noise
  (`_Breakup` 0.12: an even sheen reads as moulded), and the main light wrapped past the shadow edge in a warm tint
  (`_Scatter` 0.18, a cheap stand-in for subsurface light). Hair smoothness 0.30 (was 0.45). Wounds stay wet (0.6,
  F0 0.04); the painted underclothes on the body stay cloth. The values live in `HumanSetup` (SkinSmoothness ...), set
  on M_HumanSkin / M_HumanBody / M_HumanHair at every rebuild. Chosen from a front-lit sweep (0.25 / 0.02 / 0.35
  read as clay). Renders: `renders/skin_matte_before_after.png`; Unity `Logs/SkinLook`. Goblins were already matte
  (URP Lit 0.08).


- 2026-10-23: **the ghoul** (Daniel: "Undead first, you can start with the ghoul" / "ghoul being a type of zombie"; the
  ask was an undead "with big claws and an arched posture"). README "The ghoul": Ghoul builds + keys Claws, LongArms,
  Arch (body) and Lipless (face), added in place and propagated (63 hair/LOD objects); rags + GhoulClaws built for
  MGhoul/FGhoul only; preset `Ghoul` (noBeard: new C# field; `horn` palette + "Horn" group in HumanFaceConfig); exported
  with `hum_ghoul.export()` (no other cloth family touched), installed in MedievalSetting, `Rebuild Prefab Only` (new
  menu item: no showcase scene, safe while others have scenes open). Daniel mid-way: "claws can be even larger, it is
  hard to see them from a distance" -> 8-12 cm, thicker, light horn. MedievalSetting `GhoulCheck` renders a lineup on
  Kevin crouch / sprint / dual-wield clips and the zombie clips with the GoblinPosture bend applied (Logs/Ghoul).
  Gotchas: a key added to hum_faces.BODY_SLIDERS needs hum_builds reloaded too, or add_keys files it as a face key (no
  joint deltas); toe claws pointing down went 7 mm under the floor (turned up until they clear it).
  Open: not a game creature yet (no def, clip set or GoblinPosture hook in Creature.DressHuman: where ghouls live and
  how they fight is Daniel's call); no teeth or mouth interior (Lipless only flattens the lips); with fists (Kevin's
  punches) the talons pass through the palm; the Ghoul builds carry rags and claws only.

- 2026-10-23 (same day, Daniel: "don't bother with adding them to the game, build the creatures"): the undead batch from
  his card game. **Lich** (README "The lich"): preset + LichCrown fitted to the skull, robe in the magister's colours,
  checked in Unity (`Lich Lineup`); Human_Cloth_Undead.fbx + config re-exported and installed, Rebuild Prefab Only.
  **Vampire deprecated** (README "The vampire - deprecated"): he disliked the fangs on sight; the preset, Fangs and
  VampireCape are unregistered, their built meshes deleted from humans.blend, nothing was exported. The zombie wolf is
  in the Beasts repo.
  Gotcha: a plate garment needs the `Ornament` UV (zeros) or Humans/Plate shows ornament on it.

- 2026-10-23 (later, Daniel: "Keep moving on the creatures / humanoids"): **elves, giants, earth elementals** (README "More
  peoples"). New: `hum_races.py` (ELF, GIANT, EARTH_ELEMENTAL), `hum_elemental.py` (the rock garment), C# preset fields
  `ageMin`/`ageMax` (drawn last) and the `stone` palette ("Stone" group); `Human_Cloth_Elemental.fbx`. Installed with the
  install script + Rebuild Prefab Only; checked in Unity lineups. Gotchas: the Cloak's hood is a companion and comes with
  it (hid the elves' ears: "-CloakHood"); a preset can't force the sex (sexMin only pushes further the way it already
  leans), so the elemental is built on both Orc builds. Open: the elves' faces keep the head's slightly melancholy mouth;
  no elven garments (the leather coat in greens); the giant's face is a heavy human's.
- Same round: **demon, imp, angel + wings** (README "Demons, imps, angels and their wings"): Horns beard style (rigid keys
  per horn: long rigid pieces must not ride Surface Deform), presets DEMON/IMP/ANGEL, `hum_wings` (DemonWings, AngelWings,
  rigid on spine_03). Exported Human_Hair.fbx (horns), Human_Cloth_Wings.fbx, config; Unity lineups checked. Open: wings
  don't flap (no wing bones yet); the angel's feathers use the bone pattern (greyish: dress them white); the imp is a
  scaled Slim body (no own proportions).
- 2026-10-23 (evening, Daniel: "Do these tasks you mentioned"): **the wings move + the angel's feathers** (README "Demons,
  imps, angels and their wings"). Six wing helper bones (`hum_helpers.WING`, synced into the live HumanRig with
  `sync_bones`: 102 bones), both wings re-skinned onto them, the rig json's `wings` list, the `HumanWings` runtime
  component (beat, breath, fold) set up by `HumanSetup.AddWings` and switched on by `HumanFace`. The angel got
  `T_Cloth_Feather` + `M_HumanFeather` (per-blade UVs) and a white "Feather" colour group (config `feather`). Exported
  Human_Body.fbx, Human_Cloth_Wings.fbx, rig + config; installed, Rebuild Prefab Only; no clip import warnings after the
  bone count change; checked with `Wings Beat` + `Angel Lineup`. Open: nothing in the game sets `flap`/`fold` yet (no
  flying creature AI); from the front the wings show their shaded undersides (greyer).
- 2026-10-23 (night, Daniel: "Do the number 4" - my list of rough edges): **the imp's own proportions and the elves'
  clothes** (README "Demons, imps, angels and their wings" > Imp, "More peoples" > Elven clothes). Imp: an Imp build
  (MImp/FImp, BUILD_ODDS 0) from body keys plus a new one, ShortLegs (added in place with `add_keys` +
  `propagate_keys`), and a preset head scale on the head bone (C# HumanFaceData.headScale, Preset headScaleMin/Max,
  HumanFace.ApplySkeleton); DemonWings + RagTrousers built for it. Elves: `hum_elven` ElvenTunic + ElvenCape (leaf
  hems), `_cloak` got `hem` and `leaves`. Exported Human_Body.fbx (the key), Human_Cloth_Wings/Rags/Elven.fbx, rig,
  config; installed, Rebuild Prefab Only; Imp + Elf lineups checked (GhoulCheck now grounds characters and logs it).
  Gotcha: a deform that lowers the body must keep `joint-ground` still - `full_coords` re-grounds by it after every
  deform, which first undid the drop (feet 18.8 cm up, pelvis unmoved). Open: the imp's face is still the human head
  with sliders (no grin of its own); nothing in the game spawns imps or elves yet.
- 2026-10-24 (Daniel, after watching MedievalSetting's Creatures_Test: "the ghoul has the fist clutched in some
  animations, making the nails pierce the hand to the other side"): **`HumanClawHands`** (README "The ghoul" > No
  fists): finger joints held to 40/40/20 deg from the open hand while claws are worn. Measured in Unity first (no limit:
  309/900 frames pierced, up to 13 cm; 45/45/25: 3; 40/40/20: 1, a thumb at 0.7 cm), renders of the worst hands with
  and without in MedievalSetting `Logs/Ghoul/claw_*.png`. Installed, Rebuild Prefab Only; on for the ghoul, off for
  the elf and the lich.
- 2026-10-24 (Daniel: "no fantasy pack is done if it does not have dwarves"): **dwarves** (README "More peoples" >
  Dwarf). The Dwarf build (body keys incl. ShortLegs), `hum_races.DWARF`, the Dwarf beard, preset options
  `beard_masc_only` / `beard_from_hair` (Python undead_face + C# ApplyPreset), the whole wardrobe built for MDwarf and
  FDwarf in batches of ~20 garments (each batch ~70-135 s in the live Blender; a single call for all 74 would be ~10
  min). Exported every cloth family, Human_Hair.fbx and the config (body and rig unchanged: no new key); installed,
  Rebuild Prefab Only; MedievalSetting `Dwarf Lineup` and a dwarf pair in Creatures_Test. Gotcha: my first check
  outfit put a Belt and a Shirt with the Hauberk / Gambeson, and HumanActor.Dress dropped the mail (Excludes). Open:
  the women's beards are my call (off); no dwarven garments of their own yet (the human gear fits); nothing in the
  game spawns dwarves.
