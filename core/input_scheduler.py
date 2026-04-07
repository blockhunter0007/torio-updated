import ctypes
import ctypes.wintypes as wt
import threading
import time
import queue
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Optional

MOUSEEVENTF_MOVE      = 0x0001
MOUSEEVENTF_LEFTDOWN  = 0x0002
MOUSEEVENTF_LEFTUP    = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP   = 0x0010
INPUT_MOUSE           = 0
MY_EXTRA              = 0xABCD1234
ULONG_PTR             = ctypes.c_uint64


class InputPriority(Enum):
    LOW         = 0
    NORMAL      = 1
    MEDIUM      = 2
    HIGH        = 3
    CRITICAL    = 4
    AIM         = 5


@dataclass
class MouseInput:
    flags: int
    dx: int = 0
    dy: int = 0
    priority: InputPriority = InputPriority.NORMAL
    timestamp: float = field(default_factory=time.perf_counter)
    callback: Optional[Callable] = None
    
    def __lt__(self, other):
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.timestamp < other.timestamp


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          wt.LONG),
        ("dy",          wt.LONG),
        ("mouseData",   wt.DWORD),
        ("dwFlags",     wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         wt.WORD),
        ("wScan",       wt.WORD),
        ("dwFlags",     wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wt.ULONG)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg",    wt.DWORD),
        ("wParamL", wt.WORD),
        ("wParamH", wt.WORD),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("union", _InputUnion)]


class DEVMODE(ctypes.Structure):
    pass

DEVMODE._fields_ = [
    ("dmDeviceName", ctypes.c_char * 32),
    ("dmSpecVersion", wt.WORD),
    ("dmDriverVersion", wt.WORD),
    ("dmSize", wt.WORD),
    ("dmDriverExtra", wt.WORD),
    ("dmFields", wt.DWORD),
    ("dmOrientation", wt.SHORT),
    ("dmPaperSize", wt.SHORT),
    ("dmPaperLength", wt.SHORT),
    ("dmPaperWidth", wt.SHORT),
    ("dmScale", wt.SHORT),
    ("dmCopies", wt.SHORT),
    ("dmDefaultSource", wt.SHORT),
    ("dmPrintQuality", wt.SHORT),
    ("dmColor", wt.SHORT),
    ("dmDuplex", wt.SHORT),
    ("dmYResolution", wt.SHORT),
    ("dmTTOption", wt.SHORT),
    ("dmCollate", wt.SHORT),
    ("dmFormName", ctypes.c_char * 32),
    ("dmLogPixels", wt.WORD),
    ("dmBitsPerPel", wt.DWORD),
    ("dmPelsWidth", wt.DWORD),
    ("dmPelsHeight", wt.DWORD),
    ("dmDisplayFlags", wt.DWORD),
    ("dmDisplayFrequency", wt.DWORD),
    ("dmICMMethod", wt.DWORD),
    ("dmICMIntent", wt.DWORD),
    ("dmMediaType", wt.DWORD),
    ("dmDitherType", wt.DWORD),
    ("dmReserved1", wt.DWORD),
    ("dmReserved2", wt.DWORD),
]


class VSyncDetector:
    def __init__(self):
        self._refresh_hz: Optional[float] = None
        self._vsync_period: Optional[float] = None
        self._detect_lock = threading.Lock()
    
    def detect(self) -> float:
        with self._detect_lock:
            if self._vsync_period is not None:
                return self._vsync_period
        
        try:
            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)
            devmode.dmDriverExtra = 0
            
            user32 = ctypes.WinDLL('user32.dll')
            user32.EnumDisplaySettingsW.restype = ctypes.c_bool
            user32.EnumDisplaySettingsW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.POINTER(DEVMODE)]
            
            if user32.EnumDisplaySettingsW(None, 4294967295, ctypes.byref(devmode)):
                refresh_hz = devmode.dmDisplayFrequency
                if 0 < refresh_hz <= 240:
                    self._refresh_hz = float(refresh_hz)
                    self._vsync_period = 1.0 / self._refresh_hz
                    with self._detect_lock:
                        return self._vsync_period
        except Exception as e:
            pass
        
        with self._detect_lock:
            if self._vsync_period is None:
                self._vsync_period = 1.0 / 60.0
            return self._vsync_period
    
    def get_vsync_period(self) -> float:
        if self._vsync_period is None:
            return self.detect()
        return self._vsync_period
    
    def get_refresh_hz(self) -> float:
        if self._refresh_hz is None:
            self.detect()
        return self._refresh_hz or 60.0


