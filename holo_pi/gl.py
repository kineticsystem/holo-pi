"""Shows holograms through the GPU: the interleaving is a shader, OpenGL ES 3, and the screen is the Looking Glass's,
through DRM/KMS, without a desktop.

The CPU's interleaving, interleave.py, turns a quilt into a hologram in a table lookup, about 80 ms on a Raspberry
Pi 5: enough for still quilts, not for a video of quilts. Here the GPU does it while it draws: each pixel of the
screen takes, for each of its sub-pixels, the colour of the view seen from that sub-pixel's direction, with the
formula of interleave.py, about 27 ms for a Portrait's screen on a Pi 5's GPU. A video's frames go to the GPU as
the decoder gives them, YUV 4:2:0, and the shader turns them into RGB: less to copy than RGB, and no conversion on
the processor.

Renderer draws into whatever framebuffer is bound, so that it works on the screen and, for the tests, off screen.
GlScreen draws on the Looking Glass: GBM gives the GPU buffers that the display controller scans out, EGL makes
an OpenGL ES context on them, and a page flip puts each new picture on the screen at its next refresh. OpenGL
needs every call of a context on one thread: GlScreen runs them all on a thread of its own.

On a Raspberry Pi 5 the GPU, v3d, and the display controller, vc4, are two cards; Mesa renders on the first for
the second when GBM is opened on the second, the one with the screen.
"""

import ctypes
import ctypes.util
import errno
import os
import queue
import select
import threading
from concurrent.futures import Future
from ctypes import POINTER, byref, c_char_p, c_float, c_int, c_uint, c_uint32, c_uint64, c_void_p

import numpy as np

from .drm import CARDS, PAGE_FLIP_EVENT, _check, _library, find_output

# How long a page flip may take: a refresh, 17 ms at 60 Hz, unless the screen is gone.
FLIP_TIMEOUT_S = 1

GBM_FORMAT_XRGB8888 = 0x34325258
GBM_BO_USE_SCANOUT, GBM_BO_USE_RENDERING = 1, 4

EGL_NONE, EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_PBUFFER_BIT = 0x3038, 0x3033, 4, 1
EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_NATIVE_VISUAL_ID = 0x3040, 0x40, 0x302E
EGL_RED_SIZE, EGL_GREEN_SIZE, EGL_BLUE_SIZE = 0x3024, 0x3023, 0x3022
EGL_OPENGL_ES_API, EGL_CONTEXT_CLIENT_VERSION, EGL_PLATFORM_SURFACELESS_MESA = 0x30A0, 0x3098, 0x31DD

GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, GL_COMPILE_STATUS, GL_LINK_STATUS = 0x8B31, 0x8B30, 0x8B81, 0x8B82
GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_NEAREST, GL_TEXTURE0 = 0x0DE1, 0x2801, 0x2800, 0x2600, \
    0x84C0
GL_R8, GL_RED, GL_RGB, GL_RGB8, GL_RGBA, GL_RGBA8 = 0x8229, 0x1903, 0x1907, 0x8051, 0x1908, 0x8058
GL_UNSIGNED_BYTE, GL_TRIANGLES, GL_COLOR_BUFFER_BIT, GL_MAX_TEXTURE_SIZE = 0x1401, 4, 0x4000, 0x0D33
GL_UNPACK_ALIGNMENT, GL_PACK_ALIGNMENT, GL_UNPACK_ROW_LENGTH = 0x0CF5, 0x0D05, 0x0CF2
GL_FRAMEBUFFER, GL_RENDERBUFFER, GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_COMPLETE = 0x8D40, 0x8D41, 0x8CE0, 0x8CD5

