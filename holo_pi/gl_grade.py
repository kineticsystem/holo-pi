"""A quilt shown with a grade, on the GPU, fast enough to follow a slider on a Raspberry Pi. Experimental.

A slider moves only a few numbers, so what does not depend on them is done once per picture, and kept:

- the interleaving: for each sub-pixel of the screen, the whole colour of the quilt's pixel it shows, in three
  textures of the screen's size, one per sub-pixel;
- what the tools that look around a pixel need of it, in three more: its area's light, its texture, its shapes and
  its edges, each view filtered alone, as a picture of its own. Only when one of these tools is first used.

Then each change of the grade takes two steps: the tools that look at a pixel alone, e.g. the contrast or the colour
mixer, are worked out for 33 x 33 x 33 colours, into a table, a 3D texture; and each sub-pixel of the screen takes its
colour from the textures, its gain from the tools that look around it, and its result from the table.

The tools are StepIt Grader's, see grade.py. They differ in this: the gain of the tools that look around a pixel goes
before the others, not among them, as the table can only come last; its size is corrected for the contrast, which
comes after it. The luminances have a floor and the gains of the edges a limit, as a quilt, unlike a photograph, often
has a pure black sky: without them, its objects get a bright rim.
"""

import ctypes
from ctypes import byref, c_float, c_int, c_uint

import numpy as np

from .gl import (GL_CLAMP_TO_EDGE, GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER, GL_FRAMEBUFFER_BINDING,
                 GL_FRAMEBUFFER_COMPLETE, GL_LINEAR, GL_NEAREST, GL_R16F, GL_RGB, GL_RGB8, GL_RGB10_A2, GL_RGBA,
                 GL_RGBA8, GL_RGBA16F, GL_TEXTURE0, GL_TEXTURE_2D, GL_TEXTURE_3D, GL_TEXTURE_MAG_FILTER,
                 GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_R, GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TRIANGLES,
                 GL_UNPACK_ROW_LENGTH, GL_UNSIGNED_BYTE, TEXEL, VERTEX, link_program)
from .grade import (BAND_HUES, LMS_FROM_REC2020, OKLAB_FROM_LMS, REC2020_TO_SRGB, SPATIAL, SRGB_TO_REC2020, mixer,
                    tone_curve, white_balance)

# The table's colours per axis: 24 steps for the tones of the quilt, 0 to 1, and 8 above, for what the gains lift over
# white, which the table can bring back.
TABLE = 33
# The filters' sizes, in pixels of a view, StepIt Grader's: the fine and the coarse blur, whose difference is the
# texture, and the radii of the areas and of the shapes, as a share of the view's diagonal.
FINE_SIGMA, COARSE_SIGMA = 1.0, 4.0
AREA_OF_DIAGONAL, SHAPES_OF_DIAGONAL = 0.02, 0.01
# The areas and the shapes are found on the views this many times smaller.
SHRINK = 4
# The most taps on each side of a blur, the uniform array's size.
MAX_TAPS = 12

# The tone of a linear value, a pure power, so that a gain in stops is a product. What StepIt Grader calls luminance
# is in stops from middle grey.
HEAD = b"""#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;
precision highp sampler3D;
const float GAMMA = 2.4;
const float MIDDLE_GREY = 0.18;
const float FLOOR = 0.004;  // The least luminance seen by the tools that look around a pixel.

vec3 decode(vec3 c) {  // sRGB to linear.
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}
float decode(float c) {
    return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4);
}
vec3 encode(vec3 c) {  // Linear to sRGB.
    return mix(c * 12.92, 1.055 * pow(max(c, 0.0), vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}
"""

# The quilt's pixel that is drawn: of sub-pixel `sub` of the screen, for the hologram, or the same, for the whole quilt.
OF_THE_SCREEN = TEXEL + b"""
uniform int sub;
ivec2 place() { return texel(sub, gl_FragCoord.xy / screen); }
"""
OF_THE_QUILT = b"""
uniform ivec2 grid, quiltSize;
ivec2 place() { return ivec2(gl_FragCoord.xy); }
"""

