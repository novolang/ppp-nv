# ppp-nv

PPP, the Point-to-Point Protocol, is how a microcontroller talks IP through a
cellular module's serial port. The firmware dials with `ATD*99#`, the module
answers `CONNECT`, and from then on the UART carries PPP frames to the mobile
network: the two ends agree on the link, the network asks the device to prove
who it is, assigns it an IP address and the addresses of its DNS servers, and
the datagrams follow. This package is the client side of that conversation for
novo-lang: the framing of
[RFC 1662](https://www.rfc-editor.org/rfc/rfc1662), the Link Control Protocol
of [RFC 1661](https://www.rfc-editor.org/rfc/rfc1661), IPCP
([RFC 1332](https://www.rfc-editor.org/rfc/rfc1332) with the DNS options of
[RFC 1877](https://www.rfc-editor.org/rfc/rfc1877)), IPv6CP
([RFC 5072](https://www.rfc-editor.org/rfc/rfc5072)), and PAP
([RFC 1334](https://www.rfc-editor.org/rfc/rfc1334)) and CHAP with MD5
([RFC 1994](https://www.rfc-editor.org/rfc/rfc1994)) as the authentication the
client answers.

## What it is

The device program of a modem client is a loop. It reads a byte from the
module's UART, gives it to the session, writes the frames the session hands
back, and says how many milliseconds have passed. The session decides
everything else: which options to ask for, which of the network's options to
accept, how to answer a CHAP challenge, when to send a request again, and when
the IP address is known.

```novo norun:fragment
hal.uart.write("ATD*99#\r")
// ... read until the module says CONNECT ...
var s = pppsess.sess_new()
pppsess.sess_set_credentials(var s, "internet", "secret")
pppsess.sess_set_ip(var s, 0, true)        // ask for an address and the DNS servers
let _ = pppsess.sess_start(var s)
flush(var s)                                // write the Configure-Request
loop
    let b = hal.uart.try_read_byte()
    if b >= 0
        let ev = pppsess.sess_rx_byte(var s, b)
        if (ev & pppsess.PPP_EV_IPCP_UP) != 0
            // s.ip_local, s.dns1 and s.dns2 are known; hand them to the IP stack
        if (ev & pppsess.PPP_EV_IP_PACKET) != 0
            // the datagram is s.rx.buf
        if ev != 0
            flush(var s)
    else
        hal.timer.delay_ms(1)
        let _ = pppsess.sess_tick(var s, 1)
        flush(var s)
```

The package has no serial port, no clock and no IP stack. A program that uses
it owns the UART and the timer, and the datagrams are handed to it and taken
from it as bytes. **Nothing is allocated.** The session is a `@value` the
caller holds, a frame is a `Vec[u8; 3018]` and an information field a
`Vec[u8; 1504]`. The whole package builds for a Cortex-M with no heap, and
the self-test in `tests/embedded_probe.nv` asks the arena for no bytes.

**The session is a step.** `sess_rx_byte` takes a byte and answers a mask of
events. `sess_tick` takes the milliseconds since the last call. `sess_tx`
appends the next frame to send to a wire buffer and answers whether there was
one. Every layer is the automaton of RFC 1661 section 4 (`pppfsm`), driven
through the table of that section, so the retransmission, the give-up after
ten requests and the Terminate-Request after a close are the RFC's.

## Install

```
novo pkg add ppp-nv
```

## Example

A session is made, configured and started; its first frame is the LCP
Configure-Request. Then the network's Configure-Request, which asks for an MRU
of 1500 and carries the magic number 0x543, is framed and given to the session
a byte at a time. The session acknowledges it and waits in the Ack-Sent state
(8) for the network to acknowledge its own.

```novo
use pppframe
use pppsess

fn main() [io]
    var s = pppsess.sess_new()
    pppsess.sess_set_credentials(var s, "internet", "secret")
    pppsess.sess_set_magic(var s, 0xCF2759C0)
    pppsess.sess_set_ip(var s, 0, true)
    let _ = pppsess.sess_start(var s)

    var wire: pppframe.PppWire = Vec.new()
    let sent = pppsess.sess_tx(var s, var wire)
    println("${sent} ${wire.len()} ${s.phase}")   // true 37 1

    var req: pppframe.PppInfo = Vec.new()
    for b in [0x01, 0x01, 0x00, 0x0E, 0x01, 0x04, 0x05, 0xDC, 0x05, 0x06, 0x00, 0x00, 0x05, 0x43]
        let _ = req.push(b as u8)
    var from_peer: pppframe.PppWire = Vec.new()
    let _ = pppframe.frame_encode(pppframe.PPP_P_LCP, var req, pppframe.opts_default(), var from_peer)
    var ev = 0
    for i in 0..from_peer.len()
        ev = ev | pppsess.sess_rx_byte(var s, from_peer[i] as Int)
    println("${ev} ${s.fsm[0].state} ${s.peer_magic}")   // 0 8 1347
```

Build and test with `novo pkg build` and `novo test tests`.

## What the package contains

| Module | Contents |
| --- | --- |
| `pppsess` | The session: `sess_new`, the setters for the credentials, the magic number, the ACCM, the compression, the DNS and the IPv6 options, and `sess_start`, `sess_rx_byte`, `sess_tx`, `sess_tick`, `sess_send`, `sess_echo`, `sess_close` and `sess_lower_down`. It runs LCP, IPCP and IPv6CP, answers PAP and CHAP, and tells the caller what happened as `PPP_EV_` bits. |
| `pppfsm` | The option negotiation automaton of RFC 1661 section 4: ten states, sixteen events, thirteen actions, the restart counter and the restart timer. |
| `pppframe` | The HDLC-like frame of RFC 1662: `frame_encode`, with the escape by an ACCM, the compression of the address, control and protocol fields and the 32-bit FCS, and `PppRx`, which takes the frame a byte at a time. |
| `pppfcs` | The 16-bit and 32-bit FCS of RFC 1662 Appendix C, with their tables. |
| `pppcp` | The control packet of RFC 1661 section 5 (code, identifier, length, options) and the lists of options a layer asks for. |
| `pppmd5` | MD5, RFC 1321, as a streaming hash, because CHAP answers a challenge with it. |

Every `pub` declaration is documented where it is declared, and
[the package's page](https://novo-lang.org/packages/ppp-nv) is that
reference.

## The rules a user needs

1. **The caller moves the bytes.** Nothing here reads a port. The `CONNECT`
   line and every byte before the first flag are the caller's: the receiver
   counts bytes that are not a frame as a frame error (`PPP_EV_FRAME_ERROR`)
   and goes on.
2. **Drain `sess_tx` after every event.** The session holds one reply at a
   time, the answer to the last frame, and a set of packets it can build
   again: the Configure-Requests, the Terminate-Requests, the PAP request and
   the Echo-Request. After any call that answers a nonzero event, and after
   `sess_tick`, call `sess_tx` until it answers false. A reply built before
   the last was taken replaces it, and `tx_lost` counts that.
3. **Frame options follow LCP.** Until LCP opens, frames go out with every
   control character escaped, the full header and a 16-bit FCS. LCP packets
   that negotiate (codes 1 to 7) always go that way, as RFC 1661 section 5
   requires. When LCP opens, the ACCM, the compression and the MRU the peer
   asked for come into force, and the ACCM this end asked for is the one the
   receiver expects.
4. **This end authenticates; it does not ask the peer to.** If the network's
   Configure-Request holds an authentication option, the session accepts PAP
   or CHAP with algorithm 5 when it has a name, Naks any other protocol with
   CHAP-MD5, and Rejects the option when it has no name. A CHAP challenge is
   answered with MD5 over the identifier, the secret and the challenge. PAP is
   sent when LCP opens and every three seconds until it is answered or ten
   requests have gone unanswered.
5. **The network assigns the address.** IPCP asks for the address 0 (or the one
   given to `sess_set_ip`) and, if asked, for both DNS addresses of RFC 1877.
   The peer Naks with the values and the session asks again with them. The
   event `PPP_EV_IPCP_UP` says `ip_local`, `ip_peer`, `dns1` and `dns2` are
   known. IPv6CP is off until `sess_set_ipv6` turns it on, and negotiates the
   64-bit interface identifier.
6. **A peer that never agrees is given up on.** A request is sent again after
   three seconds, ten times, and then the layer finishes. A peer that Naks or
   Rejects ten times in a row is given up on as well. This end Naks a peer's
   options five times in a row and then Rejects them, so that two ends that
   disagree stop.
7. **Datagrams move only in the network phase.** `PPP_EV_IP_PACKET` and
   `PPP_EV_IPV6_PACKET` mean the datagram is in `s.rx.buf` until the next
   byte. `sess_send` frames a datagram with the options in force and answers
   false when its layer is not open, when the datagram is longer than the
   peer's MRU, or when it does not fit the wire buffer.
8. **A protocol this end does not run is rejected.** A frame of an unknown
   protocol on an open link is answered with an LCP Protocol-Reject, which is
   how the session declines compression (CCP, 0x80FD) and Multilink. An
   unknown LCP code is answered with a Code-Reject.
9. **The link ends with a Terminate-Request.** `sess_close` takes the network
   layers down and sends it; `PPP_EV_CLOSED` follows the peer's answer or the
   second timeout, after two Terminate-Requests, and the caller then hangs the
   call up. `sess_lower_down` is
   for a carrier that dropped (`NO CARRIER`).

## Running on a microcontroller

All six modules are `@tier(embedded)` throughout and allocate nothing, and the
package declares no effects. `tests/embedded_probe.nv` is a firmware program
for a modem client. It plays the network's side from the same package and runs
a whole link through the session: the LCP exchange with a request for CHAP,
the CHAP response, the IPCP exchange in which the network assigns the address
100.72.3.9 and two DNS servers, a datagram out and one in, the check values of
the FCS and of MD5, and a check that the arena was asked for no bytes. Then it
prints `PASS: ppp-embedded`, dials with `ATD*99#` and runs the link on the
UART. It is compiled for a Cortex-M as part of this package's checks, so the
claim is built rather than asserted. It builds for `nrf52-qemu`, where it
prints the verdict, and for `nrf52840-dk` with `--hci-uart=physical`.

The image for `nrf52-qemu` is 41,960 bytes of flash and 520 bytes of static
RAM, including the runtime and the board's startup code; the program's own
code is 25,898 bytes of that flash, of which 6,054 are tables (the two FCS
tables, the MD5 constants and the automaton). For `nrf52840-dk` it is 42,900
bytes of flash. The session is 4,024 bytes in the frame of the function that
holds it, of which the receiver is 1,584; a wire buffer is 3,032 bytes and
an information field 1,512.

The device effects are the caller's. The package reads no register and no
clock, so a call costs what its caller's transport costs.

## What is not included

- **Multilink PPP, RFC 1990,** and the Multilink protocol itself.
- **Compression and encryption,** CCP (RFC 1962) and ECP (RFC 1968). The
  session answers their frames with a Protocol-Reject, which tells the peer to
  stop offering them.
- **Van Jacobson header compression,** IPCP option 2. The option is rejected.
- **Authenticating the peer,** the server side of PAP and CHAP, and the
  authentication-protocol option in this end's own request.
- **MS-CHAP, MS-CHAPv2 and EAP.** A network that insists on one of them cannot
  be joined; the session Naks it with CHAP-MD5 and, if that is refused, the
  link is closed by the peer.
- **Link quality monitoring,** RFC 1989, and the callback and
  FCS-alternatives options of RFC 1570. The 32-bit FCS is a framing option
  (`PppFrameOpts.fcs32`, `rx_set_fcs32`); LCP does not negotiate it.
- **The NetBIOS name server options** of RFC 1877 (130 and 132), the old
  IP-Addresses option of RFC 1172, and the Restart option of RFC 1661.
- **Passive open.** The session always sends its own Configure-Request when it
  starts.
- **Bit-synchronous HDLC.** The frame is the asynchronous one, with octet
  stuffing.
- **PPP over Ethernet, over L2TP and over SSH,** and **the dial.** The `AT`
  commands are the caller's.
- **An IP stack,** and what to do with the addresses.

## Related packages

- [slip-nv](https://novo-lang.org/packages/slip-nv) is the framing for a link
  that needs nothing but IP packets.
- [cobs-nv](https://novo-lang.org/packages/cobs-nv) frames a stream with a
  fixed overhead, for a link that does not carry IP.

## Tests

The suite is nine files under `tests/`. What they assert comes from the RFCs,
and from a separate program that writes the frames, rather than from this
implementation.

`tests/pppfcs_tests.nv` holds both tables to the polynomials (every entry is
recomputed), to the catalogue's check values for "123456789" (0x906E and
0xCBF43926) and to the receipt check of RFC 1662 Appendix C.

`tests/pppframe_tests.nv` holds the frame to byte strings worked out by hand
and checked with a bit-at-a-time CRC, in every combination of the compression
and the FCS, the escapes, the abort, the faults a receiver reports and the
limits of both buffers; it ends by sending 300 generated frames under
generated options.

`tests/pppmd5_tests.nv` runs the suite of RFC 1321 section A.5, the lengths
around the padding boundary against the standard library's `crypto.md5`, and
recomputes the constants from the sine.

`tests/pppfsm_tests.nv` tries all 160 cells of the transition table of RFC 1661
section 4.1, typed from the RFC and not generated from the package's table,
and then the restart counter and timer: ten Configure-Requests and a give-up,
two Terminate-Requests, the interval and partial ticks.

`tests/pppcp_tests.nv` holds the control packet and the option lists,
including every way a length can lie.

`tests/pppsess_lcp_tests.nv` holds the rules of LCP in the session: every
verdict on every option, the five-Nak limit, the Nak and Reject of this end's
own request, retransmission, echo, termination, and the codes and protocols
the session does not run.

`tests/pppsess_net_tests.nv` holds PAP and its timer, CHAP, IPCP, IPv6CP and
the datagrams.

`tests/pppsess_link_tests.nv` is the whole link of a cellular client from
dial to hang-up, 17 steps in which every frame is a wire string written by
`tests/vectors.py`, a separate framer with no table. The first request and the
network's request in it are the ones in a pppd debug log posted to the lwIP
users list, <https://lists.nongnu.org/archive/html/lwip-users/2016-02/msg00096.html>:
`sent [LCP ConfReq id=0x1 <asyncmap 0x0> <magic 0xcf2759c0> <pcomp> <accomp>]`
and `rcvd [LCP ConfReq id=0x1 <accomp> <pcomp> <asyncmap 0x0> <mru 1500>
<magic 0x543> <auth 0xc223 05>]`. The log is a printed one: the frames are
derived from its option lists, not captured bytes, and the exchanges after LCP
are hand-derived.

`tests/embedded_probe.nv` is the microcontroller program described above.

`tests/coverage.sh` merges the line coverage of the suites over `src/` and
prints it; it reads 100%.

## Licence

Apache-2.0. See `LICENSE`.
