"""Small, declarative launcher mods.

A mod lives in ``<data home>/mods/<folder>/mod.json``.  The manifest may add
environment variables to the game and expose options that are written to an INI
file in the mod folder.  This is deliberately narrow: mods cannot execute code in
the launcher or replace files in the ReImagined runtime.
"""
import configparser
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

MANIFEST = "mod.json"
MANIFEST_SCHEMA = 1
ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
MAX_ARCHIVE_FILES = 10_000
MAX_ARCHIVE_BYTES = 4 * 1024 ** 3


class InstallError(RuntimeError):
    pass


@dataclass
class ModOption:
    key: str
    label: str
    kind: str
    default: object
    help: str = ""
    choices: list = field(default_factory=list)
    ini_file: str = ""
    ini_section: str = ""
    ini_key: str = ""
    values: dict = field(default_factory=dict)


@dataclass
class LauncherMod:
    id: str
    name: str
    description: str
    directory: Path
    environment: dict
    options: list
    enabled_by_default: bool = False
    requires: dict = field(default_factory=dict)
    platforms: list = field(default_factory=list)


def _option(raw: dict) -> ModOption:
    if not isinstance(raw, dict):
        raise ValueError("an option is not an object")
    key = str(raw["key"])
    if not ID_RE.fullmatch(key):
        raise ValueError(f"invalid option id {key!r}")
    kind = str(raw.get("type", "choice"))
    if kind not in ("bool", "choice"):
        raise ValueError(f"option {key!r} has unsupported type {kind!r}")
    ini = raw.get("ini", {})
    if not isinstance(ini, dict):
        raise ValueError(f"option {key!r} has an invalid ini object")
    values = raw.get("values", {})
    if not isinstance(values, dict):
        raise ValueError(f"option {key!r} has an invalid values object")
    choices = []
    for choice in raw.get("choices", []):
        if not isinstance(choice, dict) or "value" not in choice:
            raise ValueError(f"option {key!r} has an invalid choice")
        choices.append((choice["value"], str(choice.get("label", choice["value"]))))
    if kind == "choice" and not choices:
        raise ValueError(f"choice option {key!r} has no choices")
    default = raw.get("default", False if kind == "bool" else choices[0][0])
    if kind == "choice" and default not in [v for v, _label in choices]:
        raise ValueError(f"option {key!r} has a default that is not a choice")
    return ModOption(key, str(raw.get("label", key)), kind, default,
                     str(raw.get("help", "")), choices, str(ini.get("file", "")),
                     str(ini.get("section", "")), str(ini.get("key", "")),
                     {str(k): str(v) for k, v in values.items()})


def load_manifest(path: Path) -> LauncherMod:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("the manifest is not an object")
    if raw.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported manifest schema {raw.get('schema')!r}")
    mod_id = str(raw["id"])
    if not ID_RE.fullmatch(mod_id):
        raise ValueError(f"invalid mod id {mod_id!r}")
    raw_platforms = raw.get("platforms", [])
    if not isinstance(raw_platforms, list):
        raise ValueError("platforms is not a list")
    platforms = [str(p).lower() for p in raw_platforms]
    environment = raw.get("environment", {})
    if not isinstance(environment, dict):
        raise ValueError("environment is not an object")
    environment = {str(k): str(v) for k, v in environment.items()}
    invalid_env = [key for key in environment if not ENV_RE.fullmatch(key)]
    if invalid_env:
        raise ValueError(f"invalid environment variable {invalid_env[0]!r}")
    options = [_option(item) for item in raw.get("options", [])]
    if len({o.key for o in options}) != len(options):
        raise ValueError("duplicate option id")
    requires = raw.get("requires", {})
    if not isinstance(requires, dict) or not isinstance(requires.get("settings", {}), dict):
        raise ValueError("requires is not an object with a settings object")
    return LauncherMod(mod_id, str(raw.get("name", mod_id)), str(raw.get("description", "")),
                       path.parent, environment, options, bool(raw.get("enabled_by_default", False)),
                       requires, platforms)


def discover(cfg: Config) -> tuple[list[LauncherMod], list[str]]:
    root = cfg.data_home() / "mods"
    found, warnings = [], []
    try:
        manifests = sorted(root.glob(f"*/{MANIFEST}"))
    except OSError as e:
        return [], [f"Could not scan the mods folder: {e}"]
    for path in manifests:
        try:
            mod = load_manifest(path)
            if mod.platforms and ("windows" if sys.platform == "win32" else "linux") not in mod.platforms:
                continue
            if any(other.id == mod.id for other in found):
                raise ValueError(f"duplicate mod id {mod.id!r}")
            found.append(mod)
        except (OSError, ValueError, KeyError, TypeError) as e:
            warnings.append(f"Could not load {path}: {e}")
    return found, warnings


def _package_root(folder: Path) -> Path:
    if (folder / MANIFEST).is_file():
        return folder
    manifests = [p for p in folder.glob(f"*/{MANIFEST}") if p.is_file()]
    if len(manifests) == 1:
        return manifests[0].parent
    if not manifests:
        raise InstallError(f"No {MANIFEST} was found at the package root.")
    raise InstallError(f"The package contains more than one {MANIFEST}.")


