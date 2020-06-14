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
    "version": (0, 0, 1),
    "location": "Operator Search",
    "warning": "",
    "doc_url": "",
    "category": "Texture"
}

import bpy
import gpu
import bgl
from gpu_extras.batch import batch_for_shader

class TEXTURE_OT_glsl_texture(bpy.types.Operator):
    """Make a texture from a GLSL Shader"""
    bl_idname = 'texture.glsl_texture'
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
    
    def file_reload(self, filename):
        text = bpy.data.texts[self.source]
#        text.filepath = filename
#        fp = bpy.path.abspath(text.filepath)
        fp = bpy.path.abspath(filename)
        text.clear()
        
        with open(fp) as f:
            text.write(f.read())
        return True
    
    _timer = None
    
    def invoke(self, context, event):
        
        self.vertex_shader = '''
in vec2 a_position;
in vec2 a_texcoord;

void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
}
'''
            
        self.default_shader = '''
uniform vec2    u_resolution;

void main() {
    vec3 color = vec3(0.0); 
    vec2 st = gl_FragCoord.xy / u_resolution;
    
    color.rg = st;

    gl_FragColor = vec4(color, 1.0);
}
'''

        self.current_shader = ''
        self.fromFile = False
    
        wm = context.window_manager
        return wm.invoke_props_dialog(self)
    
    def modal(self, context, event):
        # if event.type in {'ESC'}:
        #     self.cancel(context)
        #     return {'CANCELLED'}
        
        if event.type == 'TIMER':
            
            if not self.source in bpy.data.texts:
                print(f'File name {self.source} not found. Ready to create one')
                
                if self.file_exist(self.source):
                    print("It's a file")
                    bpy.ops.text.open(filepath=self.source)
                    self.fromFile = True
                else:
                    bpy.data.texts.new(self.source)
                    print("It's not a file, populate with the default shader")
                    bpy.data.texts[self.source].write(self.default_shader)
            
            recompile = False
            
            if not bpy.data.texts[self.source].is_in_memory and bpy.data.texts[self.source].is_modified:
                print("Have been modify")
#                bpy.ops.text.resolve_conflict(resolution='RELOAD')
#                self.file_reload(self.source)
                text = bpy.data.texts[self.source]
                ctx = context.copy()
#                ctx["edit_text"] = text
#                bpy.ops.text.reload(ctx)
                #Ensure  context area is not None
                ctx['area'] = ctx['screen'].areas[0]
                oldAreaType = ctx['area'].type
                ctx['area'].type = 'TEXT_EDITOR'
                ctx['edit_text'] = text
                bpy.ops.text.resolve_conflict(ctx, resolution='RELOAD')
                #Restore context
                ctx['area'].type = oldAreaType
                    
            if self.current_shader != bpy.data.texts[self.source].as_string():
                recompile = True
                
            if recompile:
                print("Recompile... ")
                
                fragment_shader = bpy.data.texts[self.source].as_string()
                self.current_shader = fragment_shader
            
                offscreen = gpu.types.GPUOffScreen(self.width, self.height)

                with offscreen.bind():
                    bgl.glClear(bgl.GL_COLOR_BUFFER_BIT)
    
                    try:
                        shader = gpu.types.GPUShader(self.vertex_shader, fragment_shader)
                    except Exception as Err:
                        print(Err)
                        recompile = False
                    
                    if recompile:
                        batch = batch_for_shader(
                            shader, 
                            'TRI_FAN', {
                                'a_position': ((-1, -1), (1, -1), (1, 1), (-1, 1))
                            },
                        )
                
                        shader.bind()
            
#                        try:
#                            shader.uniform_float('u_time', bpy.context.scene.frame_float/bpy.context.scene.render.fps)
#                        except ValueError:
#                            print('Uniform: u_time not used')
                
                        try:
                            shader.uniform_float('u_resolution', (self.width, self.height))
                        except ValueError: 
                            print('Uniform: u_resolution not used')
            
                        batch.draw(shader)

                        buffer = bgl.Buffer(bgl.GL_BYTE, self.width * self.height * 4)
                        bgl.glReadBuffer(bgl.GL_BACK)
                        bgl.glReadPixels(0, 0, self.width, self.height, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, buffer)

                offscreen.free()

                if recompile:
                    print("Success recompiling")
                    name = self.source.split(".")[0]

                    if not name in bpy.data.images:
                        bpy.data.images.new(name, self.width, self.height)
                    image = bpy.data.images[name]
                    image.scale(self.width, self.height)
                    image.pixels = [v / 255 for v in buffer]
                    
        
        return {'PASS_THROUGH'}
    
    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        print(f'GlslTexture {self.source} cancel refreshing')
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

def register():
    bpy.utils.register_class(TEXTURE_OT_glsl_texture)

def unregister():
    bpy.utils.unregister_class(TEXTURE_OT_glsl_texture)