# The colour of the quilt's pixel at place(), as tones of GAMMA. Goes after HEAD and one of the two above.
COLOURS = b"""
uniform sampler2D quilt;
out vec4 colour;
void main() {
    vec3 c = texelFetch(quilt, place(), 0).rgb;
    colour = vec4(pow(decode(c), vec3(1.0 / GAMMA)), 1.0);
}
"""

# The quilt's luminance, in stops from middle grey.
LUMINANCE = HEAD + b"""
uniform sampler2D quilt;
out vec4 colour;
void main() {
    vec3 c = decode(texelFetch(quilt, ivec2(gl_FragCoord.xy), 0).rgb);
    float luminance = dot(c, vec3(0.2126, 0.7152, 0.0722));
    colour = vec4(log2((luminance + FLOOR) / MIDDLE_GREY));
}
"""

# The view a pixel of the quilt is in, and its first and last pixels: the filters stay in it.
VIEW = b"""
uniform ivec2 grid, quiltSize;
ivec2 viewOf(ivec2 at) { return at * grid / quiltSize; }
ivec2 firstOf(ivec2 view) { return (view * quiltSize + grid - 1) / grid; }
"""

# A Gaussian blur along `along`, within each view.
BLUR = HEAD + VIEW + b"""
uniform sampler2D image;
uniform ivec2 along;
uniform int taps;
uniform float weights[13];
out vec4 colour;
void main() {
    ivec2 at = ivec2(gl_FragCoord.xy);
    ivec2 view = viewOf(at);
    ivec2 first = firstOf(view), last = firstOf(view + 1) - 1;
    float sum = texelFetch(image, at, 0).r * weights[0];
    for (int i = 1; i <= taps; i++) {
        sum += (texelFetch(image, clamp(at + i * along, first, last), 0).r
                + texelFetch(image, clamp(at - i * along, first, last), 0).r) * weights[i];
    }
    colour = vec4(sum);
}
"""

# Each view SHRINK times smaller, in cells of `cell` pixels: the mean luminance, around -1.5 stops so that half floats
# keep its square's precision, and the mean of its square, twice.
SMALL = HEAD + VIEW + b"""
uniform sampler2D image;
uniform ivec2 cell;
uniform int shrink;
out vec4 colour;
void main() {
    ivec2 at = ivec2(gl_FragCoord.xy);
    ivec2 view = at / cell;
    ivec2 first = firstOf(view), last = firstOf(view + 1) - 1;
    ivec2 corner = first + (at - view * cell) * shrink;
    vec2 sum = vec2(0.0);
    for (int y = 0; y < shrink; y++) {
        for (int x = 0; x < shrink; x++) {
            float v = texelFetch(image, min(corner + ivec2(x, y), last), 0).r + 1.5;
            sum += vec2(v, v * v);
        }
    }
    colour = (sum / float(shrink * shrink)).xyxy;
}
"""

# The means of a box along `along`, within each cell, of one radius for xy and another for zw.
BOX = HEAD + b"""
uniform sampler2D image;
uniform ivec2 cell, along, radii;
out vec4 colour;
void main() {
    ivec2 at = ivec2(gl_FragCoord.xy);
    ivec2 first = at / cell * cell, last = first + cell - 1;
    vec4 sum = vec4(0.0), count = vec4(0.0);
    int most = max(radii.x, radii.y);
    for (int i = -most; i <= most; i++) {
        ivec2 p = at + i * along;
        if (p != clamp(p, first, last)) continue;
        vec4 in_ = step(float(abs(i)), vec2(radii)).xxyy;
        sum += texelFetch(image, p, 0) * in_;
        count += in_;
    }
    colour = sum / count;
}
"""

# The guided filter's coefficients, of the areas, xy, and of the shapes, zw.
GUIDED = HEAD + b"""
uniform sampler2D image;
uniform vec2 epsilons;
out vec4 colour;
void main() {
    vec4 means = texelFetch(image, ivec2(gl_FragCoord.xy), 0);
    vec2 variance = max(means.yw - means.xz * means.xz, 0.0);
    vec2 a = variance / (variance + epsilons);
    vec2 b = means.xz * (1.0 - a);
    colour = vec4(a.x, b.x, a.y, b.y);
}
"""

