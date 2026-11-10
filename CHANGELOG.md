# Changelog

All notable changes to ppp-nv are recorded here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 rule that a breaking change bumps the MINOR number.

## 0.1.0

The first release.

### Added

- **`pppfcs`** and **`pppframe`**, the frame of RFC 1662 with no allocation:
  the 16-bit and 32-bit FCS tables, `frame_encode` with the escape by an
  ACCM, the compression of the address, control and protocol fields and the
  32-bit FCS, and `PppRx`, a receiver that takes the frame a byte at a time,
  drops unescaped control characters its ACCM names, and reports each frame
  as good or as the fault that spoiled it. LCP packets that negotiate are sent
  in the default form whatever the options say.
- **`pppfsm`**, the option negotiation automaton of RFC 1661 section 4: ten
  states, sixteen events and thirteen actions from the RFC's table, the
  restart counter (Max-Configure 10, Max-Terminate 2) and the restart timer,
  driven by the caller's milliseconds.
- **`pppcp`**, the control packet of RFC 1661 section 5 and the lists of
  options a layer asks for, with a reader that is bounds-checked.
- **`pppmd5`**, MD5 (RFC 1321) as a streaming hash, for CHAP.
- **`pppsess`**, one PPP link as a session the caller drives: LCP with the
  options MRU, ACCM, authentication protocol, magic number, PFC and ACFC;
  Configure-Ack, Nak and Reject in both directions with the Max-Failure limit;
  Terminate, Code-Reject, Protocol-Reject, Echo and Discard; IPCP with the
  IP-Address and the RFC 1877 DNS options; IPv6CP with the interface
  identifier; the client side of PAP and of CHAP with MD5; and the phases of
  RFC 1661 section 3.2.
- **`tests/embedded_probe.nv`**, a firmware program for a modem client, built
  for `--target=nrf52-qemu` and for `--target=nrf52840-dk --hci-uart=physical`.
  It prints `PASS: ppp-embedded` under QEMU and asks the arena for no bytes.
  The image for `nrf52-qemu` is 41,960 bytes of flash and 520 bytes of static
  RAM.
- Nine test suites, with vectors worked out by hand and a framer
  (`tests/vectors.py`) that shares nothing with the package, the full table
  of RFC 1661 section 4.1, the suite of RFC 1321 section A.5, and the
  LCP exchange of a pppd debug log; `tests/coverage.sh`, which reports 100%
  line coverage of `src/`.

### Not included

- Multilink (RFC 1990), compression (CCP, RFC 1962) and encryption (ECP, RFC
  1968). Their frames are answered with a Protocol-Reject.
- Van Jacobson header compression, MS-CHAP, MS-CHAPv2 and EAP.
- Authenticating the peer, and the server side of PAP and CHAP.
- Link quality monitoring, the callback and FCS-alternatives options, the
  NetBIOS options of RFC 1877, and the Restart option of RFC 1661.
- Passive open, bit-synchronous HDLC, PPP over Ethernet and L2TP, the dial, and
  an IP stack.

### Known

- `pppsess` spells the element of its list of option lists out, `Vec[Vec[u8;
  64]; 3]`, where `Vec[PppOpts; 3]` would read better. An alias from another
  module inside the type arguments of `Vec` is not resolved by the
  compiler. The filing is
  `a-cross-module-alias-as-the-element-of-a-heapless-vec-is-not-resolved`.
- The session holds one reply at a time. A caller that does not take the frame
  it asked for before feeding the next byte loses the earlier reply, and
  `tx_lost` counts it.
