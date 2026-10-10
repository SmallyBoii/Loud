"""Minimal WASAPI access over ctypes: endpoint lookup, loopback capture, exclusive-mode render.

Only what Loud needs. COM objects are driven through raw vtable calls so there is no
dependency beyond the standard library and numpy.
"""
import ctypes
import time
from ctypes import POINTER, byref, c_float, c_int, c_int64, c_uint, c_uint32, c_ulong, c_void_p
from ctypes import HRESULT, WINFUNCTYPE, Structure, wintypes

import numpy as np

ole32 = ctypes.windll.ole32
ole32.CoTaskMemFree.argtypes = [c_void_p]

CLSCTX_ALL = 23
E_RENDER, E_MULTIMEDIA = 0, 1
DEVICE_STATE_ACTIVE = 1
SHAREMODE_SHARED, SHAREMODE_EXCLUSIVE = 0, 1
STREAMFLAGS_LOOPBACK = 0x00020000
STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_PCM, WAVE_FORMAT_IEEE_FLOAT, WAVE_FORMAT_EXTENSIBLE = 1, 3, 0xFFFE

_HRESULT_MESSAGES = {
    0x88890002: "the audio device was invalidated (unplugged or changed)",
    0x88890004: "the audio device was invalidated (unplugged or changed)",
    0x88890008: "the device does not support the requested format",
    0x8889000A: "the headphone output is in use by another app that holds exclusive control",
    0x8889000E: ("exclusive mode is turned off for this device - enable 'Allow applications to take "
                 "exclusive control of this device' in Sound > device Properties > Advanced"),
    0x88890019: "buffer size not aligned",
}


class WasapiError(Exception):
    pass


def explain(err):
    code = (getattr(err, "winerror", None) or 0) & 0xFFFFFFFF
    return _HRESULT_MESSAGES.get(code, f"WASAPI error 0x{code:08X}")


class GUID(Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text=None):
        super().__init__()
        if text:
            ole32.CLSIDFromString(text, byref(self))


class PROPERTYKEY(Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(Structure):
    _fields_ = [("vt", wintypes.WORD), ("r1", wintypes.WORD), ("r2", wintypes.WORD), ("r3", wintypes.WORD),
                ("ptr", c_void_p), ("pad", c_void_p)]


class WAVEFORMATEXTENSIBLE(Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD), ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", wintypes.WORD),
                ("wBitsPerSample", wintypes.WORD), ("cbSize", wintypes.WORD),
                ("wValidBitsPerSample", wintypes.WORD), ("dwChannelMask", wintypes.DWORD),
                ("SubFormat", GUID)]


CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
IID_IAudioClient = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
IID_IAudioRenderClient = GUID("{F294ACFC-3146-4483-A7BF-ADDCA7C260E2}")
IID_IAudioCaptureClient = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
IID_IAudioEndpointVolume = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")
PKEY_FRIENDLY_NAME = PROPERTYKEY(GUID("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14)
SUBFORMAT_PCM = GUID("{00000001-0000-0010-8000-00AA00389B71}")
SUBFORMAT_FLOAT = GUID("{00000003-0000-0010-8000-00AA00389B71}")


def init_com():
    ole32.CoInitializeEx(None, 0)  # MTA; a repeat or mode mismatch is harmless here


class _Iface:
    """A raw COM interface pointer with vtable-slot binding."""

    def __init__(self, ptr):
        self.ptr = ptr if isinstance(ptr, c_void_p) else c_void_p(ptr)

    def _slot(self, index):
        vtbl = ctypes.cast(ctypes.cast(self.ptr, POINTER(c_void_p))[0], POINTER(c_void_p))
        return vtbl[index]

    def _m(self, index, *argtypes):
        fn = WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(self._slot(index))
        ptr = self.ptr
        return lambda *args: fn(ptr, *args)

    def release(self):
        if self.ptr and self.ptr.value:
            WINFUNCTYPE(c_ulong, c_void_p)(self._slot(2))(self.ptr)
            self.ptr = c_void_p(0)


class Device(_Iface):
    def id(self):
        out = c_void_p()
        self._m(5, POINTER(c_void_p))(byref(out))
        text = ctypes.wstring_at(out.value)
        ole32.CoTaskMemFree(out)
        return text

    def name(self):
        store = c_void_p()
        self._m(4, wintypes.DWORD, POINTER(c_void_p))(0, byref(store))
        prop = PROPVARIANT()
        _Iface(store)._m(5, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))(byref(PKEY_FRIENDLY_NAME), byref(prop))
        text = ctypes.wstring_at(prop.ptr) if prop.vt == 31 else "(unnamed device)"
        ole32.PropVariantClear(byref(prop))
        _Iface(store).release()
        return text

    def activate(self, iid):
        out = c_void_p()
        self._m(3, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p))(byref(iid), CLSCTX_ALL, None, byref(out))
        return out


