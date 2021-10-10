#Copyright (c) 2021 Victor "NegInfinity" Eremin

#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.

#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

"""
This file is under MIT license.

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
"""

import bpy
import bmesh
import os.path
import json

bl_info = {
	"name": "Texture Palette",
	"blender": (2, 93, 0),
	"version": (0, 0, 1),
	"description": "Multi-material texture palette for low poly models",
	"author": "Victor \"NegInfinity\" Eremin",
	"category": "Material"
}

class MultiTexSubMatProps(bpy.types.PropertyGroup):
	subMatName: bpy.props.StringProperty(
		name = "Name",
		description = "Submaterial name"
	)
	albedo: bpy.props.FloatVectorProperty(
		name = "Albedo",
		subtype = 'COLOR',
		default = (1.0, 1.0, 1.0),
		description = "albedo color",
		min = 0.0,
		max = 1.0
	)
	alpha: bpy.props.FloatProperty(
		name = "Alpha",
		description = "Alpha transparency",
		default = 1.0,
		min = 0.0,
		max = 1.0
	)
	metallic: bpy.props.FloatProperty(
		name = "Metallic",
		description = "Metallic PBR parameter",
		default = 0.0,
		min = 0.0,
		max = 1.0
	)
	roughness: bpy.props.FloatProperty(
		name = "Roughness",
		description = "Roughness PBR parameter",
		default = 0.5,
		min = 0.0,
		max = 1.0
	)
	emissive: bpy.props.FloatVectorProperty(
		name = "Emissive",
		subtype = 'COLOR',
		default = (0.0, 0.0, 0.0),
		description = "Emissive Color",
		min = 0.0,
		max = 1.0
	)
	emission_strength: bpy.props.FloatProperty(
		name = "Strength",
		description = "Emission strength of this material",
		default = 1.0,
		min = 0.0,
		max = 256.0
	)

class MultiTexProps(bpy.types.PropertyGroup):
	numColumns: bpy.props.IntProperty(
		name = "Num Columns",
		description = "Number of columns in final texture",
		default = 4,
		min = 1,
		max = 16
	)
	numRows: bpy.props.IntProperty(
		name = "Num Rows",
		description = "Number of rows in final texture",
		default = 4,
		min = 1,
		max = 16
	)
	cellSize: bpy.props.IntProperty(
		name = "Cell Size",
		description = "Number of pixels per cell",
		default = 4,
		min = 1,
		max = 32
	)
	maxEmissionStrength: bpy.props.IntProperty(
		name = "Max Emission",
		description = "Maximum Emission Strength",
		default = 1,
		min = 1,
		max = 32
	)
	useRgbRoughness: bpy.props.BoolProperty(
		name = "Rgb Roughness",
		description = "Encode metallic and roughness into RGB in this material",
		default = True
	)
	useSmoothness: bpy.props.BoolProperty(
		name = "Use Smoothness",
		description = "Use Smoothness instead of Roughness (Unity style)",
		default = False
	)
	texNamePrefix: bpy.props.StringProperty(
		name = "Texture Prefix",
		description = "Prefix used when generating texture names",
		default = "multiTex"
	)	
	saveTexDir: bpy.props.StringProperty(
		name = "Save to Dir",
		description = "Save textures to directory",
		default = "//",
		subtype = 'DIR_PATH'
	)
	useMaterialName: bpy.props.BoolProperty(
		name = "Use Mat Name",
		description = "Use material name for prefix",
		default = False
	)
	useShortTexNames: bpy.props.BoolProperty(
		name = "Use Short Names",
		description = "Use short text names (al instead of Albedo, etc)",
		default = False
	)
	useLinearSpace: bpy.props.BoolProperty(
		name = "Linear color",
		description = "Use linear colorspace for new textures.",
		default = True
	)
	useTga: bpy.props.BoolProperty(
		name = "Use tga",
		description = "Save color textures to tga instead of png",
		default = False
	)
	compactUi: bpy.props.BoolProperty(
		name = "Compact ui",
		description = "Use compact ui layout",
		default = False
	)
	submats: bpy.props.CollectionProperty(type=MultiTexSubMatProps)
	
	def genTexName(self, longName: str, shortName: str, matName: str = ""):
		prefix = matName if (matName and self.useMaterialName) else self.texNamePrefix 
		if self.useShortTexNames:
			return prefix + shortName
		return prefix + longName

	def getTextureSize(self) -> tuple[int, int]:
		return (self.numColumns * self.cellSize, self.numRows * self.cellSize)
	
	def getMatRowCol(self, matIndex: int) -> tuple[int, int]:
		matX = matIndex % self.numColumns
		#matY = int(matIndex / self.numColumns)
		matY = self.numRows - 1 - int(matIndex / self.numColumns)
		return (matX, matY)
	
	def getMatIndexFromRowCol(self, rowCol) -> int:
		return rowCol[0] + (self.numRows - 1 - rowCol[1]) * self.numColumns
		#return rowCol[0] + rowCol[1] * self.numColumns

	def getMatRect(self, matIndex: int) -> tuple[int, int]:
		return self.getRowColRect(self.getMatRowCol(matIndex))
	
	def getMatRectUv(self, matIndex: int) -> tuple[float, float]:
		return self.getRowColRectUv(self.getMatRowCol(matIndex))

	def getRowColRect(self, rowCol: tuple[int, int]) -> tuple[int, int, int, int]:
		texSize = self.getTextureSize()
		x0 = rowCol[0] * self.cellSize
		y0 = rowCol[1] * self.cellSize
		return (x0, y0, x0 + self.cellSize, y0 + self.cellSize)
				
	def getRowColRectUv(self, rowCol: tuple[int, int]) -> tuple[float, float, float, float]:
		pixelRect = self.getRowColRect(rowCol)
		sizes = self.getTextureSize()
		return (pixelRect[0]/sizes[0], pixelRect[1]/sizes[1], 
			pixelRect[2]/sizes[0], pixelRect[3]/sizes[1]
		)
		
	def getRowColFromUv(self, uv: tuple[float, float]) -> tuple[int, int]:
		return (int(uv[0] * self.numColumns), int(uv[1]*self.numRows))

