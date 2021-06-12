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

bl_info = {
	"name": "Texture Palette",
	"blender": (2, 93, 0),
	"version": (0, 0),
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
	
	pass

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
	submats: bpy.props.CollectionProperty(type=MultiTexSubMatProps)
	
	def getTextureSize(self):
		return (self.numColumns * self.cellSize, self.numRows * self.cellSize)
	
	def getMatRowCol(self, matIndex):
		matX = matIndex % self.numColumns
		matY = int(matIndex / self.numColumns)
		return (matX, matY)
	
	def getMatRect(self, matIndex):
		return self.getRowColRect(self.getMatRowCol(matIndex))
	
	def getMatRectUv(self, matIndex):
		return self.getRowColRectUv(self.getMatRowCol(matIndex))

	def getRowColRect(self, rowCol):        
		x0 = rowCol[0] * self.cellSize
		y0 = rowCol[1] * self.cellSize
		return (x0, y0, x0 + self.cellSize, y0 + self.cellSize)
				
	def getRowColRectUv(self, rowCol):
		pixelRect = self.getRowColRect(rowCol)
		sizes = self.getTextureSize()
		return (pixelRect[0]/sizes[0], pixelRect[1]/sizes[1], 
			pixelRect[2]/sizes[0], pixelRect[3]/sizes[1]
		)
		
	def getRowColFromUv(self, uv):
		return (int(uv[0] * self.numColumns), int(uv[1]*self.numRows))
	
	def getMatIndexFromRowCol(self, rowCol):
		return rowCol[0] + rowCol[1] * self.numColumns        
	pass

def getObjectFromContext(context):
	return context.material

def getObjectProps(obj):
	return obj.multiTexProps

def getPropsFromContext(context):
	obj = getObjectFromContext(context)
	props = getObjectProps(obj)
	return props

def objectHasProps(obj):
	return obj.multiTexProps is not None

def initObjectProps(obj):
	if not (obj.multiTexProps is None):
		return False
	obj.multiTexProps = bpy.props.PointerProperty(type=MultiTexProps)
	return True

def contextHasData(context):
	return getObjectFromContext(context) is not None
	
def uvRectApplyMargin(uvRect, margin = 0.25):
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
	
def applyUvRect(uv, uvRect):
	return(
		uvRect[0] + (uvRect[2] - uvRect[0])*uv[0],
		uvRect[1] + (uvRect[3] - uvRect[1])*uv[1],
	)

def unApplyUvRect(uv, uvRect):
	return(
		(uv[0] - uvRect[0])/(uvRect[2] - uvRect[0]),
		(uv[1] - uvRect[1])/(uvRect[3] - uvRect[1])
	)

class MultiTexAddMat(bpy.types.Operator):
	bl_label = "Add New Sub Material"
	bl_idname = "multitex.add_new_submat"
	
	@classmethod
	def poll(self, context):
		return contextHasData(context)
	
	def execute(self, context):
		props = getPropsFromContext(context)
		newMat = props.submats.add()
		newMat.subMatName = "Mat {0}".format(len(props.submats)-1)
		return {'FINISHED'}
	
class MultiTexInitProps(bpy.types.Operator):
	bl_label = "Init Multitexture"
	bl_idname = "multitex.init_props"
	
	@classmethod
	def poll(self, context):
		obj = getObjectFromContext(context)
		return (obj is not None) and not objectHasProps(obj)
	
	def execute(self, context):
		obj = getObjectFromContext(context)
		initObjectProps(obj)        
		return {'FINISHED'}

class MultiTexRemoveMat(bpy.types.Operator):
	bl_label = "Remove"
	bl_idname = "multitex.remove_submat"
	
	index: bpy.props.IntProperty(
		min = 0
	)
	
	@classmethod
	def poll(self, context):
		return contextHasData(context) and (context.mode != 'EDIT_MESH')
	
	def execute(self, context):
		props = getPropsFromContext(context)
		props.submats.remove(self.index)
		return {'FINISHED'} 
	
class MultiTexMoveMatUp(bpy.types.Operator):
	bl_label = "Move Up"
	bl_idname = "multitex.move_mat_up"
	
	index: bpy.props.IntProperty(
		min = 0
	)    
	
	@classmethod
	def poll(self, context):
		return contextHasData(context) and (context.mode != 'EDIT_MESH')
	
	def execute(self, context):
		props = getPropsFromContext(context)
		if (self.index > 0):
			props.submats.move(self.index, self.index-1)
		return {'FINISHED'} 
	  
class MultiTexMoveMatDown(bpy.types.Operator):
	bl_label = "Move Down"
	bl_idname = "multitex.move_mat_down"
	
	index: bpy.props.IntProperty(
		min = 0
	)    
	
	@classmethod
	def poll(self, context):
		return contextHasData(context) and (context.mode != 'EDIT_MESH')
	
	def execute(self, context):
		props = getPropsFromContext(context)
		if (self.index < (len(props.submats) - 1)):
			props.submats.move(self.index, self.index+1)
		return {'FINISHED'} 

def getUvRectSize(uvRect):
	return (uvRect[2] - uvRect[0], uvRect[3] - uvRect[1])

class MultiTexAssignMat(bpy.types.Operator):
	bl_label = "Assign"
	bl_idname = "multitex.assign_mat"
	
	index: bpy.props.IntProperty(
		min = 0
	)    
	
	@classmethod
	def poll(self, context):
		return contextHasData(context) \
			and (context.mode == 'EDIT_MESH') and context.edit_object
	
	def execute(self, context):
		props = getPropsFromContext(context)
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
				curUv = loop[uvLay].uv;
				print(curUv)
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
		print(minUv, maxUv, minRowCol, maxRowCol)
		print(minRowCol == maxRowCol)
		
		if minRowCol == maxRowCol:
			print("uv reassignment")
			origRowCol = minRowCol
			newRowCol = props.getMatRowCol(self.index)
			print(origRowCol, newRowCol)
			origUvRect = props.getRowColRectUv(origRowCol)
			newUvRect = props.getRowColRectUv(newRowCol)
			print(origUvRect, newUvRect)
			for face in bm.faces:
				if not face.select:
					continue
				for loop in face.loops:
					curUv = loop[uvLay].uv;
					newUv = applyUvRect(
						unApplyUvRect(
							curUv,
							origUvRect
						),
						newUvRect
					)
					print(curUv, newUv)
					loop[uvLay].uv = newUv
				pass
		else:
			print("first time uv assignment")
			newRowCol = props.getMatRowCol(self.index)
			uvRect = props.getRowColRectUv(newRowCol)
			uvRect = uvRectApplyMargin(uvRect)
			for face in bm.faces:
				if not face.select:
					continue
				for loop in face.loops:
					curUv = loop[uvLay].uv;
					newUv = applyUvRect(curUv, uvRect)
					print(curUv, newUv)
					loop[uvLay].uv = newUv
				pass        
		
		bmesh.update_edit_mesh(obj.data, True)
		return {'FINISHED'} 

class MultiTexSelectByMat(bpy.types.Operator):
	bl_label = "Select"
	bl_idname = "multitex.select_by_mat"
	
	index: bpy.props.IntProperty(
		min = 0
	)    
	
	@classmethod
	def poll(self, context):
		return contextHasData(context) \
			and (context.mode == 'EDIT_MESH') and context.edit_object
	
	def execute(self, context):
		obj = context.edit_object
		
		bm = bmesh.from_edit_mesh(obj.data)
		props = getPropsFromContext(context)
		uvLay = bm.loops.layers.uv.active
		for face in bm.faces:
			face.select = False
			firstUv = True
			minUv = (0.0, 0.0)
			maxUv = (0.0, 0.0)
			for loop in face.loops:
				curUv = loop[uvLay].uv;
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
		return contextHasData(context)
	
	def execute(self, context):
		obj = getObjectFromContext(context)
		props = getPropsFromContext(context)
		buildMultiTexMaterial(obj, props)
		return {'FINISHED'} 
	
def findMatTreeNode(mat, type):
	for node in mat.node_tree.nodes:
		if node.type == type:
			return node
	return None

def getOrCreateNode(nodeName, nodeTree, nodeClassName, location=[0.0, 0.0]):
	node = nodeTree.nodes.get(nodeName)
	if not node:
		node = nodeTree.nodes.new(nodeClassName)
		node.name = nodeName
		node.location = location
	return node

def getOrCreateTexNode(nodeName, nodeTree, interpolation='Closest', location=[0.0,0.0]):
	texNode = nodeTree.nodes.get(nodeName)
	if not texNode:
		texNode = nodeTree.nodes.new('ShaderNodeTexImage')
		texNode.name = nodeName
		texNode.interpolation = interpolation
		texNode.location = location
	return texNode

def fillRgbaRect(image, x0, y0, xSize, ySize, r, g, b, a):
	for y in range(0, ySize):
		lineStart = (y0 + y) * image.size[0] * image.channels
		offset = x0 * image.channels + lineStart
		for x in range(0, xSize):
			image.pixels[offset + 0] = r
			image.pixels[offset + 1] = g
			image.pixels[offset + 2] = b
			image.pixels[offset + 3] = a
			offset += image.channels

def adjustOrCreateTexture(tex, sizeX, sizeY, numChannels, alpha, newTexName):
	if not tex or (tex and (tex.channels != numChannels)):
		tex = bpy.data.images.new(
			newTexName, 
			width=sizeX, 
			height=sizeY,
			alpha=alpha
		)
	if (tex.size[0] != sizeX) or (tex.size[1] != sizeY):
		tex.scale(sizeX, sizeY)
	return tex
	

def buildMultiTexMaterial(mat, props):
	if not mat.use_nodes:
		print("Enabling nodes")
		mat.use_nodes = True
		
	outputNode = findMatTreeNode(mat, 'OUTPUT_MATERIAL')
	bsdfNode = findMatTreeNode(mat, 'BSDF_PRINCIPLED')
	
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
		
	albedoSocket = bsdfNode.inputs['Base Color']
	metallicSocket = bsdfNode.inputs['Metallic']
	roughnessSocket = bsdfNode.inputs['Roughness']
	alphaSocket = bsdfNode.inputs['Alpha']
	
	print(albedoSocket)
	print(metallicSocket)
	print(roughnessSocket)
	print(alphaSocket)
	
	albedoTexNodeName = 'multitex_albedo'
	metallicTexNodeName = 'multitex_metallic'
	emissiveTexNodeName = 'multitex_emissive'    
	
	albedoTexNode = getOrCreateTexNode(albedoTexNodeName, 
		nodeTree, 'Closest', [-600.0, 100.0]
	)
		
	nodeTree.links.new(albedoTexNode.outputs['Color'], albedoSocket)
	nodeTree.links.new(albedoTexNode.outputs['Alpha'], alphaSocket)
	
	metallicTexNode = getOrCreateTexNode(metallicTexNodeName, 
		nodeTree, 'Closest', [-600.0, -200.0]
	)
	nodeTree.links.new(metallicTexNode.outputs['Color'], metallicSocket)
	nodeTree.links.new(metallicTexNode.outputs['Alpha'], roughnessSocket)
	
	emissiveMaxPower = getOrCreateNode("multitex_emissive_maxpower", nodeTree,
		'ShaderNodeValue', [-500.0, -800.0]
	)
	emissiveMaxPower.outputs[0].default_value = props.maxEmissionStrength
	emissiveMul1 = getOrCreateNode("multitex_emissive_mul1", nodeTree,
		'ShaderNodeMath', [-300.0, -600.0]
	)
	emissiveMul1.operation = 'MULTIPLY'
	nodeTree.links.new(emissiveMaxPower.outputs[0], emissiveMul1.inputs[1])
	emissiveTexNode = getOrCreateTexNode(emissiveTexNodeName,
		nodeTree, 'Closest', [-600.0, -500.0]
	)
	nodeTree.links.new(emissiveTexNode.outputs['Alpha'], emissiveMul1.inputs[0])
	nodeTree.links.new(emissiveMul1.outputs[0], bsdfNode.inputs['Emission Strength'])
	nodeTree.links.new(emissiveTexNode.outputs['Color'], bsdfNode.inputs['Emission'])
		
		
	cellSize = props.cellSize
	sizeX = props.numColumns * cellSize
	sizeY = props.numRows * cellSize
	
	albedoTexNode.image = adjustOrCreateTexture(
		albedoTexNode.image, 
		sizeX, sizeY, 4, True, "multiTexAlbedo"
	)
	metallicTexNode.image = adjustOrCreateTexture(
		metallicTexNode.image, 
		sizeX, sizeY, 4, True, "multiTexMetallic"
	)
	emissiveTexNode.image = adjustOrCreateTexture(
		emissiveTexNode.image, 
		sizeX, sizeY, 4, True, "multiTexEmissive"
	)
	albedoImage = albedoTexNode.image
	metallicImage = metallicTexNode.image
	emissiveImage = emissiveTexNode.image
		
	print(albedoImage)
	print(albedoImage.channels)
	print(albedoImage.pixels)
	
	rectX = 0
	rectY = 0
	print(props.submats)
	
	maxNumMats = props.numColumns * props.numRows
	
	for matIndex in range(0, maxNumMats):
		rectX = cellSize * (matIndex % props.numColumns)
		rectY = cellSize * int(matIndex / props.numColumns)
		
		if matIndex < len(props.submats):
			curMat = props.submats[matIndex]
			print(rectX, rectY, curMat, curMat.albedo[0])
			fillRgbaRect(albedoImage, 
				rectX, rectY, cellSize, cellSize, 
				curMat.albedo[0], curMat.albedo[1], curMat.albedo[2], curMat.alpha
			)
			fillRgbaRect(metallicImage, 
				rectX, rectY, cellSize, cellSize, 
				curMat.metallic, curMat.metallic, curMat.roughness, curMat.roughness
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
			fillRgbaRect(metallicImage, rectX, rectY, cellSize, cellSize,
				0.0, 0.0, 1.0, 1.0
			)
			fillRgbaRect(emissiveImage, rectX, rectY, cellSize, cellSize,
				0.0, 0.0, 0.0, 1.0
			)
		
		
	pass    

class MultiTexPanel(bpy.types.Panel):
	bl_idname = "OBJECT_PT_multitex_panel"
	bl_label = "Multitexture"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "material"
	
	@classmethod
	def poll(self, context):
		return contextHasData(context)
	
	def drawSubmat(self, layout, submat, index, title):
		subLayout = layout.box()
		if title:
			subLayout.label(text=title)
		subLayout.prop(submat, "subMatName")
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
		
	
	def draw(self, context):
		layout = self.layout
		obj = getObjectFromContext(context)
		props = getObjectProps(obj)
		
		row = layout.row()
		row.prop(props, "numColumns")
		row.prop(props, "numRows")
		row.prop(props, "cellSize")
		
		layout.prop(props, "maxEmissionStrength")
		
		layout.operator(MultiTexBuild.bl_idname)
		
		row = layout.row()
		row.label(text = "Mat slots: {0}".format(props.numRows * props.numColumns))
		row.label(text = "Current mats: {0}".format(len(props.submats)))

		#self.drawSubmat(layout, props.submat, "Submat")
		for i in range(0, len(props.submats)):
			self.drawSubmat(layout, props.submats[i], i, "Mat {0}".format(i))
			
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
	MultiTexPanel
)

def register():
	for cls in classes:
		bpy.utils.register_class(cls);
	bpy.types.Material.multiTexProps = bpy.props.PointerProperty(type=MultiTexProps)
	pass

def unregister():
	for cls in classes:
		bpy.utils.unregister_class(cls);
	del bpy.types.Material.multiTexProps
	pass

if __name__ == "__main__":
	register()