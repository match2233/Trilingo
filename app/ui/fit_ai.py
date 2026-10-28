"""AI 建议页：周报 / 月报 / 半年报 + 历史报告.

每次生成都会存进 fit_report，历史里带日期和类型，点开可以回看。

数据口径：发给模型的是统计区间内的**全部原始记录** —— 每一条体重、
每一组力量训练（时间/动作/哑铃重量/每组次数）、每一次有氧，都不抽样、
不截断。周报只输出 150 字以内；月报和半年报则尽可能详细。
"""
from __future__ import annotations

import datetime as dt
import threading
import tkinter as tk

from .. import fit, llm
from . import theme
from .fit_dialogs import KIND_LABEL, ReportHistory
from .widgets import Card, FlatButton

PERIODS = {"week": ("周报", 7), "month": ("月报", 30), "half": ("半年报", 182)}

WEEK_LIMIT = 150


def _num(text) -> float | None:
    """把数据库里的 TEXT 数字转成 float；空值/非数字返回 None."""
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def _fmt_num(value: float) -> str:
    """48.0 -> '48'，12.5 -> '12.5'."""
    return f"{value:g}"


def _move_name(slug: str) -> str:
    return fit.MOVE_BY_SLUG.get(slug, {}).get("cn", slug)


def _stamp(at: str) -> str:
    """ISO 时间 -> '2026-10-28 12:30:49'（保留秒，动作时间要具体）."""
    if len(at) >= 19:
        return f"{at[:10]} {at[11:19]}"
    return at.replace("T", " ")


def _limit_week(text: str, limit: int = WEEK_LIMIT) -> str:
    """周报强制压到 limit 字以内：去标题/换行，超长优先在句末截断."""
    text = (text or "").strip()
    for mark in ("**", "##", "`"):
        text = text.replace(mark, "")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max((head.rfind(mark) for mark in
               ("。", "！", "？", "；", "!", "?", ";")), default=-1)
    if cut >= limit * 3 // 4:
        return head[:cut + 1]
    return head[:limit - 1].rstrip("，,、 ") + "…"


def _is_deepseek(cfg: dict) -> bool:
    """当前配置是不是 DeepSeek（官方或同名模型）."""
    model = str(cfg.get("model", "")).lower()
    base = str(cfg.get("base_url", "")).lower()
    return model.startswith("deepseek") or "deepseek" in base


def _system_prompt(key: str, label: str) -> str:
    """周报要短，月报/半年报要尽量详细 —— 两种提示词分开写."""
    if key == "week":
        return f"""你是私人健身教练，给用户写{label}。用户目标：增重增肌、长期坚持、每天不比前一天轻松。

只写**一段话**，**不超过 {WEEK_LIMIT} 个字（标点也算）**，不要标题、不要分点、不要换行、不要寒暄、不要复述原始数据。

内容必须包含：
1. 用 1~2 个最关键的数据判断这周练得够不够、体重/饮食是否达标；
2. 只挑最致命的 1 个问题；
3. 给出下周唯一重点，必须是能立刻执行的动作 + 组数×次数×重量，或每日热量/蛋白目标。

禁止"注意休息""均衡饮食"这类空话；没有数据就直说"本周没有记录"，不要编造。"""

    half = key == "half"
    plan = ("给出未来 4 周的具体安排，并按月份对比这半年的长期变化"
            if half else "给出未来 2 周的具体安排")
    floor = 1000 if half else 600
    return f"""你是私人健身教练，给用户写{label}。用户目标：增重增肌、长期坚持、每天不比前一天轻松。

这次要**尽可能详细**：篇幅不设上限，通常不少于 {floor} 字；宁可长而具体，不要短而空泛。每个判断都必须引用数据中的日期、动作、组数、次数、重量、体重或心率；数据里没有的不要编造，缺数据就写"数据不足"。

按下面结构输出（保留短标题）：
一、总体结论：这{label}练够了还是没练够、吃够了还是没吃够，用数据说明。
二、体重与饮食：期初→期末、变化速度、日/周波动、BMI 趋势；结合增重目标判断吃得够不够。
三、力量训练：**逐个动作**分析训练频率、组数、每组次数、重量变化、总容量和进步/停滞原因；明确指出哪个动作该加重量、哪个该加次数、哪个该减量或换动作。
四、有氧：次数、距离、时长、配速、心率，判断是否影响增肌恢复。
五、问题与风险：按严重程度列出，必须有数据支撑。
六、下一阶段计划：{plan}，逐动作写清组数×次数×重量；饮食给出每日热量/蛋白目标。

硬性要求：不要泛泛而谈"均衡饮食""注意休息"；不要只复述原始明细，要把明细归纳成趋势和结论，但保留关键数字。"""


class FitAiFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("fitness"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7
                   ).pack(side="left")
        tk.Label(head, text="AI建议", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.status = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                               font=theme.f(10))
        self.status.pack(side="left", padx=8)
        FlatButton(head, "历史报告", self._history, bg=theme.CARD,
                   font=theme.f(11), padx=16, pady=7).pack(side="right")

        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(fill="x", padx=30, pady=(6, 10))
        for key, (label, _days) in PERIODS.items():
            FlatButton(bar, label, lambda k=key: self._run(k), bg=theme.PRIMARY,
                       fg="#FFFFFF", hover=theme.PRIMARY_DARK,
                       active_bg=theme.PRIMARY_DARK, font=theme.f(12, "bold"),
                       padx=26, pady=10).pack(side="left", padx=(0, 10))
        self.last = tk.Label(bar, text="", bg=theme.BG, fg=theme.MUTED,
                             font=theme.f(10))
        self.last.pack(side="left", padx=8)

        card = Card(self)
        card.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        self.text = tk.Text(card, wrap="word", bg=theme.CARD, fg=theme.TEXT,
                            font=theme.f(12), bd=0, padx=22, pady=18,
                            relief="flat", highlightthickness=0)
        # 月报/半年报可以很长，必须有滚动条，否则看不到下半段。
        self.scroll = tk.Scrollbar(
            card, command=self.text.yview, width=12, bg=theme.CARD,
            troughcolor=theme.SUNK, activebackground=theme.BORDER,
            bd=0, relief="flat", highlightthickness=0)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y", pady=12)
        self.text.pack(side="left", fill="both", expand=True)
        self.text.configure(state="disabled")
        self._set_text("点上面的按钮生成报告。\n\n"
                       "会把统计区间内的全部原始记录发给 AI：体重每一次、"
                       "力量训练每一组（时间/动作/重量/次数）、有氧每一次，\n"
                       "不抽样也不截断。周报 150 字以内，月报和半年报尽量详细。")

    # ------------------------------------------------------------ 数据
    def _digest(self, days: int) -> str:
        """把统计区间内的全部原始记录整理成给模型的材料.

        原则：**不抽样、不截断**。体重每一条、力量训练每一组、有氧每一次
        都带时间戳发过去；再附按天/按动作/按项目的汇总，方便模型既看到
        细节，也能直接引用趋势。
        """
        db = self.app.db
        today = dt.date.today()
        start = today - dt.timedelta(days=days - 1)
        since, until = start.isoformat(), today.isoformat()

        who = []
        sex = str(fit.PROFILE.get("sex") or "").strip()
        sex = {"male": "男", "female": "女", "m": "男", "f": "女"}.get(
            sex.lower(), sex)
        if sex:
            who.append(sex)
        if fit.PROFILE.get("height_cm"):
            who.append(f"{fit.PROFILE['height_cm']}cm")
        age = fit.age_on()
        if age:
            who.append(f"{age} 岁")
        profile_txt = "、".join(who) if who else "未填性别身高年龄"

        lines = [
            f"统计区间：{since} 至 {until}（最近 {days} 天，含首尾）",
            f"用户：{profile_txt}，目标增重增肌、长期坚持、每天至少不比前一天轻松",
            "说明：下面是区间内全部原始记录，未抽样、未截断。",
            "",
        ]

        # ---------------------------------------------------------- 体重
        # 全部记录都列出来（时间精确到秒），再附日平均和趋势。
        ws = [(at, kg) for at, kg in db.fit_weight_all()
              if since <= at[:10] <= until]
        lines.append("【体重】")
        if ws:
            daily = fit.daily_mean(ws)
            first, last = daily[0][1], daily[-1][1]
            bmi = fit.bmi(last)
            lines.append(
                f"汇总：{len(ws)} 次记录 / {len(daily)} 个记录日；"
                f"期初（{daily[0][0]:%Y-%m-%d}）{_fmt_num(first)}kg → "
                f"期末（{daily[-1][0]:%Y-%m-%d}）{_fmt_num(last)}kg；"
                f"变化 {last - first:+.1f}kg；"
                f"趋势 {fit.trend_slope(daily):+.2f}kg/周"
                + (f"；期末 BMI {bmi}" if bmi else ""))
            lines.append("全部体重记录（时间 · 数值）：")
            for at, kg in ws:
                lines.append(f"  {_stamp(at)} · {_fmt_num(kg)}kg")
            lines.append("按天平均：" + "；".join(
                f"{d:%Y-%m-%d} {_fmt_num(v)}kg" for d, v in daily))
        else:
            lines.append(f"  {days} 天内没有体重记录")
        lines.append("")

        # ------------------------------------------------------ 力量训练
        # 逐组明细是核心：模型必须看到每一组的时刻、动作、重量、次数。
        logs = [r for r in db.fit_log_since(since) if r["day"] <= until]
        lines.append("【力量训练】")
        if logs:
            db_default = db.fit_setting("dumbbell", "")
            reps_default = {
                m["slug"]: db.fit_setting(f"reps:{m['slug']}", str(m["reps"]))
                for m in fit.MOVES
            }

            def weight_of(row: dict) -> str:
                return (row.get("dumbbell") or "").strip() or db_default

            def reps_of(row: dict) -> str:
                return (row.get("reps") or "").strip() or reps_default.get(
                    row["move"], "12")

            per_day: dict[str, list[dict]] = {}
            per_move: dict[str, list[dict]] = {}
            total_reps = 0.0
            total_volume = 0.0
            for r in logs:
                per_day.setdefault(r["day"], []).append(r)
                per_move.setdefault(r["move"], []).append(r)
                reps = _num(reps_of(r))
                weight = _num(weight_of(r))
                if reps:
                    total_reps += reps
                if reps and weight:
                    total_volume += reps * weight

            trained = len(per_day)
            last_day = max(per_day)
            gap_now = (today - dt.date.fromisoformat(last_day)).days
            lines.append(
                f"汇总：{trained} 天有打卡（{trained}/{days}）；"
                f"共 {len(logs)} 组 / {_fmt_num(total_reps)} 次 / "
                f"总容量 {_fmt_num(round(total_volume, 1))} kg·次；"
                f"最近一次 {last_day}（距今 {gap_now} 天）")
            marks = []
            for i in range(days):
                d = (start + dt.timedelta(days=i)).isoformat()
                marks.append("练" if d in per_day else "·")
            lines.append(f"逐日打卡：{''.join(marks)}（左旧右新）")
            lines.append("逐组全部明细（时间 · 动作 · 哑铃重量 · 每组次数）：")
            for r in logs:
                lines.append(
                    f"  {_stamp(r['at'])} · {_move_name(r['move'])} · "
                    f"{weight_of(r) or '—'}kg · {reps_of(r) or '—'}次")

            lines.append("按天汇总：")
            for day in sorted(per_day):
                rs = per_day[day]
                d_reps = sum(_num(reps_of(r)) or 0 for r in rs)
                d_vol = sum((_num(weight_of(r)) or 0) *
                            (_num(reps_of(r)) or 0) for r in rs)
                day_moves = "、".join(
                    _move_name(s) for s in dict.fromkeys(r["move"] for r in rs))
                lines.append(
                    f"  {day}：{len(rs)} 组 / {_fmt_num(d_reps)} 次 / "
                    f"{_fmt_num(round(d_vol, 1))} kg·次；动作：{day_moves}")

            lines.append("按动作汇总：")
            for slug, rs in sorted(
                    per_move.items(),
                    key=lambda kv: min(r["at"] for r in kv[1])):
                m_reps = sum(_num(reps_of(r)) or 0 for r in rs)
                m_vol = sum((_num(weight_of(r)) or 0) *
                            (_num(reps_of(r)) or 0) for r in rs)
                weights = sorted(
                    {weight_of(r) for r in rs if weight_of(r)},
                    key=lambda s: _num(s) or 0)
                reps_set = sorted(
                    {reps_of(r) for r in rs if reps_of(r)},
                    key=lambda s: _num(s) or 0)
                lines.append(
                    f"  {_move_name(slug)}：{len(rs)} 组 / "
                    f"{_fmt_num(m_reps)} 次 / {_fmt_num(round(m_vol, 1))} kg·次；"
                    f"{_stamp(min(r['at'] for r in rs))} 至 "
                    f"{_stamp(max(r['at'] for r in rs))}；"
                    f"重量 {'、'.join(weights) or '—'}kg；"
                    f"每组次数 {'、'.join(reps_set) or '—'}")
        else:
            lines.append(f"  {days} 天内一次都没练")
        lines.append("")

        # ---------------------------------------------------------- 有氧
        cardio = [c for c in db.fit_cardio_since(since) if c["day"] <= until]
        lines.append("【有氧】")
        if cardio:
            runs = [c for c in cardio if c["kind"] == "run"]
            bikes = [c for c in cardio if c["kind"] == "bike"]
            hr = [c["hr"] for c in runs if c["hr"]]
            rk = sum(c["km"] for c in runs)
            bk = sum(c["km"] for c in bikes)
            lines.append(
                f"汇总：跑步 {len(runs)} 次 {rk:.1f}km"
                + (f"（平均心率 {round(sum(hr) / len(hr))}bpm）" if hr else "")
                + f"；骑行 {len(bikes)} 次 {bk:.1f}km；共 {len(cardio)} 次")
            lines.append("全部有氧记录（时间 · 项目 · 距离 · 时长 · "
                         "配速/均速 · 心率）：")
            for c in cardio:
                if c["kind"] == "run":
                    speed = fit.pace_text(c["km"], c["minutes"])
                elif c["minutes"] > 0:
                    speed = f'{c["km"] / (c["minutes"] / 60):.1f}km/h'
                else:
                    speed = "—"
                hr_txt = f'{c["hr"]}bpm' if c["hr"] else "—"
                lines.append(
                    f"  {_stamp(c['at'])} · "
                    f"{'跑步' if c['kind'] == 'run' else '骑行'} · "
                    f"{c['km']:.2f}km · {c['minutes']:.0f}分钟 · "
                    f"{speed} · 心率 {hr_txt}")
        else:
            lines.append(f"  {days} 天内没有有氧记录")

        return "\n".join(lines)

    def _run(self, key: str) -> None:
        label, days = PERIODS[key]
        if not llm.is_configured():
            self.status.configure(text="还没配置 AI（同步 → AI 里填 key）",
                                  fg=theme.ERROR)
            return
        digest = self._digest(days)
        self._set_text(f"正在生成{label}……\n\n{digest}")
        self.status.configure(text=f"{label}生成中…", fg=theme.MUTED)

        def work():
            try:
                cfg = llm.load_config()
                url = cfg["base_url"].rstrip("/") + "/chat/completions"
                payload = {
                    "model": cfg["model"],
                    "messages": [
                        {"role": "system", "content": _system_prompt(key, label)},
                        {"role": "user", "content": digest},
                    ],
                    "temperature": 0.4,
                    "stream": False,
                    # 周报只要 150 字；月报/半年报尽量给足输出空间。
                    "max_tokens": (500 if key == "week"
                                   else 8192 if key == "half" else 4096),
                }
                if _is_deepseek(cfg):
                    # DeepSeek 默认先输出很长的 reasoning_content。月报/半年报
                    # 的 max_tokens 会被推理全部吃掉，最终正文为空 —— 报告不需要
                    # 思维链，直接关掉思考模式，让 token 全部用于正文。
                    payload["thinking"] = {"type": "disabled"}
                # 月报/半年报要长，给足时间；周报很快返回。
                timeout = {"week": 120, "month": 300, "half": 600}[key]
                data = llm._post(url, payload, cfg["api_key"], timeout=timeout)
                choice = (data.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get(
                    "content", "").strip()
                if not text:
                    if choice.get("finish_reason") == "length":
                        raise RuntimeError("AI 输出被截断（max_tokens 用完），请重试")
                    raise RuntimeError("AI 没有返回内容")
                if key == "week":
                    # 提示词只是约束，模型偶尔会超长；这里再强制压到 150 字。
                    text = _limit_week(text)
                rid = self.app.db.fit_report_add(key, text)
                stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
                self.after(0, lambda: self._set_text(text))
                self.after(0, lambda: self.status.configure(
                    text=f"{label} 已生成 · {stamp}", fg=theme.SUCCESS))
                self.after(0, self._refresh_last)
            except Exception as exc:      # noqa: BLE001
                msg = str(exc)[:120]
                self.after(0, lambda: self._set_text(f"生成失败：{msg}"))
                self.after(0, lambda: self.status.configure(
                    text="生成失败", fg=theme.ERROR))

        threading.Thread(target=work, daemon=True).start()

    def _set_text(self, content: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")

    def _history(self) -> None:
        self._hist = ReportHistory(self, self.app)

    def _refresh_last(self) -> None:
        rows = self.app.db.fit_reports(1)
        if rows:
            r = rows[0]
            self.last.configure(
                text=f'上次：{r["at"][:16].replace("T", " ")} '
                     f'{KIND_LABEL.get(r["kind"], r["kind"])}')

    def on_show(self, **_):
        self._refresh_last()
        # 进来先显示最近一份报告, 空白页太浪费
        rows = self.app.db.fit_reports(1)
        if rows:
            r = rows[0]
            stamp = r["at"][:16].replace("T", " ")
            head = f'【{KIND_LABEL.get(r["kind"], r["kind"])}】{stamp}'
            self._set_text(f"{head}\n\n{r['content']}")
