"""单词测验页 (英语 / 日语共用).

流程: 第一行显示中文意思 -> 第二行输入单词(回车提交)
      正确: 第三行显示音标(日语显示声调), 5 秒后自动进入下一个
      错误: 第三行显示正确拼写和音标, 右下角出现【下一个】按钮, 点击才继续
"""
from __future__ import annotations

import re
import tkinter as tk

from .. import config as C
from ..db import today
from . import theme
from .widgets import Card, FlatButton

DELAY_S = C.CORRECT_DELAY_MS // 1000

_KATA_TO_HIRA = {chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)}


def norm_en(s: str) -> str:
    """英文比对: 忽略大小写、空格与连字符."""
    return re.sub(r"[\s\-'’,.]+", "", (s or "").strip().lower())


def norm_jp(s: str) -> str:
    """日文比对: 片假名转平假名, 忽略空格/波浪号/顿号/大小写."""
    s = (s or "").strip()
    s = "".join(_KATA_TO_HIRA.get(ch, ch) for ch in s)
    s = re.sub(r"[\s　～~、，,。.・ー]+", "", s)
    return s.lower()


class QuizFrame(tk.Frame):
    def __init__(self, master, app, lang: str):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self.lang = lang
        self.queue: list = []
        self.index = 0
        self.current = None
        self.revealed = False
        self._timers: list[str] = []
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 8))

        FlatButton(head, "← 返回", lambda: self._go_back(), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7).pack(side="left")

        self.title_label = tk.Label(
            head, text="英语词汇" if self.lang == "en" else "日语词汇",
            bg=theme.BG, fg=theme.TEXT, font=theme.f(16, "bold"),
        )
        self.title_label.pack(side="left", padx=14)

        self.progress_label = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(11))
        self.progress_label.pack(side="right")

        # 进度条
        bar_bg = tk.Frame(self, bg=theme.BORDER, height=4)
        bar_bg.pack(fill="x", padx=30, pady=(0, 6))
        self.bar = tk.Frame(bar_bg, bg=theme.PRIMARY, height=4)
        self.bar.place(x=0, y=0, relwidth=0.0, relheight=1)
        self._bar_bg = bar_bg

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=30, pady=6)

        self.card = Card(body)
        self.card.pack(fill="both", expand=True)

        inner = tk.Frame(self.card, bg=theme.CARD)
        inner.pack(fill="both", expand=True, padx=44, pady=(30, 26))
        self._inner = inner

        self.badge = tk.Label(inner, text="", bg=theme.CARD, fg=theme.PRIMARY, font=theme.f(9))
        self.badge.pack(anchor="center")

        # 第一行: 中文意思
        self.meaning_label = tk.Label(
            inner, text="", bg=theme.CARD, fg=theme.TEXT,
            font=theme.f(27, "bold"), wraplength=760, justify="center",
        )
        self.meaning_label.pack(pady=(18, 34))

        # 第二行: 输入框
        entry_wrap = tk.Frame(inner, bg=theme.CARD)
        entry_wrap.pack()
        self.entry = tk.Entry(
            entry_wrap, font=theme.f(22), justify="center", width=22,
            relief="flat", bg="#F7F8FC", fg=theme.TEXT,
            highlightthickness=2, highlightbackground=theme.BORDER,
            highlightcolor=theme.PRIMARY, insertbackground=theme.PRIMARY,
        )
        self.entry.pack(ipady=10, ipadx=8)
        self.entry.bind("<Return>", lambda e: self.submit())

        self.hint_label = tk.Label(
            inner, text="输入单词后按回车", bg=theme.CARD, fg=theme.MUTED, font=theme.f(9)
        )
        self.hint_label.pack(pady=(10, 0))

        # 第三行: 结果 (音标 / 声调)
        self.result_frame = tk.Frame(inner, bg=theme.CARD)
        self.result_frame.pack(fill="x", pady=(26, 0))
        self.result_main = tk.Label(
            self.result_frame, text="", bg=theme.CARD, font=theme.f(15, "bold"), wraplength=760
        )
        self.result_main.pack()
        self.result_sub = tk.Label(
            self.result_frame, text="", bg=theme.CARD, font=theme.ipa(21), wraplength=760
        )
        self.result_sub.pack(pady=(8, 0))
        self.countdown_label = tk.Label(
            self.result_frame, text="", bg=theme.CARD, fg=theme.MUTED, font=theme.f(10)
        )
        self.countdown_label.pack(pady=(10, 0))

        # 右下角【下一个】
        self.next_wrap = tk.Frame(inner, bg=theme.CARD)
        self.next_wrap.pack(fill="x", side="bottom")
        self.next_btn = FlatButton(
            self.next_wrap, "下一个", self.next_word, bg=theme.PRIMARY, fg="#FFFFFF",
            hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
            font=theme.f(13, "bold"), padx=30, pady=12,
        )
        self.next_btn.pack(side="right")
        self.next_wrap.pack_forget()

    # ------------------------------------------------------------ 生命周期
    def cancel_timers(self) -> None:
        for t in self._timers:
            try:
                self.after_cancel(t)
            except Exception:
                pass
        self._timers.clear()

    def _after(self, ms: int, fn) -> None:
        self._timers.append(self.after(ms, fn))

    def on_show(self, reset: bool = False, **_):
        self.cancel_timers()
        if reset:
            self.app.db.reset_plan(self.lang)
        self.queue = [w for w in self.app.db.ensure_plan(self.lang) if not w["answered"]]
        self.index = 0
        self._render()

    def _go_back(self) -> None:
        self.cancel_timers()
        self.app.refresh_menu()
        self.app.show("menu")

    # ------------------------------------------------------------ 渲染
    def _render(self) -> None:
        self.cancel_timers()
        answered, total = self.app.db.today_status(self.lang)
        self.progress_label.configure(text=f"已答 {answered} / {total}")
        frac = (answered / total) if total else 0.0
        self.bar.place_configure(relwidth=min(1.0, frac))

        if self.index >= len(self.queue):
            self._render_done()
            return

        self.current = self.queue[self.index]
        self.revealed = False
        w = self.current

        self.card.pack(fill="both", expand=True)
        self.meaning_label.configure(text=w["meaning"] or "（缺中文释义，请在数据库中补充）")
        self.badge.configure(
            text="错题复习" if w["kind"] == "review" else "新词",
            fg=theme.PRIMARY if w["kind"] == "review" else theme.MUTED,
        )
        self.title_label.configure(
            text=f"{'英语' if self.lang=='en' else '日语'}词汇 · 第 {self.index + 1}/{len(self.queue)} 个"
        )

        self.result_main.configure(text="", fg=theme.TEXT)
        self.result_sub.configure(text="")
        self.countdown_label.configure(text="")
        self.next_wrap.pack_forget()
        self.entry.configure(state="normal", highlightbackground=theme.BORDER)
        self.entry.delete(0, tk.END)
        self.hint_label.configure(text="输入单词后按回车", fg=theme.MUTED)
        self.entry.focus_set()

    def _render_done(self) -> None:
        self.card.pack(fill="both", expand=True)
        self.badge.configure(text="")
        self.title_label.configure(text=f"{'英语' if self.lang=='en' else '日语'}词汇 · 今日完成")
        self.progress_label.configure(text="已全部完成")
        self.bar.place_configure(relwidth=1.0)
        self.meaning_label.configure(text="🎉  今日任务已完成", fg=theme.SUCCESS)
        self.entry.configure(state="disabled", highlightbackground=theme.BORDER)
        self.result_main.configure(text="", fg=theme.TEXT)
        self.result_sub.configure(text="")
        self.hint_label.configure(text="明天再来吧，错题会按 day+1/+3/+7/+15/+30 自动排期")

        answered, total = self.app.db.today_status(self.lang)
        log = self.app.db.conn.execute(
            "SELECT correct FROM daily_log WHERE day=? AND lang=?", (today(), self.lang)
        ).fetchone()
        acc = f"　正确率 {log['correct']}/{total}" if log and total else ""
        self.countdown_label.configure(text=f"完成 {answered}/{total}{acc}")
        self.next_wrap.pack_forget()
        self.next_btn.set_text("下一个")

    # ------------------------------------------------------------ 判题
    def submit(self) -> None:
        if self.revealed or self.current is None:
            return
        raw = self.entry.get().strip()
        if not raw:
            return
        w = self.current
        ok = self._check(raw, w)
        self.revealed = True
        self.entry.configure(state="disabled")

        self.app.db.mark_answered(self.lang, w["word_id"], ok)
        if ok:
            if w["kind"] == "review":
                self.app.db.record_review_pass(self.lang, w["word_id"])
        else:
            self.app.db.record_wrong(self.lang, w["word_id"], raw)

        self._show_result(ok, w)
        answered, total = self.app.db.today_status(self.lang)
        self.progress_label.configure(text=f"已答 {answered} / {total}")
        self.bar.place_configure(relwidth=min(1.0, (answered / total) if total else 0.0))

        if ok:
            # 正确: 5 秒后自动跳转到下一个单词
            self._countdown = DELAY_S
            self._tick()
        else:
            # 错误: 必须点击【下一个】
            self.next_wrap.pack(fill="x", side="bottom")
            self.next_btn.set_text("下一个 ›")

    def _check(self, raw: str, w) -> bool:
        if self.lang == "en":
            return norm_en(raw) == norm_en(w["word"])
        candidates = {norm_jp(w["word"])}
        for key in ("reading",):
            if w[key]:
                candidates.add(norm_jp(w[key]))
        # 复合读音 (げつ、か、…) 允许去掉顿号后连写
        if w["reading"]:
            candidates.add(norm_jp(re.sub(r"[、，]", "", w["reading"])))
        return norm_jp(raw) in candidates

    def _show_result(self, ok: bool, w) -> None:
        word = w["word"]
        if self.lang == "en":
            detail = w["ipa"] or "（缺音标）"
            detail_font = theme.ipa(22)
        else:
            acc = w["accent"] or "声调待补"
            detail = f"{acc}　{w['reading']}" if w["reading"] else acc
            detail_font = theme.jp(20)

        if ok:
            self.hint_label.configure(text="✓ 正确", fg=theme.SUCCESS)
            self.result_main.configure(text="拼写正确", fg=theme.SUCCESS)
            self.entry.configure(highlightbackground=theme.SUCCESS, highlightcolor=theme.SUCCESS)
        else:
            self.hint_label.configure(text="✗ 错误", fg=theme.ERROR)
            self.result_main.configure(
                text=f"正确拼写：{word}" + ("" if self.lang == "en" else f"　（{w['reading']}）" if w["reading"] else ""),
                fg=theme.ERROR,
            )
            self.entry.configure(highlightbackground=theme.ERROR, highlightcolor=theme.ERROR)
        self.result_sub.configure(text=detail, font=detail_font, fg=theme.TEXT)

    def _tick(self) -> None:
        if self._countdown <= 0:
            self.next_word()
            return
        self.countdown_label.configure(text=f"{self._countdown} 秒后进入下一个单词…")
        self._countdown -= 1
        self._after(1000, self._tick)

    def next_word(self) -> None:
        self.cancel_timers()
        self.index += 1
        self._render()
