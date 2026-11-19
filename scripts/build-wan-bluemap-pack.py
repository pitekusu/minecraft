#!/usr/bin/env python3

import argparse
import io
import json
import zipfile


MOD_PATH = "mods/wan_ancient_beasts-forge_1.20.1_1.4.3.jar"
MODEL_PATH = "assets/wan_ancient_beasts/models/block"
EXPECTED_REMOVALS = {"equisetum_stem": 64, "equisetum_top": 8, "rafflesia": 20}
FACE_NORMAL_AXIS = {"east": 0, "west": 0, "up": 1, "down": 1, "north": 2, "south": 2}


def remove_placeholder_faces(model, name, expected_count):
    count = 0
    for element in model["elements"]:
        faces = element["faces"]
        for direction, face in list(faces.items()):
            if face["texture"] != "#missing":
                continue

            normal_axis = FACE_NORMAL_AXIS[direction]
            if not any(
                axis != normal_axis and element["from"][axis] == element["to"][axis]
                for axis in range(3)
            ):
                raise ValueError(f"{name} contains a placeholder face with nonzero area")
            del faces[direction]
            count += 1

    if count != expected_count:
        raise ValueError(f"{name} has {count} placeholder faces, expected {expected_count}")


def build_pack(serverpack, output):
    with zipfile.ZipFile(serverpack) as release:
        mod = io.BytesIO(release.read(MOD_PATH))

    with zipfile.ZipFile(mod) as native, zipfile.ZipFile(output, "w") as overlay:
        for name, expected_count in EXPECTED_REMOVALS.items():
            path = f"{MODEL_PATH}/{name}.json"
            model = json.loads(native.read(path))
            remove_placeholder_faces(model, name, expected_count)

            # Fixed ZIP metadata keeps the generated pack reproducible.
            overlay.writestr(
                zipfile.ZipInfo(path), json.dumps(model) + "\n", zipfile.ZIP_DEFLATED
            )


def main():
    parser = argparse.ArgumentParser(description="Build the BlueMap overlay for Wan Ancient Beasts.")
    parser.add_argument("serverpack", help="Verified TerraFirmaGreg Modern serverpack ZIP")
    parser.add_argument("output", help="Destination ZIP")
    args = parser.parse_args()
    build_pack(args.serverpack, args.output)


if __name__ == "__main__":
    main()
