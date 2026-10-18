"""AutoReply Analytics: hisoblash va grafiklar (Matplotlib).

Maxfiylik: bu yerga faqat soatlik hisoblagichlar keladi (vaqt + tur + son) — xabar matni, chat ID yoki
mijoz ma'lumoti hech qayerda yo'q.

Grafik matnida emoji ishlatilmaydi (DejaVu shrifti emoji'siz); yorliqlar chaqiruvchidan (uz/en/ru) keladi.
Render alohida oqimda (executor) bajariladi, bir vaqtda 2 tadan ortiq emas, bir xil grafik ~60 soniya keshlanadi
(Render bepul tarifida 512 MB RAM).
"""
import asyncio
import io
import threading
import time
from datetime import datetime, timedelta, timezone

SENT_KINDS = ("faq", "ai", "static", "sleep")
CHART_CACHE_SECONDS = 60
MAX_CONCURRENT_RENDERS = 2

# Grafik ranglari (yorqin, kontrastli)
_COLORS = {"incoming": "#4C78A8", "sent": "#54A24B", "faq": "#F58518", "ai": "#B279A2", "static": "#4C78A8", "sleep": "#7F7F7F"}


def period_start(days: int, tz, now: datetime | None = None) -> datetime:
    """`days` kunlik oraliqning boshi: bugungi kun ham kiradi, tz bo'yicha yarim tundan."""
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=max(days, 1) - 1)


def summarize(rows, days: int, tz, now: datetime | None = None) -> dict:
    """rows: [(bucket_ts, kind, count)]. Natija: jami sonlar, kunlar kesimi, soatlar kesimi, eng faol oyna va h.k."""
    start = period_start(days, tz, now)
    start_ts = start.timestamp()
    kinds = {"incoming": 0, "faq": 0, "ai": 0, "static": 0, "sleep": 0, "skipped": 0}
    day_in: dict = {}
    day_sent: dict = {}
    hourly_in = [0] * 24
    hourly_sent = [0] * 24
    hourly_all = [0] * 24
    for bucket, kind, count in rows:
        if bucket < start_ts or kind not in kinds:
            continue
        kinds[kind] += count
        local = datetime.fromtimestamp(bucket, tz)
        d = local.date()
        if kind == "incoming":
            day_in[d] = day_in.get(d, 0) + count
            hourly_in[local.hour] += count
        elif kind in SENT_KINDS:
            day_sent[d] = day_sent.get(d, 0) + count
            hourly_sent[local.hour] += count
        if kind == "incoming" or kind in SENT_KINDS:
            hourly_all[local.hour] += count
    incoming = kinds["incoming"]
    sent = sum(kinds[k] for k in SENT_KINDS)
    daily = []
    for i in range(max(days, 1)):
        d = (start + timedelta(days=i)).date()
        daily.append((d, day_in.get(d, 0), day_sent.get(d, 0)))
    busiest_day = max(daily, key=lambda x: x[1]) if incoming else None
    return {
        "days": days,
        "incoming": incoming,
        "sent": sent,
        "kinds": kinds,
        "daily": daily,
        "hourly": hourly_in,
        "hourly_sent": hourly_sent,
        "peak": busiest_window(hourly_in),
        "busiest_day": (busiest_day[0], busiest_day[1]) if busiest_day and busiest_day[1] else None,
        "daily_avg": round(incoming / max(days, 1), 1),
        "reply_rate": round(100 * sent / incoming) if incoming else 0,
        "skipped": kinds["skipped"],
    }


def busiest_window(hourly, width: int = 2):
    """Eng ko'p xabar kelgan ketma-ket `width` soatlik oyna: barcha oraliqlar yig'indisi solishtiriladi.
    Teng bo'lsa — faol soatdan boshlanadigani, so'ng eng erta oyna. Natija: (boshlanish, tugash) yoki None."""
    if not any(hourly):
        return None
    start = max(range(0, 24 - width + 1), key=lambda h: (sum(hourly[h:h + width]), hourly[h], -h))
    return start, start + width


def is_empty(summary: dict) -> bool:
    return summary["incoming"] == 0 and summary["sent"] == 0


# ---------------------------------------------------------------------------
# Grafiklar (sinxron — executor ichida chaqiriladi)
# ---------------------------------------------------------------------------
def _fig_to_png(fig) -> bytes:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    finally:
        plt.close(fig)
    return buf.getvalue()


def _new_fig(figsize=(7.5, 4.2)):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("white")
    return fig, ax