class Utils:
	@staticmethod
	def getObjectFromContext(context) -> bpy.types.Material:
		return context.material

	@staticmethod
	def getObjectProps(obj) -> MultiTexProps:
		return obj.multiTexProps

	@staticmethod
	def getPropsFromContext(context) -> MultiTexProps:
		obj = Utils.getObjectFromContext(context)
		props = Utils.getObjectProps(obj)
		return props

	@staticmethod
	def objectHasProps(obj) -> bool:
		return obj.multiTexProps is not None

	@staticmethod
	def initObjectProps(obj) -> bool:
		if not (obj.multiTexProps is None):
			return False
		obj.multiTexProps = bpy.props.PointerProperty(type=MultiTexProps)
		return True

	@staticmethod
	def contextHasData(context) -> bool:
		return Utils.getObjectFromContext(context) is not None

	@staticmethod
	def uvRectApplyMargin(uvRect: tuple[float, float, float, float], margin:float = 0.25)->tuple[float, float, float, float]:
		midPoint = (
			(uvRect[0] + uvRect[2])*0.5, 
			(uvRect[1] + uvRect[3])*0.5
		)
		scale = 1.0 - margin
		return(
			(uvRect[0] - midPoint[0])*scale + midPoint[0],
			(uvRect[1] - midPoint[1])*scale + midPoint[1],
			(uvRect[2] - midPoint[0])*scale + midPoint[0],
			(uvRect[3] - midPoint[1])*scale + midPoint[1],
		)
		
	@staticmethod
	def applyUvRect(uv:tuple[float, float], uvRect: tuple[float, float, float, float]) -> tuple[float, float]:
		return(
			uvRect[0] + (uvRect[2] - uvRect[0])*uv[0],
			uvRect[1] + (uvRect[3] - uvRect[1])*uv[1],
		)

	@staticmethod
	def unApplyUvRect(uv:tuple[float, float], uvRect: tuple[float, float, float, float]) -> tuple[float, float]:
		return(
			(uv[0] - uvRect[0])/(uvRect[2] - uvRect[0]),
			(uv[1] - uvRect[1])/(uvRect[3] - uvRect[1])
		)

class MatKeys:
	NAME = "name"
	ALBEDO_R = "albedoR"
	ALBEDO_G = "albedoG"
	ALBEDO_B = "albedoB"
	ALPHA = "alpha"
	EMISSIVE_R = "emissiveR"
	EMISSIVE_G = "emissiveG"
	EMISSIVE_B = "emissiveB"
	EMISSIVE_STRENGTH = "emissiveStrength"
	METALLIC = "metallic"
	ROUGHNESS = "roughness"

class BsdfInputNames:
	albedo = 'Base Color'
	metallic = 'Metallic'
	roughness = 'Roughness'
	alpha = 'Alpha'
	emission = 'Emission'
	emissionStrength = 'Emission Strength'

class TexNodeNames:
	albedo = 'multitex_albedo'
	metallic = 'multitex_metallic'
	emissive = 'multitex_emissive'

class MatNodeNames:
	outputMat = 'OUTPUT_MATERIAL'
	bsdf = 'BSDF_PRINCIPLED'

class MultiTexAddMat(bpy.types.Operator):
	bl_label = "Add New Sub Material"
	bl_idname = "multitex.add_new_submat"
	bl_options = {'REGISTER', 'UNDO'}
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context)
	
	def execute(self, context):
		props = Utils.getPropsFromContext(context)
		newMat: MultiTexSubMatProps = props.submats.add()
		newMat.subMatName = "Mat {0}".format(len(props.submats)-1)
		return {'FINISHED'}
	
class MultiTexInitProps(bpy.types.Operator):
	bl_label = "Init Multitexture"
	bl_idname = "multitex.init_props"
	
	@classmethod
	def poll(self, context):
		obj = Utils.getObjectFromContext(context)
		return (obj is not None) and not Utils.objectHasProps(obj)
	
	def execute(self, context):
		obj = Utils.getObjectFromContext(context)
		Utils.initObjectProps(obj)
		return {'FINISHED'}

