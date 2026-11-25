"""The transitions from one medium of the playlist to the next: their names, without OpenGL. See gl_transition.py."""

# Nothing in between, also where the GPU does not draw the screen.
CUT = "cut"
KINDS = (CUT, "cross fade", "fade through black", "fade through white")
# How long one takes, in seconds, unless the playlist says otherwise.
SECONDS = 1
