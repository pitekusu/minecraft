# Repository Guidelines

## Project Structure

- `quadlet/` defines the rootless Podman services, their shared network, and the Caddy proxy. Minecraft runs TerraFirmaGreg Modern on Forge. BlueMap CLI renders terrain and sends SSE updates. Forge BlueMap serves player positions and head images through Caddy.
- `config/bluemap/` contains the shared Overworld, underground, and Beneath map definitions and the `packs/TFG_Map_Compatibility/` resource overlay. `config/bluemap-cli/` holds standalone settings and the version-specific player polling script under `web/`.
- `scripts/` contains the setup script and Python resource-pack builders. `LICENSES/` records upstream asset notices. See [README.md](README.md) for deployment and recovery steps.

## Setup and Validation

- Run `./scripts/prepare.sh` to verify pinned downloads and build the local overlays. It requires Python 3.10+ and libpng 1.6. Inspect generated packs with `unzip -t downloads/BlueMap-GTCEu-Mojang-v1.zip`.
- Run `bash -n scripts/prepare.sh`, `node --check config/bluemap-cli/web/player-polling-5.29.js`, and `git diff --check` for syntax and whitespace checks. On the deployment host, use `QUADLET_UNIT_DIRS="$PWD/quadlet" /usr/lib/systemd/user-generators/podman-user-generator --user --dryrun` to validate Quadlet generation.
- Follow the README to install the units and start the services with `systemctl --user`. For a test instance, use a separate systemd user and adjust bind mounts and loopback ports before starting the units.

## Testing

The repository uses manual smoke tests. For map or proxy changes, check `/settings.json` and `/maps/overworld/live/players.json` at `http://127.0.0.1:8100`. In the browser, load all three maps and inspect affected blocks. For live-update changes, verify terrain refresh and SSE reconnection through Playit, player polling, and head PNG loading.

## Style and Configuration

Use two spaces in Bash and JSON, four in Python and browser JavaScript, and tabs in the Caddyfile. Preserve Minecraft resource namespaces and lowercase map IDs. Update pinned versions and checksums together. Keep worlds, rendered tiles, downloads, backups, and credentials out of Git. Record the source and license of imported assets.

## Commits and Pull Requests

Use imperative commit subjects, such as `Include upstream notices for BlueMap compatibility models`. In pull requests, describe the affected services, list validation performed, link relevant issues, and include screenshots for visible rendering fixes.
