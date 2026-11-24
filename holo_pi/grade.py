"""The grade of a quilt: how its light and its colours are changed when it is shown.

The tools, their ranges and their math are StepIt Grader's, a desktop program that grades photographs: PARAMETERS is
the table of them, which the API and the web page read, so that a tool is added here and in the shader, gl_grade.py,
only. Like there, the work is done on linear Rec. 2020 values, and a grade at its defaults changes nothing.

A grade never changes the file: it is kept beside it, in the library's index, and applied when the quilt is shown.

This module is the values and the numbers the shader needs of them, with no OpenGL.
"""

from dataclasses import dataclass, field

import numpy as np

# The middles of the colour mixer's bands, as hues of sRGB, in degrees: StepIt Grader's.
BANDS = {"red": 0, "orange": 30, "yellow": 60, "green": 120, "aqua": 180, "blue": 240, "purple": 270, "magenta": 300}


@dataclass(frozen=True)
class Parameter:
    """One value of a grade: what it is called, its range and its default."""

    id: str  # e.g. exposure: its name in the API and in the library's index.
    label: str
    section: str  # The section of the tools it belongs to, e.g. Light.
    description: str
    minimum: float = -100
    maximum: float = 100
    default: float = 0
    decimals: int = 0  # Shown and set: 0 for whole numbers.


def _mixer():
    for kind, what in [("hue", "turns its hue, up to 30 degrees"), ("saturation", "makes it greyer or more vivid"),
                       ("luminance", "makes it darker or lighter, up to a stop")]:
        for band in BANDS:
            yield Parameter(f"{band}_{kind}", f"{band.capitalize()} {kind}", f"Color Mixer: {kind.capitalize()}",
                            f"The {band} of the picture: {what}.")


PARAMETERS = [
    Parameter("temperature", "Temperature", "Color", "Warmer, above 0, or cooler."),
    Parameter("tint", "Tint", "Color", "More magenta, above 0, or more green."),
    Parameter("vibrance", "Vibrance", "Color", "The saturation of the muted colours; the vivid ones change little."),
    Parameter("saturation", "Saturation", "Color", "The saturation of every colour; -100 is black and white."),
    Parameter("exposure", "Exposure", "Light", "The light, in stops: 1 is twice as much.", -5, 5, 0, 2),
    Parameter("contrast", "Contrast", "Light", "The contrast around middle grey."),
    Parameter("highlights", "Highlights", "Light", "The bright areas, lighter or darker."),
    Parameter("shadows", "Shadows", "Light", "The dark areas, lighter or darker."),
    Parameter("blacks", "Blacks", "Light", "The black, lifted to a dark grey, or the darkest tones sunk to black."),
    Parameter("curve_shadows", "Shadows", "Tone Curve", "The curve's shadows, its darkest zone."),
    Parameter("curve_darks", "Darks", "Tone Curve", "The curve's darks, its second zone."),
    Parameter("curve_lights", "Lights", "Tone Curve", "The curve's lights, its third zone."),
    Parameter("curve_highlights", "Highlights", "Tone Curve", "The curve's highlights, its brightest zone."),
    Parameter("shadow_split", "Shadows split", "Tone Curve", "The tone where the shadows end, in percent.", 5, 45, 25),
    Parameter("midtone_split", "Midtones split", "Tone Curve", "The tone where the darks end, in percent.", 25, 75, 50),
    Parameter("highlight_split", "Highlights split", "Tone Curve", "The tone where the lights end, in percent.",
              55, 95, 75),
    *_mixer(),
    Parameter("structure", "Structure", "Effects", "The contrast of the shapes, within their edges."),
    Parameter("detail", "Detail", "Effects", "The contrast of the texture, a few pixels wide; below 0 smooths it."),
    Parameter("sharpness", "Sharpness", "Effects", "The contrast of the finest edges.", 0, 150),
]
BY_ID = {parameter.id: parameter for parameter in PARAMETERS}
# The tools that look around a pixel, not only at it.
SPATIAL = ("highlights", "shadows", "structure", "detail", "sharpness")
# The splits say where the curve's zones are: without a zone changed, they do nothing.
SPLITS = ("shadow_split", "midtone_split", "highlight_split")


