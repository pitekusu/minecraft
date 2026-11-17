#!/usr/bin/env python3

import argparse
import ctypes
import ctypes.util
import hashlib
import io
import json
import struct
import tempfile
import urllib.request
import zipfile
import zlib
from functools import cache
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
RECIPES = Path(__file__).with_name("gtceu-mojang-bluemap-ore-recipes.json")
GTCEU_MOD = "mods/gtceu-1.20.1-7.5.3.jar"
TFG_CORE_MOD = "mods/TerraFirmaGreg-Core-Modern-0.9.34.jar"
TFG_TEXTURES = "https://raw.githubusercontent.com/TerraFirmaGreg-Team/Modpack-Modern/0.13.18/kubejs"
CLIENT_NAME = "minecraft-client-1.20.1.jar"
CLIENT_URL = (
    "https://piston-data.mojang.com/v1/objects/"
    "0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838/client.jar"
)
CLIENT_SHA256 = "56b71336d2b4fdffd197f56595b0da93e32a946f78f382a299b8f4b92758bb0f"
STONE_TEXTURES = {
    "deepslate": ("deepslate", "deepslate_top"),
    "pyroxenite": ("blackstone", "blackstone_top"),
    "tuff": ("tuff",),
}


class PngImage(ctypes.Structure):
    # libpng's simplified API expands palette, transparency, and image formats to RGBA.
    _fields_ = [
        ("opaque", ctypes.c_void_p),
        ("version", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("format", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("colormap_entries", ctypes.c_uint32),
        ("warning_or_error", ctypes.c_uint32),
        ("message", ctypes.c_char * 64),
    ]


@cache
def libpng():
    library = ctypes.util.find_library("png16")
    if library is None:
        raise RuntimeError("libpng 1.6 is required to build the ore resource pack")
    png = ctypes.CDLL(library)
    png.png_image_begin_read_from_memory.argtypes = [
        ctypes.POINTER(PngImage), ctypes.c_void_p, ctypes.c_size_t
    ]
    png.png_image_finish_read.argtypes = [
        ctypes.POINTER(PngImage), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p
    ]
    png.png_image_free.argtypes = [ctypes.POINTER(PngImage)]
    png.png_image_free.restype = None
    return png


def decode_png(data):
    png = libpng()
    image = PngImage(version=1)
    try:
        if not png.png_image_begin_read_from_memory(ctypes.byref(image), data, len(data)):
            raise ValueError(image.message.decode())
        image.format = 3  # PNG_FORMAT_RGBA
        rgba = (ctypes.c_uint8 * (image.width * image.height * 4))()
        if not png.png_image_finish_read(ctypes.byref(image), None, rgba, 0, None):
            raise ValueError(image.message.decode())
        return image.width, image.height, bytes(rgba)
    finally:
        png.png_image_free(ctypes.byref(image))


def encode_png(image):
    width, height, pixels = image

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    stride = width * 4
    rows = b"".join(b"\0" + pixels[i:i + stride] for i in range(0, len(pixels), stride))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def tint(image, color):
    width, height, data = image
    rgb = bytes.fromhex(color)
    pixels = bytes(
        (value * rgb[i % 4] + 127) // 255 if i % 4 < 3 else value
        for i, value in enumerate(data)
    )
    return width, height, pixels


def composite(bottom, top):
    width, height, background = bottom
    if (width, height) != top[:2]:
        raise ValueError(f"Ore texture dimensions differ: {bottom[:2]} and {top[:2]}")
    foreground = top[2]
    pixels = bytearray()
    for i in range(0, len(background), 4):
        foreground_alpha = foreground[i + 3] * 255
        background_alpha = background[i + 3] * (255 - foreground[i + 3])
        combined_alpha = foreground_alpha + background_alpha
        if combined_alpha == 0:
            pixels.extend((0, 0, 0, 0))
            continue
        for channel in range(i, i + 3):
            weighted = foreground[channel] * foreground_alpha + background[channel] * background_alpha
            pixels.append((weighted + combined_alpha // 2) // combined_alpha)
        pixels.append((combined_alpha + 127) // 255)
    return width, height, bytes(pixels)


def verified_download(destination, url, digest):
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == digest:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {url}", flush=True)
    with urllib.request.urlopen(url, timeout=45) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Checksum mismatch for {url}")
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(data)
            file.close()
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def minecraft_client(cache_dir, client):
    if client is not None:
        if hashlib.sha256(client.read_bytes()).hexdigest() != CLIENT_SHA256:
            raise ValueError(f"Checksum mismatch for {client}")
        return client

    for directory in ("bluemap-cli/data", "bluemap"):
        path = REPOSITORY / "data" / directory / CLIENT_NAME
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == CLIENT_SHA256:
            return path

    return verified_download(cache_dir / CLIENT_NAME, CLIENT_URL, CLIENT_SHA256)


def write_pack(serverpack, cache_dir, output, client):
    recipes = json.loads(RECIPES.read_text())
    external = recipes["remote-texture-sha256"]
    client_jar = minecraft_client(cache_dir, client)

    with (
        zipfile.ZipFile(serverpack) as release,
        zipfile.ZipFile(io.BytesIO(release.read(GTCEU_MOD))) as gtceu,
        zipfile.ZipFile(io.BytesIO(release.read(TFG_CORE_MOD))) as tfg_core,
        zipfile.ZipFile(client_jar) as minecraft,
        zipfile.ZipFile(output, "w") as overlay,
    ):
        archives = {"gtceu": gtceu, "tfc": tfg_core, "minecraft": minecraft}

        @cache
        def texture(reference):
            namespace, file = reference.split(":")
            path = f"assets/{namespace}/textures/{file}.png"
            if reference in external:
                cached = verified_download(
                    cache_dir / "gtceu-bluemap-source" / path, f"{TFG_TEXTURES}/{path}", external[reference]
                )
                return decode_png(cached.read_bytes())
            return decode_png(archives[namespace].read(path))

        pack = {"pack": {"pack_format": 15, "description": "Locally generated GTCEu ore textures for BlueMap"}}
        overlay.writestr(zipfile.ZipInfo("pack.mcmeta"), json.dumps(pack) + "\n", zipfile.ZIP_DEFLATED)
        for material, recipe in recipes["ores"].items():
            layers = []
            for layer in recipe["layers"]:
                image = texture(layer["texture"])
                layers.append(tint(image, layer["tint"]) if "tint" in layer else image)
            for stone in recipe["stones"]:
                for index, base in enumerate(STONE_TEXTURES[stone]):
                    result = texture(f"minecraft:block/{base}")
                    for layer in layers:
                        result = composite(result, layer)
                    name = f"{stone}_{material}_ore"
                    if index:
                        name += "_top"
                    path = f"assets/gtceu/textures/block/bluemap/{name}.png"
                    overlay.writestr(zipfile.ZipInfo(path), encode_png(result), zipfile.ZIP_DEFLATED)


def main():
    parser = argparse.ArgumentParser(description="Build local GTCEu ore textures for BlueMap.")
    parser.add_argument("serverpack", type=Path, help="Verified TerraFirmaGreg Modern 0.13.18 serverpack ZIP")
    parser.add_argument("cache", type=Path, help="Directory for downloaded source files")
    parser.add_argument("output", type=Path, help="Destination resource pack ZIP")
    parser.add_argument("--minecraft-client", type=Path, help="Use an existing official Minecraft 1.20.1 client JAR")
    args = parser.parse_args()
    write_pack(args.serverpack, args.cache, args.output, args.minecraft_client)


if __name__ == "__main__":
    main()
