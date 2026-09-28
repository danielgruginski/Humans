# Combat clip QA (Blender, run through the MCP / Text editor with sys.path on `src`)

Set the globals first, then `exec(open(<file>).read())`:

- `weapons_helper.py` - stand-in sword / greatsword / spear on hand_r's grip frame, round shield on the left
  forearm (the same shapes HumanSetup builds in Unity); `show("sword" | "twohand" | "spear" | "none")`.
- `combat_sheet.py` - contact sheet: `CLIPS = [(clip, kit)]`, `FRAMES_N`, `VIEWS = [(yaw, dist)]`, `OUT`
  (written to `renders/_tmp`).
- `combat_check.py` - per frame, blade/shaft depth inside the skin and blade crossing the shield: `CHECK = [(clip, kit)]`.
  (A hit right behind the fist - the shaft inside the hand - is the grip itself.)
- `strain_check.py` - worst wrist twist / flex / deviation against Humanoid's limits and the biggest frame-to-frame
  turns: `NAMES = [clip]`.
- `key_search.py` - for keys whose wrists cost more than `THRESH` (hum_anim.wrist_comfort), the nearest blade
  direction (and with `POS = True` fist position) held comfortably: `NAMES`, `W_DIR`, `W_POS`, `MAXD`, `THRESH`,
  `ONLY = {clip: [key times]}`. Keys carrying elbows (4th item) are solved at those elbows. Prints replacement
  keys; paste them into hum_anim.py by hand.
