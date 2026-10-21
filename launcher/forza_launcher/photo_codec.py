"""Read authenticated native photos using tables from the player's executable."""
from functools import lru_cache
import hmac
from pathlib import Path
import struct

from . import TITLE_ID, save_editor

MAX_BYTES = 64 * 1024 * 1024
# Disc and TU4 addresses only; no game key material is distributed.
TABLES = ((0x8204FB58, 0x8204FB38), (0x82060D38, 0x82060D18))


@lru_cache(maxsize=4)
def _tables(path, size, modified):
    if size > 128 * 1024**2:
        raise ValueError("Game executable exceeds the size limit.")
    raw = Path(path).read_bytes()
    from .xexcheck import header_info
    info = header_info(raw)
    if not info or info[3] != int(TITLE_ID, 16):
        raise ValueError("Choose your FH1 game files in Setup to read native photos.")
    try:
        xex = save_editor._aes_tools().Xex(raw)
        if xex.image_size > 128 * 1024**2 or xex.pages_size() > 128 * 1024**2:
            raise ValueError("Executable image exceeds the size limit.")
        image = xex.image()
    except (SystemExit, ValueError, struct.error) as exc:
        raise ValueError("Could not read native-photo tables from the game executable.") from exc
    result = []
    for aes_address, mac_address in TABLES:
        a, m = aes_address - xex.load_address, mac_address - xex.load_address
        if min(a, m) >= 0 and a + 16 <= len(image) and m + 32 <= len(image):
            result.append((bytes(image[a:a+16]), bytes(image[m:m+32])))
    return tuple(result)


def keys_for(cfg):
    executable = cfg.game_files() / "default.xex"
    info = executable.stat()
    owner = save_editor._owner(cfg)
    return tuple((bytes(((a[i] ^ owner[(i-3) % 8]) + 2*i) % 256 for i in range(16)),
                  bytes(((m[i] ^ owner[(i-4) % 8]) + 2*i) % 256 for i in range(32)))
                 for a, m in _tables(str(executable.resolve()), info.st_size, info.st_mtime_ns))


def encrypted_length(raw):
    if not 68 <= len(raw) <= MAX_BYTES or (len(raw)-52) % 16:
        return None
    length = 0
    for word in struct.unpack_from(">5I", raw, 32):
        length ^= word
    if not 0 < length <= MAX_BYTES-52 or 52 + ((length+15)//16)*16 != len(raw):
        return None
    return length


def decode(raw, candidates):
    length = encrypted_length(raw)
    if length is None:
        raise ValueError("Invalid encrypted photo length.")
    for aes_key, mac_key in candidates:
        if len(aes_key) != 16 or len(mac_key) != 32:
            raise ValueError("Invalid photo key sizes.")
        if not hmac.compare_digest(hmac.digest(mac_key, raw[32:], "sha256"), raw[:32]):
            continue
        cipher = raw[52:]
        ecb = save_editor._aes_tools().aes_decrypt(aes_key, cipher, cbc=False)
        plain = bytes(a ^ b for a, b in zip(ecb, raw[36:52] + cipher[:-16]))[:length]
        if not plain.startswith(b"\xff\xd8\xff"):
            raise ValueError("Authenticated photo does not contain a supported JPEG.")
        return plain
    raise ValueError("Native photo authentication failed. Check the game files and profile identity.")