class InputScheduler:    
    def __init__(self, vsync_detector: Optional[VSyncDetector] = None):
        self._vsync = vsync_detector or VSyncDetector()
        self._input_queue = queue.PriorityQueue()
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active = False
        
        self._user32 = ctypes.WinDLL('user32.dll')
        
        self._lock = threading.Lock()
        self._last_send_time = 0.0
        self._send_count = 0
    
    def start(self):
        if self._active:
            return
        
        self._active = True
        self._stop_event.clear()
        
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except:
            pass
        
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="InputSchedulerWorker"
        )
        self._worker_thread.start()
    
    def stop(self):
        if not self._active:
            return
        
        self._active = False
        self._stop_event.set()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except:
            pass
    
    def queue_mouse_input(
        self,
        flags: int,
        dx: int = 0,
        dy: int = 0,
        priority: InputPriority = InputPriority.NORMAL,
        callback: Optional[Callable] = None,
    ):
        if not self._active:
            self._send_mouse_input_immediate(flags, dx, dy)
            if callback:
                callback()
            return
        
        cmd = MouseInput(
            flags=flags,
            dx=dx,
            dy=dy,
            priority=priority,
            callback=callback,
        )
        self._input_queue.put(cmd)
    
    def _worker_loop(self):
        try:
            vsync_period = self._vsync.get_vsync_period()
        except Exception:
            vsync_period = 1.0 / 60.0
        
        next_frame_time = time.perf_counter() + vsync_period
        
        while not self._stop_event.is_set():
            try:
                now = time.perf_counter()
                
                wait_time = next_frame_time - now
                if wait_time > 0.0001:
                    time.sleep(max(0, wait_time - 0.0005))
                    while time.perf_counter() < next_frame_time:
                        pass
                
                next_frame_time += vsync_period
                
                batch_inputs = []
                try:
                    for _ in range(10):
                        try:
                            cmd = self._input_queue.get_nowait()
                            batch_inputs.append(cmd)
                        except queue.Empty:
                            break
                except Exception:
                    pass
                
                for cmd in batch_inputs:
                    try:
                        self._send_mouse_input_immediate(cmd.flags, cmd.dx, cmd.dy)
                        if cmd.callback:
                            try:
                                cmd.callback()
                            except Exception:
                                pass
                    except Exception:
                        pass
                
                if batch_inputs:
                    with self._lock:
                        self._send_count += len(batch_inputs)
                        self._last_send_time = time.perf_counter()
            except Exception:
                time.sleep(0.01)
    
    def _send_mouse_input_immediate(self, flags: int, dx: int = 0, dy: int = 0):
        try:
            ii_ = _InputUnion()
            ii_.mi = MOUSEINPUT(dx, dy, 0, flags, 0, MY_EXTRA)
            x = INPUT(INPUT_MOUSE, ii_)
            self._user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))
        except Exception:
            pass
    
    def get_stats(self) -> dict:
        with self._lock:
            return {
                'vsync_hz': self._vsync.get_refresh_hz(),
                'vsync_period_ms': self._vsync.get_vsync_period() * 1000,
                'send_count': self._send_count,
                'is_active': self._active,
            }

_scheduler: Optional[InputScheduler] = None
_scheduler_lock = threading.Lock()


def get_shared_input_scheduler() -> InputScheduler:
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = InputScheduler()
                _scheduler.start()
    return _scheduler


def reset_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None