class MultiTexRemoveMat(bpy.types.Operator):
	bl_label = "Remove"
	bl_idname = "multitex.remove_submat"
	bl_description = "Remove"
	bl_options = {'REGISTER', 'UNDO'}
	
	index: bpy.props.IntProperty(
		min = 0
	)
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context) and (context.mode != 'EDIT_MESH')
	
	def execute(self, context):
		props = Utils.getPropsFromContext(context)
		props.submats.remove(self.index)
		return {'FINISHED'} 
	
class MultiTexMoveMatUp(bpy.types.Operator):
	bl_label = "Move Up"
	bl_idname = "multitex.move_mat_up"
	bl_description = "Move Up"
	bl_options = {'REGISTER', 'UNDO'}
	
	index: bpy.props.IntProperty(
		min = 0
	)
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context) and (context.mode != 'EDIT_MESH')
	
	def execute(self, context):
		props = Utils.getPropsFromContext(context)
		if (self.index > 0):
			props.submats.move(self.index, self.index-1)
		return {'FINISHED'} 
	  
class MultiTexMoveMatDown(bpy.types.Operator):
	bl_label = "Move Down"
	bl_idname = "multitex.move_mat_down"
	bl_description = "Move Down"
	bl_options = {'REGISTER', 'UNDO'}
	
	index: bpy.props.IntProperty(
		min = 0
	)
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context) and (context.mode != 'EDIT_MESH')
	
	def execute(self, context):
		props = Utils.getPropsFromContext(context)
		if (self.index < (len(props.submats) - 1)):
			props.submats.move(self.index, self.index+1)
		return {'FINISHED'} 

class MultiTexAssignMat(bpy.types.Operator):
	bl_label = "Assign"
	bl_idname = "multitex.assign_mat"
	bl_description = "Assign material to selected faces"
	bl_options = {'REGISTER', 'UNDO'}
	
	index: bpy.props.IntProperty(
		min = 0
	)
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context) \
			and (context.mode == 'EDIT_MESH') and context.edit_object
	
	def execute(self, context):
		props = Utils.getPropsFromContext(context)
		uvRect = props.getMatRectUv(self.index)
		obj = context.edit_object
		rect = props.get
		
		bm = bmesh.from_edit_mesh(obj.data)
		uvLay = bm.loops.layers.uv.active
		
		minUv = (0.0, 0.0)
		maxUv = (0.0, 0.0)
		foundFaces = False
		for face in bm.faces:
			if not face.select:
				continue
			for loop in face.loops:
				curUv = loop[uvLay].uv
				if not foundFaces:
					minUv = (curUv[0], curUv[1])
					maxUv = (curUv[0], curUv[1])
					foundFaces = True
				else:
					minUv = (
						min(minUv[0], curUv[0]),
						min(minUv[1], curUv[1])
					)
					maxUv = (
						max(maxUv[0], curUv[0]), 
						max(maxUv[1], curUv[1])
					)
				
			pass
		
		if not foundFaces:
			self.report({'WARNING'}, 'No selected faces found')
			return {'FINISHED'} 
		
		minRowCol = props.getRowColFromUv(minUv)
		maxRowCol = props.getRowColFromUv(maxUv)
		
		if minRowCol == maxRowCol:
			print("uv reassignment")
			origRowCol = minRowCol
			newRowCol = props.getMatRowCol(self.index)
			#print(origRowCol, newRowCol)
			origUvRect = props.getRowColRectUv(origRowCol)
			newUvRect = props.getRowColRectUv(newRowCol)
			#print(origUvRect, newUvRect)
			for face in bm.faces:
				if not face.select:
					continue
				for loop in face.loops:
					curUv = loop[uvLay].uv
					newUv = Utils.applyUvRect(
						Utils.unApplyUvRect(
							curUv,
							origUvRect
						),
						newUvRect
					)
					#print(curUv, newUv)
					loop[uvLay].uv = newUv
				pass
		else:
			print("first time uv assignment")
			newRowCol = props.getMatRowCol(self.index)
			uvRect = props.getRowColRectUv(newRowCol)
			uvRect = Utils.uvRectApplyMargin(uvRect)
			for face in bm.faces:
				if not face.select:
					continue
				for loop in face.loops:
					curUv = loop[uvLay].uv
					newUv = Utils.applyUvRect(curUv, uvRect)
					#print(curUv, newUv)
					loop[uvLay].uv = newUv
				pass
		
		bmesh.update_edit_mesh(obj.data, True)
		return {'FINISHED'} 

class MultiTexSelectByMat(bpy.types.Operator):
	bl_label = "Select"
	bl_idname = "multitex.select_by_mat"
	bl_description = "Select faces used by this material"
	bl_options = {'REGISTER', 'UNDO'}
	
	index: bpy.props.IntProperty(
		min = 0
	)
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context) \
			and (context.mode == 'EDIT_MESH') and context.edit_object
	
	def execute(self, context):
		obj = context.edit_object
		
		bm = bmesh.from_edit_mesh(obj.data)
		props = Utils.getPropsFromContext(context)
		uvLay = bm.loops.layers.uv.active
		for face in bm.faces:
			face.select = False
			firstUv = True
			minUv = (0.0, 0.0)
			maxUv = (0.0, 0.0)
			for loop in face.loops:
				curUv = loop[uvLay].uv
				if firstUv:
					firstUv = False
					minUv = maxUv = (curUv[0], curUv[1])
				else:
					minUv = (
						min(minUv[0], curUv[0]), 
						min(minUv[1], curUv[1])
					)
					maxUv = (
						max(maxUv[0], curUv[0]), 
						max(maxUv[1], curUv[1])
					)
					
			minRowCol = props.getRowColFromUv(minUv)
			maxRowCol = props.getRowColFromUv(maxUv)
			if minRowCol != maxRowCol:
				continue
			
			matIndex = props.getMatIndexFromRowCol(minRowCol)
			if matIndex == self.index:
				face.select = True
			
		bmesh.update_edit_mesh(obj.data, True)
		return {'FINISHED'} 