@dataclass(frozen=True)
class Grade:
    """The values of a grade, by their parameters' ids: those not at their default. `enabled` false shows the quilt
    as it is, and keeps the values."""

    values: dict = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def of(cls, data):
        """The grade of a dictionary of values, and of `enabled`, as the API or the library's index has it: unknown
        names are left out, and the values put in their ranges, e.g. of another version."""
        data = data or {}
        values = {}
        for parameter in PARAMETERS:
            value = float(data.get(parameter.id, parameter.default))
            if not np.isfinite(value):
                continue
            value = min(max(value, parameter.minimum), parameter.maximum)
            if value != parameter.default:
                values[parameter.id] = value
        return cls(values, bool(data.get("enabled", True)))

    def __getitem__(self, id):
        return self.values.get(id, BY_ID[id].default)

    @property
    def kept(self):
        """What the library keeps of it: None when there is nothing to keep."""
        return dict(self.values, enabled=self.enabled) if self.values or not self.enabled else None

    @property
    def full(self):
        """Every value, and `enabled`, as the API answers it."""
        return dict({parameter.id: self[parameter.id] for parameter in PARAMETERS}, enabled=self.enabled)

    @property
    def changes(self):
        """Whether it changes the picture."""
        return self.enabled and any(id not in SPLITS for id in self.values)

    @property
    def spatial(self):
        """Whether one of its tools looks around a pixel."""
        return any(id in self.values for id in SPATIAL)


# The colours, as StepIt Grader's Color.cpp.

_XYZ_TO_SRGB = np.array([[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560],
                         [0.0556434, -0.2040259, 1.0572252]])
_REC2020_TO_XYZ = np.array([[0.6369580, 0.1446169, 0.1688810], [0.2627002, 0.6779981, 0.0593017],
                            [0.0, 0.0280727, 1.0609851]])
_BRADFORD = np.array([[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]])
_OKLAB_M1 = np.array([[0.8189330101, 0.3618667424, -0.1288597137], [0.0329845436, 0.9293118715, 0.0361456387],
                      [0.0482003018, 0.2643662691, 0.6338517070]])
OKLAB_FROM_LMS = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
                           [0.0259040371, 0.7827717662, -0.8086757660]])
REC2020_TO_SRGB = _XYZ_TO_SRGB @ _REC2020_TO_XYZ
SRGB_TO_REC2020 = np.linalg.inv(REC2020_TO_SRGB)
# Oklab's matrix is made for D65 rounded differently: each row is scaled so that a grey has no colour at all.
LMS_FROM_REC2020 = _OKLAB_M1 @ _REC2020_TO_XYZ
LMS_FROM_REC2020 = LMS_FROM_REC2020 / LMS_FROM_REC2020.sum(1, keepdims=True)
_D65 = (0.31271, 0.32902)
_REFERENCE_KELVIN, _V_PER_TINT_STEP = 6504.0, 0.0002


def _planckian(kelvin):
    """The chromaticity of a black body, 1667 to 25000 K (Kim et al., 2002)."""
    t = 1e3 / min(max(kelvin, 1667.0), 25000.0)
    x = np.polyval([-0.2661239, -0.2343589, 0.8776956, 0.179910] if kelvin <= 4000
                   else [-3.0258469, 2.1070379, 0.2226347, 0.240390], t)
    y = np.polyval([-1.1063814, -1.34811020, 2.18555832, -0.20219683] if kelvin <= 2222
                   else [-0.9549476, -1.37418593, 2.09137015, -0.16748867] if kelvin <= 4000
                   else [3.0817580, -5.87338670, 3.75112997, -0.37001483], x)
    return x, y


