"""新标日测试: 答题页 + 整张试卷回顾.

三种交互 (对应三种大题):
  fill      一次性列出整大题的小题 -> 【显示答案】 -> 逐题标记对/错 (默认对)
  choice    一次一小题, 选项按钮; 答对 5 秒后自动下一题, 答错给【下一题】
  translate 一次一小题, 先看题目 -> 【显示答案】 -> 【对】【错】

中途可以退出, 位置与已判定的结果都会存下来; 做完后进入整张试卷回顾,
错题用红字标出。原卷没附答案的课 (第 24 课) 全部走"自评"路径。
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import tkinter as tk
from tkinter import messagebox

from .. import llm, minna
from . import theme
from .widgets import Card, FlatButton, ScrollFrame, center_window

# 对话型题干里说话人的标记: "A:" "B:" "Ａ：" —— 前面通常跟空格或句末标点
_SPEAKER = re.compile(r"(?<=[\s。、！？…」』）)])[ \t]*([A-DＡ-Ｄ][:：])")


def pretty_prompt(text: str) -> str:
    """把对话型题干按说话人分行.

    原卷把对话挤成一行, 例如 "A: キムさんは 会社員では ありませんか。
    B: はい、会社員＿＿。"。整行排下来又长又难读, 在第二个说话人前面
    断行会清楚很多。只在确实有两个以上说话人时才动, 普通句子原样返回。
    """
    if not text:
        return text
    hits = _SPEAKER.findall(text)
    if len(hits) < 1:
        return text
    out = _SPEAKER.sub(lambda m: "\n" + m.group(1), text.strip())
    return out

CORRECT_WAIT_MS = 5000      # 选择题答对后停留多久自动下一题



def item_image(it: dict, master, bg: str, max_w: int = 520,
               key: str = "image"):
    """题目配图 (导入时从 PDF 裁出来的). 没有就返回 None.

    图片路径相对 data/ 目录; 文件不在就当没有图, 不显示占位。
    """
    rel = (it or {}).get(key)
    if not rel:
        return None
    try:
        from pathlib import Path as _P
        from PIL import Image, ImageTk
        from ..config import APP_DIR
        path = _P(APP_DIR) / "data" / rel
        if not path.is_file():
            return None
        img = Image.open(path)
        if img.width > max_w:
            img = img.resize((max_w, int(img.height * max_w / img.width)),
                             Image.LANCZOS)
        tkimg = ImageTk.PhotoImage(img)
        lab = tk.Label(master, image=tkimg, bg=bg, bd=0)
        lab.image = tkimg          # 必须留引用, 否则会被 GC 掉变成空白
        return lab
    except Exception:      # noqa: BLE001
        return None

class MinnaTestFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self.les: dict | None = None
        self.sections: list[dict] = []
        self.results: dict[str, bool] = {}
        self.sec_i = 0
        self.item_i = 0
        self.started_at: dt.datetime | None = None      # 兼容旧字段, 不再用于计时
        self._base_seconds: int = 0                     # 之前累计的作答秒数
        self._session_start: dt.datetime | None = None  # 本次进入的时间点
        self._tick_id = None
        self._next_id = None
        self._timer_label: tk.Label | None = None
        self._mode = "test"        # test | paper
        self._build_shell()

    # ------------------------------------------------------------ 外框
    def _build_shell(self) -> None:
        self.head = tk.Frame(self, bg=theme.BG)
        self.head.pack(fill="x", padx=30, pady=(18, 4))
        self.back_btn = FlatButton(self.head, "← 返回", self._leave, bg=theme.BG,
                                   hover=theme.CARD, font=theme.f(11),
                                   padx=12, pady=7)
        self.back_btn.pack(side="left")
        self.title = tk.Label(self.head, text="", bg=theme.BG, fg=theme.TEXT,
                              font=theme.f(16, "bold"))
        self.title.pack(side="left", padx=14)
        self.sub = tk.Label(self.head, text="", bg=theme.BG, fg=theme.MUTED,
                            font=theme.f(10))
        self.sub.pack(side="left")
        self.timer = tk.Label(self.head, text="00:00", bg=theme.BG, fg=theme.PRIMARY,
                              font=theme.f(14, "bold"))
        self.timer.pack(side="right", padx=(10, 0))
        self.timer_cap = tk.Label(self.head, text="用时", bg=theme.BG, fg=theme.MUTED,
                                  font=theme.f(9))
        self.timer_cap.pack(side="right")

        # 题目选择: 可以跳着做, 不必按顺序
        self.pick_btn = FlatButton(self.head, "题目选择", self.open_picker,
                                   bg=theme.CARD, font=theme.f(11),
                                   padx=12, pady=6)
        self.pick_btn.pack(side="right", padx=(0, 12))

        # 听力播放条 (只有带音频的卷子才建, 平时 pack_forget)
        self.audio_bar = tk.Frame(self, bg=theme.CARD, highlightthickness=1,
                                  highlightbackground=theme.BORDER)
        self.audio_player = None
        self._audio_tick = None
        self._build_audio_bar()

        self.progress = tk.Frame(self, bg=theme.BORDER, height=4)
        self.progress.pack(fill="x", padx=30, pady=(2, 6))
        self.progress_bar = tk.Frame(self.progress, bg=theme.PRIMARY, height=4)
        self.progress_bar.place(x=0, y=0, relwidth=0.0, relheight=1)

        self.body = tk.Frame(self, bg=theme.BG)
        self.body.pack(fill="both", expand=True, padx=30, pady=(2, 0))

        # 底部操作条 (下一大题 / 下一题 / 交卷)
        self.foot = tk.Frame(self, bg=theme.BG)
        self.foot.pack(fill="x", padx=30, pady=(6, 16))
        self.foot_left = tk.Label(self.foot, text="", bg=theme.BG, fg=theme.MUTED,
                                  font=theme.f(9))
        self.foot_left.pack(side="left")
        self.foot_btn = FlatButton(self.foot, "下一题", self._next_section,
                                   bg=theme.PRIMARY, fg="#FFFFFF",
                                   hover=theme.PRIMARY_DARK,
                                   active_bg=theme.PRIMARY_DARK,
                                   font=theme.f(12, "bold"), padx=26, pady=10)
        # 初始不显示, 该出现时再 pack

        # 全部判定完才出现的【交卷】
        self.submit_btn = FlatButton(self.foot, "交卷", self._confirm_finish,
                                     bg=theme.SUCCESS, fg="#FFFFFF",
                                     hover="#1B8A4B", active_bg="#1B8A4B",
                                     border=theme.SUCCESS,
                                     font=theme.f(12, "bold"), padx=22, pady=10)

    # ------------------------------------------------------------ 听力播放器
    def _build_audio_bar(self) -> None:
        """听力题用的播放条: ▶/⏸ + 前后 10 秒 + 重头 + 进度."""
        bar = self.audio_bar
        self.audio_btn = FlatButton(bar, "▶ 播放", self._audio_toggle,
                                    bg=theme.PRIMARY, fg="#FFFFFF",
                                    hover=theme.PRIMARY_DARK,
                                    active_bg=theme.PRIMARY_DARK,
                                    font=theme.f(11, "bold"), padx=14, pady=5)
        self.audio_btn.pack(side="left", padx=(12, 6), pady=6)
        FlatButton(bar, "« 10 秒", lambda: self._audio_seek(-10),
                   bg=theme.BG, font=theme.f(10), padx=10, pady=5
                   ).pack(side="left", padx=3)
        FlatButton(bar, "10 秒 »", lambda: self._audio_seek(10),
                   bg=theme.BG, font=theme.f(10), padx=10, pady=5
                   ).pack(side="left", padx=3)
        FlatButton(bar, "重头", lambda: self._audio_seek(-99999),
                   bg=theme.BG, font=theme.f(10), padx=10, pady=5
                   ).pack(side="left", padx=3)
        self.audio_time = tk.Label(bar, text="00:00", bg=theme.CARD,
                                   fg=theme.MUTED, font=theme.f(10))
        self.audio_time.pack(side="right", padx=12)

    def _audio_load(self, rel: str | None) -> None:
        """卷子带 audio 字段时装载并显示播放条."""
        self.audio_bar.pack_forget()
        if self._audio_tick:
            self.after_cancel(self._audio_tick)
            self._audio_tick = None
        if not rel:
            return
        from pathlib import Path as _P

        from ..audio import AudioPlayer
        from ..config import APP_DIR
        path = _P(APP_DIR) / "data" / rel
        if not path.is_file():
            return
        if self.audio_player is None:
            self.audio_player = AudioPlayer()
        if not self.audio_player.open(str(path)):
            return
        self.audio_bar.pack(fill="x", padx=30, pady=(0, 6), before=self.progress)
        self.audio_btn.set_text("▶ 播放")
        self._audio_tick = self.after(500, self._audio_update)

    def _audio_toggle(self) -> None:
        if not self.audio_player or not self.audio_player.opened:
            return
        self.audio_player.toggle()
        self.audio_btn.set_text("⏸ 暂停" if self.audio_player.is_playing() else "▶ 播放")

    def _audio_seek(self, delta: int) -> None:
        if not self.audio_player or not self.audio_player.opened:
            return
        pos = self.audio_player.position() + delta
        self.audio_player.seek(max(0, pos))
        self._audio_update()

    def _audio_update(self) -> None:
        """每半秒刷一次进度; 播完自动变回"播放"."""
        if not self.audio_bar.winfo_ismapped() or not self.audio_player:
            self._audio_tick = None
            return
        pos = self.audio_player.position()
        self.audio_time.configure(text=minna.fmt_clock(int(pos)))
        playing = self.audio_player.is_playing()
        self.audio_btn.set_text("⏸ 暂停" if playing else "▶ 播放")
        self._audio_tick = self.after(500, self._audio_update)

    def _audio_stop(self) -> None:
        if self._audio_tick:
            self.after_cancel(self._audio_tick)
            self._audio_tick = None
        if self.audio_player:
            self.audio_player.stop()
            self.audio_player.close()

    # ------------------------------------------------------------ 题目选择
    def open_picker(self):
        """题目选择面板: 直接跳到任意一题 (不必按顺序做). 返回窗口方便测试."""
        if self._mode != "test":
            return None
        win = tk.Toplevel(self)
        win.title("题目选择")
        win.configure(bg=theme.BG)
        win.transient(self.winfo_toplevel())
        center_window(win, 720, 560)

        tk.Label(win, text="点题号直接跳过去", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10)).pack(anchor="w", padx=16, pady=(12, 4))

        sc = ScrollFrame(win)
        sc.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        body = sc.body

        answered = sum(1 for v in self.results.values() if v is not None)
        total = sum(len(s["items"]) for s in self.sections)
        tk.Label(win, text=f"已判定 {answered}/{total}", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10)).pack(side="left", padx=16, pady=(0, 10))
        FlatButton(win, "关闭", win.destroy, bg=theme.CARD, font=theme.f(11),
                   padx=16, pady=6).pack(side="right", padx=14, pady=(0, 8))

        # 按题型分组: 文字・語彙/文法、読解、聴解
        groups: dict[str, list[int]] = {}
        for si, sec in enumerate(self.sections):
            groups.setdefault(sec.get("group") or "文字・語彙・文法", []).append(si)

        for gname, sec_ids in groups.items():
            head = tk.Frame(body, bg=theme.BG)
            head.pack(fill="x", pady=(14, 4), padx=4)
            n_g = sum(len(self.sections[si]["items"]) for si in sec_ids)
            tk.Label(head, text=gname, bg=theme.BG, fg=theme.PRIMARY,
                     font=theme.f(13, "bold"), anchor="w").pack(side="left")
            tk.Label(head, text=f"  {n_g} 题", bg=theme.BG, fg=theme.MUTED,
                     font=theme.f(10)).pack(side="left")

            for si in sec_ids:
                sec = self.sections[si]
                tk.Label(body, text=f"{sec['no']}、{sec['title']}",
                         bg=theme.BG, fg=theme.TEXT, font=theme.f(10),
                         anchor="w").pack(fill="x", padx=8, pady=(4, 2))
                grid = tk.Frame(body, bg=theme.BG)
                grid.pack(fill="x", padx=8, pady=(0, 4))
                per = 12
                for i, it in enumerate(sec["items"]):
                    ok = self.results.get(it["id"])
                    if ok is True:
                        bg, fg = theme.SUCCESS_SOFT, theme.SUCCESS
                    elif ok is False:
                        bg, fg = theme.ERROR_SOFT, theme.ERROR
                    else:
                        bg, fg = theme.CARD, theme.MUTED
                    # 正方形格子 (固定 42x42): 之前用 FlatButton(width=44) 把
                    # 列撑爆, 一部分题号被挤出可视区, 看起来像"按钮消失"。
                    cell = tk.Frame(grid, width=42, height=42, bg=bg,
                                    highlightthickness=1,
                                    highlightbackground=theme.BORDER,
                                    cursor="hand2")
                    cell.grid(row=i // per, column=i % per, padx=2, pady=2)
                    cell.grid_propagate(False)
                    lbl = tk.Label(cell, text=str(i + 1), bg=bg, fg=fg,
                                   font=theme.f(11, "bold"))
                    lbl.place(relx=0.5, rely=0.5, anchor="center")
                    for w in (cell, lbl):
                        w.bind("<Button-1>",
                               lambda e, s=si, k=i: (self._jump(s, k), win.destroy()))
        return win

    def _jump(self, sec_i: int, item_i: int) -> None:
        if not 0 <= sec_i < len(self.sections):
            return
        self._clear_after()
        self.sec_i = sec_i
        self.item_i = item_i
        self.foot_btn.pack_forget()
        self._render_section()
        self._update_progress()

    def _confirm_finish(self) -> None:
        left = sum(len(s["items"]) for s in self.sections) - len(self.results)
        if left > 0 and not messagebox.askyesno(
                "交卷", f"还有 {left} 题没判定，现在交卷吗？", parent=self):
            return
        self._finish()

    # ------------------------------------------------------------ 生命周期
    def on_show(self, lesson: int | None = None, resume: bool = False,
                review: bool = False, **_):
        if lesson is None:
            return
        self._clear_after()
        les = minna.lesson(lesson)
        if les is None:
            messagebox.showerror("题库缺失",
                                 "找不到题库文件 data/minna_tests.json，"
                                 "请先运行 tools/build_minna_tests.py 生成。",
                                 parent=self)
            self.app.show("minna")
            return
        self.les = les
        self.limit_min = int(les.get("duration_min") or 0)
        self.sections = [s for s in les["sections"] if s.get("items")]
        self.lesson_no = lesson
        self.results = self.app.db.minna_results(lesson)
        self._mode = "paper" if review else "test"

        if review:
            self._show_paper()
            return

        prog = self.app.db.minna_progress(lesson)
        total = minna.total_items(les)
        self._reset_foot()
        if not resume or prog is None or prog["status"] != "doing":
            self.app.db.minna_start(lesson, total)
            self.results = {}
            self.sec_i = self.item_i = 0
            self._base_seconds = 0
        else:
            self.sec_i = min(int(prog["section"] or 0), len(self.sections) - 1)
            self.item_i = int(prog["idx"] or 0)
            self._base_seconds = int(prog["seconds"] or 0)
        self._session_start = dt.datetime.now()
        self.title.configure(text=f"第 {lesson} 课" if not les.get("title")
                             else str(les["title"]))
        self.timer_cap.configure(text="剩余" if self.limit_min else "用时")
        self._audio_load(les.get("audio"))
        self.timer.pack(side="right", padx=(10, 0))
        self._tick()
        self._render_section()

    def cancel_timers(self) -> None:
        self._clear_after()

    def _clear_after(self) -> None:
        for attr in ("_tick_id", "_next_id"):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:      # noqa: BLE001
                    pass
                setattr(self, attr, None)

    # ------------------------------------------------------------ 计时
    def elapsed(self) -> int:
        """本次 + 之前累计的作答秒数.

        以前直接用 "当前时间 − 首次打开时间", 于是中途退出隔天再进来,
        计时会从几小时甚至几天开始 (实际见过一进去就 27 分钟)。
        现在只累计"真正在做"的时间: 恢复时把上次存下的秒数当基数。
        """
        if not self._session_start:
            return int(self._base_seconds)
        delta = (dt.datetime.now() - self._session_start).total_seconds()
        return max(0, int(self._base_seconds + delta))

    def limit_seconds(self) -> int:
        """这份卷子的限时(秒). 0 = 不限时 (练习模式)."""
        if not self.limit_min:
            return 0
        return int(self.limit_min) * 60

    def remaining(self) -> int:
        """倒计时剩余秒数 (不限时返回 -1)."""
        limit = self.limit_seconds()
        if not limit:
            return -1
        return max(0, limit - self.elapsed())

    def _tick(self) -> None:
        if self._mode != "test":
            return
        limit = self.limit_seconds()
        if limit:
            left = self.remaining()
            self.timer.configure(text=minna.fmt_clock(left),
                                 fg=theme.ERROR if left <= 300 else theme.PRIMARY)
            if left <= 0:
                self._time_up()
                return
        else:
            self.timer.configure(text=minna.fmt_clock(self.elapsed()))
        self._tick_id = self.after(1000, self._tick)

    def _time_up(self) -> None:
        """时间到: 按已作答的交卷, 剩下的题算错."""
        self._clear_after()
        messagebox.showinfo("时间到", "这套卷子的时间用完了，按已作答的交卷。",
                            parent=self)
        self.foot_btn.pack_forget()
        self._finish()

    def _update_progress(self) -> None:
        total = sum(len(s["items"]) for s in self.sections) or 1
        done = len(self.results)
        self.progress_bar.place(relwidth=min(1.0, done / total))
        self.sub.configure(text=f"{done}/{total} 已判定")
        self._sync_submit()

    def _sync_submit(self) -> None:
        """全部判定完才把【交卷】摆出来 (试卷回顾模式不显示)."""
        total = sum(len(s["items"]) for s in self.sections)
        if self._mode == "test" and total and len(self.results) >= total:
            if not self.submit_btn.winfo_ismapped():
                self.submit_btn.pack(side="right", padx=(8, 0))
        else:
            self.submit_btn.pack_forget()

    # ------------------------------------------------------------ 渲染分发
    def _clear_body(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        self._reset_foot()
        self.foot_left.configure(text="")

    def _center_card(self) -> Card:
        """正文区垂直居中放一张卡片 (内容少时用)."""
        tk.Frame(self.body, bg=theme.BG).pack(expand=True)
        card = Card(self.body)
        card.pack(fill="x")
        tk.Frame(self.body, bg=theme.BG).pack(expand=True)
        return card

    def _fill_card(self) -> tuple[Card, tk.Frame]:
        """铺满正文区的卡片, 内部内容垂直居中.

        卡片占满整屏而不是浮在中间, 视觉上更"整"; 内容依旧居中,
        不会全挤在顶部。
        """
        card = Card(self.body)
        card.pack(fill="both", expand=True)
        # 顶部留一点点, 内容靠上排; 剩余空间留在下面 (比上下均分更像正常页面)
        tk.Frame(card, bg=theme.CARD, height=34).pack(fill="x")
        inner = tk.Frame(card, bg=theme.CARD)
        inner.pack(fill="x", padx=24)
        tk.Frame(card, bg=theme.CARD).pack(expand=True)
        return card, inner

    def _reset_foot(self) -> None:
        """清掉底栏左侧提示以外的按钮, 避免上一个状态残留."""
        for w in self.foot.winfo_children():
            if w is not self.foot_left:
                w.pack_forget()
        if not self.foot_left.winfo_ismapped():
            self.foot_left.pack(side="left")

    def _current(self) -> dict | None:
        if 0 <= self.sec_i < len(self.sections):
            return self.sections[self.sec_i]
        return None

    def _render_section(self) -> None:
        self._clear_body()
        sec = self._current()
        if sec is None:
            self._finish()
            return
        self._update_progress()
        if sec["kind"] == "choice":
            self._render_choice(sec)
        elif sec["kind"] == "translate":
            self._render_translate(sec)
        else:
            self._render_fill(sec)

    # ---------------------------------------------------------- 填空整大题
    def _render_fill(self, sec: dict) -> None:
        items = sec["items"]
        n = len(items)
        card = Card(self.body)
        card.pack(fill="both", expand=True)

        top = tk.Frame(card, bg=theme.CARD)
        top.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(top, text=f"{sec['no']}、{sec['title']}", bg=theme.CARD,
                 fg=theme.TEXT, font=theme.f(15, "bold")).pack(side="left")
        tk.Label(top, text=f"{n} 小题", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(11)).pack(side="left", padx=10)
        self.ask_btn = FlatButton(top, "显示答案", self._reveal_fill,
                                  bg=theme.BLUE, fg="#FFFFFF", hover=theme.BLUE_DARK,
                                  active_bg=theme.BLUE_DARK, border=theme.BLUE,
                                  font=theme.f(11, "bold"), padx=16, pady=6)
        self.ask_btn.pack(side="right")

        # 每行最多 5 小题: 10 题就是整齐的两行, 不会挤成一排小字。
        # 行块用 expand 铺满卡片剩余高度, 内容在里面垂直居中 —— 既用满了
        # 窗口, 又不会因为留白显得空荡。
        per_row = 5 if n > 5 else n
        rows = (n + per_row - 1) // per_row
        # 注意: 这里读 winfo_width 可能还是 1 (尚未布局), 所以先用一个保守值,
        # 布局完成后在 _fix_fill_wrap 里按真实宽度重算一次, 否则长一点的假名
        # 会被折成两行 (きょうじゅ -> きょうじ / ゅ)
        wrap = self._fill_wrap_for(per_row)

        self._fill_grid = tk.Frame(card, bg=theme.CARD)
        self._fill_grid.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._fill_ans_labels = []
        self._fill_toggle_btns = []
        self._fill_toggles = {}
        self._fill_units: list[tk.Frame] = []      # 每个小题的"竖条"(小题+答案+按钮)
        self._fill_wraplabels: list[tk.Label] = []

        for r in range(rows):
            band = tk.Frame(self._fill_grid, bg=theme.SUNK,
                            highlightthickness=1,
                            highlightbackground=theme.BORDER)
            band.pack(fill="both", expand=True, pady=(0, 6))
            tk.Frame(band, bg=theme.SUNK).pack(expand=True)
            inner = tk.Frame(band, bg=theme.SUNK)
            inner.pack(fill="x", padx=10, pady=4)
            for c in range(per_row):
                idx = r * per_row + c
                col = tk.Frame(inner, bg=theme.SUNK)
                col.grid(row=0, column=c, sticky="nsew", padx=3)
                inner.grid_columnconfigure(c, weight=1, uniform="fillcol")
                if idx >= n:
                    continue
                it = items[idx]
                head = tk.Frame(col, bg=theme.SUNK)
                head.pack(anchor="center")
                tk.Label(head, text=str(idx + 1), bg=theme.SUNK, fg=theme.BLUE,
                         font=theme.f(11, "bold")).pack(side="left", padx=(0, 5))
                tk.Label(head, text=it["prompt"], bg=theme.SUNK, fg=theme.TEXT,
                         font=theme.f(15, "bold"), wraplength=wrap,
                         justify="left").pack(side="left")
                ans = tk.Label(col, text="", bg=theme.SUNK, fg=theme.BLUE,
                               font=theme.f(14, "bold"), wraplength=wrap,
                               justify="center", height=2)
                ans.pack(anchor="center", pady=(4, 0))
                self._fill_ans_labels.append(ans)
                self._fill_units.append(col)
                self._fill_wraplabels.append(ans)
            tk.Frame(band, bg=theme.SUNK).pack(expand=True)

        self._fill_per_row = per_row
        self.after_idle(self._fix_fill_wrap)
        self.foot_left.configure(
            text="点【显示答案】核对；再逐题点按钮标记答错的，默认为答对")

    def _fill_wrap_for(self, per_row: int) -> int:
        """按真实宽度算每个格子的换行宽度 (拿不到就保守给 200)."""
        avail = self.body.winfo_width()
        if avail < 400:
            avail = self.winfo_width()
        if avail < 400:
            avail = 1100
        return max(120, int((avail - 90) / max(per_row, 1)) - 20)

    def _fix_fill_wrap(self) -> None:
        per_row = getattr(self, "_fill_per_row", 0)
        if not per_row or not hasattr(self, "_fill_wraplabels"):
            return
        wrap = self._fill_wrap_for(per_row)
        for lab in self._fill_wraplabels:
            try:
                lab.configure(wraplength=wrap)
            except tk.TclError:
                pass

    def _reveal_fill(self) -> None:
        sec = self._current()
        if sec is None:
            return
        for it, lab in zip(sec["items"], self._fill_ans_labels):
            lab.configure(text=it.get("answer") or "（未提供答案）")
        for i, it in enumerate(sec["items"]):
            if i < len(self._fill_toggle_btns):
                continue
            var = tk.BooleanVar(value=True)
            self._fill_toggles[it["id"]] = var
            prev = self.results.get(it["id"])
            if prev is not None:
                var.set(bool(prev))
            b = FlatButton(self._fill_units[i], "对",
                           lambda k=it["id"]: self._toggle_fill(k),
                           bg=theme.SUCCESS_SOFT, fg=theme.SUCCESS,
                           hover=theme.SUCCESS_SOFT, active_bg=theme.SUCCESS_SOFT,
                           border=theme.SUCCESS, font=theme.f(11, "bold"),
                           padx=8, pady=4)
            b.pack(fill="x", pady=(6, 0))
            self._fill_toggle_btns.append(b)
            self.results[it["id"]] = var.get()
            self.app.db.minna_mark(self.lesson_no, it["id"], var.get())
            self._paint_toggle(it["id"])
        self.ask_btn.set_text("重新隐藏")
        self.ask_btn._command = self._hide_fill          # noqa: SLF001
        self._show_next_section_btn("下一大题")
        self._update_progress()

    def _hide_fill(self) -> None:
        for lab in self._fill_ans_labels:
            lab.configure(text="")
        for b in self._fill_toggle_btns:
            b.destroy()
        self._fill_toggle_btns.clear()
        self._fill_toggles.clear()
        self.ask_btn.set_text("显示答案")
        self.ask_btn._command = self._reveal_fill         # noqa: SLF001
        self.foot_btn.pack_forget()

    def _toggle_fill(self, qid: str) -> None:
        var = self._fill_toggles[qid]
        var.set(not var.get())
        self.results[qid] = var.get()
        self.app.db.minna_mark(self.lesson_no, qid, var.get())
        self._paint_toggle(qid)

    def _paint_toggle(self, qid: str) -> None:
        ok = self.results.get(qid, True)
        for i, it in enumerate(self._current()["items"]):
            if it["id"] == qid and i < len(self._fill_toggle_btns):
                b = self._fill_toggle_btns[i]
                b.set_text("对" if ok else "错")
                b.set_palette(theme.SUCCESS_SOFT if ok else theme.ERROR_SOFT,
                              fg=theme.SUCCESS if ok else theme.ERROR)

    # ---------------------------------------------------------- 选择题
    def _render_choice(self, sec: dict) -> None:
        items = sec["items"]
        idx = min(self.item_i, len(items) - 1)
        it = items[idx]
        known = minna.has_answer(it)

        card, inner = self._fill_card()

        head = tk.Frame(inner, bg=theme.CARD)
        head.pack(fill="x", pady=(0, 8))
        tk.Label(head, text=f"{sec['no']}、{sec['title']}", bg=theme.CARD,
                 fg=theme.BLUE, font=theme.f(11, "bold")).pack(side="left")
        tk.Label(head, text=f"第 {idx + 1} / {len(items)} 小题", bg=theme.CARD,
                 fg=theme.MUTED, font=theme.f(11)).pack(side="right")
        # 题干: 有原卷截图就显示截图 (保留下划线/加粗/标红), 否则显示文字
        shot = item_image(it, inner, theme.CARD, max_w=900, key="prompt_image")
        if shot is not None:
            shot.pack(anchor="w", pady=(0, 16))
        else:
            tk.Label(inner, text=pretty_prompt(it["prompt"]), bg=theme.CARD,
                     fg=theme.TEXT, font=theme.f(20, "bold"), wraplength=760,
                     justify="left").pack(anchor="w", pady=(0, 16))
        pic = item_image(it, inner, theme.CARD)
        if pic is not None:
            pic.pack(anchor="w", pady=(0, 12))

        opts = tk.Frame(inner, bg=theme.CARD)
        opts.pack(fill="x")
        self._opt_btns: list[FlatButton] = []
        for j, text in enumerate(it.get("options") or []):
            b = FlatButton(opts, f"{'①②③④'[j] if j < 4 else j + 1}   {text}",
                           lambda k=j + 1: self._pick_choice(k),
                           bg=theme.CARD, hover=theme.BLUE_SOFT,
                           active_bg=theme.BLUE_SOFT, fg=theme.TEXT_SOFT,
                           font=theme.f(14), padx=16, pady=10, anchor="w")
            b.pack(fill="x", pady=4)
            self._opt_btns.append(b)

        self._choice_hint = tk.Label(inner, text="", bg=theme.CARD, fg=theme.MUTED,
                                     font=theme.f(12, "bold"))
        self._choice_hint.pack(anchor="w", pady=(14, 0))
        self._choice_done = False
        if not known:
            # 原卷缺答案 -> 直接给自评
            self._choice_hint.configure(text="本题原卷未附答案，请自行判断：")
            self._show_self_judge(it)

    def _pick_choice(self, pick: int) -> None:
        if self._choice_done:
            return
        sec = self._current()
        it = sec["items"][min(self.item_i, len(sec["items"]) - 1)]
        want = it.get("answer")
        if not isinstance(want, int):
            return
        self._choice_done = True
        ok = pick == want
        self._record(it["id"], ok)
        for j, b in enumerate(self._opt_btns):
            b.set_palette(theme.SUCCESS_SOFT if j + 1 == want else theme.CARD,
                          fg=theme.SUCCESS if j + 1 == want else theme.MUTED)
        if ok:
            self._choice_hint.configure(
                text=f"✅ 正确。{CORRECT_WAIT_MS // 1000} 秒后自动进入下一题…",
                fg=theme.SUCCESS)
            self._next_id = self.after(CORRECT_WAIT_MS, self._advance_choice)
        else:
            self._opt_btns[pick - 1].set_palette(theme.ERROR_SOFT, fg=theme.ERROR)
            self._choice_hint.configure(
                text=f"❌ 答错了，正确答案是 {'①②③④'[want - 1] if want <= 4 else want}"
                     f"  {it['options'][want - 1]}", fg=theme.ERROR)
            self._show_next_btn("下一题", self._advance_choice)

    def _advance_choice(self) -> None:
        self._clear_after()
        sec = self._current()
        self.item_i += 1
        if self.item_i >= len(sec["items"]):
            self._goto_next_section()
        else:
            self._render_section()

    # ---------------------------------------------------------- 翻译题
    def _render_translate(self, sec: dict) -> None:
        items = sec["items"]
        idx = min(self.item_i, len(items) - 1)
        it = items[idx]
        known = minna.has_answer(it)

        card, inner = self._fill_card()

        head = tk.Frame(inner, bg=theme.CARD)
        head.pack(fill="x", pady=(0, 8))
        tk.Label(head, text=f"{sec['no']}、{sec['title']}", bg=theme.CARD,
                 fg=theme.BLUE, font=theme.f(11, "bold")).pack(side="left")
        tk.Label(head, text=f"第 {idx + 1} / {len(items)} 小题", bg=theme.CARD,
                 fg=theme.MUTED, font=theme.f(11)).pack(side="right")
        tk.Label(inner, text=pretty_prompt(it["prompt"]), bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(20, "bold"), wraplength=780, justify="left").pack(
            anchor="w", pady=(0, 14))

        # 自己写译文 -> AI 判分 -> 给出参考答案
        tip = "译成日语" if "日语" in sec["title"] else "译成汉语"
        tk.Label(inner, text=f"请写出{tip}的译文：", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(11)).pack(anchor="w", pady=(0, 4))
        self._tr_input = tk.Text(inner, height=3, wrap="word", font=theme.f(14),
                                 bg=theme.SUNK, fg=theme.TEXT,
                                 relief="flat", padx=10, pady=8,
                                 highlightthickness=1,
                                 highlightbackground=theme.BORDER_STRONG,
                                 highlightcolor=theme.BLUE)
        self._tr_input.pack(fill="x", pady=(0, 10))
        self._tr_input.bind("<Control-Return>",
                            lambda e: (self._submit_translate(), "break")[1])
        self._tr_input.focus_set()

        row = tk.Frame(inner, bg=theme.CARD)
        row.pack(anchor="w")
        self._tr_btn = FlatButton(row, "提交（Ctrl+Enter）", self._submit_translate,
                                  bg=theme.BLUE, fg="#FFFFFF", hover=theme.BLUE_DARK,
                                  active_bg=theme.BLUE_DARK, border=theme.BLUE,
                                  font=theme.f(11, "bold"), padx=20, pady=8)
        self._tr_btn.pack(side="left")
        self._tr_skip = FlatButton(row, "不会，直接看答案", self._reveal_translate,
                                   bg=theme.CARD, font=theme.f(11),
                                   padx=16, pady=8)
        self._tr_skip.pack(side="left", padx=(10, 0))

        self._tr_ans = tk.Label(inner, text="", bg=theme.SUNK, fg=theme.BLUE,
                                font=theme.f(15, "bold"), wraplength=760,
                                justify="left", anchor="w", padx=12, pady=8)
        self._tr_judge = tk.Frame(inner, bg=theme.CARD)
        self._tr_judge.pack(anchor="w", pady=(10, 0))
        self._tr_hint = tk.Label(inner, text="", bg=theme.CARD, fg=theme.MUTED,
                                 font=theme.f(12, "bold"), wraplength=760,
                                 justify="left", anchor="w")
        self._tr_hint.pack(anchor="w", pady=(8, 0))
        self._tr_poll_id = None
        self._tr_prompt_text = it["prompt"]
        self._tr_ref = it.get("answer") or ""
        self._tr_to_jp = "日语" in sec["title"]
        if not known:
            self._tr_hint.configure(text="本题原卷未附答案，按自己的译文自评。")

    # ---------------------------------------------------------- 翻译: 判分
    def _submit_translate(self) -> None:
        if getattr(self, "_tr_busy", False) or self._mode != "test":
            return
        text = self._tr_input.get("1.0", "end").strip()
        if not text:
            self._tr_hint.configure(text="先写一句译文再提交，或点「直接看答案」。",
                                    fg=theme.MUTED)
            return
        if not llm.is_configured():
            self._tr_hint.configure(
                text="没有配置 AI，改为自己对照答案判分。", fg=theme.MUTED)
            self._reveal_translate()
            return
        self._tr_busy = True
        self._tr_user = text
        self._tr_btn.set_text("判分中…")
        self._tr_btn.set_enabled(False)
        self._tr_skip.set_enabled(False)
        self._tr_hint.configure(text="AI 正在判分…", fg=theme.MUTED)
        self._tr_input.configure(state="disabled")
        prompt, ref, to_jp = self._tr_prompt_text, self._tr_ref, self._tr_to_jp
        box: dict = {}

        def work():
            box["r"] = llm.judge_translation(prompt, text, ref, to_jp)

        threading.Thread(target=work, daemon=True).start()
        self._poll_judge(box, 0)

    def _poll_judge(self, box: dict, waited: int) -> None:
        if not self.winfo_exists() or self._mode != "test":
            return
        if "r" in box:
            self._on_judged(*box["r"])
            return
        if waited > 40000:                     # 40 秒还没回来就放弃
            self._on_judged(None, "AI 判分超时")
            return
        self._tr_poll_id = self.after(150, lambda: self._poll_judge(box, waited + 150))

    def _on_judged(self, ok, reason: str) -> None:
        self._tr_busy = False
        sec = self._current()
        it = sec["items"][min(self.item_i, len(sec["items"]) - 1)]
        self._tr_btn.pack_forget()
        self._tr_skip.pack_forget()
        self._show_reference()
        if ok is None:
            # AI 不可用 -> 退回自评, 答案照常给出
            self._tr_hint.configure(text=f"{reason}，请自己对照答案判断：",
                                    fg=theme.MUTED)
            for w in self._tr_judge.winfo_children():
                w.destroy()
            FlatButton(self._tr_judge, "对", lambda: self._judge(True),
                       bg=theme.SUCCESS_SOFT, fg=theme.SUCCESS,
                       hover=theme.SUCCESS_SOFT, active_bg=theme.SUCCESS_SOFT,
                       border=theme.SUCCESS, font=theme.f(12, "bold"),
                       padx=24, pady=8).pack(side="left")
            FlatButton(self._tr_judge, "错", lambda: self._judge(False),
                       bg=theme.ERROR_SOFT, fg=theme.ERROR, hover=theme.ERROR_SOFT,
                       active_bg=theme.ERROR_SOFT, border=theme.ERROR,
                       font=theme.f(12, "bold"), padx=24, pady=8).pack(
                side="left", padx=10)
            return
        self._record(it["id"], ok)
        mark = "✅ 判为正确" if ok else "❌ 判为错误"
        self._tr_hint.configure(
            text=f"{mark}　{reason}" if reason else mark,
            fg=theme.SUCCESS if ok else theme.ERROR)
        self._show_next_btn("下一题", self._advance_translate)
        self._update_progress()

    def _show_reference(self) -> None:
        self._tr_ans.configure(text=f"参考译文：{self._tr_ref or '（未提供答案）'}")
        if not self._tr_ans.winfo_ismapped():
            self._tr_ans.pack(fill="x", pady=(6, 10), before=self._tr_judge)

    def _reveal_translate(self) -> None:
        """不会做: 直接给参考答案, 自己判对错 (算答错更合理, 但仍给选择)."""
        sec = self._current()
        it = sec["items"][min(self.item_i, len(sec["items"]) - 1)]
        self._tr_ref = it.get("answer") or self._tr_ref
        self._tr_btn.pack_forget()
        self._tr_skip.pack_forget()
        self._tr_input.configure(state="disabled")
        self._show_reference()
        for w in self._tr_judge.winfo_children():
            w.destroy()
        FlatButton(self._tr_judge, "对", lambda: self._judge(True),
                   bg=theme.SUCCESS_SOFT, fg=theme.SUCCESS, hover=theme.SUCCESS_SOFT,
                   active_bg=theme.SUCCESS_SOFT, border=theme.SUCCESS,
                   font=theme.f(12, "bold"), padx=24, pady=8).pack(side="left")
        FlatButton(self._tr_judge, "错", lambda: self._judge(False),
                   bg=theme.ERROR_SOFT, fg=theme.ERROR, hover=theme.ERROR_SOFT,
                   active_bg=theme.ERROR_SOFT, border=theme.ERROR,
                   font=theme.f(12, "bold"), padx=24, pady=8).pack(side="left", padx=10)
        self._tr_hint.configure(text="对照答案自评：", fg=theme.MUTED)

    def _judge(self, ok: bool) -> None:
        sec = self._current()
        it = sec["items"][min(self.item_i, len(sec["items"]) - 1)]
        self._record(it["id"], ok)
        self._tr_hint.configure(text="✅ 记为答对" if ok else "❌ 记为答错",
                                fg=theme.SUCCESS if ok else theme.ERROR)
        self._show_next_btn("下一题", self._advance_translate)
        self._update_progress()

    def _advance_translate(self) -> None:
        self._clear_after()
        if getattr(self, "_tr_poll_id", None):
            try:
                self.after_cancel(self._tr_poll_id)
            except Exception:       # noqa: BLE001
                pass
            self._tr_poll_id = None
        self._tr_busy = False
        sec = self._current()
        self.item_i += 1
        if self.item_i >= len(sec["items"]):
            self._goto_next_section()
        else:
            self.foot_btn.pack_forget()
            self._render_section()

    # ---------------------------------------------------------- 自评 (无答案)
    def _show_self_judge(self, it: dict) -> None:
        box = tk.Frame(self.body.winfo_children()[-1], bg=theme.CARD)
        box.pack(anchor="w", padx=34, pady=(0, 20))
        FlatButton(box, "对", lambda: self._self_judge(it, True),
                   bg=theme.SUCCESS_SOFT, fg=theme.SUCCESS, hover=theme.SUCCESS_SOFT,
                   active_bg=theme.SUCCESS_SOFT, font=theme.f(12, "bold"),
                   padx=22, pady=8).pack(side="left")
        FlatButton(box, "错", lambda: self._self_judge(it, False),
                   bg=theme.ERROR_SOFT, fg=theme.ERROR, hover=theme.ERROR_SOFT,
                   active_bg=theme.ERROR_SOFT, font=theme.f(12, "bold"),
                   padx=22, pady=8).pack(side="left", padx=10)

    def _self_judge(self, it: dict, ok: bool) -> None:
        if self._choice_done:
            return
        self._choice_done = True
        self._record(it["id"], ok)
        self._choice_hint.configure(text="✅ 记为答对" if ok else "❌ 记为答错",
                                    fg=theme.SUCCESS if ok else theme.ERROR)
        self._show_next_btn("下一题", self._advance_choice)

    # ---------------------------------------------------------- 流转
    def _record(self, qid: str, ok: bool) -> None:
        self.results[qid] = ok
        self.app.db.minna_mark(self.lesson_no, qid, ok)
        self._update_progress()

    def _show_next_btn(self, text: str, cmd) -> None:
        self.foot_btn.set_text(text)
        self.foot_btn._command = cmd          # noqa: SLF001
        if not self.foot_btn.winfo_ismapped():
            self.foot_btn.pack(side="right")

    def _show_next_section_btn(self, text: str) -> None:
        self._show_next_btn(text, self._next_section)

    def _next_section(self) -> None:
        self._save_cursor()
        self._goto_next_section()

    def _goto_next_section(self) -> None:
        self.foot_btn.pack_forget()
        self.sec_i += 1
        self.item_i = 0
        self._save_cursor()
        self._render_section()

    def _save_cursor(self) -> None:
        self.app.db.minna_save_cursor(self.lesson_no, self.sec_i, self.item_i,
                                      self.elapsed(), len([1 for v in self.results.values() if v]))

    # ---------------------------------------------------------- 收藏
    def _star(self, parent, it: dict, compact: bool = False) -> tk.Label:
        """题目右侧/左侧的 ☆ 按钮: 点一下收藏, 再点取消."""
        on = (self.lesson_no, it["id"]) in getattr(self, "_favs", set())
        lab = tk.Label(parent, text="★" if on else "☆", bg=theme.SUNK,
                       fg=theme.PRIMARY if on else theme.MUTED,
                       font=theme.f(13 if compact else 15, "bold"),
                       cursor="hand2")
        lab.bind("<Button-1>", lambda e, q=it["id"]: self._toggle_fav(q, lab))
        return lab

    def _toggle_fav(self, qid: str, lab: tk.Label) -> None:
        on = self.app.db.minna_fav_toggle(self.lesson_no, qid)
        if on:
            self._favs.add((self.lesson_no, qid))
        else:
            self._favs.discard((self.lesson_no, qid))
        lab.configure(text="★" if on else "☆",
                      fg=theme.PRIMARY if on else theme.MUTED)
        self.foot_left.configure(
            text=f"已收藏 {len(self._favs)} 题，可在「收藏夹」里写笔记" if on
            else "已取消收藏")

    # ---------------------------------------------------------- 交卷
    def _finish(self) -> None:
        self._audio_stop()
        self._clear_after()
        total = sum(len(s["items"]) for s in self.sections)
        score = sum(1 for v in self.results.values() if v)
        self.app.db.minna_finish(self.lesson_no, self.elapsed(), score, total)
        self._mode = "paper"
        self._show_paper(just_finished=True)

    # ---------------------------------------------------------- 试卷回顾
    def _show_paper(self, just_finished: bool = False) -> None:
        self._mode = "paper"
        self._clear_after()
        self._clear_body()
        les = self.les
        prog = self.app.db.minna_progress(self.lesson_no)
        total = minna.total_items(les)
        score = prog["score"] if prog else sum(1 for v in self.results.values() if v)
        done_total = prog["total"] if prog else total

        self.title.configure(text=f"第 {self.lesson_no} 课 · 试卷")
        self.sub.configure(text=f"{score}/{done_total} 题答对")
        self.timer.configure(text=minna.fmt_clock(prog["seconds"] if prog else 0))
        self.timer_cap.configure(text="用时")
        self.progress_bar.place(relwidth=score / max(done_total, 1))

        if just_finished:
            self.foot_left.configure(
                text="本课已完成，下面是整张试卷，滚轮上下翻看，错题已标红")
        else:
            self.foot_left.configure(text="已完成的课直接显示整张试卷，滚轮上下翻看")

        sc = ScrollFrame(self.body)
        sc.pack(fill="both", expand=True)
        width = max(self.body.winfo_width(), 600)
        self._favs = self.app.db.minna_fav_ids()

        for sec in self.sections:
            box = Card(sc.body)
            box.pack(fill="x", pady=(0, 7))
            head = tk.Frame(box, bg=theme.CARD)
            head.pack(fill="x", padx=14, pady=(8, 6))
            tk.Label(head, text=f"{sec['no']}、{sec['title']}", bg=theme.CARD,
                     fg=theme.TEXT, font=theme.f(12, "bold")).pack(side="left")
            tk.Label(head, text=minna.KIND_NAME.get(sec["kind"], ""), bg=theme.BLUE_SOFT,
                     fg=theme.BLUE, font=theme.f(9, "bold"), padx=6).pack(
                side="left", padx=8)

            body = tk.Frame(box, bg=theme.CARD)
            body.pack(fill="x", padx=14, pady=(0, 10))

            if sec["kind"] == "fill":
                # 填空短, 横着排成多列, 一屏能看完整大题
                cols = 4
                for c in range(cols):
                    body.grid_columnconfigure(c, weight=1, uniform="pp")
                for i, it in enumerate(sec["items"]):
                    ok = self.results.get(it["id"])
                    cell = tk.Frame(body, bg=theme.SUNK)
                    cell.grid(row=i // cols, column=i % cols, sticky="nsew",
                              padx=2, pady=2)
                    inner = tk.Frame(cell, bg=theme.SUNK)
                    inner.pack(fill="x", padx=8, pady=5)
                    self._star(inner, it, compact=True).pack(side="left", padx=(0, 4))
                    tk.Label(inner, text=f"{i + 1}.", bg=theme.SUNK,
                             fg=theme.MUTED, font=theme.f(10)).pack(side="left")
                    tk.Label(inner, text=it["prompt"], bg=theme.SUNK,
                             fg=theme.ERROR if ok is False else theme.TEXT,
                             font=theme.f(12, "bold")).pack(side="left", padx=(3, 0))
                    ans = it.get("answer") or "—"
                    tk.Label(inner, text=f"  {ans}", bg=theme.SUNK,
                             fg=theme.ERROR if ok is False else theme.BLUE,
                             font=theme.f(12, "bold")).pack(side="left")
            else:
                for i, it in enumerate(sec["items"]):
                    ok = self.results.get(it["id"])
                    bad = ok is False
                    line = tk.Frame(body, bg=theme.SUNK)
                    line.pack(fill="x", pady=1)

                    # 第一行: ☆ 序号 题干 ……… 正确项
                    head = tk.Frame(line, bg=theme.SUNK)
                    head.pack(fill="x", padx=8, pady=(4, 0))
                    self._star(head, it).pack(side="left", padx=(0, 4))
                    tk.Label(head, text=f"{i + 1}.", bg=theme.SUNK, fg=theme.MUTED,
                             font=theme.f(10), width=3, anchor="ne").pack(side="left")
                    ans = it.get("answer")
                    if sec["kind"] == "choice" and isinstance(ans, int):
                        tk.Label(head, text=f"({'①②③④'[ans - 1] if ans <= 4 else ans})",
                                 bg=theme.SUNK,
                                 fg=theme.ERROR if bad else theme.BLUE,
                                 font=theme.f(13, "bold")).pack(side="right", padx=(8, 0))
                    else:
                        tk.Label(head, text=ans or "—", bg=theme.SUNK,
                                 fg=theme.ERROR if bad else theme.BLUE,
                                 font=theme.f(12, "bold"),
                                 wraplength=int(width * 0.55), justify="right",
                                 anchor="e").pack(side="right", padx=(8, 0))
                    if bad:
                        tk.Label(head, text="✗", bg=theme.SUNK, fg=theme.ERROR,
                                 font=theme.f(11, "bold")).pack(side="right")
                    # 题干独占剩余宽度, 对话按说话人换行
                    tk.Label(head, text=pretty_prompt(it["prompt"]), bg=theme.SUNK,
                             fg=theme.ERROR if bad else theme.TEXT,
                             font=theme.f(12), wraplength=max(220, int(width * 0.55)),
                             justify="left", anchor="w").pack(
                        side="left", fill="x", expand=True)

                    # 第二行: 选项 (选择题才有)
                    if sec["kind"] == "choice":
                        opts = it.get("options") or []
                        opt_txt = "　".join(
                            f"{'①②③④'[j] if j < 4 else j + 1}{o}"
                            for j, o in enumerate(opts))
                        tk.Label(line, text=opt_txt, bg=theme.SUNK,
                                 fg=theme.MUTED, font=theme.f(11),
                                 wraplength=max(260, width - 90), justify="left",
                                 anchor="w").pack(fill="x", padx=(38, 10), pady=(0, 4))
                    else:
                        tk.Frame(line, bg=theme.SUNK, height=4).pack()
        sc.scroll_to_top()

        # 底部: 返回列表 / 重做
        for w in self.foot.winfo_children():
            if w not in (self.foot_left,):
                w.pack_forget()
        FlatButton(self.foot, "返回列表", lambda: self.app.show("minna"),
                   bg=theme.CARD, font=theme.f(11), padx=18, pady=8).pack(side="right")
        FlatButton(self.foot, "收藏夹", lambda: self.app.show("minna_fav"),
                   bg=theme.CARD, font=theme.f(11), padx=18, pady=8).pack(
            side="right", padx=(0, 8))
        FlatButton(self.foot, "重做这一课", self._redo,
                   bg=theme.CARD, font=theme.f(11), padx=18, pady=8).pack(
            side="right", padx=(0, 8))
        self.foot_left.pack(side="left")

    def _redo(self) -> None:
        if not messagebox.askyesno("重做", "清空这一课的作答记录，重新开始？", parent=self):
            return
        self.app.db.minna_reset(self.lesson_no)
        self.results = {}
        self.app.show("minna_test", lesson=self.lesson_no, resume=False, review=False)

    # ---------------------------------------------------------- 退出
    def _leave(self) -> None:
        self._audio_stop()
        if self._mode == "test" and self.results:
            self._save_cursor()
            self.app.db.minna_save_cursor(
                self.lesson_no, self.sec_i, self.item_i, self.elapsed(),
                sum(1 for v in self.results.values() if v))
        self._clear_after()
        self.app.show("minna")


def _parse_dt(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s)
    except Exception:          # noqa: BLE001
        return None