class MultiTexBuild(bpy.types.Operator):
	bl_label = "Build Material"
	bl_idname = "multitex.build"
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context)
	
	def execute(self, context):
		obj = Utils.getObjectFromContext(context)
		props = Utils.getPropsFromContext(context)
		buildMultiTexMaterial(obj, props)
		return {'FINISHED'} 
	
class MultiTexSaveTextures(bpy.types.Operator):
	bl_label = "Save textures"
	bl_idname = "multitex.save_textures"
	bl_description = "Saves texture files to specific folder. Files with same name will be overwritten!"
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context)
	
	def saveTexNodeToFile(self, nodeName: str, obj: bpy.types.Material, props:MultiTexProps, colorTexture: bool):
		texNode = obj.node_tree.nodes.get(nodeName)
		if not texNode or not texNode.image:
			self.report({'WARNING'}, 'Could not find texture node {0}'.format(nodeName))
			return
		
		image: bpy.types.Image = texNode.image
		name, ext = os.path.splitext(image.name)

		colorExt = ".tga" if props.useTga else ".png"
		colorFormat = 'TARGA' if props.useTga else 'PNG'

		newExt = colorExt if colorTexture else ".exr"
		fullPath = os.path.join(props.saveTexDir, name + newExt)

		image.filepath_raw = fullPath
		image.file_format = colorFormat if colorTexture else 'OPEN_EXR'
		image.save()
		pass

	def execute(self, context):
		obj = Utils.getObjectFromContext(context)
		props = Utils.getPropsFromContext(context)
		emissiveTexNode = obj.node_tree.nodes.get(TexNodeNames.emissive)
		metallicTexNode = obj.node_tree.nodes.get(TexNodeNames.metallic)
		self.saveTexNodeToFile(TexNodeNames.albedo, obj, props, True)
		self.saveTexNodeToFile(TexNodeNames.emissive, obj, props, True)
		self.saveTexNodeToFile(TexNodeNames.metallic, obj, props, False)
		print("plug")
		return {'FINISHED'} 

class MultiTexCopyMat(bpy.types.Operator):
	bl_label = "Copy Material Settings"
	bl_idname = "multitex.copy_mat_settings"
	bl_description = "Copy material settings into json string. Can be pasted later as a submaterial"
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context)
	
	def execute(self, context):
		obj = Utils.getObjectFromContext(context)
		props = Utils.getPropsFromContext(context)

		bsdfNode: bpy.types.ShaderNodeBsdfPrincipled = findMatTreeNode(obj, MatNodeNames.bsdf)
		if not bsdfNode:
			self.report({'WARNING'}, 'BSDF node not found')
			return {'FINISHED'} 

		s = bsdfToJson(obj, bsdfNode)
		print(s)
		bpy.context.window_manager.clipboard = s
		return {'FINISHED'}

class MultiTexCopySubMat(bpy.types.Operator):
	bl_label = "Copy"
	bl_idname = "multitex.copy_sub_mat"
	bl_description = "Copy sub material settings into json string. Can be pasted later into another submaterial"
	
	index: bpy.props.IntProperty(
		min = 0
	)
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context)
	
	def execute(self, context):
		obj = Utils.getObjectFromContext(context)
		props = Utils.getPropsFromContext(context)
		if (self.index >= 0) and (self.index < len(props.submats)):
			submat = props.submats[self.index]
			s = subMatToJson(submat)
			print(s)
			bpy.context.window_manager.clipboard = s
		return {'FINISHED'} 

class MultiTexPasteSubMat(bpy.types.Operator):
	bl_label = "Paste"
	bl_idname = "multitex.paste_sub_mat"
	bl_description = "Paste sub material settings"
	bl_options = {'REGISTER', 'UNDO'}
	
	index: bpy.props.IntProperty(
		min = 0
	)
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context) and bpy.context.window_manager.clipboard
	
	def execute(self, context):
		obj = Utils.getObjectFromContext(context)
		props = Utils.getPropsFromContext(context)
		if (self.index >= 0) and (self.index < len(props.submats)):
			submat = props.submats[self.index]
			try:
				js = bpy.context.window_manager.clipboard
				jsonToSubMat(submat, js)
				pass
			except ValueError:
				self.report({'WARNING'}, 'Could not decode json')
		return {'FINISHED'} 