class Enumerator(_Iface):
    @classmethod
    def create(cls):
        ptr = c_void_p()
        ole32.CoCreateInstance(byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                               byref(IID_IMMDeviceEnumerator), byref(ptr))
        return cls(ptr)

    def default_render_id(self):
        out = c_void_p()
        self._m(4, c_int, c_int, POINTER(c_void_p))(E_RENDER, E_MULTIMEDIA, byref(out))
        dev = Device(out)
        ident = dev.id()
        dev.release()
        return ident

    def device(self, endpoint_id):
        out = c_void_p()
        self._m(5, wintypes.LPCWSTR, POINTER(c_void_p))(endpoint_id, byref(out))
        return Device(out)

    def render_endpoints(self):
        coll = c_void_p()
        self._m(3, c_int, wintypes.DWORD, POINTER(c_void_p))(E_RENDER, DEVICE_STATE_ACTIVE, byref(coll))
        collection = _Iface(coll)
        count = c_uint()
        collection._m(3, POINTER(c_uint))(byref(count))
        found = []
        for i in range(count.value):
            item = c_void_p()
            collection._m(4, c_uint, POINTER(c_void_p))(i, byref(item))
            dev = Device(item)
            found.append((dev.id(), dev.name()))
            dev.release()
        collection.release()
        return found


def list_render_endpoints():
    """[(endpoint_id, friendly_name)] for every active playback device."""
    init_com()
    enum = Enumerator.create()
    try:
        return enum.render_endpoints()
    finally:
        enum.release()


def default_render_endpoint_id():
    init_com()
    enum = Enumerator.create()
    try:
        return enum.default_render_id()
    finally:
        enum.release()


def get_endpoint_volume(endpoint_id):
    """Windows master volume of an endpoint as 0..1, or None if it can't be read."""
    init_com()
    enum = Enumerator.create()
    try:
        dev = enum.device(endpoint_id)
        vol = _Iface(dev.activate(IID_IAudioEndpointVolume))
        level = c_float()
        vol._m(9, POINTER(c_float))(byref(level))
        vol.release()
        dev.release()
        return level.value
    except OSError:
        return None
    finally:
        enum.release()


def set_endpoint_volume(endpoint_id, level):
    init_com()
    enum = Enumerator.create()
    try:
        dev = enum.device(endpoint_id)
        vol = _Iface(dev.activate(IID_IAudioEndpointVolume))
        vol._m(7, c_float, c_void_p)(c_float(level), None)
        vol.release()
        dev.release()
    finally:
        enum.release()


