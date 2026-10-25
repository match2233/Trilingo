"""内嵌音频播放器 (pygame.mixer).

Windows 自带的 MCI mp3 解码在本机不可用 (open 直接报 277), 所以用 pygame ——
它自带 SDL_mixer, 能解 mp3, 且只有一个纯 wheel 依赖。

用法:
    p = AudioPlayer()
    p.open(r"C:\\path\\a.mp3"); p.toggle(); p.seek(30); p.stop()
    p.position() / p.duration() / p.is_playing()
"""
from __future__ import annotations

import pathlib

_READY = False


def _ensure_mixer():
    """只在第一次真正播放时初始化混音器 (启动时初始化会拖慢应用启动)."""
    global _READY
    if _READY:
        return True
    try:
        import pygame
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.music.set_volume(1.0)
        _READY = True
        return True
    except Exception:      # noqa: BLE001
        return False


class AudioPlayer:
    def __init__(self) -> None:
        self._path: str = ""
        self._base = 0.0      # 已经播过的秒数 (get_pos 只给"这次播放"的进度)
        self._paused = False
        self._playing = False
        self._avail = False
        self._error = ""

    # ------------------------------------------------------------ 接口
    @property
    def available(self) -> bool:
        """这台机器能不能放音频."""
        return _ensure_mixer()

    @property
    def error(self) -> str:
        return self._error

    @property
    def opened(self) -> bool:
        return bool(self._path)

    def open(self, path: str) -> bool:
        if not _ensure_mixer():
            self._error = "没有可用的音频设备"
            return False
        try:
            import pygame
            pygame.mixer.music.load(str(path))
            self._path = str(path)
            self._playing = False
            return True
        except Exception as exc:      # noqa: BLE001
            self._error = f"打不开音频：{exc}"
            self._path = ""
            return False

    def play(self) -> None:
        """从当前位置开始播 (不是从头)."""
        if not self._path:
            return
        import pygame
        try:
            pygame.mixer.music.play(start=self._base)
            self._playing = True
            self._paused = False
        except Exception:      # noqa: BLE001
            self._playing = False

    def pause(self) -> None:
        if not self._path:
            return
        import pygame
        self._base = self.position()
        pygame.mixer.music.pause()
        self._playing = False
        self._paused = True

    def resume(self) -> None:
        if not self._path:
            return
        import pygame
        pygame.mixer.music.unpause()
        self._playing = True
        self._paused = False

    def toggle(self) -> None:
        """播放 / 暂停 切换."""
        if not self._path:
            return
        if self._playing:
            self.pause()
        elif self._paused:
            self.resume()
        else:
            self.play()

    def stop(self) -> None:
        if not self._path:
            return
        import pygame
        pygame.mixer.music.stop()
        self._playing = False
        self._paused = False
        self._base = 0.0

    def seek(self, seconds: float) -> None:
        """跳到指定秒数 (pygame 只能"从某处重新开始播放", 所以要自己记偏移)."""
        if not self._path:
            return
        import pygame
        try:
            self._base = max(0.0, float(seconds))
            paused = self._paused
            pygame.mixer.music.play(start=self._base)
            if paused:
                pygame.mixer.music.pause()
            self._playing = not paused
        except Exception:      # noqa: BLE001
            pass

    def position(self) -> float:
        if not self._path:
            return 0.0
        import pygame
        try:
            if self._playing:
                pos = pygame.mixer.music.get_pos()
                if pos and pos > 0:
                    return self._base + pos / 1000.0
            return self._base
        except Exception:      # noqa: BLE001
            return self._base

    def duration(self) -> float:
        """pygame 不给时长, 这里用一个上限让进度条能画 (实际按播放进度走)."""
        return 0.0

    def is_playing(self) -> bool:
        if not self._path:
            return False
        import pygame
        try:
            return bool(pygame.mixer.music.get_busy())
        except Exception:      # noqa: BLE001
            return False

    def close(self) -> None:
        if self._path:
            try:
                import pygame
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:      # noqa: BLE001
                pass
        self._path = ""
        self._playing = False
