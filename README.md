# Ultrawide for Forza Horizon 1: ReImagined

An experimental native mod that widens the gameplay camera to the window's aspect ratio.
It also corrects HUD proportions and requests the original 16:9 presentation for the map
and non-gameplay screens. It uses no NVIDIA SDK, DLSS libraries, or other vendor runtime.

This package needs the **experimental native-mod runtime branch** of ReImagined and SDK
patch `0041-native-mod-hud-horizontal-scale.patch`. The existing upstream release cannot
load this DLL. The mod refuses initialization if the HUD graphics capability is missing.

## Install

Build the release package, then choose **Settings > Mods > + > Install from folder** in
the launcher and select `dist/ultrawide`. A ZIP containing those same files can also be
installed with **Install from ZIP**. Select Ultrawide to configure it.

Use a window or display wider than 16:9; the mod follows its actual pixel dimensions.
It leaves 16:9 and narrower windows in the original presentation. The launcher controls
the output size and render resolution as usual. The game still renders to its original
16:9 buffers, using a corrected camera aspect before presentation; this is not a new
native ultrawide render-target implementation.

- **Keep HUD in the center** preserves its original proportions in a centered 16:9 area.
- **Preserve menu framing** requests 16:9 presentation when gameplay projection stops.

Settings are read from `ultrawide.ini` at launch. Disabling the mod takes effect at the
next launch. Neither setting edits the game's assets or the player's save.

## Build

The only runtime dependency is the system C++ runtime. Build with a C++17 compiler:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
cmake --install build --config Release --prefix dist/ultrawide
```

`include/forza_mod.h` is the matching experimental ABI header from ReImagined. Keep the
header and host ABI version aligned. Windows releases contain `ultrawide.dll`,
`mod.json`, `ultrawide.ini` and this project's license notices.

After a single-configuration Windows build, run the DLL integration checks with:

```sh
python -m unittest discover -s tests -v
```

## Status and limits

The camera and menu detection are specific to FH1's base executable and TU4. The hook
does not identify every cinematic camera or pre-rendered video, so complete cutscene
coverage must be checked before calling this release ready. Live smoke tests covered
21:9 and 32:9 gameplay, centered HUD proportions, and restoration of 16:9 pause-menu
framing. The map has automated view-state coverage but still needs a live pass beyond
the tutorial's restrictions. Menu transitions use a
short fallback delay. Windows/Vulkan is the packaged test target; other platforms and
graphics backends are not advertised as validated.

## Credits

The viewport-aspect approach, gameplay/map caller identification and HUD render-target
correction are adapted from Pinyon Shift's BSD-3-Clause implementation. Its copyright
and license are retained in `LICENSE`. No original game assets are distributed.
The ReImagined ABI header's MIT notice is included in `LICENSE-ReImagined`.