# What the tools that look around a pixel need of the quilt's pixel at place(): its area's light, and its texture's,
# its shapes' and its edges' gains, in stops. Goes after HEAD too.
AROUND = b"""
uniform sampler2D luminance, fine, coarse, guided;
uniform ivec2 cell;
uniform int shrink;
out vec4 colour;
const float DETAIL_NOISE = 0.05, EDGE_NOISE = 0.02;  // What is smaller, in stops, is noise.
const float LIMIT = 0.5;  // The most, in stops, before the tool's strength.

float cored(float stops, float noise) {
    stops *= stops * stops / (stops * stops + noise * noise);
    return stops / sqrt(1.0 + stops * stops / (LIMIT * LIMIT));
}
void main() {
    ivec2 at = place();
    float l = texelFetch(luminance, at, 0).r;
    float f = texelFetch(fine, at, 0).r;
    ivec2 view = at * grid / quiltSize;
    ivec2 first = (view * quiltSize + grid - 1) / grid;
    vec2 inCell = clamp((vec2(at - first) + 0.5) / float(shrink), vec2(0.5), vec2(cell) - 0.5);
    vec4 c = texture(guided, (vec2(view * cell) + inCell) / vec2(textureSize(guided, 0)));
    float area = c.x * (l + 1.5) + c.y - 1.5;
    float base = c.z * (l + 1.5) + c.w - 1.5;
    colour = vec4(area, cored(f - texelFetch(coarse, at, 0).r, DETAIL_NOISE), l - base, cored(l - f, EDGE_NOISE));
}
"""

# One layer of the table: the tools that look at a pixel alone, in StepIt Grader's order.
TABLE_LAYER = HEAD + b"""
uniform float layer, size;
uniform mat3 toWorking, toScreen, toLms, fromLms, toLab, fromLab;
uniform float contrast, blacks, vibrance, saturation;
uniform float curveX[6], curveY[6], curveTangent[6];
uniform int curved, mixed;
uniform float hues[8], turns[8], chromas[8], stops[8];
out vec4 colour;
const vec3 LUMA = vec3(0.2627, 0.6780, 0.0593);

float curve(float tone) {
    int i = 0;
    while (i < 4 && tone > curveX[i + 1]) i++;
    float h = curveX[i + 1] - curveX[i];
    float t = (tone - curveX[i]) / h, t2 = t * t, t3 = t2 * t;
    return (2.0 * t3 - 3.0 * t2 + 1.0) * curveY[i] + (t3 - 2.0 * t2 + t) * h * curveTangent[i]
        + (3.0 * t2 - 2.0 * t3) * curveY[i + 1] + (t3 - t2) * h * curveTangent[i + 1];
}

vec3 mixColours(vec3 lab, out float gain) {
    float chroma = length(lab.yz);
    float colourful = smoothstep(0.02, 0.04, chroma);
    gain = 1.0;
    if (colourful <= 0.0) return lab;
    float hue = degrees(atan(lab.z, lab.y));
    if (hue < hues[0]) hue += 360.0;
    int band = 7;
    while (band > 0 && hue < hues[band]) band--;
    int next = (band + 1) % 8;
    float to = hues[next] + (next == 0 ? 360.0 : 0.0);
    float weight = smoothstep(hues[band], to, hue);
    float angle = radians(hue + colourful * mix(turns[band], turns[next], weight));
    chroma *= max(0.0, 1.0 + colourful * mix(chromas[band], chromas[next], weight));
    gain = exp2(colourful * mix(stops[band], stops[next], weight));
    return vec3(lab.x, chroma * cos(angle), chroma * sin(angle));
}

void main() {
    vec3 tone = vec3(floor(gl_FragCoord.xy), layer) / (size - 1.0) / 0.75;
    tone = mix(tone, 1.0 + (tone - 1.0) * 3.0, step(1.0, tone));
    vec3 c = toWorking * pow(tone, vec3(GAMMA));

    float s = log2(max(dot(c, LUMA), 1e-6) / MIDDLE_GREY);
    c *= exp2(contrast * 3.0 * tanh(s / 3.0));

    float light = max(0.0, dot(c, LUMA));
    if (blacks > 0.0) c += blacks * (1.0 - smoothstep(0.0, MIDDLE_GREY, light));
    else if (blacks < 0.0) c *= light / (light - blacks);

    if (curved != 0) {
        // Black has no colour to keep: its gain is that of the first tone above it.
        light = max(dot(c, LUMA), 2e-5);
        if (light < 1.0) c *= decode(curve(encode(vec3(light)).x)) / light;
    }

    vec3 lms = toLms * c;
    vec3 lab = toLab * (sign(lms) * pow(abs(lms), vec3(1.0 / 3.0)));
    lab.yz *= 1.0 + vibrance * (1.0 - smoothstep(0.0, 0.25, length(lab.yz)));
    lab.yz *= saturation;
    float gain = 1.0;
    if (mixed != 0) lab = mixColours(lab, gain);
    lms = fromLab * lab;
    c = toScreen * (fromLms * (lms * lms * lms)) * gain;
    colour = vec4(encode(clamp(c, 0.0, 1.0)), 1.0);
}
"""

