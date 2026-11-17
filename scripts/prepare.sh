#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
mkdir -p -- data/bluemap-cli/data data/bluemap-cli/web downloads backups

temporary_file=
trap 'if [[ -n $temporary_file ]]; then rm -f -- "$temporary_file"; fi' EXIT

download_verified() {
  local checksum_command=$1 checksum=$2 destination=$3 url=$4

  if [[ -f $destination ]] && "$checksum_command" --check --status <<< "$checksum  $destination"; then
    printf 'Verified %s\n' "$destination"
    return
  fi

  temporary_file=$(mktemp -- "${destination}.XXXXXX")
  curl --fail --location --retry 3 --connect-timeout 20 \
    --proto '=https' --proto-redir '=https' --output "$temporary_file" "$url"
  if ! "$checksum_command" --check --status <<< "$checksum  $temporary_file"; then
    printf 'Checksum mismatch for %s\n' "$destination" >&2
    return 1
  fi
  mv -f -- "$temporary_file" "$destination"
  temporary_file=
  printf 'Verified %s\n' "$destination"
}

build_pack() {
  local builder=$1 destination=$2
  shift 2

  temporary_file=$(mktemp -- "${destination}.XXXXXX")
  python3 "$builder" "$@" "$temporary_file"
  mv -f -- "$temporary_file" "$destination"
  temporary_file=
  printf 'Built %s\n' "$destination"
}

download_verified sha256sum \
  88245a70dc3373f0c0970cc9dc56285c01587ed57b85927dff745f617c05221e \
  downloads/TerraFirmaGreg-Modern-0.13.18-serverpack.zip \
  https://github.com/TerraFirmaGreg-Team/Modpack-Modern/releases/download/0.13.18/TerraFirmaGreg-Modern-0.13.18-serverpack.zip

download_verified sha512sum \
  e3c704792e6fc0243ecc3c7e68aab409b8475ed97b77b1cffa7feaf513e92df2b77af139e3c9a14a24eee85009bd855c7e0918d9d1d90024a98b419961054cce \
  downloads/bluemap-5.12-mc1.20-6-forge.jar \
  https://cdn.modrinth.com/data/swbUV1cr/versions/kC7iYqja/bluemap-5.12-mc1.20-6-forge.jar

download_verified sha256sum \
  d022abaeac28e6f4edb200e6d928d117ad3a0367a9383a342327cc7fa52da669 \
  downloads/BlueMap-Create-Resource-Pack-v1.zip \
  https://github.com/Uiniel/BlueMap-Create-Resource-Pack/releases/download/v1/BlueMap-Create-Resource-Pack.zip

build_pack scripts/build-wan-bluemap-pack.py downloads/BlueMap-Wan-Ancient-Beasts-1.4.3-v1.zip \
  downloads/TerraFirmaGreg-Modern-0.13.18-serverpack.zip

build_pack scripts/build-gtceu-mojang-bluemap-pack.py downloads/BlueMap-GTCEu-Mojang-v1.zip \
  downloads/TerraFirmaGreg-Modern-0.13.18-serverpack.zip downloads