IID_IAudioSessionManager2 = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
IID_IAudioSessionControl2 = GUID("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
SESSION_INACTIVE, SESSION_ACTIVE, SESSION_EXPIRED = 0, 1, 2


def process_name(pid):
    """Executable name for a process id, or '' if it can't be read."""
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = c_void_p
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(c_void_p(handle), 0, buf, byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        kernel32.CloseHandle(c_void_p(handle))


def audio_sessions(endpoint_id):
    """[(process_name, state)] for every app with an audio session on this playback device.

    state is SESSION_ACTIVE while the app is actually playing sound there."""
    init_com()
    enum = Enumerator.create()
    found = []
    try:
        dev = enum.device(endpoint_id)
        mgr = _Iface(dev.activate(IID_IAudioSessionManager2))
        listing = c_void_p()
        mgr._m(5, POINTER(c_void_p))(byref(listing))
        sessions = _Iface(listing)
        count = c_int()
        sessions._m(3, POINTER(c_int))(byref(count))
        for i in range(count.value):
            raw = c_void_p()
            sessions._m(4, c_int, POINTER(c_void_p))(i, byref(raw))
            control = _Iface(raw)
            raw2 = c_void_p()
            control._m(0, POINTER(GUID), POINTER(c_void_p))(byref(IID_IAudioSessionControl2), byref(raw2))
            control2 = _Iface(raw2)
            state, pid = c_int(), wintypes.DWORD()
            control2._m(3, POINTER(c_int))(byref(state))
            control2._m(14, POINTER(wintypes.DWORD))(byref(pid))
            found.append((process_name(pid.value) or f"pid {pid.value}", state.value))
            control2.release()
            control.release()
        sessions.release()
        mgr.release()
        dev.release()
    except OSError:
        pass
    finally:
        enum.release()
    return found


class _AudioClient(_Iface):
    def __init__(self, ptr):
        super().__init__(ptr)
        self.initialize = self._m(3, c_int, wintypes.DWORD, c_int64, c_int64, c_void_p, c_void_p)
        self.get_buffer_size = self._m(4, POINTER(c_uint32))
        self.get_padding = self._m(6, POINTER(c_uint32))
        self.is_format_supported = self._m(7, c_int, c_void_p, c_void_p)
        self.get_mix_format = self._m(8, POINTER(c_void_p))
        self.get_device_period = self._m(9, POINTER(c_int64), POINTER(c_int64))
        self.start = self._m(10)
        self.stop = self._m(11)
        self.get_service = self._m(14, POINTER(GUID), POINTER(c_void_p))

    def buffer_size(self):
        n = c_uint32()
        self.get_buffer_size(byref(n))
        return n.value

    def padding(self):
        n = c_uint32()
        self.get_padding(byref(n))
        return n.value


def _activate_client(enumerator, endpoint_id):
    dev = enumerator.device(endpoint_id)
    try:
        return _AudioClient(dev.activate(IID_IAudioClient))
    finally:
        dev.release()


def _make_format(rate, channels, container_bits, valid_bits, is_float=False):
    fmt = WAVEFORMATEXTENSIBLE()
    fmt.wFormatTag = WAVE_FORMAT_EXTENSIBLE
    fmt.nChannels = channels
    fmt.nSamplesPerSec = rate
    fmt.wBitsPerSample = container_bits
    fmt.nBlockAlign = channels * container_bits // 8
    fmt.nAvgBytesPerSec = rate * fmt.nBlockAlign
    fmt.cbSize = 22
    fmt.wValidBitsPerSample = valid_bits
    fmt.dwChannelMask = 0x3 if channels == 2 else 0
    fmt.SubFormat = SUBFORMAT_FLOAT if is_float else SUBFORMAT_PCM
    return fmt


# (container bits, valid bits) in order of preference for exclusive render
_EXCLUSIVE_FORMATS = [(32, 24), (32, 32), (16, 16)]


def exclusive_support(endpoint_id, rates=(44100, 48000, 96000, 192000)):
    """Which (rate, container, valid) combos the device accepts in exclusive mode."""
    init_com()
    enum = Enumerator.create()
    ok = []
    try:
        for rate in rates:
            for container, valid in _EXCLUSIVE_FORMATS:
                client = _activate_client(enum, endpoint_id)
                try:
                    client.is_format_supported(SHAREMODE_EXCLUSIVE, byref(_make_format(rate, 2, container, valid)), None)
                    ok.append((rate, container, valid))
                except OSError:
                    pass
                finally:
                    client.release()
    finally:
        enum.release()
    return ok


class LoopbackCapture:
    """Captures whatever Windows is playing to `endpoint_id` (shared-mode loopback), as float32 stereo."""

    def __init__(self, endpoint_id):
        init_com()
        self._enum = Enumerator.create()
        self._client = _activate_client(self._enum, endpoint_id)
        fmt_ptr = c_void_p()
        self._client.get_mix_format(byref(fmt_ptr))
        base = WAVEFORMATEXTENSIBLE.from_address(fmt_ptr.value)
        self.rate = base.nSamplesPerSec
        self.channels = base.nChannels
        self.block_align = base.nBlockAlign
        self.bits = base.wBitsPerSample
        tag = base.wFormatTag
        if tag == WAVE_FORMAT_EXTENSIBLE:
            tag = base.SubFormat.Data1
        self.is_float = tag == WAVE_FORMAT_IEEE_FLOAT
        try:
            self._client.initialize(SHAREMODE_SHARED, STREAMFLAGS_LOOPBACK, 1_000_000, 0, fmt_ptr, None)
        except OSError as e:
            raise WasapiError(f"could not start capture: {explain(e)}") from e
        finally:
            ole32.CoTaskMemFree(fmt_ptr)
        svc = c_void_p()
        self._client.get_service(byref(IID_IAudioCaptureClient), byref(svc))
        self._cap = _Iface(svc)
        self._next_packet = self._cap._m(5, POINTER(c_uint32))
        self._get_buffer = self._cap._m(3, POINTER(c_void_p), POINTER(c_uint32), POINTER(wintypes.DWORD),
                                        c_void_p, c_void_p)
        self._release_buffer = self._cap._m(4, c_uint32)
        self._client.start()

    def _decode(self, raw, frames):
        if self.is_float and self.bits == 32:
            data = np.frombuffer(raw, dtype="<f4")
        elif self.bits == 16:
            data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif self.bits == 32:
            data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        elif self.bits == 24:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            data = np.where(v & 0x800000, v - 0x1000000, v).astype(np.float32) / 8388608.0
        else:
            raise WasapiError(f"unsupported capture format: {self.bits}-bit")
        data = data.reshape(frames, self.channels)
        if self.channels == 1:
            data = np.repeat(data, 2, axis=1)
        return np.ascontiguousarray(data[:, :2], dtype=np.float32)

    def read(self):
        """All frames captured since the last call, as an (N, 2) float32 array (N may be 0)."""
        chunks = []
        while True:
            size = c_uint32()
            self._next_packet(byref(size))
            if size.value == 0:
                break
            data, frames, flags = c_void_p(), c_uint32(), wintypes.DWORD()
            self._get_buffer(byref(data), byref(frames), byref(flags), None, None)
            n = frames.value
            if flags.value & BUFFERFLAGS_SILENT or not data.value:
                chunks.append(np.zeros((n, 2), dtype=np.float32))
            else:
                chunks.append(self._decode(ctypes.string_at(data.value, n * self.block_align), n))
            self._release_buffer(n)
        if not chunks:
            return np.zeros((0, 2), dtype=np.float32)
        return chunks[0] if len(chunks) == 1 else np.concatenate(chunks)

    def close(self):
        try:
            self._client.stop()
        except OSError:
            pass
        self._cap.release()
        self._client.release()
        self._enum.release()


class _Render:
    """What both output modes share: an audio client, its render service, and buffer bookkeeping."""

    def __init__(self):
        init_com()
        self._enum = Enumerator.create()
        self._client = None

    def _finish_setup(self):
        svc = c_void_p()
        self._client.get_service(byref(IID_IAudioRenderClient), byref(svc))
        self._render = _Iface(svc)
        self._get_buffer = self._render._m(3, c_uint32, POINTER(c_void_p))
        self._release_buffer = self._render._m(4, c_uint32, wintypes.DWORD)
        self.buffer_frames = self._client.buffer_size()
        self.period_frames = max(1, round(self._period_hns * self.rate / 10_000_000))

    def _read_period(self):
        default, minimum = c_int64(), c_int64()
        self._client.get_device_period(byref(default), byref(minimum))
        self._period_hns = default.value

    def _close_client(self):
        if self._client is not None:
            self._client.release()
            self._client = None

    def prefill(self, frames):
        """Queue `frames` of silence and start the stream."""
        self._write_raw(frames, None)
        self._client.start()

    def _write_raw(self, frames, payload):
        data = c_void_p()
        self._get_buffer(frames, byref(data))
        if payload is None:
            self._release_buffer(frames, BUFFERFLAGS_SILENT)
        else:
            ctypes.memmove(data.value, payload, len(payload))
            self._release_buffer(frames, 0)

    def queued(self):
        return self._client.padding()

    def free(self):
        return self.buffer_frames - self._client.padding()

    def write(self, samples):
        frames = len(samples)
        if frames:
            self._write_raw(frames, self._encode(samples))

    def close(self):
        try:
            self._client.stop()
        except (OSError, AttributeError):
            pass
        if getattr(self, "_render", None) is not None:
            self._render.release()
        self._close_client()
        self._enum.release()


class SharedRender(_Render):
    """Plays into the normal Windows mixer, so other apps keep working alongside.

    Windows converts our float stream to the device's own rate and format, but the device's effects
    (Equalizer APO, Realtek processing, loudness equalization) still apply to it."""

    def __init__(self, endpoint_id, rate):
        super().__init__()
        self.rate = rate
        self._client = _activate_client(self._enum, endpoint_id)
        self._read_period()
        flags = STREAMFLAGS_AUTOCONVERTPCM | STREAMFLAGS_SRC_DEFAULT_QUALITY
        try:
            self._client.initialize(SHAREMODE_SHARED, flags, 1_000_000, 0,
                                    byref(_make_format(rate, 2, 32, 32, is_float=True)), None)
        except OSError as e:
            self._close_client()
            self._enum.release()
            raise WasapiError(f"could not open the headphone output: {explain(e)}") from e
        self._finish_setup()

    def describe(self):
        return f"shared mode, {self.rate} Hz"

    def _encode(self, samples):
        return np.clip(samples, -1.0, 1.0).astype("<f4").tobytes()


class ExclusiveRender(_Render):
    """Plays to an endpoint in exclusive mode, which bypasses the Windows audio engine and with it every
    effect (Equalizer APO, Realtek/Windows loudness and limiter processing). Other apps can't use the
    device while this is open."""

    def __init__(self, endpoint_id, rate):
        super().__init__()
        self.rate = rate
        last_error = None
        for container, valid in _EXCLUSIVE_FORMATS:
            try:
                self._open(endpoint_id, container, valid)
                break
            except OSError as e:
                last_error = e
                self._close_client()
        else:
            self._enum.release()
            raise WasapiError(f"could not open the headphone output in exclusive mode at {rate} Hz: "
                              f"{explain(last_error)}") from last_error
        self._finish_setup()

    def _open(self, endpoint_id, container, valid):
        rate = self.rate
        fmt = _make_format(rate, 2, container, valid)
        self.container, self.valid_bits = container, valid
        self._client = _activate_client(self._enum, endpoint_id)
        self._read_period()
        self._client.is_format_supported(SHAREMODE_EXCLUSIVE, byref(fmt), None)
        hns = self._period_hns * 4
        try:
            self._client.initialize(SHAREMODE_EXCLUSIVE, 0, hns, hns, byref(fmt), None)
        except OSError as e:
            if (e.winerror & 0xFFFFFFFF) != 0x88890019:
                raise
            # The driver wants a hardware-aligned buffer: ask it what size it would take, then retry.
            frames = self._client.buffer_size()
            self._close_client()
            self._client = _activate_client(self._enum, endpoint_id)
            hns = round(10_000_000 * frames / rate)
            self._client.initialize(SHAREMODE_EXCLUSIVE, 0, hns, hns, byref(fmt), None)

    def describe(self):
        return f"exclusive mode, {self.valid_bits}-bit, {self.rate} Hz (Windows effects bypassed)"

    def _encode(self, samples):
        x = np.clip(samples, -1.0, 1.0)
        if self.container == 16:
            return np.rint(x * 32767.0).astype("<i2").tobytes()
        if self.valid_bits == 24:
            return (np.rint(x * 8388607.0).astype("<i4") << 8).tobytes()
        return np.rint(x * 2147483647.0).astype("<i4").tobytes()