class MultiTexCombineMeshes(bpy.types.Operator):
	"""Takes currently selected meshes and combines their materials into one master material"""
	bl_idname = "multitex.combine_meshes"
	bl_label = "Combine Mesh Materials"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context: bpy.context):
		print("processing")
		scene = context.scene

		objs = []

		if not context.selected_objects:
			for x in context.scene.objects:
				objs.append(x)
				print(x)
		else:
			for x in context.selected_objects:
				objs.append(x)
				print(x)

		def matHasMultiTex(mat: bpy.types.Material)-> bool:
			multiTex: MultiTexProps = mat.multiTexProps
			if multiTex and len(multiTex.submats) > 0:
				return True
			return False

		meshObjs = [x for x in objs if x and (x.type == 'MESH')]
		mats = []
		for x in meshObjs:
			curObj: bpy.types.Object = x
			print(curObj, curObj.type, curObj.data)
			mesh: bpy.types.Mesh = curObj.data
			print(mesh.materials)
			for mat in mesh.materials:
				if mat and not mat in mats and not matHasMultiTex(mat):
					mats.append(mat)

		if not mats:
			self.report({'ERROR'}, "No materials to combine")
			print("No materials to combine")
			return {'CANCELLED'}

		# print(mats)
		mats.sort(key=lambda x: x.name)
		numMats = len(mats)

		def findPow2(num: int):
			result = 1
			while result*result < num:
				result *= 2
			return result

		pow2 = findPow2(numMats)
		print(numMats, pow2)

		combinedMat = bpy.data.materials.new(name = "Combined Material")
		#multiTex:MultiTexProps = bpy.props.PointerProperty(type=MultiTexProps)
		#combinedMat.multiTexProps = multiTex
		multiTex:MultiTexProps = combinedMat.multiTexProps
				
		multiTex.numRows = pow2
		multiTex.numColumns = pow2
		multiTex.cellSize = 1

		print(mats)
		for curMat in mats:
			subMat: MultiTexSubMatProps = multiTex.submats.add()
			bsdf = findMatTreeNode(curMat, MatNodeNames.bsdf)
			if bsdf:
				js = bsdfToJson(curMat, bsdf)
				jsonToSubMat(subMat, js)

		matRects = [multiTex.getMatRectUv(x) for x in range(len(mats))]

		def objHasMultiTex(obj: bpy.types.Object) -> bool:
			if obj.data and obj.type == 'MESH':
				mesh: bpy.types.Mesh = obj.data
				if mesh.materials:
					for mat in mesh.materials:
						if matHasMultiTex(mat):
							return True
			return False

		newObjs = []
		for x in meshObjs:
			curObj: bpy.types.Object = x
			if objHasMultiTex(curObj):
				self.report({'INFO'}, "obj {0} already has multitex material, skipping".format(curObj.name))
				print("obj {0} already has multitex material, skipping".format(curObj.name))
				continue
			newObj: bpy.types.Object = curObj.copy()
			newObjs.append(newObj)
			newObj.data = curObj.data.copy()
			context.collection.objects.link(newObj)
			newMesh: bpy.types.Mesh = newObj.data

			bm = bmesh.new()
			bm.from_mesh(newMesh)
			uvLay = bm.loops.layers.uv.active

			meshMats = newMesh.materials
			meshMatIdx = [mats.index(x) for x in meshMats]
			
			for face in bm.faces:
				matIdx = meshMatIdx[face.material_index]
				uvRect = matRects[matIdx]
				print(uvRect)
				face.material_index = 0
				for loop in face.loops:
					curUv = loop[uvLay].uv
					newUv = Utils.applyUvRect(curUv, uvRect)
					loop[uvLay].uv = newUv

			bm.to_mesh(newMesh)

			newMesh.materials.clear()
			newMesh.materials.append(combinedMat)

		print("num mats: {0}".format(len(mats)))

		if not newObjs:
			self.report({'ERROR'}, "No objects were created")
			print("No objects were created")
			return {'CANCELLED'}

		multiTex.useShortTexNames = True
		multiTex.useTga = True
		multiTex.compactUi = True
		buildMultiTexMaterial(combinedMat, multiTex)

		for x in bpy.context.selected_objects:
			x.select_set(False)

		for x in newObjs:
			x.select_set(True)

		return {'FINISHED'}

	pass

def findMatTreeNode(mat: bpy.types.Material, type: str):
	for node in mat.node_tree.nodes:
		if node.type == type:
			return node
	return None

def getOrCreateNode(nodeName, nodeTree: bpy.types.NodeTree, nodeClassName, location=[0.0, 0.0]):
	node = nodeTree.nodes.get(nodeName)
	if not node:
		node = nodeTree.nodes.new(nodeClassName)
		node.name = nodeName
		node.location = location
	return node

def getOrCreateTexNode(nodeName: str, nodeTree: bpy.types.NodeTree, 
		interpolation='Closest', location=[0.0,0.0]) -> bpy.types.ShaderNodeTexImage:
	texNode: bpy.types.ShaderNodeTexImage = nodeTree.nodes.get(nodeName)
	if not texNode:
		texNode = nodeTree.nodes.new('ShaderNodeTexImage')
		texNode.name = nodeName
		texNode.interpolation = interpolation
		texNode.location = location
	return texNode

def fillRgbaRect(image: bpy.types.Image, x0, y0, xSize, ySize, r, g, b, a):
	for y in range(0, ySize):
		lineStart = (y0 + y) * image.size[0] * image.channels
		offset = x0 * image.channels + lineStart
		for x in range(0, xSize):
			image.pixels[offset + 0] = r
			image.pixels[offset + 1] = g
			image.pixels[offset + 2] = b
			image.pixels[offset + 3] = a
			offset += image.channels

