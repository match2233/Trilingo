"""AI 建议页：周报 / 月报 / 半年报 + 历史报告.

每次生成都会存进 fit_report，历史里带日期和类型，点开可以回看。
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
        self.text.pack(fill="both", expand=True)
        self.text.configure(state="disabled")
        self._set_text("点上面的按钮生成报告。\n\n"
                       "会把体重趋势、力量训练量、有氧汇总一起发给 AI，"
                       "让它给趋势判断、下一步建议和风险预警。")

    # ------------------------------------------------------------ 数据
    def _digest(self, days: int) -> str:
        """把这段时间的数据整理成给模型的材料 —— 越具体，建议越不空泛。"""
        db = self.app.db
        today = dt.date.today()
        since = (today - dt.timedelta(days=days)).isoformat()
        who = []
        if fit.PROFILE.get("height_cm"):
            who.append(f"{fit.PROFILE['height_cm']}cm")
        age = fit.age_on()
        if age:
            who.append(f"{age} 岁")
        profile_txt = "、".join(who) if who else "未填身高年龄"
        lines = [f"统计区间：最近 {days} 天（{since} 起）",
                 f"用户：{profile_txt}，目标增重增肌、每天至少不比前一天轻松"]

        # 体重：期初/期末/斜率 + 最近几个点
        ws = [(at, kg) for at, kg in db.fit_weight_all() if at[:10] >= since]
        if ws:
            daily = fit.daily_mean(ws)
            first, last = daily[0][1], daily[-1][1]
            recent = "、".join(f"{d.strftime('%m-%d')} {v}kg"
                              for d, v in daily[-5:])
            lines.append(
                f"体重：{len(ws)} 次记录 / {len(daily)} 天；期初 {first}kg → "
                f"期末 {last}kg（{last - first:+.1f}kg）；趋势 "
                f"{fit.trend_slope(daily):+.2f} kg/周；"
                + (f"BMI {fit.bmi(last)}；" if fit.bmi(last) else "") +
                f"最近几天：{recent}")
        else:
            lines.append("体重：这段时间没有记录")

        # 力量训练：每天的组数分布 + 每个动作的组数
        rows = [r for r in db.fit_log_history(days)]
        if rows:
            per_day: dict[str, int] = {}
            per_move: dict[str, int] = {}
            for r in rows:
                per_day[r["day"]] = per_day.get(r["day"], 0) + r["n"]
                per_move[r["move"]] = per_move.get(r["move"], 0) + r["n"]
            trained = len(per_day)
            gaps = []
            last_day = max(per_day)
            gap_now = (today - dt.date.fromisoformat(last_day)).days
            for i in range(days):
                d = (today - dt.timedelta(days=days - 1 - i)).isoformat()
                gaps.append("练" if per_day.get(d) else "·")
            detail = "、".join(
                f"{d} {n}组" for d, n in sorted(per_day.items())[-7:])
            moves = "、".join(
                f"{fit.MOVE_BY_SLUG.get(k, {}).get('cn', k)}{v}组"
                for k, v in sorted(per_move.items(), key=lambda kv: -kv[1]))
            lines.append(
                f"力量训练：{trained} 天有打卡（{trained}/{days}），共 "
                f"{sum(per_move.values())} 组；最近一次是 {last_day}"
                f"（距今 {gap_now} 天）")
            lines.append(f"  逐日：{''.join(gaps)}（左旧右新，练=有打卡）")
            lines.append(f"  最近几天：{detail}")
            lines.append(f"  各动作：{moves}")
        else:
            lines.append(f"力量训练：最近 {days} 天一次都没练")

        # 有氧
        cardio = db.fit_cardio_since(since)
        runs = [c for c in cardio if c["kind"] == "run"]
        bikes = [c for c in cardio if c["kind"] == "bike"]
        if runs or bikes:
            rk = sum(c["km"] for c in runs)
            bk = sum(c["km"] for c in bikes)
            hr = [c["hr"] for c in runs if c["hr"]]
            lines.append(
                f"有氧：跑步 {len(runs)} 次 {rk:.1f}km"
                + (f"（平均心率 {sum(hr)//len(hr)}）" if hr else "")
                + f"；骑行 {len(bikes)} 次 {bk:.1f}km")
        else:
            lines.append(f"有氧：最近 {days} 天没有记录")
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
                        {"role": "system", "content":
                         f"""你是私人健身教练，给用户写{label}。用户目标：增重增肌、长期坚持、每天不比前一天轻松。

必须严格按下面五段输出（用短标题，不要多余寒暄）：
一、结论：一句话说清这{label}是"练够了/没练够"、"吃够了/没吃够"。
二、最大问题：只挑最致命的**一个**，用数据点出来（例如"7 天只练 1 次"）。
三、本周唯一重点：一个具体可执行的动作，带数字（组数×次数×重量，或每日热量/蛋白）。
四、次要建议：最多 3 条，每条都要带数字，不要空话。
五、预警：只在确实有风险时写（体重连续下降、连续缺练、训练量骤降），否则写"无"。

硬性要求：每个判断后面跟数据；不要泛泛而谈"要均衡饮食""注意休息"；
不要复述我给的数据；总字数 350 字以内。"""},
                        {"role": "user", "content": digest},
                    ],
                    "temperature": 0.4,
                    "stream": False,
                }
                data = llm._post(url, payload, cfg["api_key"], timeout=180)
                text = (data.get("choices") or [{}])[0].get(
                    "message", {}).get("content", "").strip()
                if not text:
                    raise RuntimeError("AI 没有返回内容")
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