# The screen, from the textures and the table.
SCREEN = HEAD + b"""
uniform sampler2D colour0, colour1, colour2, around0, around1, around2;
uniform sampler3D table;
uniform float size, exposure, contrast, highlights, shadows, structure, detail, sharpness;
uniform int spatial, areas;
out vec4 colour;

float graded(int i, sampler2D colours, sampler2D arounds) {
    ivec2 at = ivec2(gl_FragCoord.xy);
    vec3 tone = texelFetch(colours, at, 0).rgb;
    if (spatial != 0) {
        vec4 around = texelFetch(arounds, at, 0);
        float gain = dot(vec3(detail, structure, sharpness), around.yzw);
        if (areas != 0) {
            float s = around.x + exposure;
            float t = tanh(s / 3.0);
            s += contrast * 3.0 * t;
            gain += (highlights * smoothstep(0.0, 3.0, s) + shadows * smoothstep(0.0, 4.0, -s))
                / (1.0 + contrast * (1.0 - t * t));
        }
        tone *= exp2(gain / GAMMA);
    }
    tone = mix(tone, 1.0 + (min(tone, 2.0) - 1.0) / 3.0, step(1.0, tone)) * 0.75;
    return texture(table, (tone * (size - 1.0) + 0.5) / size)[i];
}
void main() {
    colour = vec4(graded(0, colour0, around0), graded(1, colour1, around1), graded(2, colour2, around2), 1.0);
}
"""


class _Program:
    """A shader's program: use() it, then set its uniforms by name."""

    def __init__(self, gl, fragment):
        self.gl = gl
        self.handle = link_program(gl, VERTEX, fragment)
        self.places = {}

    def uniform(self, name):
        if name not in self.places:
            self.places[name] = self.gl.glGetUniformLocation(self.handle, name.encode())
        return self.places[name]

    def use(self, **values):
        """Uses it, and sets its uniforms: whole numbers, pairs of them, floats, arrays of floats, 3 x 3 matrices,
        or pairs of floats, as tuples."""
        gl = self.gl
        gl.glUseProgram(self.handle)
        for name, value in values.items():
            place = self.uniform(name)
            if isinstance(value, tuple) and isinstance(value[0], int):
                gl.glUniform2i(place, *value)
            elif isinstance(value, tuple):
                gl.glUniform2f(place, *value)
            elif isinstance(value, int):
                gl.glUniform1i(place, value)
            elif np.ndim(value) == 2:
                gl.glUniformMatrix3fv(place, 1, 1, (c_float * 9)(*np.ravel(value)))
            elif np.ndim(value) == 1:
                gl.glUniform1fv(place, len(value), (c_float * len(value))(*value))
            else:
                gl.glUniform1f(place, value)
        return self

    def close(self):
        self.gl.glDeleteProgram(self.handle)


def _gaussian(sigma):
    """The weights of a Gaussian blur, its middle first."""
    taps = min(MAX_TAPS, int(np.ceil(2.5 * sigma)))
    weights = np.exp(-0.5 * (np.arange(taps + 1) / sigma) ** 2)
    return weights / (2 * weights.sum() - weights[0])


