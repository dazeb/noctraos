# Torrent swarm notes

Findings from the NoctraOS 0.3.0 ISO torrent (observed 2026-10-07).

## The torrent

- File: `noctraos-0.3.0-amd64.iso` (3.9 GB)
- SHA-256: `97ee37900890fa7d69e3f0efb0e567a0b1deabdb4f9c2a038ff1f65bbac9dfba`
- Torrent: `noctraos-0.3.0-amd64.iso.torrent` (19 KB)
- Infohash: `f0bc06bc6a0103a08af681d580a118f73fa47483`
- Trackers:
  - `http://tracker.opentrackr.org:1337/announce`
  - `udp://tracker.opentrackr.org:1337/announce`
  - `udp://open.demonii.com:1337/announce`
  - `udp://tracker.openbittorrent.com:80/announce`
- Magnet: `magnet:?xt=urn:btih:f0bc06bc6a0103a08af681d580a118f73fa47483&dn=noctraos-0.3.0-amd64.iso&tr=http%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A80%2Fannounce`
- Webseed (BEP 19 `url-list`, same infohash): `https://dl.noctraos.dev/releases/v0.3.0/noctraos-0.3.0-amd64.iso` — prepared, pending upload of the `.torrent` to R2

## Our seeders

- ubuntubox Docker (`noctraos-seed`, linuxserver/transmission) — ratio cap 10:1
- Sandbox transmission-daemon (outbound-only, no inbound/UDP)

## Swarm observations (2026-10-07)

- opentrackr reported **3 seeders, 2 leechers, 0 finished downloads**.
- Two unknown peers appeared in the peer list (IPs are transient — they change as peers join/leave):
  - `67.21.89.42` — Sharktech (hosting/VPN provider), Los Angeles, US
  - `87.81.236.13` — Fastly ASN, Atlanta, US (likely a VPN/proxy exit)
- Neither accepted inbound peer connections when probed (connection refused / timed out), so client software and the seeder/leecher split could not be determined. An IP alone does not identify the operator.
- They most likely found the torrent via the public PR branches on GitHub before release.

## Notes

- The sandbox seeder only reaches peers through HTTP trackers (no UDP, no inbound), so its view of the swarm is partial. The ubuntubox seeder has full connectivity.
- Tracker scrape: `http://tracker.opentrackr.org:1337/scrape?info_hash=<urlencoded infohash>`