def adjustOrCreateTexture(tex: bpy.types.Image, sizeX: int, sizeY: int, numChannels: int, alpha: bool, newTexName: str, linear: bool):
	if not tex or (tex and (tex.channels != numChannels)):
		tex = bpy.data.images.new(
			newTexName, 
			width=sizeX, 
			height=sizeY,
			alpha=alpha
		)
		if linear:
			tex.colorspace_settings.name = 'Linear'
	if (tex.size[0] != sizeX) or (tex.size[1] != sizeY):
		tex.scale(sizeX, sizeY)
	return tex
	
def buildMultiTexMaterial(mat: bpy.types.Material, props: MultiTexProps):
	if not mat.use_nodes:
		print("Enabling nodes")
		mat.use_nodes = True
		
	outputNode = findMatTreeNode(mat, MatNodeNames.outputMat)
	bsdfNode = findMatTreeNode(mat, MatNodeNames.bsdf)
	
	nodeTree = mat.node_tree
	
	needToLink = False
	if not outputNode:
		needToLink = True
		outputNode = nodeTree.nodes.new('ShaderNodeOutputMaterial')
		outputNode.location = [300.0, 0.0]
		
	if not bsdfNode:
		needToLink = True
		bsdfNode = nodeTree.nodes.new('ShaderNodeBsdfPrincipled')
	
	if needToLink:
		nodeTree.links.new(outputNode.inputs['Surface'], bsdfNode.outputs['BSDF'])
		
	albedoSocket = bsdfNode.inputs[BsdfInputNames.albedo]
	metallicSocket = bsdfNode.inputs[BsdfInputNames.metallic]
	roughnessSocket = bsdfNode.inputs[BsdfInputNames.roughness]
	alphaSocket = bsdfNode.inputs[BsdfInputNames.alpha]
	
	albedoTexNode = getOrCreateTexNode(TexNodeNames.albedo, 
		nodeTree, 'Closest', [-600.0, 100.0]
	)
		
	nodeTree.links.new(albedoTexNode.outputs['Color'], albedoSocket)
	nodeTree.links.new(albedoTexNode.outputs['Alpha'], alphaSocket)
	
	#metallic chain
	metallicTexNode = getOrCreateTexNode(TexNodeNames.metallic, 
		nodeTree, 'Closest', [-600.0, -200.0]
	)
	invertRoughnessNode = getOrCreateNode("multitex_roughness_invert", nodeTree,
		"ShaderNodeMath", [-300, -300]
	)
	invertRoughnessNode.operation = 'SUBTRACT'
	invertRoughnessNode.inputs[0].default_value = 1.0
	invertRoughnessNode.inputs[1].default_value = 0.0

	nodeTree.links.new(metallicTexNode.outputs['Color'], metallicSocket)
	nodeTree.links.new(metallicTexNode.outputs['Alpha'], invertRoughnessNode.inputs[1])
	if props.useSmoothness:
		nodeTree.links.new(invertRoughnessNode.outputs[0], roughnessSocket)
	else:
		nodeTree.links.new(metallicTexNode.outputs['Alpha'], roughnessSocket)
	
	#emission chain
	emissiveMaxPower = getOrCreateNode("multitex_emissive_maxpower", nodeTree,
		'ShaderNodeValue', [-500.0, -800.0]
	)
	emissiveMaxPower.outputs[0].default_value = props.maxEmissionStrength
	emissiveMul1 = getOrCreateNode("multitex_emissive_mul1", nodeTree,
		'ShaderNodeMath', [-300.0, -600.0]
	)
	emissiveMul1.operation = 'MULTIPLY'
	nodeTree.links.new(emissiveMaxPower.outputs[0], emissiveMul1.inputs[1])
	emissiveTexNode = getOrCreateTexNode(TexNodeNames.emissive,
		nodeTree, 'Closest', [-600.0, -500.0]
	)
	nodeTree.links.new(emissiveTexNode.outputs['Alpha'], emissiveMul1.inputs[0])
	nodeTree.links.new(emissiveMul1.outputs[0], bsdfNode.inputs[BsdfInputNames.emissionStrength])
	nodeTree.links.new(emissiveTexNode.outputs['Color'], bsdfNode.inputs[BsdfInputNames.emission])
		
		
	cellSize = props.cellSize
	sizeX = props.numColumns * cellSize
	sizeY = props.numRows * cellSize
	
	albedoTexNode.image = adjustOrCreateTexture(
		albedoTexNode.image, 
		sizeX, sizeY, 4, True, 
		props.genTexName("Albedop", "_al", mat.name),
		props.useLinearSpace
	)
	metallicTexNode.image = adjustOrCreateTexture(
		metallicTexNode.image, 
		sizeX, sizeY, 4, True, 
		props.genTexName("Metallic", "_mt", mat.name),
		True
	)
	emissiveTexNode.image = adjustOrCreateTexture(
		emissiveTexNode.image, 
		sizeX, sizeY, 4, True, 
		props.genTexName("Emissive", "_em", mat.name),
		props.useLinearSpace
	)
	albedoImage = albedoTexNode.image
	metallicImage = metallicTexNode.image
	emissiveImage = emissiveTexNode.image
	
	maxNumMats = props.numColumns * props.numRows
	
	for matIndex in range(0, maxNumMats):
		matRect = props.getMatRect(matIndex)
		#print(matRect)
		rectX = matRect[0]
		rectY = matRect[1]
		
		if matIndex < len(props.submats):
			curMat = props.submats[matIndex]
			fillRgbaRect(albedoImage, 
				rectX, rectY, cellSize, cellSize, 
				curMat.albedo[0], curMat.albedo[1], curMat.albedo[2], curMat.alpha
			)
			metRough = 1.0 - curMat.roughness if props.useSmoothness else curMat.roughness
			metRg = curMat.metallic
			metB = metRough if props.useRgbRoughness else metRg
			metA = metRough
			fillRgbaRect(metallicImage, 
				rectX, rectY, cellSize, cellSize, 
				metRg, metRg, metB, metA
			)
			emStrength = max(0.0, min(1.0, curMat.emission_strength / props.maxEmissionStrength))
			fillRgbaRect(emissiveImage, 
				rectX, rectY, cellSize, cellSize, 
				curMat.emissive[0], curMat.emissive[1], curMat.emissive[2], emStrength
			)
		else:
			fillRgbaRect(albedoImage, rectX, rectY, cellSize, cellSize,
				0.0, 0.0, 0.0, 1.0
			)
			
			metB = 1.0 if props.useRgbRoughness else 0.0
			fillRgbaRect(metallicImage, rectX, rectY, cellSize, cellSize,
				0.0, 0.0, metB, 1.0
			)
			fillRgbaRect(emissiveImage, rectX, rectY, cellSize, cellSize,
				0.0, 0.0, 0.0, 1.0
			)