class GradedQuilt:
    """One quilt, drawn with one grade after another into the bound framebuffer, through a Renderer's context; or,
    without a calibration, the whole quilt with a grade, whole()."""

    def __init__(self, renderer, key, picture, layout, calibration=None, reverse=False):
        self.renderer, self.key, self.gl = renderer, key, renderer.gl
        self.picture = picture  # Kept, so that its id, in the key, is of no other.
        self.layout, self.calibration, self.reverse = layout, calibration, reverse
        self.textures, self.programs = [], []
        framebuffer = c_uint()
        self.gl.glGenFramebuffers(1, byref(framebuffer))
        self.framebuffer = framebuffer.value
        self.colours = self.around = None
        self.table = self.tabled = None  # The table, and what it was made for.
        try:
            self.screen = self._program(SCREEN)
            self.layers = self._program(TABLE_LAYER)
        except BaseException:
            self.close()
            raise

    def draw(self, grade):
        """Draws the hologram of the quilt with this grade."""
        gl, bound = self.gl, c_int()
        gl.glGetIntegerv(GL_FRAMEBUFFER_BINDING, byref(bound))
        gl.glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        try:
            self._prepare(grade)
        finally:
            gl.glBindFramebuffer(GL_FRAMEBUFFER, bound.value)
            gl.glViewport(0, 0, self.renderer.width, self.renderer.height)
        self._shade(grade)

    def whole(self, grade):
        """The quilt itself with this grade, an RGB array, rows from the top: the same colours as draw()'s."""
        gl, bound = self.gl, c_int()
        height, width = self.picture.shape[:2]
        gl.glGetIntegerv(GL_FRAMEBUFFER_BINDING, byref(bound))
        gl.glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        try:
            self._prepare(grade)
            target = self._texture(GL_RGBA8, width, height)
            gl.glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, target, 0)
            self._check()
            gl.glViewport(0, 0, width, height)
            self._shade(grade)
            pixels = np.empty((height, width, 4), np.uint8)
            gl.glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, pixels.ctypes.data)
            error = gl.glGetError()
            if error:  # e.g. no memory left for a large quilt: better no file than a wrong one.
                raise RuntimeError(f"the GPU cannot grade the whole quilt: OpenGL error {error:#x}")
        finally:
            gl.glBindFramebuffer(GL_FRAMEBUFFER, bound.value)
            gl.glViewport(0, 0, self.renderer.width, self.renderer.height)
        return np.ascontiguousarray(pixels[..., :3])

    def _shade(self, grade):
        gl = self.gl
        self._bind(self.screen, GL_TEXTURE_2D, {f"colour{i}": texture for i, texture in enumerate(self.colours)})
        if grade.spatial:
            self._bind(self.screen, GL_TEXTURE_2D, {f"around{i}": texture for i, texture in enumerate(self.around)}, 3)
        else:  # Not read, but a sampler must not share a unit with one of another kind.
            self._bind(self.screen, GL_TEXTURE_2D, {f"around{i}": self.colours[0] for i in range(3)}, 3)
        self._bind(self.screen, GL_TEXTURE_3D, {"table": self.table}, 6)
        detail = grade["detail"] / 100
        self.screen.use(
            size=float(TABLE), spatial=int(grade.spatial),
            areas=int(grade["highlights"] != 0 or grade["shadows"] != 0), exposure=float(grade["exposure"]),
            contrast=grade["contrast"] / 200, highlights=grade["highlights"] * 0.015, shadows=grade["shadows"] * 0.02,
            structure=grade["structure"] * 0.008, sharpness=grade["sharpness"] / 100,
            # Smoothing more than the whole band would invert it.
            detail=detail * 2 if detail > 0 else detail)
        gl.glDrawArrays(GL_TRIANGLES, 0, 3)
        gl.glUseProgram(self.renderer.program)

    def close(self):
        """Gives the GPU's memory back."""
        self._delete(list(self.textures))
        for program in self.programs:
            program.close()
        self.programs = []
        self.gl.glDeleteFramebuffers(1, byref(c_uint(self.framebuffer)))

    # What does not depend on the grade, once.

    def _prepare(self, grade):
        if self.colours is None or (grade.spatial and self.around is None):
            height, width = self.picture.shape[:2]
            quilt = self._upload(self.picture)
            if self.colours is None:
                self.colours = self._interleaved(COLOURS, GL_RGB10_A2, {"quilt": quilt}, width, height)
            if grade.spatial and self.around is None:
                self.around = self._look_around(quilt, width, height)
            self._delete([quilt])
        made_for = {id: value for id, value in grade.values.items() if id not in SPATIAL}
        if made_for != self.tabled:
            self._fill_table(grade)
            self.tabled = made_for

    def _upload(self, picture):
        gl = self.gl
        picture = np.ascontiguousarray(picture)
        height, width = picture.shape[:2]
        if max(width, height) > self.renderer.largest:
            raise ValueError(f"a picture of {width} x {height} is larger than the GPU takes, "
                             f"{self.renderer.largest} x {self.renderer.largest}")
        quilt = self._texture(GL_RGB8, width, height)
        gl.glPixelStorei(GL_UNPACK_ROW_LENGTH, width)
        gl.glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE, picture.ctypes.data)
        gl.glPixelStorei(GL_UNPACK_ROW_LENGTH, 0)
        return quilt

    def _interleaved(self, shader, internal, sources, width, height, **values):
        """What `shader` takes of the quilt's pixel of each sub-pixel of the screen: three textures of its size. Without
        a calibration, of each pixel of the quilt: one texture of its size, three times."""
        renderer = self.renderer
        if self.calibration is None:
            values.update(grid=(self.layout.columns, self.layout.rows), quiltSize=(width, height))
            return [self._made(HEAD + OF_THE_QUILT + shader, internal, width, height, sources, **values)] * 3
        program = self._program(HEAD + OF_THE_SCREEN + shader)
        textures = []
        for sub in range(3):
            textures.append(self._texture(internal, renderer.width, renderer.height))
            self._bind(program, GL_TEXTURE_2D, sources)
            program.use(sub=sub, **values)
            renderer.set_interleaving(program.uniform, self.layout, self.calibration, self.reverse, (width, height))
            self._fill(textures[-1], renderer.width, renderer.height)
        return textures

    def _look_around(self, quilt, width, height):
        layout = self.layout
        view = {"grid": (layout.columns, layout.rows), "quiltSize": (width, height)}
        luminance = self._made(LUMINANCE, GL_R16F, width, height, {"quilt": quilt})
        fine = self._blurred(luminance, width, height, FINE_SIGMA, view)
        coarse = self._blurred(fine, width, height, float(np.sqrt(COARSE_SIGMA**2 - FINE_SIGMA**2)), view)

        # The areas and the shapes, with guided filters, on smaller views.
        view_width, view_height = width / layout.columns, height / layout.rows
        cell = (int(np.ceil(view_width / SHRINK)), int(np.ceil(view_height / SHRINK)))
        small = (cell[0] * layout.columns, cell[1] * layout.rows)
        diagonal = np.hypot(view_width, view_height)
        radii = tuple(max(1, round(diagonal * share / SHRINK)) for share in (AREA_OF_DIAGONAL, SHAPES_OF_DIAGONAL))

        def averaged(image):
            for along in ((1, 0), (0, 1)):
                image = self._made(BOX, GL_RGBA16F, *small, {"image": image}, cell=cell, along=along, radii=radii)
            return image

        means = averaged(self._made(SMALL, GL_RGBA16F, *small, {"image": luminance}, cell=cell, shrink=SHRINK, **view))
        guided = averaged(self._made(GUIDED, GL_RGBA16F, *small, {"image": means}, epsilons=(0.5**2, 0.2**2)))
        before = list(self.textures)
        around = self._interleaved(AROUND, GL_RGBA16F, {"luminance": luminance, "fine": fine, "coarse": coarse,
                                                        "guided": guided}, width, height, cell=cell, shrink=SHRINK)
        self._delete([texture for texture in before if texture not in (quilt, *self.colours, self.table)])
        return around

    def _blurred(self, image, width, height, sigma, view):
        weights = _gaussian(sigma)
        for along in ((1, 0), (0, 1)):
            image = self._made(BLUR, GL_R16F, width, height, {"image": image}, along=along, taps=len(weights) - 1,
                               weights=weights, **view)
        return image

    # The table, at each change of the tools in it.

    def _fill_table(self, grade):
        gl = self.gl
        if self.table is None:
            self.table = self._texture(GL_RGB10_A2, TABLE, TABLE, depth=TABLE)
        x, y, tangents = tone_curve(grade)
        turns, chromas, stops = mixer(grade)
        working = white_balance(grade["temperature"], grade["tint"]) @ SRGB_TO_REC2020 * 2.0 ** grade["exposure"]
        self.layers.use(
            size=float(TABLE), toWorking=working, toScreen=REC2020_TO_SRGB, toLms=LMS_FROM_REC2020,
            fromLms=np.linalg.inv(LMS_FROM_REC2020), toLab=OKLAB_FROM_LMS, fromLab=np.linalg.inv(OKLAB_FROM_LMS),
            contrast=grade["contrast"] / 200, blacks=grade["blacks"] * 0.0002, vibrance=grade["vibrance"] / 100,
            saturation=1 + grade["saturation"] / 100, curveX=x, curveY=y, curveTangent=tangents,
            curved=int(any(id.startswith("curve_") for id in grade.values)),
            mixed=int(any(stops) or any(turns) or any(chromas)),
            hues=BAND_HUES, turns=turns, chromas=chromas, stops=stops)
        place = self.layers.uniform("layer")
        gl.glViewport(0, 0, TABLE, TABLE)
        for layer in range(TABLE):
            gl.glFramebufferTextureLayer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, self.table, 0, layer)
            if layer == 0:
                self._check()
            gl.glUniform1f(place, layer)
            gl.glDrawArrays(GL_TRIANGLES, 0, 3)

    # OpenGL.

    def _program(self, fragment):
        for program in self.programs:
            if program.fragment == fragment:
                return program
        program = _Program(self.gl, fragment)
        program.fragment = fragment
        self.programs.append(program)
        return program

    def _texture(self, internal, width, height, depth=None):
        """A new texture, bound to the first unit."""
        gl, handle = self.gl, c_uint()
        target = GL_TEXTURE_2D if depth is None else GL_TEXTURE_3D
        gl.glActiveTexture(GL_TEXTURE0)
        gl.glGenTextures(1, byref(handle))
        gl.glBindTexture(target, handle)
        filter = GL_LINEAR if internal == GL_RGBA16F or depth else GL_NEAREST
        gl.glTexParameteri(target, GL_TEXTURE_MIN_FILTER, filter)
        gl.glTexParameteri(target, GL_TEXTURE_MAG_FILTER, filter)
        for axis in (GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TEXTURE_WRAP_R):
            gl.glTexParameteri(target, axis, GL_CLAMP_TO_EDGE)
        if depth is None:
            gl.glTexStorage2D(target, 1, internal, width, height)
        else:
            gl.glTexStorage3D(target, 1, internal, width, height, depth)
        self.textures.append(handle.value)
        return handle.value

    def _delete(self, textures):
        for texture in textures:
            self.textures.remove(texture)
            self.gl.glDeleteTextures(1, byref(c_uint(texture)))

    def _bind(self, program, target, sources, first=0):
        program.use()
        for unit, (name, texture) in enumerate(sources.items(), first):
            self.gl.glActiveTexture(GL_TEXTURE0 + unit)
            self.gl.glBindTexture(target, texture)
            program.use(**{name: unit})

    def _made(self, shader, internal, width, height, sources, **values):
        """A new texture, as `shader` draws it from its sources."""
        texture = self._texture(internal, width, height)
        program = self._program(shader)
        self._bind(program, GL_TEXTURE_2D, sources)
        program.use(**values)
        self._fill(texture, width, height)
        return texture

    def _fill(self, texture, width, height):
        gl = self.gl
        gl.glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0)
        self._check()
        gl.glViewport(0, 0, width, height)
        gl.glDrawArrays(GL_TRIANGLES, 0, 3)

    def _check(self):
        status = self.gl.glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"the GPU cannot draw a grade: framebuffer status {status:#x}")