# What a frame's YUV becomes: RGB = rows . (YUV - offset), by FFmpeg's colour spaces and ranges.
YUV = {  # (BT.709, full range): (rows, offset)
    (False, False): ([[1.164, 0, 1.596], [1.164, -0.392, -0.813], [1.164, 2.017, 0]], [16 / 255, 0.5, 0.5]),
    (True, False): ([[1.164, 0, 1.793], [1.164, -0.213, -0.533], [1.164, 2.112, 0]], [16 / 255, 0.5, 0.5]),
    (False, True): ([[1, 0, 1.402], [1, -0.344, -0.714], [1, 1.772, 0]], [0, 0.5, 0.5]),
    (True, True): ([[1, 0, 1.5748], [1, -0.1873, -0.4681], [1, 1.8556, 0]], [0, 0.5, 0.5]),
}
BT709, FULL_RANGE = 1, 2  # FFmpeg's AVCOL_SPC_BT709 and AVCOL_RANGE_JPEG.

# What the shader draws from: its uniform `source`.
QUILT_RGB, QUILT_YUV, HOLOGRAM_RGB, HOLOGRAM_BGRX = 0, 1, 2, 3

VERTEX = b"""#version 300 es
// One triangle that covers the screen, with no vertex data.
void main() {
    vec2 corner = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
    gl_Position = vec4(corner * 2.0 - 1.0, 0.0, 1.0);
}
"""

FRAGMENT = b"""#version 300 es
precision highp float;
precision highp int;
uniform mediump sampler2D plane0, plane1, plane2;
uniform int source;
uniform vec2 screen;
uniform float pitch, tilt, center, subp;
uniform int inverted, reversed;
uniform ivec2 grid, quiltSize;
uniform vec3 toRgb[3];
uniform vec3 yuvOffset;
out vec4 colour;

// The pixel of the quilt that sub-pixel i of the screen shows, as interleave.py's table() works it out; uv is the
// screen's pixel from the bottom left, in fractions of the screen; the quilt's rows from the top.
ivec2 texel(int i, vec2 uv) {
    float position = fract((uv.x + float(i) * subp + uv.y * tilt) * pitch - center);
    if (inverted != 0) position = 1.0 - position;
    int views = grid.x * grid.y;
    int view = min(int(floor(position * float(views))), views - 1);
    if (reversed != 0) view = views - 1 - view;
    float x = (float(view % grid.x) + uv.x) / float(grid.x);
    float y = (float(view / grid.x) + uv.y) / float(grid.y);
    int column = clamp(int(x * float(quiltSize.x)), 0, quiltSize.x - 1);
    int row = quiltSize.y - 1 - clamp(int(y * float(quiltSize.y)), 0, quiltSize.y - 1);
    return ivec2(column, row);
}

float channel(int i, vec2 uv) {
    ivec2 at = texel(i, uv);
    if (source == 0) return texelFetch(plane0, at, 0)[i];
    // YUV 4:2:0: the colour of the 2 x 2 pixels around.
    vec3 yuv = vec3(texelFetch(plane0, at, 0).r, texelFetch(plane1, at / 2, 0).r, texelFetch(plane2, at / 2, 0).r);
    return clamp(dot(toRgb[i], yuv - yuvOffset), 0.0, 1.0);
}

void main() {
    if (source >= 2) {  // A hologram already: pixel for pixel.
        vec4 c = texelFetch(plane0, ivec2(int(gl_FragCoord.x), int(screen.y) - 1 - int(gl_FragCoord.y)), 0);
        colour = vec4(source == 3 ? c.bgr : c.rgb, 1.0);
        return;
    }
    vec2 uv = gl_FragCoord.xy / screen;
    colour = vec4(channel(0, uv), channel(1, uv), channel(2, uv), 1.0);
}
"""


