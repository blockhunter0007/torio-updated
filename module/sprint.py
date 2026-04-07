import pymem
import struct
import ctypes
from ctypes import wintypes
import re
import time
import threading
import queue
import keyboard

class SprintController:
    def __init__(self, pm: pymem.Pymem = None):
        self.pm = pm
        self.process_handle = pm.process_handle if pm else None
        self.update_queue = None
        self.should_stop = threading.Event()
        self.is_active = False
        self.is_sprinting = False
        self.initialized = False
        
        self.inject_addr = None
        self.inject_newmem = None
        self.inject_original_bytes = None
        self.inject_pattern = b'\x8B\x02\x0F\xBA\xE0\x0D'
        
        self.sprint_toggle_addr = None
        self.last_w_state_addr = None
        
        self.current_key = 'p'
        self.sprint_thread = None
        self.PAGE_EXECUTE_READWRITE = 0x40
        self.MEM_COMMIT = 0x1000
        self.MEM_RESERVE = 0x2000
        self.MEM_RELEASE = 0x8000
        self.page_size = 0x1000
        
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        
        self.VirtualAllocEx = self.kernel32.VirtualAllocEx
        self.VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
        self.VirtualAllocEx.restype = wintypes.LPVOID
        
        self.VirtualProtectEx = self.kernel32.VirtualProtectEx
        self.VirtualProtectEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.VirtualProtectEx.restype = wintypes.BOOL
        
        self.WriteProcessMemory = self.kernel32.WriteProcessMemory
        self.WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        self.WriteProcessMemory.restype = wintypes.BOOL
        
        self.VirtualFreeEx = self.kernel32.VirtualFreeEx
        self.VirtualFreeEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD]
        self.VirtualFreeEx.restype = wintypes.BOOL

    def set_update_queue(self, update_queue: queue.Queue):
        self.update_queue = update_queue

    def set_pymem_process(self, pm: pymem.Pymem):
        self.pm = pm
        self.process_handle = pm.process_handle

    def update_status(self, message, color):
        if self.update_queue:
            self.update_queue.put(('status_update', ('sprint', message, color)))

    def validate_process(self):
        try:
            if not self.pm or not self.process_handle:
                return False
            exit_code = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetExitCodeProcess(self.process_handle, ctypes.byref(exit_code)) == 0:
                return False
            return exit_code.value == 259
        except Exception:
            return False

    def validate_address(self):
        if not self.inject_addr or not self.initialized:
            return False
        if not self.validate_process():
            self.initialized = False
            self.inject_addr = None
            return False
        try:
            self.pm.read_bytes(self.inject_addr, 6)
            return True
        except Exception:
            self.initialized = False
            self.inject_addr = None
            return False

    def allocate_near(self, base_addr: int, size: int = 0x1000):
        start = base_addr & 0xFFFFFFFFFFFFF000
        offsets = [0]
        for i in range(1, 0x7FFFFF00 // 0x1000):
            offsets.append(i * 0x1000)
            offsets.append(-i * 0x1000)
        
        for offset in offsets:
            addr = start + offset
            if addr < 0x10000:
                continue
            mem = self.VirtualAllocEx(self.process_handle, ctypes.c_void_p(addr), size,
                                      self.MEM_COMMIT | self.MEM_RESERVE, self.PAGE_EXECUTE_READWRITE)
            if mem:
                return mem
        raise MemoryError("Could not allocate memory near target address")

    def find_sprint_addresses(self, retries=3, delay=1.0):
        if self.initialized and self.validate_address():
            return True
        
        if not self.validate_process():
            return False
        
        for attempt in range(retries):
            try:
                base_module = pymem.process.module_from_name(self.process_handle, "Minecraft.Windows.exe")
                if not base_module:
                    time.sleep(delay)
                    continue
                
                base_address = base_module.lpBaseOfDll
                module_size = base_module.SizeOfImage
                bytes_read = self.pm.read_bytes(base_address, module_size)
                
                pattern_matches = [m.start() for m in re.finditer(re.escape(self.inject_pattern), bytes_read)]
                
                if not pattern_matches:
                    time.sleep(delay)
                    continue
                
                self.inject_addr = base_address + pattern_matches[0]
                self.inject_original_bytes = self.pm.read_bytes(self.inject_addr, 6)
                
                self.inject_newmem = self.allocate_near(self.inject_addr, 0x1000)
                if not self.inject_newmem:
                    time.sleep(delay)
                    continue
                
                self.sprint_toggle_addr = self.inject_newmem + 0x100
                self.last_w_state_addr = self.inject_newmem + 0x104
                
                self.pm.write_int(self.sprint_toggle_addr, 0)
                self.pm.write_int(self.last_w_state_addr, 0)
                
                self.initialized = True
                print(f"Sprint: Initialized at 0x{self.inject_addr:X}")
                return True
                
            except Exception as e:
                time.sleep(delay)
        
        self.update_status("Pattern/Memory Init Failed", '#ff5252')
        return False

    def _write_sprint_patches(self):
        if not self.inject_addr:
            return False
        
        if not self.validate_address():
            return False
        
        try:
            if not self.inject_newmem:
                self.inject_newmem = self.allocate_near(self.inject_addr, 0x1000)
                if not self.inject_newmem:
                    return False
                
                self.sprint_toggle_addr = self.inject_newmem + 0x100
                self.last_w_state_addr = self.inject_newmem + 0x104
                
                self.pm.write_int(self.sprint_toggle_addr, 0)
                self.pm.write_int(self.last_w_state_addr, 0)
            
            code = bytearray()
            
            code += b'\x8B\x02'
            
            code += b'\x0F\xBA\xE0\x0D'

            code += b'\x73'
            w_not_pressed_offset_pos = len(code)
            code += b'\x00'
            
            code += b'\x83\x3D'
            last_w_state_rel = self.last_w_state_addr - (self.inject_newmem + len(code) + 6)
            code += struct.pack('<i', last_w_state_rel)
            code += b'\x00'
            
            code += b'\x75'
            check_sprint_offset_pos = len(code)
            code += b'\x00'
            
            code += b'\xC7\x05'
            sprint_toggle_rel = self.sprint_toggle_addr - (self.inject_newmem + len(code) + 10)
            code += struct.pack('<i', sprint_toggle_rel)
            code += b'\x01\x00\x00\x00'
            
            code += b'\xC7\x05'
            last_w_state_rel2 = self.last_w_state_addr - (self.inject_newmem + len(code) + 10)
            code += struct.pack('<i', last_w_state_rel2)
            code += b'\x01\x00\x00\x00'
            
            code += b'\xEB'
            check_sprint_offset_pos2 = len(code)
            code += b'\x00'
            
            w_not_pressed_label = len(code)

            code += b'\xC7\x05'
            last_w_state_rel3 = self.last_w_state_addr - (self.inject_newmem + len(code) + 10)
            code += struct.pack('<i', last_w_state_rel3)
            code += b'\x00\x00\x00\x00'
            
            code += b'\xC7\x05'
            sprint_toggle_rel2 = self.sprint_toggle_addr - (self.inject_newmem + len(code) + 10)
            code += struct.pack('<i', sprint_toggle_rel2)
            code += b'\x00\x00\x00\x00'
            
            code += b'\xEB'
            code_offset_pos = len(code)
            code += b'\x00'

            check_sprint_label = len(code)
            code += b'\x83\x3D'
            sprint_toggle_rel3 = self.sprint_toggle_addr - (self.inject_newmem + len(code) + 7)
            code += struct.pack('<i', sprint_toggle_rel3)
            code += b'\x01'
            
            code += b'\x75'
            code_offset_pos2 = len(code)
            code += b'\x00'
            
            code += b'\x50\x52'
            
            code += b'\x8B\x02'
            
            code += b'\x0F\xBA\xE8\x08'
            
            code += b'\x89\x02'
            
            code += b'\x5A\x58'
            
            code_label = len(code)
            code += b'\x8B\x02'
            
            code += b'\x0F\xBA\xE0\x0D'
            
            return_addr = self.inject_addr + 6
            jmp_offset = return_addr - (self.inject_newmem + len(code) + 5)
            code += b'\xE9'
            code += struct.pack('<i', jmp_offset)
            
            w_not_pressed_offset = w_not_pressed_label - (w_not_pressed_offset_pos + 1)
            code[w_not_pressed_offset_pos] = w_not_pressed_offset & 0xFF
            
            check_sprint_offset = check_sprint_label - (check_sprint_offset_pos + 1)
            code[check_sprint_offset_pos] = check_sprint_offset & 0xFF
            
            check_sprint_offset2 = check_sprint_label - (check_sprint_offset_pos2 + 1)
            code[check_sprint_offset_pos2] = check_sprint_offset2 & 0xFF
            
            code_offset = code_label - (code_offset_pos + 1)
            code[code_offset_pos] = code_offset & 0xFF
            
            code_offset2 = code_label - (code_offset_pos2 + 1)
            code[code_offset_pos2] = code_offset2 & 0xFF
            
            self.pm.write_bytes(self.inject_newmem, bytes(code), len(code))
            
            jmp_to_newmem = self.inject_newmem - (self.inject_addr + 5)
            jmp_code = b'\xE9' + struct.pack('<i', jmp_to_newmem) + b'\x90'
            
            old_protect = wintypes.DWORD()
            self.VirtualProtectEx(self.process_handle, ctypes.c_void_p(self.inject_addr), 6,
                                 self.PAGE_EXECUTE_READWRITE, ctypes.byref(old_protect))
            
            try:
                self.pm.write_bytes(self.inject_addr, jmp_code, len(jmp_code))
            except Exception:
                bytes_written = ctypes.c_size_t()
                self.WriteProcessMemory(self.process_handle, ctypes.c_void_p(self.inject_addr),
                                       jmp_code, len(jmp_code), ctypes.byref(bytes_written))
            
            self.VirtualProtectEx(self.process_handle, ctypes.c_void_p(self.inject_addr), 6,
                                 old_protect.value, ctypes.byref(old_protect))
            
            return True
            
        except Exception as e:
            self.update_status(f"Write Error: {e.__class__.__name__}", '#ff5252')
            return False

    def _write_anti_sprint_then_restore(self):
        if not self.inject_addr:
            return False
        
        if not self.validate_address():
            return False
        
        try:
            if not self.inject_newmem:
                self.inject_newmem = self.allocate_near(self.inject_addr, 0x1000)
                if not self.inject_newmem:
                    return False
            
            code = bytearray()
            
            code += b'\x8B\x02'
            
            code += b'\x0F\xBA\xF0\x08'
            
            code += b'\x89\x02'
            
            code += b'\x0F\xBA\xE0\x0D'
            
            return_addr = self.inject_addr + 6
            jmp_offset = return_addr - (self.inject_newmem + len(code) + 5)
            code += b'\xE9'
            code += struct.pack('<i', jmp_offset)
            
            self.pm.write_bytes(self.inject_newmem, bytes(code), len(code))
            
            jmp_to_newmem = self.inject_newmem - (self.inject_addr + 5)
            jmp_code = b'\xE9' + struct.pack('<i', jmp_to_newmem) + b'\x90'
            
            old_protect = wintypes.DWORD()
            self.VirtualProtectEx(self.process_handle, ctypes.c_void_p(self.inject_addr), 6,
                                 self.PAGE_EXECUTE_READWRITE, ctypes.byref(old_protect))
            
            try:
                self.pm.write_bytes(self.inject_addr, jmp_code, len(jmp_code))
            except Exception:
                bytes_written = ctypes.c_size_t()
                self.WriteProcessMemory(self.process_handle, ctypes.c_void_p(self.inject_addr),
                                       jmp_code, len(jmp_code), ctypes.byref(bytes_written))
            
            self.VirtualProtectEx(self.process_handle, ctypes.c_void_p(self.inject_addr), 6,
                                 old_protect.value, ctypes.byref(old_protect))
            
            time.sleep(0.05)
            
            return self._restore_original_bytes()
            
        except Exception as e:
            self.update_status(f"Anti-Sprint Error: {e.__class__.__name__}", '#ff5252')
            return False

    def _restore_original_bytes(self):
        try:
            if not self.inject_addr or not self.inject_original_bytes:
                return False
            
            old_protect = wintypes.DWORD()
            if not self.VirtualProtectEx(self.process_handle, ctypes.c_void_p(self.inject_addr), 6,
                                 self.PAGE_EXECUTE_READWRITE, ctypes.byref(old_protect)):
                return False
            
            try:
                self.pm.write_bytes(self.inject_addr, self.inject_original_bytes, len(self.inject_original_bytes))
            except Exception as e:
                bytes_written = ctypes.c_size_t()
                result = self.WriteProcessMemory(self.process_handle, ctypes.c_void_p(self.inject_addr),
                                       self.inject_original_bytes, len(self.inject_original_bytes),
                                       ctypes.byref(bytes_written))
                if not result:
                    return False
            
            self.VirtualProtectEx(self.process_handle, ctypes.c_void_p(self.inject_addr), 6,
                                 old_protect.value, ctypes.byref(old_protect))
            
            return True
            
        except Exception as e:
            return False

    def _cleanup_memory(self):
        try:
            if self.inject_newmem:
                self.VirtualFreeEx(self.process_handle, ctypes.c_void_p(self.inject_newmem), 0, self.MEM_RELEASE)
                self.inject_newmem = None
                self.sprint_toggle_addr = None
                self.last_w_state_addr = None
            return True
        except Exception as e:
            return False

    def sprint_loop(self):
        from config import ConfigManager
        config = ConfigManager("config.json")
        
        if self.update_queue:
            self.update_queue.put(('status_update', ('sprint', f"Not Sprinting ({self.current_key.upper()})", '#00e676')))
        
        rescan_delay = 5.0
        last_rescan_time = 0
        last_key_check = 0
        key_check_interval = 0.3
        
        while self.is_active and not self.should_stop.is_set():
            current_time = time.time()
            
            if current_time - last_key_check >= key_check_interval:
                try:
                    new_key = config.get_keybind("sprint") or "p"
                    if new_key != self.current_key:
                        old_key = self.current_key
                        self.current_key = new_key
                        if self.update_queue:
                            if self.is_sprinting:
                                self.update_queue.put(('status_update', ('sprint', f"Sprinting ({self.current_key.upper()})", '#00e676')))
                            else:
                                self.update_queue.put(('status_update', ('sprint', f"Not Sprinting ({self.current_key.upper()})", '#00e676')))
                except Exception as e:
                    pass
                last_key_check = current_time
            
            if not self.validate_address():
                if current_time - last_rescan_time >= rescan_delay:
                    if self.is_sprinting:
                        self.is_sprinting = False
                        if self.update_queue:
                            self.update_queue.put(('status_update', ('sprint', f"Not Sprinting ({self.current_key.upper()})", '#00e676')))
                    
                    if not self.initialize():
                        time.sleep(rescan_delay)
                    last_rescan_time = current_time
                continue
            
            try:
                if keyboard.is_pressed(self.current_key):
                    if not self.is_sprinting:
                        if self._write_sprint_patches():
                            self.is_sprinting = True
                            if self.update_queue:
                                self.update_queue.put(('status_update', ('sprint', f"Sprinting ({self.current_key.upper()})", '#00e676')))
                    else:
                        if self._write_anti_sprint_then_restore():
                            self.is_sprinting = False
                            if self.update_queue:
                                self.update_queue.put(('status_update', ('sprint', f"Not Sprinting ({self.current_key.upper()})", '#00e676')))
                    
                    while keyboard.is_pressed(self.current_key) and self.is_active:
                        time.sleep(0.05)
                
                time.sleep(0.05)
                
            except Exception as e:
                self.stop()
                break
        
        if self.is_sprinting:
            self._restore_original_bytes()
            self.is_sprinting = False
        
        self._cleanup_memory()
        
        if self.update_queue:
            self.update_queue.put(('status_update', ('sprint', "Inactive", '#b0b0b0')))

    def reset_to_default(self, is_app_closing=False):
        if not self.validate_process():
            self.is_active = False
            self.initialized = False
            self.inject_addr = None
            return True
        
        try:
            if self.is_sprinting:
                self._restore_original_bytes()
                self.is_sprinting = False
            
            if self.inject_addr and self.inject_original_bytes:
                old_protect = wintypes.DWORD()
                self.VirtualProtectEx(self.process_handle, ctypes.c_void_p(self.inject_addr), 6,
                                     self.PAGE_EXECUTE_READWRITE, ctypes.byref(old_protect))
                try:
                    self.pm.write_bytes(self.inject_addr, self.inject_original_bytes, len(self.inject_original_bytes))
                except Exception:
                    bytes_written = ctypes.c_size_t()
                    self.WriteProcessMemory(self.process_handle, ctypes.c_void_p(self.inject_addr),
                                           self.inject_original_bytes, len(self.inject_original_bytes),
                                           ctypes.byref(bytes_written))
                self.VirtualProtectEx(self.process_handle, ctypes.c_void_p(self.inject_addr), 6,
                                     old_protect.value, ctypes.byref(old_protect))
            
            self._cleanup_memory()
            
            self.inject_addr = None
            self.initialized = False
            
            self.update_status("Inactive", '#b0b0b0')
            return True
            
        except Exception as e:
            self.update_status(f"Reset Error: {e.__class__.__name__}", '#ff5252')
            return False

    def start(self):
        if not self.is_active:
            if not self.initialize():
                return False
            
            self.is_active = True
            self.should_stop.clear()
            self.sprint_thread = threading.Thread(target=self.sprint_loop, daemon=True)
            self.sprint_thread.start()
            return True
        return True

    def stop(self, is_app_closing=False):
        if self.is_active:
            self.is_active = False
            self.should_stop.set()
            
            if self.sprint_thread and self.sprint_thread.is_alive():
                try:
                    self.sprint_thread.join(timeout=1.5)
                except Exception as e:
                    pass
            
            self.sprint_thread = None
            
            if self.is_sprinting:
                self._restore_original_bytes()
                self.is_sprinting = False
            
            if is_app_closing:
                self.reset_to_default(is_app_closing=True)
        
        return True

    def toggle(self):
        if not self.is_active:
            return self.start()
        else:
            return self.stop()

    def initialize(self):
        return self.find_sprint_addresses()