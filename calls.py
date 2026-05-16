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
    trk: dict = field(default_factory=dict)


@dataclass
class Call:
    cid: str
    a: int
    b: int
    st: str = 'new'
    prs: dict = field(default_factory=dict)


class CallHub:
    @staticmethod
    def okinds(sdp):
        out = set()
        for ln in (sdp or '').splitlines():
            ln = ln.strip().lower()
            if ln.startswith('m=audio '):
                out.add('audio')
            elif ln.startswith('m=video '):
                out.add('video')
        return out or {'audio'}

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

    async def link(self, src, dst):
        if not src or not dst:
            return
        for k, trk in list(src.trk.items()):
            sndr = dst.snd.get(k)
            if not sndr or not trk:
                continue
            try:
                relt = self.rel.subscribe(trk) if self.rel else trk
                rep = sndr.replaceTrack(relt)
                if asyncio.iscoroutine(rep):
                    await rep
            except Exception:
                continue

    async def bridge(self, c):
        if not c:
            return
        pa = c.prs.get(int(c.a))
        pb = c.prs.get(int(c.b))
        if not pa or not pb:
            return
        await self.link(pa, pb)
        await self.link(pb, pa)

    async def aoffer(self, cid, uid, sdp, typ):
        c = self.get(cid)
        if not c:
            raise RuntimeError('call not found')
        uid = int(uid)
        p = c.prs.get(uid)
        if not p:
            p = await self.mkpeer(c, uid, self.okinds(sdp))
            c.prs[uid] = p

        off = RTCSessionDescription(sdp=sdp, type=typ)
        await p.pc.setRemoteDescription(off)
        
        ans = await p.pc.createAnswer()
        await p.pc.setLocalDescription(ans)
        
        return {'sdp': p.pc.localDescription.sdp, 'type': p.pc.localDescription.type}

    async def aice(self, cid, uid, ice):
        c = self.get(cid)
        if not c or c.st == 'end':
            return
        p = c.prs.get(int(uid))
        if not p:
            return
        cnd = (ice.get('candidate') or '').strip()
        if not cnd:
            return
        
        obj = self.cobj(cnd, ice.get('sdpMid'), ice.get('sdpMLineIndex'))
        if obj:
            try:
                await p.pc.addIceCandidate(obj)
            except Exception as e:
                pass

    def cobj(self, cnd, mid, idx):
        raw = cnd
        if raw.lower().startswith('candidate:'):
            raw = raw[len('candidate:'):]
        cand = candidate_from_sdp(raw)
        cand.sdpMid = mid
        if idx is not None:
            cand.sdpMLineIndex = int(idx)
        return cand

    async def mkpeer(self, c, uid, kinds=None):
        pc = RTCPeerConnection()
        snd = {}
        kinds = set(kinds or {'audio', 'video'})
        try:
            if 'audio' in kinds:
                ta = pc.addTransceiver('audio', direction='sendrecv')
                snd['audio'] = ta.sender
            if 'video' in kinds:
                tv = pc.addTransceiver('video', direction='sendrecv')
                snd['video'] = tv.sender
        except Exception:
            pass

        p = Peer(uid=uid, pc=pc, snd=snd)

        @pc.on('track')
        async def ontrk(trk):
            p.trk[trk.kind] = trk
            await self.bridge(c)

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
