import asyncio
import threading
import uuid
from dataclasses import dataclass, field

okrtc = True

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaRelay
from aiortc.sdp import candidate_from_sdp



@dataclass
class Peer:
    uid: int
    pc: object
    snd: dict = field(default_factory=dict)


@dataclass
class Call:
    cid: str
    a: int
    b: int
    st: str = 'new'
    prs: dict = field(default_factory=dict)


class CallHub:
    def init(self):
        self.lk = threading.Lock()
        self.mp = {}
        self.loop = asyncio.new_event_loop()
        self.rel = MediaRelay() if okrtc else None
        th = threading.Thread(target=self.run, daemon=True)
        th.start()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def make(self, a, b):
        with self.lk:
            for v in self.mp.values():
                if {v.a, v.b} == {a, b} and v.st != 'end':
                    return v
            cid = uuid.uuid4().hex[:16]
            c = Call(cid=cid, a=a, b=b, st='ring')
            self.mp[cid] = c
            return c

    def get(self, cid):
        with self.lk:
            return self.mp.get(cid)

    def mate(self, c, uid):
        return c.b if int(uid) == int(c.a) else c.a

    def can(self, cid, uid):
        c = self.get(cid)
        if not c:
            return False
        return int(uid) in {int(c.a), int(c.b)} and c.st != 'end'

    def acc(self, cid):
        c = self.get(cid)
        if c:
            c.st = 'talk'

    def rej(self, cid):
        c = self.get(cid)
        if c:
            c.st = 'end'
        self.end(cid)

    def end(self, cid):
        c = self.get(cid)
        if not c:
            return
        c.st = 'end'
        for p in list(c.prs.values()):
            fut = asyncio.run_coroutine_threadsafe(self.kpc(p.pc), self.loop)
            try:
                fut.result(timeout=10)
            except Exception:
                pass
        with self.lk:
            self.mp.pop(cid, None)

    async def kpc(self, pc):
        try:
            await pc.close()
        except Exception:
            pass

    def offer(self, cid, uid, sdp, typ):
        if not okrtc:
            raise RuntimeError('aiortc not installed')
        fut = asyncio.run_coroutine_threadsafe(self.aoffer(cid, uid, sdp, typ), self.loop)
        return fut.result(timeout=30)

    def iceadd(self, cid, uid, ice):
        if not okrtc:
            return
        fut = asyncio.run_coroutine_threadsafe(self.aice(cid, uid, ice), self.loop)
        fut.result(timeout=20)

    async def aoffer(self, cid, uid, sdp, typ):
        c = self.get(cid)
        if not c:
            raise RuntimeError('call not found')
        uid = int(uid)
        p = c.prs.get(uid)
        if not p:
            p = await self.mkpeer(c, uid)
            c.prs[uid] = p

        off = RTCSessionDescription(sdp=sdp, type=typ)
        await p.pc.setRemoteDescription(off)
        ans = await p.pc.createAnswer()
        await p.pc.setLocalDescription(ans)
        return {'sdp': p.pc.localDescription.sdp, 'type': p.pc.localDescription.type}

    async def aice(self, cid, uid, ice):
        c = self.get(cid)
        if not c:
            return
        p = c.prs.get(int(uid))
        if not p:
            return
        cnd = (ice.get('candidate') or '').strip()
        mid = ice.get('sdpMid')
        idx = ice.get('sdpMLineIndex')
        if not cnd:
            return
        obj = self.cobj(cnd, mid, idx)
        if obj:
            await p.pc.addIceCandidate(obj)

    def cobj(self, cnd, mid, idx):
        raw = cnd
        if raw.lower().startswith('candidate:'):
            raw = raw[len('candidate:'):]
        cand = candidate_from_sdp(raw)
        cand.sdpMid = mid
        if idx is not None:
            cand.sdpMLineIndex = int(idx)
        return cand

    async def mkpeer(self, c, uid):
        pc = RTCPeerConnection()
        snd = {}
        try:
            ta = pc.addTransceiver('audio', direction='sendrecv')
            tv = pc.addTransceiver('video', direction='sendrecv')
            snd['audio'] = ta.sender
            snd['video'] = tv.sender
        except Exception:
            pass

        p = Peer(uid=uid, pc=pc, snd=snd)

        @pc.on('track')
        async def ontrk(trk):
            oid = self.mate(c, uid)
            op = c.prs.get(int(oid))
            if not op:
                return
            sndr = op.snd.get(trk.kind)
            if not sndr:
                return
            try:
                relt = self.rel.subscribe(trk)
                rep = sndr.replaceTrack(relt)
                if asyncio.iscoroutine(rep):
                    await rep
            except Exception:
                return

        @pc.on('connectionstatechange')
        async def onst():
            st = pc.connectionState
            if st in {'failed', 'closed', 'disconnected'}:
                try:
                    await pc.close()
                except Exception:
                    pass

        return p


def mkhub():
    hub = CallHub()
    hub.init()
    return hub
