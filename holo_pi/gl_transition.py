"""Transitions from the hologram on the screen to the next one, blended by the GPU.

Each pixel of the screen is under one lens, and each of its sub-pixels belongs to one view: blending two holograms
sub-pixel by sub-pixel blends each view with the same view of the other, so that both keep their depth. A transition
keeps the two holograms, already interleaved, in textures of the screen's size, and draws a blend of them at each
refresh, which is two reads a pixel, where interleaving again would be far slower.

A shape, e.g. the edge of a wipe, is drawn on the screen itself, the same for every view, so that it lies at the
screen's depth. What moves the pictures, e.g. a slide, cannot be drawn so: a hologram shifted is under other lenses.
"""

from ctypes import byref, c_int, c_uint

from .gl import (GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER, GL_FRAMEBUFFER_BINDING, GL_FRAMEBUFFER_COMPLETE, GL_NEAREST,
                 GL_RGBA8, GL_TEXTURE0, GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER, GL_TRIANGLES, VERTEX,
                 link_program)
from .transition import CUT, KINDS

# The texture units of the two holograms: none of the Renderer's and of GradedQuilt's, which stay bound.
BEFORE, AFTER = 8, 9

FRAGMENT = b"""#version 300 es
precision highp float;
precision highp int;
uniform mediump sampler2D before, after;
uniform vec2 screen;
uniform int kind;
uniform float progress;
out vec4 colour;

const float EDGE = 0.08;  // How wide a soft edge is, of the way it goes.
const float BLOCK = 32.0;  // A dissolve's squares, in pixels: wider than a lens, so that every view sees them whole.

// How much of the next hologram is seen where the edge comes at `when`, 0 to 1: none at 0, all at 1.
float reached(float when, float edge) {
    return clamp((progress * (1.0 + edge) - when) / edge, 0.0, 1.0);
}

float noise(vec2 p) {
    uvec2 q = uvec2(p) * uvec2(1597334673u, 3812015801u);
    uint n = (q.x ^ q.y) * 1597334673u;
    n ^= n >> 15;
    n *= 2246822519u;
    n ^= n >> 13;
    return float(n >> 8) / 16777216.0;
}

void main() {
    ivec2 at = ivec2(gl_FragCoord.xy);
    vec3 a = texelFetch(before, at, 0).rgb, b = texelFetch(after, at, 0).rgb;
    vec2 uv = gl_FragCoord.xy / screen;
    float share = progress;  // A cross fade.
    if (kind == 2) {  // Through black.
        colour = vec4(progress < 0.5 ? a * (1.0 - 2.0 * progress) : b * (2.0 * progress - 1.0), 1.0);
        return;
    }
    if (kind == 3) share = reached(uv.x, EDGE);  // A wipe, from the left.
    if (kind == 4) share = reached(length(gl_FragCoord.xy - screen / 2.0) / length(screen / 2.0), EDGE);  // An iris.
    if (kind == 5) share = reached(noise(floor(gl_FragCoord.xy / BLOCK)), 2.0 * EDGE);  // A dissolve.
    colour = vec4(mix(a, b, share), 1.0);
}
"""


class Transition:
    """One transition after another, of a Renderer, into the framebuffer bound. begin() keeps the hologram before;
    target() is where to draw the one after, as often as it changes; blend() draws them both."""

    def __init__(self, renderer):
        self.renderer, self.gl = renderer, renderer.gl
        self.program = link_program(self.gl, VERTEX, FRAGMENT)
        framebuffer = c_uint()
        self.gl.glGenFramebuffers(1, byref(framebuffer))
        self.framebuffer = framebuffer.value
        self.before, self.after, self.spare = None, None, None  # Textures.
        self.kind, self.seconds = CUT, 0
        self.started = None  # When the first blend was drawn.
        self.armed = False  # From begin() on, until it is over.

    def begin(self, kind, seconds, draw):
        """Starts one: `draw` draws what is on the screen, which may be another transition. Its time counts from the
        first blend."""
        self.spare = self.spare or self._texture()  # Not `before`, which `draw` may read.
        with self._into(self.spare):
            draw()
        self.before, self.spare = self.spare, self.before
        self.after = self.after or self._texture()
        self.kind, self.seconds, self.started, self.armed = kind, seconds, None, True

    def cancel(self):
        self.armed, self.started = False, None

    @property
    def moving(self):
        """Whether the screen is to change by itself: blend() again."""
        return self.armed and self.started is not None

    def target(self):
        """A context in which what is drawn is the hologram after."""
        return self._into(self.after)

    def blend(self, now):
        """Draws the two as they are at `now`, in seconds; the last time, the one after alone."""
        if self.started is None:
            self.started = now
        progress = min(1.0, (now - self.started) / self.seconds)
        self._draw(progress)
        if progress >= 1:
            self.cancel()

    def _draw(self, progress):
        gl = self.gl
        gl.glUseProgram(self.program)

        def uniform(name):
            return gl.glGetUniformLocation(self.program, name)
        for unit, name, texture in [(BEFORE, b"before", self.before), (AFTER, b"after", self.after)]:
            gl.glActiveTexture(GL_TEXTURE0 + unit)
            gl.glBindTexture(GL_TEXTURE_2D, texture)
            gl.glUniform1i(uniform(name), unit)
        gl.glUniform2f(uniform(b"screen"), self.renderer.width, self.renderer.height)
        gl.glUniform1i(uniform(b"kind"), KINDS.index(self.kind))
        gl.glUniform1f(uniform(b"progress"), progress * progress * (3 - 2 * progress))  # Starts and ends gently.
        gl.glDrawArrays(GL_TRIANGLES, 0, 3)
        for unit in (BEFORE, AFTER):  # A texture drawn into must not be read too.
            gl.glActiveTexture(GL_TEXTURE0 + unit)
            gl.glBindTexture(GL_TEXTURE_2D, 0)
        gl.glUseProgram(self.renderer.program)

    def _texture(self):
        gl, handle = self.gl, c_uint()
        gl.glGenTextures(1, byref(handle))
        gl.glActiveTexture(GL_TEXTURE0 + BEFORE)
        gl.glBindTexture(GL_TEXTURE_2D, handle)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        gl.glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, self.renderer.width, self.renderer.height)
        gl.glBindTexture(GL_TEXTURE_2D, 0)
        return handle.value

    def _into(self, texture):
        return _Into(self.gl, self.framebuffer, texture)


class _Into:
    """Draws into a texture, and then into the framebuffer bound before again."""

    def __init__(self, gl, framebuffer, texture):
        self.gl, self.framebuffer, self.texture = gl, framebuffer, texture

    def __enter__(self):
        gl, bound = self.gl, c_int()
        gl.glGetIntegerv(GL_FRAMEBUFFER_BINDING, byref(bound))
        self.bound = bound.value
        gl.glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        gl.glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.texture, 0)
        if gl.glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
            gl.glBindFramebuffer(GL_FRAMEBUFFER, self.bound)
            raise RuntimeError("the GPU cannot draw a transition: its framebuffer is not complete")

    def __exit__(self, *_):
        self.gl.glBindFramebuffer(GL_FRAMEBUFFER, self.bound)