def _extract_zip(source: Path, destination: Path):
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as e:
        raise InstallError(f"Could not open {source.name}: {e}") from e
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_FILES:
            raise InstallError(f"The package has more than {MAX_ARCHIVE_FILES:,} files.")
        if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES:
            raise InstallError("The package expands beyond the 4 GB safety limit.")
        for entry in entries:
            # ZIP paths are POSIX, but reject backslashes too so Windows cannot reinterpret them.
            name = entry.filename.replace("\\", "/")
            parts = Path(name).parts
            if not name or name.startswith("/") or ".." in parts or Path(name).drive:
                raise InstallError(f"The package has an unsafe path: {entry.filename}")
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise InstallError(f"The package contains a symbolic link: {entry.filename}")
            target = destination.joinpath(*parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def install(cfg: Config, source: Path, replace=False) -> tuple[LauncherMod, bool]:
    """Install one manifest mod from a folder or ZIP. Returns (mod, replaced_existing)."""
    source = source.resolve()
    mods_root = cfg.data_home() / "mods"
    mods_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=mods_root, prefix=".install-") as temporary:
        work = Path(temporary)
        if source.is_dir():
            source_root = _package_root(source)
            payload = work / "payload"
            shutil.copytree(source_root, payload,
                            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        elif source.is_file() and source.suffix.lower() == ".zip":
            extracted = work / "extracted"
            extracted.mkdir()
            _extract_zip(source, extracted)
            source_root = _package_root(extracted)
            payload = work / "payload"
            source_root.rename(payload)
        else:
            raise InstallError("Choose a mod folder or a .zip package.")

        try:
            mod = load_manifest(payload / MANIFEST)
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise InstallError(f"The mod manifest is not valid: {e}") from e
        target = mods_root / mod.id
        target_resolved = target.resolve()
        if mods_root.resolve() not in target_resolved.parents:
            raise InstallError("The mod id produces an unsafe install path.")
        exists = target.exists()
        if exists and not replace:
            raise FileExistsError(f"{mod.name} is already installed.")

        backup = work / "previous"
        try:
            if exists:
                target.rename(backup)
            payload.rename(target)
        except BaseException:
            if not target.exists() and backup.exists():
                backup.rename(target)
            raise
        mod.directory = target
        set_enabled(cfg, mod, True)
        return mod, exists


def enabled(cfg: Config, mod: LauncherMod) -> bool:
    return bool(cfg.mods.get("enabled", {}).get(mod.id, mod.enabled_by_default))


def option_value(cfg: Config, mod: LauncherMod, option: ModOption):
    return cfg.mods.get("options", {}).get(mod.id, {}).get(option.key, option.default)


def set_enabled(cfg: Config, mod: LauncherMod, value: bool):
    cfg.mods.setdefault("enabled", {})[mod.id] = bool(value)


def set_option(cfg: Config, mod: LauncherMod, option: ModOption, value):
    if option.kind == "bool":
        value = bool(value)
    elif option.kind == "choice" and option.choices:
        allowed = [c[0] for c in option.choices]
        if value not in allowed:
            value = option.default
    cfg.mods.setdefault("options", {}).setdefault(mod.id, {})[option.key] = value


def _requirements_met(cfg: Config, mod: LauncherMod) -> tuple[bool, str]:
    for key, wanted in mod.requires.get("settings", {}).items():
        if cfg.settings.get(key) != wanted:
            return False, f"{mod.name} requires {key}={wanted}."
    return True, ""


def _write_options(cfg: Config, mod: LauncherMod):
    by_file = {}
    for option in mod.options:
        if option.ini_file and option.ini_section and option.ini_key:
            by_file.setdefault(option.ini_file, []).append(option)
    for name, options in by_file.items():
        path = (mod.directory / name).resolve()
        if mod.directory.resolve() not in path.parents:
            raise RuntimeError(f"{mod.name} has an invalid option file path.")
        ini = configparser.ConfigParser(strict=False, interpolation=None)
        ini.optionxform = str
        try:
            if path.is_file():
                with open(path, encoding="utf-8") as f:
                    ini.read_file(f)
        except (OSError, configparser.Error) as e:
            raise RuntimeError(f"Could not read {mod.name}'s settings file {path}: {e}") from e
        for option in options:
            if not ini.has_section(option.ini_section):
                ini.add_section(option.ini_section)
            value = option_value(cfg, mod, option)
            rendered = option.values.get(str(value), "1" if value is True else "0" if value is False else str(value))
            ini.set(option.ini_section, option.ini_key, rendered)
        out = io.StringIO()
        ini.write(out, space_around_delimiters=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(out.getvalue())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def apply(cfg: Config, env: dict, notes: list, write=True):
    """Apply enabled mods to a launch plan without mutating the global environment."""
    found, warnings = discover(cfg)
    notes.extend(warnings)
    for mod in found:
        if not enabled(cfg, mod):
            continue
        ok, reason = _requirements_met(cfg, mod)
        if not ok:
            notes.append(reason + " The mod was skipped.")
            continue
        if write:
            _write_options(cfg, mod)
        values = {"mod_dir": str(mod.directory.resolve()), "data_home": str(cfg.data_home().resolve())}
        for key, value in mod.environment.items():
            try:
                rendered = value.format_map(values)
            except (KeyError, ValueError) as e:
                raise RuntimeError(f"{mod.name} has an invalid environment value for {key}.") from e
            if key == "FORZA_NATIVE_MODS" and env.get(key):
                rendered = env[key] + os.pathsep + rendered
            elif key in env and env[key] != rendered:
                notes.append(f"{mod.name} replaces {key} set by an earlier launcher option or mod.")
            env[key] = rendered
        notes.append(f"Loaded mod: {mod.name}.")