class _Libraries:
    """libEGL, libGLESv2 and libgbm, through ctypes."""

    def __init__(self):
        def load(names, package):
            for name in names:
                try:
                    return ctypes.CDLL(name, use_errno=True)
                except OSError:
                    pass
            raise RuntimeError(f"cannot load {names[0]}: install {package}")

        self.egl = load(["libEGL.so.1", ctypes.util.find_library("EGL") or "libEGL.so"], "libegl1")
        self.gl = load(["libGLESv2.so.2", ctypes.util.find_library("GLESv2") or "libGLESv2.so"], "libgles2")
        self.gbm = None
        self._signatures()

    def load_gbm(self):
        if self.gbm is None:
            try:
                self.gbm = ctypes.CDLL("libgbm.so.1", use_errno=True)
            except OSError as error:
                raise RuntimeError(f"cannot load libgbm.so.1: install libgbm1: {error}") from error
            for name, restype, *argtypes in [
                ("gbm_create_device", c_void_p, c_int), ("gbm_device_destroy", None, c_void_p),
                ("gbm_surface_create", c_void_p, c_void_p, c_uint32, c_uint32, c_uint32, c_uint32),
                ("gbm_surface_destroy", None, c_void_p), ("gbm_surface_lock_front_buffer", c_void_p, c_void_p),
                ("gbm_surface_release_buffer", None, c_void_p, c_void_p),
                ("gbm_bo_get_handle", c_uint64, c_void_p), ("gbm_bo_get_stride", c_uint32, c_void_p),
            ]:
                _sign(self.gbm, name, restype, *argtypes)
        return self.gbm

    def _signatures(self):
        for name, restype, *argtypes in [
            ("eglGetDisplay", c_void_p, c_void_p), ("eglGetProcAddress", c_void_p, c_char_p),
            ("eglInitialize", c_uint, c_void_p, POINTER(c_int), POINTER(c_int)), ("eglTerminate", c_uint, c_void_p),
            ("eglBindAPI", c_uint, c_uint),
            ("eglChooseConfig", c_uint, c_void_p, POINTER(c_int), POINTER(c_void_p), c_int, POINTER(c_int)),
            ("eglGetConfigAttrib", c_uint, c_void_p, c_void_p, c_int, POINTER(c_int)),
            ("eglCreateContext", c_void_p, c_void_p, c_void_p, c_void_p, POINTER(c_int)),
            ("eglDestroyContext", c_uint, c_void_p, c_void_p),
            ("eglCreateWindowSurface", c_void_p, c_void_p, c_void_p, c_void_p, POINTER(c_int)),
            ("eglDestroySurface", c_uint, c_void_p, c_void_p),
            ("eglMakeCurrent", c_uint, c_void_p, c_void_p, c_void_p, c_void_p),
            ("eglSwapBuffers", c_uint, c_void_p, c_void_p), ("eglGetError", c_int),
        ]:
            _sign(self.egl, name, restype, *argtypes)
        for name, restype, *argtypes in [
            ("glCreateShader", c_uint, c_uint), ("glShaderSource", None, c_uint, c_int, POINTER(c_char_p), c_void_p),
            ("glCompileShader", None, c_uint), ("glGetShaderiv", None, c_uint, c_uint, POINTER(c_int)),
            ("glGetShaderInfoLog", None, c_uint, c_int, c_void_p, c_char_p), ("glCreateProgram", c_uint),
            ("glAttachShader", None, c_uint, c_uint), ("glLinkProgram", None, c_uint),
            ("glGetProgramiv", None, c_uint, c_uint, POINTER(c_int)),
            ("glGetProgramInfoLog", None, c_uint, c_int, c_void_p, c_char_p), ("glUseProgram", None, c_uint),
            ("glGetUniformLocation", c_int, c_uint, c_char_p), ("glUniform1f", None, c_int, c_float),
            ("glUniform2f", None, c_int, c_float, c_float), ("glUniform1i", None, c_int, c_int),
            ("glUniform2i", None, c_int, c_int, c_int), ("glUniform3f", None, c_int, c_float, c_float, c_float),
            ("glUniform3fv", None, c_int, c_int, POINTER(c_float)),
            ("glGenTextures", None, c_int, POINTER(c_uint)), ("glDeleteTextures", None, c_int, POINTER(c_uint)),
            ("glActiveTexture", None, c_uint), ("glBindTexture", None, c_uint, c_uint),
            ("glTexParameteri", None, c_uint, c_uint, c_int),
            ("glTexStorage2D", None, c_uint, c_int, c_uint, c_int, c_int),
            ("glTexSubImage2D", None, c_uint, c_int, c_int, c_int, c_int, c_int, c_uint, c_uint, c_void_p),
            ("glPixelStorei", None, c_uint, c_int), ("glViewport", None, c_int, c_int, c_int, c_int),
            ("glDrawArrays", None, c_uint, c_int, c_int), ("glFinish", None), ("glGetError", c_uint),
            ("glClearColor", None, c_float, c_float, c_float, c_float), ("glClear", None, c_uint),
            ("glGetIntegerv", None, c_uint, POINTER(c_int)),
            ("glReadPixels", None, c_int, c_int, c_int, c_int, c_uint, c_uint, c_void_p),
            ("glGenFramebuffers", None, c_int, POINTER(c_uint)), ("glBindFramebuffer", None, c_uint, c_uint),
            ("glGenRenderbuffers", None, c_int, POINTER(c_uint)), ("glBindRenderbuffer", None, c_uint, c_uint),
            ("glRenderbufferStorage", None, c_uint, c_uint, c_int, c_int),
            ("glFramebufferRenderbuffer", None, c_uint, c_uint, c_uint, c_uint),
            ("glCheckFramebufferStatus", c_uint, c_uint),
        ]:
            _sign(self.gl, name, restype, *argtypes)


