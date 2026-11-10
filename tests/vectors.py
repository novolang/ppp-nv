#!/usr/bin/env python3
"""tests/vectors.py -- the wire strings of tests/pppsess_link_tests.nv.

A PPP framer written for the purpose and separate from the package: it
computes the CRC one bit at a time with no table, builds the frame by the rules
of RFC 1662 (the address and control, the protocol, the FCS low byte first,
the escape of 7E, 7D and of the control characters in the map), and prints
each frame of the scenario as the Novo function the test file holds.  Run it
with `python3 tests/vectors.py`; the output is the list of functions from
`us_lcp_req` on.

Two of its lines are checks of the framer itself: the CRC-16 of X.25 and the
CRC-32 of the nine characters "123456789" are 0x906E and 0xCBF43926.
"""
import hashlib

def crc16(data):
    f = 0xFFFF
    for b in data:
        f ^= b
        for _ in range(8):
            f = (f >> 1) ^ 0x8408 if f & 1 else f >> 1
    return f ^ 0xFFFF


def crc32(data):
    f = 0xFFFFFFFF
    for b in data:
        f ^= b
        for _ in range(8):
            f = (f >> 1) ^ 0xEDB88320 if f & 1 else f >> 1
    return f ^ 0xFFFFFFFF


def esc(bs, accm):
    out = []
    for b in bs:
        if b in (0x7E, 0x7D) or (b < 0x20 and (accm >> b) & 1):
            out += [0x7D, b ^ 0x20]
        else:
            out.append(b)
    return out


def frame(proto, info, accm=0xFFFFFFFF, acfc=False, pfc=False, fcs32=False):
    lcp = proto == 0xC021 and info and 1 <= info[0] <= 7
    if lcp:
        accm, acfc, pfc = 0xFFFFFFFF, False, False
    body = [] if acfc else [0xFF, 0x03]
    body += [proto >> 8, proto & 0xFF] if (proto > 0xFF or not pfc) else [proto]
    body += list(info)
    if fcs32:
        c = crc32(body)
        tail = [(c >> (8 * i)) & 0xFF for i in range(4)]
    else:
        c = crc16(body)
        tail = [c & 0xFF, c >> 8]
    return [0x7E] + esc(body + tail, accm) + [0x7E], body, tail


def hx(xs):
    return " ".join("%02X" % x for x in xs)


assert crc16(b"123456789") == 0x906E and crc32(b"123456789") == 0xCBF43926



def be32(v):
    return [(v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255]


def cp(code, ident, data):
    n = 4 + len(data)
    return [code, ident, n >> 8, n & 255] + list(data)


MAGIC = 0xCF2759C0
OUR_REQ_OPTS = [2, 6, 0, 0, 0, 0] + [5, 6] + be32(MAGIC) + [7, 2, 8, 2]
PEER_REQ_OPTS = [8, 2, 7, 2, 2, 6, 0, 0, 0, 0, 1, 4, 5, 0xDC, 5, 6] + be32(0x543) + [3, 5, 0xC2, 0x23, 5]
CHALLENGE = list(range(0x10, 0x20))
SECRET = b"secret"
USER = b"internet"
digest = list(hashlib.md5(bytes([0x21]) + SECRET + bytes(CHALLENGE)).digest())

# Peer -> us, full header, accm 0 (the value we asked for).
P = dict(accm=0, acfc=False, pfc=False)
# Us -> peer after LCP is up: the peer's asyncmap 0, accomp, pcomp.
U = dict(accm=0, acfc=True, pfc=True)

steps = []


def add(name, proto, info, **kw):
    w, body, tail = frame(proto, info, **kw)
    steps.append((name, proto, info, w))


add("us_lcp_req", 0xC021, cp(1, 1, OUR_REQ_OPTS))                      # default form, all escaped
add("peer_lcp_req", 0xC021, cp(1, 1, PEER_REQ_OPTS), **P)
add("us_lcp_ack", 0xC021, cp(2, 1, PEER_REQ_OPTS))
add("peer_lcp_ack", 0xC021, cp(2, 1, OUR_REQ_OPTS), **P)
add("peer_chap_challenge", 0xC223, cp(1, 0x21, [16] + CHALLENGE + list(b"ggsn")), **P)
add("us_chap_response", 0xC223, cp(2, 0x21, [16] + digest + list(USER)), **U)
add("peer_chap_success", 0xC223, cp(3, 0x21, list(b"Welcome")), **P)
IPCP_REQ1 = [3, 6, 0, 0, 0, 0, 0x81, 6, 0, 0, 0, 0, 0x83, 6, 0, 0, 0, 0]
add("us_ipcp_req1", 0x8021, cp(1, 1, IPCP_REQ1), **U)
add("peer_ipcp_req", 0x8021, cp(1, 1, [3, 6, 10, 64, 64, 64]), **P)
add("us_ipcp_ack", 0x8021, cp(2, 1, [3, 6, 10, 64, 64, 64]), **U)
NAK = [3, 6, 100, 72, 3, 9, 0x81, 6, 8, 8, 8, 8, 0x83, 6, 8, 8, 4, 4]
add("peer_ipcp_nak", 0x8021, cp(3, 1, NAK), **P)
add("us_ipcp_req2", 0x8021, cp(1, 2, NAK), **U)
add("peer_ipcp_ack", 0x8021, cp(2, 2, NAK), **P)
DGRAM = [0x45, 0x00, 0x00, 0x1C, 0x00, 0x01, 0x00, 0x00, 0x40, 0x01, 0x7E, 0x7D, 100, 72, 3, 9, 8, 8, 8, 8]
add("us_datagram", 0x0021, DGRAM, **U)
add("peer_datagram", 0x0021, DGRAM[::-1], **P)
add("peer_echo_req", 0xC021, cp(9, 5, be32(0x543) + [0xDE, 0xAD]), **P)
add("us_echo_rep", 0xC021, cp(10, 5, be32(MAGIC) + [0xDE, 0xAD]), **U)
add("us_term_req", 0xC021, cp(5, 2, []), **U)
add("peer_term_ack", 0xC021, cp(6, 2, []), **P)

print("// digest", hx(digest))
for name, proto, info, w in steps:
    print("fn %s() -> [Int]" % name)
    lines = []
    row = []
    for b in w:
        row.append("0x%02X" % b)
        if len(row) == 16:
            lines.append(", ".join(row))
            row = []
    if row:
        lines.append(", ".join(row))
    print("    [" + ",\n     ".join(lines) + "]")
    print()
