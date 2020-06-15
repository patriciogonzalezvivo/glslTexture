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
    
    _timer = None
    
    def invoke(self, context, event):
        
        self.vertex_default = '''
in vec2 a_position;
in vec2 a_texcoord;

void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
}
'''
            
        self.default_code = '''
uniform vec2    u_resolution;
uniform float   u_time;

void main() {
    vec3 color = vec3(0.0); 
    vec2 st = gl_FragCoord.xy / u_resolution;
    
    color.rg = st;
    color.b = abs(sin(u_time));

    gl_FragColor = vec4(color, 1.0);
}
'''

        self.current_code = ''
        self.current_time = 0.0
        self.shader = None
        self.batch = None
    
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
                        try:    
                            self.shader = gpu.types.GPUShader(self.vertex_default, self.current_code)
                        except Exception as Err:
                            print(Err)
                            self.shader = None
                    
                    # if there is a shader and no batch
                    if (self.shader != None and self.batch == None):
                        self.batch = batch_for_shader(
                            self.shader, 
                            'TRI_FAN', {
                                'a_position': ((-1, -1), (1, -1), (1, 1), (-1, 1))
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
                    name = self.source.split("/")[-1].split(".")[0]
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

blender_classes = [
    TEXTURE_OT_glsl_texture
]

def register():
    for blender_class in blender_classes:
        bpy.utils.register_class(blender_class)

def unregister():
    for blender_class in blender_classes:
        bpy.utils.unregister_class(blender_class)