def _sign(library, name, restype, *argtypes):
    function = getattr(library, name)
    function.restype, function.argtypes = restype, list(argtypes)


_libraries = None


def libraries():
    global _libraries
    if _libraries is None:
        _libraries = _Libraries()
    return _libraries


class Renderer:
    """Draws holograms into the bound framebuffer, of the screen's size, with the current OpenGL ES 3 context:
    from a quilt, RGB or a video's YUV 4:2:0 frame, interleaved by the shader, or from a hologram already, copied.

    Its textures come in two sets, used in turn: a frame goes into one while the GPU may still draw from the other,
    so that the copy does not wait for the drawing."""

    def __init__(self, width, height):
        self.gl = gl = libraries().gl
        self.width, self.height = width, height
        self.program = gl.glCreateProgram()
        gl.glAttachShader(self.program, self._shader(GL_VERTEX_SHADER, VERTEX))
        gl.glAttachShader(self.program, self._shader(GL_FRAGMENT_SHADER, FRAGMENT))
        gl.glLinkProgram(self.program)
        linked = c_int()
        gl.glGetProgramiv(self.program, GL_LINK_STATUS, byref(linked))
        if not linked.value:
            log = ctypes.create_string_buffer(4096)
            gl.glGetProgramInfoLog(self.program, 4096, None, log)
            raise RuntimeError(f"cannot link the shader: {log.value.decode()}")
        gl.glUseProgram(self.program)
        for unit in range(3):
            gl.glUniform1i(self._uniform(f"plane{unit}"), unit)
        gl.glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        gl.glPixelStorei(GL_PACK_ALIGNMENT, 1)
        gl.glViewport(0, 0, width, height)
        largest = c_int()
        gl.glGetIntegerv(GL_MAX_TEXTURE_SIZE, byref(largest))
        self.largest = largest.value  # The widest texture, e.g. 4096 on a Pi 5: the largest quilt.
        self.sets = [[None] * 3, [None] * 3]  # Per set and plane: (texture, format, width, height).
        self.turn = 0

    def _shader(self, kind, source):
        gl = self.gl
        handle = gl.glCreateShader(kind)
        gl.glShaderSource(handle, 1, (c_char_p * 1)(source), None)
        gl.glCompileShader(handle)
        compiled = c_int()
        gl.glGetShaderiv(handle, GL_COMPILE_STATUS, byref(compiled))
        if not compiled.value:
            log = ctypes.create_string_buffer(4096)
            gl.glGetShaderInfoLog(handle, 4096, None, log)
            raise RuntimeError(f"cannot compile the shader: {log.value.decode()}")
        return handle

    def _uniform(self, name):
        return self.gl.glGetUniformLocation(self.program, name.encode())

    def _upload(self, planes):
        """Copies the planes, (internal format, format, width, height, row length in pixels, pointer), into the next
        set of textures, and binds them."""
        gl = self.gl
        self.turn ^= 1
        textures = self.sets[self.turn]
        for unit, (internal, format, width, height, row, pointer) in enumerate(planes):
            if max(width, height) > self.largest:
                raise ValueError(f"a picture of {width} x {height} is larger than the GPU takes, "
                                 f"{self.largest} x {self.largest}")
            gl.glActiveTexture(GL_TEXTURE0 + unit)
            texture = textures[unit]
            if texture is None or texture[1:] != (internal, width, height):
                if texture is not None:
                    gl.glDeleteTextures(1, byref(c_uint(texture[0])))
                handle = c_uint()
                gl.glGenTextures(1, byref(handle))
                gl.glBindTexture(GL_TEXTURE_2D, handle)
                gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                gl.glTexStorage2D(GL_TEXTURE_2D, 1, internal, width, height)
                textures[unit] = texture = (handle.value, internal, width, height)
            gl.glBindTexture(GL_TEXTURE_2D, texture[0])
            gl.glPixelStorei(GL_UNPACK_ROW_LENGTH, row)
            gl.glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, format, GL_UNSIGNED_BYTE, pointer)
        gl.glPixelStorei(GL_UNPACK_ROW_LENGTH, 0)

    def _draw(self, source, layout=None, calibration=None, reverse=False, quilt_size=(1, 1)):
        gl, uniform = self.gl, self._uniform
        gl.glUseProgram(self.program)
        gl.glUniform1i(uniform("source"), source)
        gl.glUniform2f(uniform("screen"), self.width, self.height)
        if calibration is not None:
            gl.glUniform1f(uniform("pitch"), calibration.pitch)
            gl.glUniform1f(uniform("tilt"), calibration.tilt)
            gl.glUniform1f(uniform("center"), calibration.center)
            gl.glUniform1f(uniform("subp"), calibration.subp)
            gl.glUniform1i(uniform("inverted"), int(calibration.inverted))
            gl.glUniform1i(uniform("reversed"), int(reverse))
            gl.glUniform2i(uniform("grid"), layout.columns, layout.rows)
            gl.glUniform2i(uniform("quiltSize"), *quilt_size)
        gl.glDrawArrays(GL_TRIANGLES, 0, 3)

    def quilt(self, picture, layout, calibration, reverse=False):
        """Draws the hologram of a quilt, an RGB array, rows from the top."""
        picture = np.ascontiguousarray(picture)
        height, width = picture.shape[:2]
        self._upload([(GL_RGB8, GL_RGB, width, height, width, picture.ctypes.data)])
        self._draw(QUILT_RGB, layout, calibration, reverse, (width, height))

    def quilt_frame(self, frame, layout, calibration, reverse=False):
        """Draws the hologram of a quilt video's frame, a PyAV VideoFrame in YUV 4:2:0, yuv420p, as decoded."""
        if frame.format.name != "yuv420p":
            frame = frame.reformat(format="yuv420p")
        width, height = frame.width, frame.height
        sizes = [(width, height), ((width + 1) // 2, (height + 1) // 2), ((width + 1) // 2, (height + 1) // 2)]
        self._upload([(GL_R8, GL_RED, w, h, plane.line_size, plane.buffer_ptr)
                      for plane, (w, h) in zip(frame.planes, sizes)])
        rows, offset = YUV[(getattr(frame, "colorspace", 0) == BT709, getattr(frame, "color_range", 0) == FULL_RANGE)]
        self.gl.glUniform3fv(self._uniform("toRgb"), 3, (c_float * 9)(*np.ravel(rows)))
        self.gl.glUniform3f(self._uniform("yuvOffset"), *offset)
        self._draw(QUILT_YUV, layout, calibration, reverse, (width, height))

    def hologram(self, picture):
        """Draws a hologram already interleaved, of the screen's size: RGB, or XRGB8888, blue, green, red and a
        padding byte, e.g. a hologram video's frame decoded as BGRA."""
        picture = np.ascontiguousarray(picture)
        height, width, channels = picture.shape
        if channels == 4:
            self._upload([(GL_RGBA8, GL_RGBA, width, height, width, picture.ctypes.data)])
            self._draw(HOLOGRAM_BGRX)
        else:
            self._upload([(GL_RGB8, GL_RGB, width, height, width, picture.ctypes.data)])
            self._draw(HOLOGRAM_RGB)

    def black(self):
        self.gl.glClearColor(0, 0, 0, 1)
        self.gl.glClear(GL_COLOR_BUFFER_BIT)

    def read(self):
        """What was drawn, an RGB array of the screen's size, rows from the top: for the tests."""
        pixels = np.empty((self.height, self.width, 4), np.uint8)
        self.gl.glReadPixels(0, 0, self.width, self.height, GL_RGBA, GL_UNSIGNED_BYTE, pixels.ctypes.data)
        return np.ascontiguousarray(pixels[::-1, :, :3])


def _choose_config(egl, display, surface_type, visual=None):
    attributes = (c_int * 11)(EGL_SURFACE_TYPE, surface_type, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
                              EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE)
    configs, count = (c_void_p * 64)(), c_int()
    egl.eglChooseConfig(display, attributes, configs, 64, byref(count))
    for config in configs[:count.value]:
        native = c_int()
        egl.eglGetConfigAttrib(display, config, EGL_NATIVE_VISUAL_ID, byref(native))
        if visual is None or native.value == visual:
            return config
    raise RuntimeError("no EGL configuration for OpenGL ES 3" + (" in XRGB8888" if visual else ""))


def _context(egl, display, config):
    context = egl.eglCreateContext(display, config, None, (c_int * 3)(EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE))
    if not context:
        raise RuntimeError(f"cannot create an OpenGL ES 3 context: EGL error {egl.eglGetError():#x}")
    return context


class Offscreen:
    """A Renderer drawing into memory, with no screen, e.g. for the tests: renderer, then close()."""

    def __init__(self, width, height):
        libs = libraries()
        egl, gl = libs.egl, libs.gl
        self.egl = egl
        address = egl.eglGetProcAddress(b"eglGetPlatformDisplayEXT")
        display = None
        if address:
            platform_display = ctypes.CFUNCTYPE(c_void_p, c_uint, c_void_p, POINTER(c_int))(address)
            display = platform_display(EGL_PLATFORM_SURFACELESS_MESA, None, None)
        self.display = display or egl.eglGetDisplay(None)
        if not self.display or not egl.eglInitialize(self.display, None, None):
            raise RuntimeError(f"no EGL display: EGL error {egl.eglGetError():#x}")
        egl.eglBindAPI(EGL_OPENGL_ES_API)
        self.context = _context(egl, self.display, _choose_config(egl, self.display, EGL_PBUFFER_BIT))
        if not egl.eglMakeCurrent(self.display, None, None, self.context):
            raise RuntimeError(f"cannot use an OpenGL ES context without a surface: EGL error {egl.eglGetError():#x}")
        framebuffer, renderbuffer = c_uint(), c_uint()
        gl.glGenFramebuffers(1, byref(framebuffer))
        gl.glBindFramebuffer(GL_FRAMEBUFFER, framebuffer)
        gl.glGenRenderbuffers(1, byref(renderbuffer))
        gl.glBindRenderbuffer(GL_RENDERBUFFER, renderbuffer)
        gl.glRenderbufferStorage(GL_RENDERBUFFER, GL_RGBA8, width, height)
        gl.glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, renderbuffer)
        if gl.glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("cannot draw into memory: the framebuffer is not complete")
        self.renderer = Renderer(width, height)

    def close(self):
        self.egl.eglMakeCurrent(self.display, None, None, None)
        self.egl.eglDestroyContext(self.display, self.context)
        self.egl.eglTerminate(self.display)


class GlScreen:
    """The Looking Glass, through the GPU and DRM/KMS: show(), show_quilt() and show_quilt_frame() draw on the
    connected screen of the hologram's size, which stays until the next one or close(). Thread-safe: every call runs
    on the screen's own thread, and returns once the picture is on the screen or will be at its next refresh."""

    name = "gl"

    def __init__(self, folder=CARDS):
        self.folder = folder
        self.jobs = queue.Queue()
        self.fd = self.output = self.saved = None
        self.device = self.surface = self.display = self.context = self.window = None
        self.renderer = None
        self.framebuffers = {}  # Per GBM buffer, its DRM framebuffer.
        self.on_screen = self.pending = None  # The GBM buffers on the screen, and the one a page flip will put there.
        threading.Thread(target=self._work, name="gl", daemon=True).start()

    # The screen's thread.

    def _work(self):
        while True:
            job, future = self.jobs.get()
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(job())
                except BaseException as error:  # noqa: BLE001 - handed to the caller.
                    future.set_exception(error)

    def _call(self, job):
        future = Future()
        self.jobs.put((job, future))
        return future.result()

    # The screen's methods.

    def show(self, hologram):
        """Shows a hologram already interleaved, RGB or XRGB8888, on the screen of its size. Returns where."""
        height, width = hologram.shape[:2]
        return self._call(lambda: self._present(width, height, lambda renderer: renderer.hologram(hologram)))

    def show_quilt(self, picture, layout, calibration, reverse=False):
        """Shows the hologram of a quilt, an RGB array, interleaved by the GPU. Returns where."""
        return self._call(lambda: self._present(calibration.width, calibration.height,
                                                lambda renderer: renderer.quilt(picture, layout, calibration, reverse)))

    def show_quilt_frame(self, frame, layout, calibration, reverse=False):
        """Shows the hologram of a quilt video's frame, a PyAV VideoFrame, interleaved by the GPU. Returns where."""
        return self._call(lambda: self._present(
            calibration.width, calibration.height,
            lambda renderer: renderer.quilt_frame(frame, layout, calibration, reverse)))

    def clear(self):
        """Shows black, if anything is shown."""
        def black():
            if self.output is not None:
                self._present(*self.output.size, lambda renderer: renderer.black())
        self._call(black)

    def close(self):
        """Gives the screen back, e.g. to the console."""
        self._call(self._release)

    def run(self, stop):
        """Waits until `stop`, a threading.Event, is set: the screen's thread needs no loop of the main one."""
        while not stop.wait(0.5):
            pass

    # On the screen's thread only.

    def _present(self, width, height, draw):
        if self.output is not None and self.output.size != (width, height):
            self._release()
        for attempt in range(2):
            try:
                if self.fd is None:
                    self._open(width, height)
                draw(self.renderer)
                self._flip()
                return f"{self.output.name} of {self.output.card}, {width} x {height}, through the GPU"
            except OSError as error:
                self._release()
                if error.errno in (errno.EACCES, errno.EPERM):
                    raise RuntimeError(f"{error}: another program drives the screens, e.g. a desktop, or this "
                                       "user may not open them, e.g. not in the groups video and render") from error
                if attempt:  # The screen may have been unplugged and plugged in again: look for it once more.
                    raise RuntimeError(str(error)) from error
            except RuntimeError:
                self._release()
                raise
        raise AssertionError("unreachable")

    def _open(self, width, height):
        libs = libraries()
        egl, gbm, drm = libs.egl, libs.load_gbm(), _library()
        drm.drmModePageFlip.argtypes = [c_int, c_uint32, c_uint32, c_uint32, c_void_p]
        self.fd, self.output = find_output(width, height, self.folder)
        self.saved = drm.drmModeGetCrtc(self.fd, self.output.crtc)
        self.device = gbm.gbm_create_device(self.fd)
        if not self.device:
            raise RuntimeError(f"cannot use the GPU with {self.output.card}: gbm_create_device failed")
        self.surface = gbm.gbm_surface_create(self.device, width, height, GBM_FORMAT_XRGB8888,
                                              GBM_BO_USE_SCANOUT | GBM_BO_USE_RENDERING)
        self.display = egl.eglGetDisplay(self.device)
        if not self.surface or not self.display or not egl.eglInitialize(self.display, None, None):
            raise RuntimeError(f"cannot use the GPU with {self.output.card}: EGL error {egl.eglGetError():#x}")
        egl.eglBindAPI(EGL_OPENGL_ES_API)
        config = _choose_config(egl, self.display, EGL_WINDOW_BIT, GBM_FORMAT_XRGB8888)
        self.context = _context(egl, self.display, config)
        self.window = egl.eglCreateWindowSurface(self.display, config, self.surface, None)
        if not self.window or not egl.eglMakeCurrent(self.display, self.window, self.window, self.context):
            raise RuntimeError(f"cannot draw on {self.output.card}: EGL error {egl.eglGetError():#x}")
        self.renderer = Renderer(width, height)

    def _flip(self):
        """Puts what was drawn on the screen: at once the first time, then with a page flip at the next refresh,
        without waiting for it. The next flip waits for this one, then gives its old buffer back to GBM."""
        libs, drm = libraries(), _library()
        libs.egl.eglSwapBuffers(self.display, self.window)
        buffer = libs.gbm.gbm_surface_lock_front_buffer(self.surface)
        if not buffer:
            raise RuntimeError("the GPU has no buffer to show")
        if buffer not in self.framebuffers:
            framebuffer = c_uint32()
            width, height = self.output.size
            _check(drm.drmModeAddFB(self.fd, width, height, 24, 32, libs.gbm.gbm_bo_get_stride(buffer),
                                    libs.gbm.gbm_bo_get_handle(buffer) & 0xFFFFFFFF, byref(framebuffer)),
                   "cannot show the GPU's picture")
            self.framebuffers[buffer] = framebuffer.value
        if self.on_screen is None:
            connector = c_uint32(self.output.connector)
            _check(drm.drmModeSetCrtc(self.fd, self.output.crtc, self.framebuffers[buffer], 0, 0, byref(connector), 1,
                                      byref(self.output.mode)), "cannot show on the screen")
            self.on_screen = buffer
            return
        self._wait_for_flip()
        _check(drm.drmModePageFlip(self.fd, self.output.crtc, self.framebuffers[buffer], PAGE_FLIP_EVENT, None),
               "cannot show on the screen")
        self.pending = buffer

    def _wait_for_flip(self):
        if self.pending is None:
            return
        pending, self.pending = self.pending, None
        ready, _, _ = select.select([self.fd], [], [], FLIP_TIMEOUT_S)
        if not ready:
            raise OSError(errno.ETIMEDOUT, "the screen did not take the new picture")
        os.read(self.fd, 4096)  # The flip's event.
        libraries().gbm.gbm_surface_release_buffer(self.surface, self.on_screen)
        self.on_screen = pending

    def _release(self):
        libs = libraries()
        drm = _library()
        try:
            self._wait_for_flip()
        except OSError:
            pass  # The screen is gone: closing the card ends the flip.
        if self.saved:  # What it showed before first, e.g. the console: removing a framebuffer on screen blanks it.
            crtc = self.saved.contents
            if crtc.buffer_id and crtc.mode_valid:
                connector = c_uint32(self.output.connector)
                drm.drmModeSetCrtc(self.fd, crtc.crtc_id, crtc.buffer_id, crtc.x, crtc.y, byref(connector), 1,
                                   byref(crtc.mode))
            drm.drmModeFreeCrtc(self.saved)
        for framebuffer in self.framebuffers.values():
            drm.drmModeRmFB(self.fd, framebuffer)
        if self.display:
            libs.egl.eglMakeCurrent(self.display, None, None, None)
            if self.window:
                libs.egl.eglDestroySurface(self.display, self.window)
            if self.context:
                libs.egl.eglDestroyContext(self.display, self.context)
            libs.egl.eglTerminate(self.display)
        if self.surface:
            libs.gbm.gbm_surface_destroy(self.surface)
        if self.device:
            libs.gbm.gbm_device_destroy(self.device)
        if self.fd is not None:
            os.close(self.fd)
        self.fd = self.output = self.saved = None
        self.device = self.surface = self.display = self.context = self.window = None
        self.renderer = None
        self.framebuffers, self.on_screen, self.pending = {}, None, None

