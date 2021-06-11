# Imporant

You *only* need "texture_palette.py" file from this repository and nothing else.
README.md and LICENSE.md are provided for github and convenience only.

# Readme

This project is under MIT license.

This is a simple tool for generating multi-material meshes for game engines,
using low-polygonal style.

The main idea is that in any material you can define multiple 'sub-materials',
and then based on the sub-material configuration, the script will generate a 
combined 'palette' texture, that will store albedo color, metallic and roughness,
and emission, along with emission power.

The reason why this exists is because FBX exporters do not correctly transfer
PBR data into game engines, and usually it has to be typed in by hand. This is 
not much of a problem in a traditional workflow, where everything is painted on
a texture, but it is a pain to deal with when you have a model with LARGE 
number of simple untextured materails. Also, having multiple materials increases
number of drawcalls, which is something you'd want to avoid.

To use the tool, create any blank material, unfold "Multitexture" panel, click
"Build Material". This will create node network, all the required textures, and 
it will also connect them correctly to each other.

You can destroy all the nodes if you want, just click "build" again, and it will
regenrate the shader. You update the texture by pressing the same button.
The textures will not be rebuilt automatically.

To start adding materials, click "add sub material" button. This will 
create a new sub material where you can configure indifividual parameters.
You can remove it with "remove", move up/down in the list, and so on.

Assign and select buttons work in mesh edit mode pretty much the same way 
normal material list does. If you have UV generated,
pressing Assign will stuff the UVs in question into related square, OR reassign
it into a new square. This will properly scale down the UVs the first time you do it,
so you can just pretty much "Unwrap" and then "Assign", which should work fairly quickly.

Select will selct all faces that fit into a specific material square for that 
particular material.

Multitexture settings:
Num Column and Num Rows specify how many rows and columns are in the texture,
which affects how many materials are stuffe into it.
Be aware, that if you change those UVs will NOT be recalculated and you'll have to redo
all of them.
Cell size is size of a single square in pixels.

Now, max emission affects a multiplier you apply to emissive color. The idea is to store
emission color in RGB, and multiplier in alpha channel, where ALPHA 1.0 will mean
the maximum emission power. This is something that you'll need to replicate in the 
game engine, and won't work out of the box. If you don't need emission overbrightening,
just leave it at 1.

Generated texture formats.
Albedo texture stores albedo in RGB, and Alpha in alpha channel.
Metallic texture stores Metallic in RG channels, and Roughness in BA channel.
Emissive texture stores emission color in RGB and emission power in alpha. 
Value stored in alpha channel is based on emission strength and max emission.

And that should be all. Have fun.
