# Built-in ultrawide gameplay and HUD layout

Enable **Settings > Display > Ultrawide gameplay**, then restart. The gameplay
camera follows the physical window aspect with a wider horizontal view. The
viewport query supplies both projection and culling, so the newly visible sides
do not rely on stretching the original camera or cropping its vertical view.
The feature is off by default and does not load external libraries or manifests.

The SDK uses integer render scales along each axis. At startup this feature
allocates at least the initial physical window's pixel dimensions, respecting a
higher requested render scale, up to the SDK's 7x axis limit. A 3440x1440 window
uses a 3840x1440 internal target and downsamples horizontally for presentation.
This is not an arbitrary-size render-target implementation. Windows DPI scaling
is included: a logical 3440x1440 window at 125% is physically 4300x1800. Resizing
updates camera/HUD framing; restart after increasing the window size to increase
the internal detail allocation.

## HUD controls

Enable **Customize HUD layout** to use the sliders at either 16:9 or ultrawide.
This can be enabled independently of camera widening. The default ultrawide HUD is centered in a 16:9 rectangle, retaining its proportions on a
wider display. **HUD safe width/height** fit that rectangle uniformly within a
smaller safe area; the smaller percentage controls the scale. This scales the
HUD as a group rather than stretching gauges independently along each axis.

**HUD horizontal/vertical position** move the group, with offsets clamped so the
rectangle remains on screen. Horizontal positive moves right; vertical positive
moves down. At 100% height there is no vertical space to move into: reduce the
safe area first. These are whole-HUD controls, not individual minimap/speedometer
anchors or an in-game drag editor. The launcher applies changes on the next run;
the corresponding engine cvars can also be adjusted through the SDK console.

The renderer transforms non-depth-tested packed front-buffer UI draws. World
geometry and depth-tested overlays are excluded. The map viewport is excluded
from camera widening; a recent map view or disappearance of gameplay projection
queries restores 16:9 presentation. The swap hook updates this state even while
gameplay timing is paused.

## Validation and current limits

Windows/Vulkan testing on an RTX 5060 Ti covered 2560x1080 and 3440x1440 physical
windows, centered and inset/offset HUD layouts, and a pause-menu round trip.
The 3440x1440 run logged a 3840x1440 target and completed 95 seconds without an
early exit. A separate native-1440p 16:9 run exercised HUD-only adjustments.
The launcher settings/slider checks, persistence tests and standalone
C++ layout/state tests passed. The SDK patch series applies without the DLSS PR.

Full map-screen transitions, car-name overlays in races, split-screen, cutscenes,
and D3D12/Linux runtime behavior still need testing. NVIDIA rendering above 2x
already has known artifacts (issue #47); the higher axis scales used here also
showed reflection changes, so this remains experimental. This PR does not claim
to resolve that renderer issue. DLSS/DLAA integration is separate and currently
assumes 16:9 output.

For the standalone math/state test, compile and run
`forza-recomp/tests/ultrawide_math_test.cpp` with a C++17 compiler. Launcher tests
run with `python -m unittest discover -s launcher -p 'test_*.py'`.