def bsdfToJson(mat: bpy.types.Material, bsdfNode: bpy.types.Material):
	albedoSocket: bpy.types.NodeSocket = bsdfNode.inputs[BsdfInputNames.albedo]
	metallicSocket: bpy.types.NodeSocket = bsdfNode.inputs[BsdfInputNames.metallic]
	roughnessSocket: bpy.types.NodeSocket = bsdfNode.inputs[BsdfInputNames.roughness]
	alphaSocket: bpy.types.NodeSocket = bsdfNode.inputs[BsdfInputNames.alpha]
	emissiveSocket: bpy.types.NodeSocket = bsdfNode.inputs[BsdfInputNames.emission]

	data = {
		MatKeys.NAME: mat.name,
		MatKeys.ALBEDO_R: albedoSocket.default_value[0],
		MatKeys.ALBEDO_G: albedoSocket.default_value[1],
		MatKeys.ALBEDO_B: albedoSocket.default_value[2],
		MatKeys.ALPHA: alphaSocket.default_value,
		MatKeys.EMISSIVE_R: emissiveSocket.default_value[0],
		MatKeys.EMISSIVE_G: emissiveSocket.default_value[1],
		MatKeys.EMISSIVE_B: emissiveSocket.default_value[2],
		MatKeys.EMISSIVE_STRENGTH: bsdfNode.inputs[BsdfInputNames.emissionStrength].default_value,
		MatKeys.METALLIC: metallicSocket.default_value,
		MatKeys.ROUGHNESS: roughnessSocket.default_value
	}
	return json.dumps(data, indent=4)

def subMatToJson(sm: MultiTexSubMatProps):
	data = {
		MatKeys.NAME: sm.name,
		MatKeys.ALBEDO_R: sm.albedo[0],
		MatKeys.ALBEDO_G: sm.albedo[1],
		MatKeys.ALBEDO_B: sm.albedo[2],
		MatKeys.ALPHA: sm.alpha,
		MatKeys.EMISSIVE_R: sm.emissive[0],
		MatKeys.EMISSIVE_G: sm.emissive[1],
		MatKeys.EMISSIVE_B: sm.emissive[2],
		MatKeys.EMISSIVE_STRENGTH: sm.emission_strength,
		MatKeys.METALLIC: sm.metallic,
		MatKeys.ROUGHNESS: sm.roughness
	}
	return json.dumps(data, indent=4)

def jsonToSubMat(sm: MultiTexSubMatProps, js: str):
	data:dict = json.loads(js)
	sm.subMatName = data.get(MatKeys.NAME, sm.name)
	sm.albedo[0] = data.get(MatKeys.ALBEDO_R, sm.albedo[0])
	sm.albedo[1] = data.get(MatKeys.ALBEDO_G, sm.albedo[1])
	sm.albedo[2] = data.get(MatKeys.ALBEDO_B, sm.albedo[2])
	sm.alpha = data.get(MatKeys.ALPHA, sm.alpha)
	sm.emissive[0] = data.get(MatKeys.EMISSIVE_R, sm.emissive[0])
	sm.emissive[1] = data.get(MatKeys.EMISSIVE_G, sm.emissive[1])
	sm.emissive[2] = data.get(MatKeys.EMISSIVE_B, sm.emissive[2])
	sm.emission_strength = data.get(MatKeys.EMISSIVE_STRENGTH, sm.emission_strength)
	sm.metallic = data.get(MatKeys.METALLIC, sm.metallic)
	sm.roughness = data.get(MatKeys.ROUGHNESS, sm.roughness)

