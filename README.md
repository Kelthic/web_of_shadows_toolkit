# Web of Shadows Toolkit

There is a bunch of scripts or materials to work with Spider-man: Web of Shadows game

## Normal Map convertor

This is simple script that converts default DX normal maps to Web of Shadows normals

Usage:

1. Put script inside texture sets
2. Open CMD using adress line
3. Put to cmd: "python pbr_to_wos.py"
4. After that put the name of your DX normal map (e.g "helmet_n_baked.png")
5. Done. Now your normals is converted to Web of Shadows game engine

Video tutorial with semi-detailed explain: https://youtu.be/tfR867lGgXU


## Diffuse and Emission mixer

This is simple script that mix diffuse map and emission mask in single one map

1. Put script inside texture sets
2. Open CMD using adress line
3. Put to cmd: "python diffuse_emission_mix.py"
4. After that put the name of your diffuse map (e.g "helmet_d_baked.png")
5. After that put the name of your emission mask (e.g "helmet_e_baked.png")
6. Done. Now your diffuse map have emission mask and game will use it

No video tutorial atm


## Blend "PBR To WoS"

This blend files include two nodegroups: WoS textures to Blender (PBR) or Blender (PBR) to Web of Shadows

Watch the videotut about how to use that blend file: https://youtu.be/tfR867lGgXU