def render_line_chart(summary: dict, labels: dict) -> bytes:
    """Kunlik kelgan va yuborilgan xabarlar (chiziqli grafik)."""
    fig, ax = _new_fig()
    if summary["days"] == 1:  # bugun: bitta nuqta ma'nosiz — soatlar kesimida chiziladi
        xs = [f"{h:02d}" for h in range(24)]
        inc, snt = summary["hourly"], summary["hourly_sent"]
        ax.set_xlabel(labels["hour"])
    else:
        xs = [d.strftime("%d.%m") for d, _, _ in summary["daily"]]
        inc = [i for _, i, _ in summary["daily"]]
        snt = [s for _, _, s in summary["daily"]]
    ax.plot(xs, inc, marker="o", color=_COLORS["incoming"], linewidth=2.2, label=labels["incoming"])
    ax.plot(xs, snt, marker="o", color=_COLORS["sent"], linewidth=2.2, label=labels["sent"])
    ax.set_title(labels["title"], fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)
    ax.yaxis.get_major_locator().set_params(integer=True)
    if len(xs) > 10:
        step = max(1, len(xs) // 10)
        ax.set_xticks(range(0, len(xs), step))
        ax.set_xticklabels(xs[::step], rotation=45, ha="right")
    ax.legend()
    return _fig_to_png(fig)


def render_pie_chart(summary: dict, labels: dict) -> bytes:
    """Javob turlari ulushi (Smart FAQ / AI / Oddiy / Uxlash rejimi)."""
    fig, ax = _new_fig((6, 4.6))
    items = [(labels[k], summary["kinds"][k], _COLORS[k]) for k in ("faq", "ai", "static", "sleep") if summary["kinds"][k] > 0]
    if not items:
        items = [(labels["none"], 1, "#CCCCCC")]
    names, values, colors = zip(*items)
    total = sum(values)
    ax.pie(
        values, labels=None, colors=colors, startangle=90, counterclock=False,
        autopct=lambda p: f"{p:.0f}%" if p >= 4 else "", pctdistance=0.75,
        wedgeprops={"edgecolor": "white", "linewidth": 2}, textprops={"color": "white", "fontweight": "bold"},
    )
    ax.legend([f"{n} - {v}" for n, v in zip(names, values)] if total else names, loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
    ax.set_title(labels["title"], fontsize=13, fontweight="bold")
    ax.axis("equal")
    return _fig_to_png(fig)


def render_bar_chart(summary: dict, labels: dict) -> bytes:
    """Eng faol soatlar (soat bo'yicha kelgan xabarlar, ustunli grafik)."""
    fig, ax = _new_fig((8, 4.2))
    hours = list(range(24))
    values = summary["hourly"]
    peak = summary["peak"]
    colors = [_COLORS["faq"] if peak and peak[0] <= h < peak[1] else _COLORS["incoming"] for h in hours]
    ax.bar(hours, values, color=colors)
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=8)
    ax.set_xlabel(labels["hour"])
    ax.set_title(labels["title"], fontsize=13, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.yaxis.get_major_locator().set_params(integer=True)
    return _fig_to_png(fig)


_render_lock = threading.Lock()  # pyplot umumiy holati oqim-xavfsiz emas: renderlar ketma-ket bajariladi


def _locked(fn):
    def run(summary, labels):
        with _render_lock:
            return fn(summary, labels)
    return run


RENDERERS = {"line": _locked(render_line_chart), "pie": _locked(render_pie_chart), "bar": _locked(render_bar_chart)}

# ---------------------------------------------------------------------------
# Asinxron o'rama: executor + bir vaqtdagi renderlar chegarasi + qisqa kesh
# ---------------------------------------------------------------------------
_semaphore: asyncio.Semaphore | None = None
_cache: dict = {}


def _cache_key(kind: str, owner_id: int, summary: dict, labels: dict):
    return (kind, owner_id, summary["days"], summary["incoming"], summary["sent"], tuple(summary["hourly"]), tuple(summary["hourly_sent"]),
            tuple(sorted(summary["kinds"].items())), labels.get("title"), summary["daily"][-1][0] if summary["daily"] else None)


async def render_chart(kind: str, owner_id: int, summary: dict, labels: dict) -> bytes:
    global _semaphore
    key = _cache_key(kind, owner_id, summary, labels)
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < CHART_CACHE_SECONDS:
        return hit[1]
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)
    async with _semaphore:
        loop = asyncio.get_running_loop()
        png = await loop.run_in_executor(None, RENDERERS[kind], summary, labels)
    for k in [k for k, (ts, _) in _cache.items() if now - ts >= CHART_CACHE_SECONDS]:
        _cache.pop(k, None)
    _cache[key] = (time.monotonic(), png)
    return png
