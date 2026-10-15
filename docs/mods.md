# Launcher mods

The launcher discovers optional mods in `<game data folder>/mods`. Each mod has its own folder
containing a `mod.json` manifest. Mods can add environment variables to the game process and expose
settings backed by an INI file in that folder. They cannot execute code in the launcher or replace
files in the ReImagined runtime.

Open **Settings > Mods** and choose **Install from ZIP** for a downloaded release or **Install from
folder** for a local checkout. A GitHub source archive may contain one top-level repository folder;
the launcher finds the manifest inside it. The installer rejects absolute paths, parent-directory
traversal, symbolic links, archives with more than 10,000 entries, and archives that expand beyond
4 GB. Updating an installed mod requires an explicit replacement prompt.

Example:

```json
{
  "schema": 1,
  "id": "example-vulkan-layer",
  "name": "Example Vulkan layer",
  "description": "Adds an optional Vulkan layer.",
  "platforms": ["windows"],
  "enabled_by_default": false,
  "requires": {"settings": {"gpu_backend": "vulkan"}},
  "environment": {
    "VK_INSTANCE_LAYERS": "VK_LAYER_example",
    "VK_LAYER_PATH": "{mod_dir}"
  }
}
```

The launcher expands `{mod_dir}` and `{data_home}` in environment values. A manifest can also
declare `bool` and `choice` options. An option with `ini.file`, `ini.section`, and `ini.key` is
written immediately before the game starts. Choice options may map their visible values to INI
values through a `values` object.

Mods are listed under **Settings > Mods**. Their enabled state and option values are stored in
`launcher.json`; disabling a mod removes its environment from subsequent game launches.

## Experimental native runtime extensions

The native-mod development branch additionally accepts `FORZA_NATIVE_MODS`, a list of absolute
library paths separated by the platform's path separator (`;` on Windows, `:` on Linux). The
launcher combines this variable across enabled mods rather than replacing the earlier library.
Each library exports `ForzaModInit` and implements the versioned C ABI in
`forza-recomp/include/forza_mod.h`. This is an experimental interface, not part of upstream's
release contract.

The host supplies output-size/frame events and viewport-aspect events, without exposing guest
memory pointers. A mod can request presentation letterboxing and the optional HUD horizontal-scale
capability supplied by SDK patch 0041. Presentation requests also identify the source image as
16:9 independently of the SDK's configured video mode, so menu letterboxing works in a wide window.
Frame callbacks are serialized on guest update threads;
projection callbacks can execute on other guest threads, so shared mod state must be synchronized.
UI presentation changes are dispatched to the UI thread. Libraries remain loaded until exit.

The separate Ultrawide example package uses these hooks and an INI file for its HUD/menu options.
It does not require NVIDIA libraries. An upstream runtime that lacks the native interface will
not load it; the mod also rejects hosts missing its required HUD graphics capability.

Environment values may use `{mod_dir}` and `{data_home}`. Supported options are `bool` and `choice`.
The launcher writes only declared INI values; arbitrary installer or launcher scripts are not part
of the format. A package may still contain a native library that the game loads through a declared
environment variable, so install mods only from authors you trust.
