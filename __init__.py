# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name": "glslTexture",
    "author": "Patricio Gonzalez Vivo",
    "description": "Adds a texture generated from a GLSL frament shader",
    "blender": (2, 80, 0),
    "version": (0, 0, 2),
    "location": "Add",
    "warning": "",
    "doc_url": "",
    "category": "Texture"
}

import bpy
import gpu
import bgl
from gpu_extras.batch import batch_for_shader
from bpy.app.handlers import persistent

class GlslTexture(bpy.types.Operator):
    """Make a texture from a GLSL Shader"""
    bl_idname = 'add.glsltexture'
    bl_label = 'GlslTexture'
    bl_options = { 'REGISTER', 'UNDO' }
    
    width: bpy.props.IntProperty(
        name = 'width',
        description = 'Texture width',
        default = 512,
        min = 1
    )
        
    height: bpy.props.IntProperty(
        name = 'height',
        description = 'Texture height',
        default = 512,
        min = 1
    )

    source: bpy.props.StringProperty(
#        subtype="FILE_PATH",
        name = 'Source',
        description = 'Text file name which contain the frament shader source code',
        default = 'default.frag'
    )

    @classmethod
    def poll(cls, context):
        return True
    
    def file_exist(self, filename):
        try:
            file = open( bpy.path.abspath(filename) ,'r')
            file.close()
            return True
        except:
            return False
    
    _timer = None
    
    def invoke(self, context, event):
        self.current_code = ""
        self.current_time = 0.0

        self.shader = None
        self.batch = None

        self.vertex_default = '''
void main() {
    v_texcoord = a_texcoord;
    gl_Position = vec4(a_position, 0.0, 1.0);
}
'''

        self.default_code = '''
void main() {
    vec4 color = vec4(0.0, 0.0, 0.0, 1.0); 
    vec2 uv = v_texcoord;
    
    color.rg = st;
    color.b = abs(sin(u_time));

    FragColor = color;
}
'''
    
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}
        
        if event.type == 'TIMER':
            
            # If there is no reference to source on the text editor, create one
            if not self.source in bpy.data.texts:
                print(f'File name {self.source} not found. Will create an internal one')
                
                # If match an external file 
                if self.file_exist(self.source):
                    bpy.ops.text.open(filepath=self.source)

                # else create a internal file with the default fragment code
                else:
                    bpy.data.texts.new(self.source)
                    bpy.data.texts[self.source].write(self.default_code)
            
            # If the source file is external and it have been modify, reload it
            if not bpy.data.texts[self.source].is_in_memory and bpy.data.texts[self.source].is_modified:
                print(f'External file {self.source} have been modify. Reloading...')
                text = bpy.data.texts[self.source]
                ctx = context.copy()
                #Ensure  context area is not None
                ctx['area'] = ctx['screen'].areas[0]
                oldAreaType = ctx['area'].type
                ctx['area'].type = 'TEXT_EDITOR'
                ctx['edit_text'] = text
                bpy.ops.text.resolve_conflict(ctx, resolution='RELOAD')
                #Restore context
                ctx['area'].type = oldAreaType

            render = False
            recompile = False

            now = context.scene.frame_float / context.scene.render.fps
            
            # If shader content change 
            if self.current_code != bpy.data.texts[self.source].as_string():
                recompile = True

            if self.current_time != now:
                render = True

            if render or recompile:
                self.current_code = bpy.data.texts[self.source].as_string()
                self.current_time = now
            
                offscreen = gpu.types.GPUOffScreen(self.width, self.height)
                with offscreen.bind():
                    bgl.glClear(bgl.GL_COLOR_BUFFER_BIT)
    
                    # If there is no shader or need to be recompiled
                    if self.shader == None or recompile:

                        vert_out = gpu.types.GPUStageInterfaceInfo("my_interface")
                        vert_out.smooth('VEC2', "v_texcoord")

                        shader_info = gpu.types.GPUShaderCreateInfo()
                        # shader_info.push_constant('MAT4', "viewProjectionMatrix")
                        # shader_info.push_constant('MAT4', "modelMatrix")
                        shader_info.push_constant('VEC2', "u_resolution")
                        shader_info.push_constant('FLOAT', "u_time")
                        # shader_info.sampler(0, 'FLOAT_2D', "image")
                        shader_info.vertex_in(0, 'VEC2', "a_position")
                        shader_info.vertex_in(1, 'VEC2', "a_texcoord")
                        shader_info.vertex_out(vert_out)
                        shader_info.fragment_out(0, 'VEC4', "FragColor")
                        shader_info.vertex_source( self.vertex_default )
                        shader_info.fragment_source( self.current_code )

                        try:    
                            self.shader = gpu.shader.create_from_info(shader_info)
                        except Exception as Err:
                            print(Err)
                            self.shader = None
                    
                    # if there is a shader and no batch
                    if (self.shader != None and self.batch == None):
                        self.batch = batch_for_shader(
                            self.shader, 
                            'TRI_FAN', {
                                'a_position': ((-1, -1), (1, -1), (1, 1), (-1, 1)),
                                "a_texcoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
                            },
                        )
                
                    if self.shader != None:
                        self.shader.bind()
            
                        try:
                            self.shader.uniform_float('u_time', self.current_time)
                        except ValueError:
                            pass
            
                        try:
                            self.shader.uniform_float('u_resolution', (self.width, self.height))
                        except ValueError: 
                            pass
            
                        self.batch.draw(self.shader)

                    buffer = bgl.Buffer(bgl.GL_BYTE, self.width * self.height * 4)
                    bgl.glReadBuffer(bgl.GL_BACK)
                    bgl.glReadPixels(0, 0, self.width, self.height, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, buffer)
                    render = True

                offscreen.free()

                if render:
                    name = self.source
                    if not name in bpy.data.images:
                        bpy.data.images.new(name, self.width, self.height)
                    image = bpy.data.images[name]
                    image.scale(self.width, self.height)
                    image.pixels = [v / 255 for v in buffer]
                    
        return {'PASS_THROUGH'}
    
    def execute(self, context):
        wm = context.window_manager
        self.timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        print(f'GlslTexture {self.source} cancel refreshing')
        wm = context.window_manager
        wm.event_timer_remove(self.timer)


@persistent
def loadGlslTextures(dummy):

    print("Looking for GlslTexture")
    for source_name in bpy.data.texts.keys():
        if source_name in bpy.data.images.keys():
            width = bpy.data.images[source_name].generated_width
            height = bpy.data.images[source_name].generated_height
            print(f"Loading GlslTexture {source_name}")
            bpy.ops.texture.glsl_texture('INVOKE_DEFAULT', width=width, height=height, source=source_name)

def menu_func(self, context):
    self.layout.operator(GlslTexture.bl_idname, text=GlslTexture.bl_label,icon='COLORSET_02_VEC')

def register():
    bpy.utils.register_class(GlslTexture)
    bpy.app.handlers.load_post.append(loadGlslTextures)
    bpy.types.VIEW3D_MT_add.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_add.remove(menu_func)
    bpy.app.handlers.load_post.remove(loadGlslTextures)
    bpy.utils.unregister_class(GlslTexture)
    



if __name__ == "__main__":
    register()