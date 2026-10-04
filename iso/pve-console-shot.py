#!/usr/bin/env python3
"""pve-console-shot.py — screenshot a Proxmox VM console with only an API token.

usage: pve-console-shot.py <vmid> <out.png>
env:   PVE_HOST (default 192.168.8.195)  PVE_NODE (files)  PVE_TOKEN_FILE ("user@realm!id=secret")
       PVE_SOCKS (host:port of a SOCKS5 proxy, e.g. tailscaled --socks5-server; empty = direct)

Asks the node for a console ticket (vncproxy), opens the vncwebsocket and speaks just enough RFB
(VNC auth, raw encoding) to grab one frame. Nothing is exposed on the LAN. Needs: requests,
websocket-client, python-socks (if PVE_SOCKS), pycryptodome, pillow.
"""
import os, ssl, struct, sys, urllib.parse
import requests, websocket
from Crypto.Cipher import DES
from PIL import Image
HOST, NODE = os.environ.get('PVE_HOST', '192.168.8.195'), os.environ.get('PVE_NODE', 'files')
SOCKS = os.environ.get('PVE_SOCKS', '')
vmid, out = sys.argv[1], sys.argv[2]
tok = open(os.environ['PVE_TOKEN_FILE']).read().strip()
hdr = {'Authorization': 'PVEAPIToken=' + tok}
px = {'https': 'socks5h://' + SOCKS} if SOCKS else None
socks = dict(http_proxy_host=SOCKS.split(':')[0], http_proxy_port=int(SOCKS.split(':')[1]), proxy_type='socks5h') if SOCKS else {}
r = requests.post(f'https://{HOST}:8006/api2/json/nodes/{NODE}/qemu/{vmid}/vncproxy', headers=hdr, data={'websocket': 1},
                  proxies=px, verify=False, timeout=30).json()['data']
url = (f'wss://{HOST}:8006/api2/json/nodes/{NODE}/qemu/{vmid}/vncwebsocket?port={r["port"]}&vncticket='
       + urllib.parse.quote(r['ticket'], safe=''))
ws = websocket.create_connection(url, header=['Authorization: ' + hdr['Authorization']], subprotocols=['binary'],
        sslopt={'cert_reqs': ssl.CERT_NONE}, timeout=30, **socks)
buf = b''
def need(n):
    global buf
    while len(buf) < n:
        d = ws.recv()
        buf += d if isinstance(d, bytes) else d.encode('latin1')
    d, buf = buf[:n], buf[n:]
    return d
need(12); ws.send_binary(b'RFB 003.008\n')
n = need(1)[0]; types = list(need(n))
assert 2 in types, types
ws.send_binary(b'\x02')
chal = need(16)
key = bytes(int('{:08b}'.format(c)[::-1], 2) for c in r['ticket'].encode()[:8].ljust(8, b'\0'))
ws.send_binary(DES.new(key, DES.MODE_ECB).encrypt(chal))
assert struct.unpack('>I', need(4))[0] == 0, 'vnc auth failed'
ws.send_binary(b'\x01')
w, h = struct.unpack('>HH', need(4)); need(16); need(struct.unpack('>I', need(4))[0])
ws.send_binary(struct.pack('>BxxxBBBBHHHBBBxxx', 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
ws.send_binary(struct.pack('>BxHi', 2, 1, 0))
ws.send_binary(struct.pack('>BBHHHH', 3, 0, 0, 0, w, h))
img = Image.new('RGB', (w, h)); got = 0
while got < w * h:
    t = need(1)[0]
    if t == 0:
        need(1); nr = struct.unpack('>H', need(2))[0]
        for _ in range(nr):
            x, y, rw, rh, enc = struct.unpack('>HHHHi', need(12))
            assert enc == 0, enc
            raw = need(rw * rh * 4)
            img.paste(Image.frombuffer('RGB', (rw, rh), raw, 'raw', 'BGRX', 0, 1), (x, y)); got += rw * rh
    elif t == 2: pass
img.save(out); print('saved', out, w, h)