class MultiTexPanel(bpy.types.Panel):
	bl_idname = "OBJECT_PT_multitex_panel"
	bl_label = "Multitexture"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "material"
	
	@classmethod
	def poll(self, context):
		return Utils.contextHasData(context)
	
	def drawSubmat(self, layout, submat, index):
		subLayout = layout.box()
		#if title:
		#	subLayout.label(text=title)
		row = subLayout.row()
		row.prop(submat, "subMatName")
		row.operator(MultiTexCopySubMat.bl_idname).index = index
		row.operator(MultiTexPasteSubMat.bl_idname).index = index

		row = subLayout.row()
		row.prop(submat, "albedo")
		row.prop(submat, "alpha")
		row = subLayout.row()
		row.prop(submat, "metallic")
		row.prop(submat, "roughness")
		
		row = subLayout.row()
		row.prop(submat, "emissive")
		row.prop(submat, "emission_strength")
		if index >= 0:
			row = subLayout.row()
			row.operator(MultiTexAssignMat.bl_idname).index = index
			row.operator(MultiTexSelectByMat.bl_idname).index = index
			row.operator(MultiTexRemoveMat.bl_idname).index = index
			row.operator(MultiTexMoveMatUp.bl_idname).index = index
			row.operator(MultiTexMoveMatDown.bl_idname).index = index
		
	def drawSubmatCompact(self, layout, submat, index):
		subLayout = layout.box()

		row = subLayout.row()
		split = row.split()
		col1 = split.column()
		col2 = split.column()
		col1.prop(submat, "subMatName", text="")
		row = col2.row()		
		row.operator(MultiTexCopySubMat.bl_idname, text="C").index = index
		row.operator(MultiTexPasteSubMat.bl_idname, text="P").index = index
		if index >= 0:
			#row = subLayout.row()
			row.operator(MultiTexAssignMat.bl_idname, text="A").index = index
			row.operator(MultiTexSelectByMat.bl_idname, text="S").index = index
			row.operator(MultiTexRemoveMat.bl_idname, icon='X', text="").index = index
			row.operator(MultiTexMoveMatUp.bl_idname, icon='TRIA_UP', text="").index = index
			row.operator(MultiTexMoveMatDown.bl_idname, icon='TRIA_DOWN', text="").index = index

		row = subLayout.row()
		row.prop(submat, "albedo", text="")
		row.prop(submat, "alpha", text="A")

		row.prop(submat, "emissive", text="")
		row.prop(submat, "emission_strength", text="EmStr")
		row.prop(submat, "metallic", text="M")
		row.prop(submat, "roughness", text="R")
	
	def draw(self, context):
		layout = self.layout
		obj = Utils.getObjectFromContext(context)
		props = Utils.getObjectProps(obj)

		layout.operator(MultiTexCopyMat.bl_idname)
		
		row = layout.row()
		row.prop(props, "numColumns")
		row.prop(props, "numRows")
		row.prop(props, "cellSize")

		row = layout.row()
		row.prop(props, "useRgbRoughness")
		row.prop(props, "useSmoothness")
		row.prop(props, "maxEmissionStrength")

		layout.prop(props, "texNamePrefix")

		row = layout.row()
		row.prop(props, "useShortTexNames")
		row.prop(props, "useMaterialName")

		row = layout.row()
		row.prop(props, "useTga")
		row.prop(props, "useLinearSpace")

		row = layout.row()
		row.prop(props, "compactUi")
		
		row = layout.row()
		row.prop(props, "saveTexDir")

		row = layout.row()
		row.operator(MultiTexBuild.bl_idname)
		row.operator(MultiTexSaveTextures.bl_idname)
		
		row = layout.row()
		row.label(text = "Mat slots: {0}".format(props.numRows * props.numColumns))
		row.label(text = "Current mats: {0}".format(len(props.submats)))

		for i in range(0, len(props.submats)):
			if props.compactUi:
				self.drawSubmatCompact(layout, props.submats[i], i)
			else:
				self.drawSubmat(layout, props.submats[i], i)
			
		layout.operator(MultiTexAddMat.bl_idname)
		
		
classes = (
	MultiTexSubMatProps,
	MultiTexProps,
	MultiTexAddMat,
	MultiTexRemoveMat,
	MultiTexInitProps,
	MultiTexMoveMatUp,
	MultiTexMoveMatDown,
	MultiTexSelectByMat,
	MultiTexAssignMat,
	MultiTexBuild,
	MultiTexSaveTextures,
	MultiTexCopyMat,
	MultiTexCopySubMat,
	MultiTexPasteSubMat,
	MultiTexPanel,
	MultiTexCombineMeshes
)

objectMenuClasses = (
	MultiTexCombineMeshes,
)

def register():
	for cls in classes:
		bpy.utils.register_class(cls)

	for cls in objectMenuClasses:
		bpy.types.VIEW3D_MT_object.append(lambda self, context, cls=cls: self.layout.operator(cls.bl_idname))

	bpy.types.Material.multiTexProps = bpy.props.PointerProperty(type=MultiTexProps)
	pass

def unregister():
	for cls in classes:
		bpy.utils.unregister_class(cls)
	del bpy.types.Material.multiTexProps
	pass

if __name__ == "__main__":
	register()