def _to_uv(xy):
    x, y = xy
    d = -2 * x + 12 * y + 3
    return 4 * x / d, 6 * y / d


def _from_uv(u, v):
    d = 2 * u - 8 * v + 4
    return 3 * u / d, 2 * v / d


def white_balance(temperature, tint):
    """What adapts linear Rec. 2020 values from the light of this temperature and tint to D65, with the Bradford
    transform. The light shifts from D65 along the black bodies, one mired a step, and across them for the tint."""
    u, v = _to_uv(_D65)
    from_u, from_v = _to_uv(_planckian(_REFERENCE_KELVIN))
    to_u, to_v = _to_uv(_planckian(1e6 / (1e6 / _REFERENCE_KELVIN - temperature)))
    source = _from_uv(u + to_u - from_u, v + to_v - from_v + tint * _V_PER_TINT_STEP)

    def cone(xy):
        x, y = xy
        return _BRADFORD @ np.array([x / y, 1, (1 - x - y) / y])

    adapt = np.linalg.inv(_BRADFORD) @ np.diag(cone(_D65) / cone(source)) @ _BRADFORD
    return np.linalg.inv(_REC2020_TO_XYZ) @ adapt @ _REC2020_TO_XYZ


_CURVE_SHIFT, _CURVE_GAP = 0.5, 0.02


def tone_curve(grade):
    """The tone curve, six knots and the tangents at them, as x, y and tangent, of a cubic that always rises."""
    low = grade["shadow_split"] / 100
    middle = max(grade["midtone_split"] / 100, low + _CURVE_GAP)
    high = min(max(grade["highlight_split"] / 100, middle + _CURVE_GAP), 1 - _CURVE_GAP)
    borders = np.array([0, low, middle, high, 1])
    amounts = np.array([grade[f"curve_{zone}"] for zone in ("shadows", "darks", "lights", "highlights")]) / 100
    widths = np.diff(borders)
    x = np.concatenate([[0], borders[:-1] + widths / 2, [1]])
    y = np.concatenate([[0], x[1:-1] + amounts * _CURVE_SHIFT * widths, [1]])
    for i in range(1, 5):  # Every knot above the one before and below white.
        y[i] = min(max(y[i], y[i - 1] + _CURVE_GAP), 1 - _CURVE_GAP * (5 - i))
    # Fritsch and Carlson: the tangents of a cubic that does not overshoot between the knots.
    secants = np.diff(y) / np.diff(x)
    tangents = np.concatenate([[secants[0]], (secants[:-1] + secants[1:]) / 2, [secants[-1]]])
    for i, secant in enumerate(secants):
        length = np.hypot(tangents[i], tangents[i + 1]) / secant
        if length > 3:
            tangents[i:i + 2] *= 3 / length
    return x, y, tangents


def _band_hues():
    """The middles of the mixer's bands, as hues of Oklab, in degrees, rising from the first."""
    hues = []
    for degrees in BANDS.values():
        k = np.mod(np.array([5, 3, 1]) + degrees / 60, 6)
        srgb = 1 - np.clip(np.minimum(np.minimum(k, 4 - k), 1), 0, None)
        lab = OKLAB_FROM_LMS @ np.cbrt(LMS_FROM_REC2020 @ (SRGB_TO_REC2020 @ srgb))
        hues.append(np.degrees(np.arctan2(lab[2], lab[1])) % 360)
    return np.array(hues)


BAND_HUES = _band_hues()


def mixer(grade):
    """The colour mixer: per band, the turn of its hue, in degrees, the change of its chroma and its light, in
    stops."""
    def of(kind, scale):
        return np.array([grade[f"{band}_{kind}"] for band in BANDS]) / 100 * scale
    return of("hue", 30.0), of("saturation", 1.0), of("luminance", 1.0)
