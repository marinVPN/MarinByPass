"""MarinByPass — графическая оболочка для обхода DPI-блокировок.

Оформление: светлый «системный» интерфейс в духе macOS — нейтральные
поверхности, один акцент, hairline-разделители. Логика (движок, пресеты,
проверка сети, автозапуск) полностью отделена от отрисовки.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import font as tkfont

import engine as eng
import engine_meta
import engine_update
import theme as T
from constants import (
    APP_NAME, APP_TAG, APP_TITLE, APP_VER, ENGINE_DIR, LOG_DIR, is_admin,
    res_dir, sp,
)
from netcheck import SERVICES, NetChecker
from presets import ENGINE_NAMES, PRESETS, preset_by_id
from theme import ft
from ui_render import rounded_photo, shadow_photo
from widgets import (
    Chip, HLine, LogView, NavItem, Panel, PowerControl, PresetCard, RoundButton,
    ScrollFrame, ServiceCard, Switch, apply_fonts, draw_dot, draw_icon, draw_logo,
)

NAV_ITEMS = [
    ("home", "Главная", "home"),
    ("network", "Соединение", "activity"),
    ("strategies", "Стратегии", "shield"),
    ("settings", "Настройки", "sliders"),
    ("about", "О программе", "info"),
]

QUICK_START = [
    ("1", "bolt", "Включите защиту",
     "Переключатель на главной запускает движок. Трафик обрабатывается локально."),
    ("2", "activity", "Проверьте сервисы",
     "Карточки показывают, что открывается, а что пока блокируется провайдером."),
    ("3", "shield", "Подберите стратегию",
     "Если не помогло — смените пресет: он применяется сразу, без перезапуска."),
]

SIDEBAR_W = 236


def _light_titlebar(root: tk.Tk) -> None:
    """Светлый заголовок окна и скруглённые углы (Windows 10/11)."""
    try:
        root.update_idletasks()
        handles = []
        hwnd = ctypes.windll.user32.FindWindowW(None, root.title())
        if hwnd:
            handles.append(hwnd)
        inner = root.winfo_id()
        parent = ctypes.windll.user32.GetParent(inner)
        handles += [parent, inner]
        light = ctypes.c_int(0)
        round_val = ctypes.c_int(2)
        for h in handles:
            if not h:
                continue
            for attr in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(h, attr,
                                                           ctypes.byref(light), 4)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(h, 33,
                                                       ctypes.byref(round_val), 4)
    except Exception:
        pass


def _icon(parent, name, size, color, bg, weight=1.6):
    """Небольшая иконка на собственном прозрачном Canvas."""
    c = tk.Canvas(parent, width=sp(size), height=sp(size), bg=bg,
                  highlightthickness=0, bd=0)
    draw_icon(c, name, sp(size) / 2, sp(size) / 2, sp(size - 2), color, weight)
    return c


def _bind_click(widget, command):
    widget.bind("<Button-1>", lambda e: command())
    for child in widget.winfo_children():
        _bind_click(child, command)


class App(tk.Tk):
    def __init__(self, autostart: bool = False, minimize: bool = True):
        super().__init__()
        self.cfg = eng.load_config()
        self.engine = eng.EngineManager()
        self.net = NetChecker()
        self.autostart_flag = autostart
        self.is_admin = is_admin()
        self.running = False
        self.checking = False
        self._starting = False
        self._net_pending = 0
        self._page = ""
        self._check_buttons: list = []
        self._toast = None
        self._toast_pic = None
        self._toast_jobs: list = []
        self._net_ok = 0
        self._net_checked = False

        apply_fonts(self)
        self.title(APP_TITLE)
        self.configure(bg=T.BG)
        w, h = sp(1240), sp(816)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = max(sp(980), min(w, sw - sp(24)))
        h = max(sp(680), min(h, sh - sp(72)))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - sp(18))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(sp(1120), w), min(sp(720), h))
        try:
            self.iconbitmap(str(res_dir() / "assets" / "icon.ico"))
        except Exception:
            pass
        self.update_idletasks()
        self.after(60, lambda: _light_titlebar(self))
        self.after(700, lambda: _light_titlebar(self))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_shell()
        self.pages: dict[str, tk.Frame] = {}
        self._build_home()
        self._build_network()
        self._build_strategies()
        self._build_settings()
        self._build_about()
        self.show_page("home", animate=False)
        start_page = os.environ.get("FDPI_PAGE", "")
        start_page = {"log": "network"}.get(start_page, start_page)
        if start_page in self.pages:
            self.show_page(start_page, animate=False)

        self._update_status()

        force_auto = os.environ.get("FDPI_AUTOSTART") == "1"
        self._auto_start_pending = bool(
            self.is_admin
            and (force_auto or (self.autostart_flag and self.cfg.auto_enable)))
        self._update_done = False
        self._updating_engine = False

        if not self.is_admin:
            self.log("Программа запущена без прав администратора — включение будет недоступно.", "warn")
            self.log("Закройте приложение и запустите exe от имени администратора.", "warn")
        self.log(f"{APP_NAME} {APP_VER} готов к работе", "accent")
        self.log(self._engine_line(), "muted")

        self.after(120, self._pump)
        self.after(500, self._tick)

        if self.cfg.auto_update_engines:
            self.after(700, self._start_engine_updates)
        else:
            self.after(500, self._finish_engine_updates)
        if self.autostart_flag and self.cfg.start_minimized and minimize:
            self.after(1400, self.iconify)
        if os.environ.get("FDPI_CHECK") == "1":
            self.after(6000 if self.is_admin else 1600, self._check_services)

    def _engine_line(self) -> str:
        return engine_meta.version_line() + " · WinDivert 2.2"

    # ================================================================= shell
    def _build_shell(self):
        side = tk.Frame(self, bg=T.SIDEBAR, width=sp(SIDEBAR_W))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Frame(self, bg=T.HAIR, width=1).pack(side="left", fill="y")
        self.content = tk.Frame(self, bg=T.BG)
        self.content.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(side, bg=T.SIDEBAR)
        inner.pack(fill="both", expand=True, padx=sp(14), pady=sp(18))

        brand = tk.Frame(inner, bg=T.SIDEBAR)
        brand.pack(fill="x", pady=(0, sp(22)))
        logo = tk.Canvas(brand, width=sp(34), height=sp(34), bg=T.SIDEBAR,
                         highlightthickness=0, bd=0)
        logo.pack(side="left")
        draw_logo(logo, sp(17), sp(17), sp(34))
        word = tk.Frame(brand, bg=T.SIDEBAR)
        word.pack(side="left", padx=(sp(10), 0))
        tk.Label(word, text=APP_NAME, bg=T.SIDEBAR, fg=T.TEXT,
                 font=ft("semi", 14.5)).pack(anchor="w")
        tk.Label(word, text=APP_TAG, bg=T.SIDEBAR, fg=T.MUTED,
                 font=ft("text", 11)).pack(anchor="w", pady=(sp(1), 0))

        self.nav: dict[str, NavItem] = {}
        for key, label, icon in NAV_ITEMS:
            item = NavItem(inner, label, icon, lambda k=key: self.show_page(k),
                           width=204, height=38, bg=T.SIDEBAR)
            item.pack(fill="x", pady=(0, sp(2)))
            self.nav[key] = item

        tk.Frame(inner, bg=T.SIDEBAR).pack(fill="both", expand=True)

        status = Panel(inner, fill=T.CARD, border=T.HAIR, radius=10, pad=12,
                       bg=T.SIDEBAR)
        status.pack(fill="x", pady=(0, sp(16)))
        box = status.inner
        head = tk.Frame(box, bg=T.CARD)
        head.pack(fill="x")
        self.side_dot = tk.Canvas(head, width=sp(12), height=sp(12), bg=T.CARD,
                                  highlightthickness=0, bd=0)
        self.side_dot.pack(side="left", padx=(0, sp(7)))
        tk.Label(head, text="Защита", bg=T.CARD, fg=T.MUTED,
                 font=ft("text", 11.5)).pack(side="left")
        self.lbl_side_state = tk.Label(box, text="Выключена", bg=T.CARD, fg=T.TEXT,
                                       font=ft("semi", 14.5))
        self.lbl_side_state.pack(anchor="w", pady=(sp(4), sp(6)))
        HLine(box, bg=T.CARD, color=T.HAIR).pack(fill="x", pady=(0, sp(8)))
        self.lbl_side_preset = tk.Label(box, text="", bg=T.CARD, fg=T.TEXT_DIM,
                                        font=ft("text", 11.5), anchor="w",
                                        justify="left")
        self.lbl_side_preset.pack(anchor="w")
        self.lbl_side_meta = tk.Label(box, text="", bg=T.CARD, fg=T.MUTED,
                                      font=ft("text", 11), anchor="w",
                                      justify="left")
        self.lbl_side_meta.pack(anchor="w", pady=(sp(2), 0))
        for wdg in (box, head, self.lbl_side_state, self.lbl_side_preset,
                    self.lbl_side_meta):
            try:
                wdg.configure(cursor="hand2")
            except Exception:
                pass
        _bind_click(box, lambda: self.show_page("home"))

        footer = tk.Frame(inner, bg=T.SIDEBAR)
        footer.pack(fill="x", padx=sp(2))
        tk.Label(footer, text=f"версия {APP_VER}", bg=T.SIDEBAR, fg=T.MUTED,
                 font=ft("text", 11)).pack(anchor="w")
        tk.Label(footer, text="локально · без серверов", bg=T.SIDEBAR, fg=T.MUTED,
                 font=ft("text", 11)).pack(anchor="w", pady=(sp(1), 0))

    # ================================================================= pages
    def _new_page(self, key: str) -> tk.Frame:
        page = tk.Frame(self.content, bg=T.BG, padx=sp(32), pady=sp(26))
        page.place(x=0, y=0, relwidth=1, relheight=1)
        self.pages[key] = page
        return page

    def _header(self, page, title, subtitle, chip_text=None, chip_kind="neutral"):
        head = tk.Frame(page, bg=T.BG)
        head.pack(fill="x", pady=(0, sp(20)))
        left = tk.Frame(head, bg=T.BG)
        left.pack(side="left", anchor="n")
        tk.Label(left, text=title, bg=T.BG, fg=T.TEXT,
                 font=ft("display_semi", 26)).pack(anchor="w")
        tk.Label(left, text=subtitle, bg=T.BG, fg=T.MUTED,
                 font=ft("text", 12.5)).pack(anchor="w", pady=(sp(5), 0))
        right = tk.Frame(head, bg=T.BG)
        right.pack(side="right", anchor="n", pady=(sp(6), 0))
        if chip_text:
            tones = {
                "green": (T.GREEN, T.GREEN_SOFT),
                "red": (T.RED, T.RED_SOFT),
                "neutral": (T.TEXT_DIM, T.CARD_ALT),
            }
            fg, bg = tones.get(chip_kind, tones["neutral"])
            Chip(right, chip_text, fg=fg, bg=bg, bg_parent=T.BG,
                 height=26, font=ft("text", 11.5)).pack()
        return head, right

    def _section(self, parent, text, hint=None):
        row = tk.Frame(parent, bg=T.BG)
        row.pack(fill="x", pady=(0, sp(10)))
        tk.Label(row, text=text, bg=T.BG, fg=T.TEXT,
                 font=ft("semi", 14)).pack(side="left")
        lbl = None
        if hint is not None:
            lbl = tk.Label(row, text=hint, bg=T.BG, fg=T.MUTED,
                           font=ft("text", 11.5), anchor="e")
            lbl.pack(side="right")
        return row, lbl

    def _group_label(self, parent, text):
        tk.Label(parent, text=text.upper(), bg=T.BG, fg=T.MUTED,
                 font=ft("semi", 10.5)).pack(anchor="w", padx=sp(2),
                                             pady=(0, sp(8)))

    # ------------------------------------------------------------------ home
    def _build_home(self):
        page = self._new_page("home")
        self._header(
            page, "Главная", "Обход DPI — локально, без серверов и аккаунтов",
            "Администратор" if self.is_admin else "Без прав администратора",
            "green" if self.is_admin else "red")

        self.home_scroll = ScrollFrame(page, bg=T.BG)
        self.home_scroll.pack(fill="both", expand=True)
        body = self.home_scroll.inner

        # ---- hero
        hero = Panel(body, fill=T.CARD, border=T.HAIR, radius=12, pad=24)
        hero.pack(fill="x", pady=(0, sp(24)))
        top = tk.Frame(hero.inner, bg=T.CARD)
        top.pack(fill="x")

        left = tk.Frame(top, bg=T.CARD)
        left.pack(side="left", fill="both", expand=True)
        status_row = tk.Frame(left, bg=T.CARD)
        status_row.pack(anchor="w")
        self.hero_dot = tk.Canvas(status_row, width=sp(12), height=sp(12),
                                  bg=T.CARD, highlightthickness=0, bd=0)
        self.hero_dot.pack(side="left", padx=(0, sp(6)))
        self.lbl_hero_status = tk.Label(status_row, text="ЗАЩИТА ВЫКЛЮЧЕНА",
                                        bg=T.CARD, fg=T.MUTED,
                                        font=ft("semi", 10.5))
        self.lbl_hero_status.pack(side="left")

        self.lbl_hero_title = tk.Label(left, text="Защита выключена", bg=T.CARD,
                                       fg=T.TEXT, font=ft("display_semi", 26))
        self.lbl_hero_title.pack(anchor="w", pady=(sp(10), 0))
        self.lbl_hero_preset = tk.Label(left, text="", bg=T.CARD, fg=T.TEXT_DIM,
                                        font=ft("text", 13))
        self.lbl_hero_preset.pack(anchor="w", pady=(sp(8), 0))
        self.lbl_hero_desc = tk.Label(left, text="", bg=T.CARD, fg=T.MUTED,
                                      font=ft("text", 12), justify="left",
                                      wraplength=sp(560))
        self.lbl_hero_desc.pack(anchor="w", pady=(sp(6), 0))

        right = tk.Frame(top, bg=T.CARD)
        right.pack(side="right", padx=(sp(28), 0))
        self.power = PowerControl(right, command=self._toggle_engine, size=100,
                                  bg=T.CARD)
        self.power.pack()
        self.lbl_power_cap = tk.Label(right, text="", bg=T.CARD, fg=T.MUTED,
                                      font=ft("text", 11), justify="center",
                                      wraplength=sp(150))
        self.lbl_power_cap.pack(pady=(sp(8), 0))

        HLine(hero.inner, bg=T.CARD, color=T.HAIR).pack(fill="x",
                                                        pady=(sp(22), sp(14)))

        stats = tk.Frame(hero.inner, bg=T.CARD)
        stats.pack(fill="x")
        for i in range(3):
            stats.columnconfigure(i, weight=1, uniform="stat")
        self.val_uptime = self._stat(stats, 0, "ВРЕМЯ РАБОТЫ", "—", mono=True)
        self.val_preset = self._stat(stats, 1, "ПРЕСЕТ", "—")
        self.val_engine = self._stat(stats, 2, "ДВИЖОК", "—")

        actions = tk.Frame(hero.inner, bg=T.CARD)
        actions.pack(fill="x", pady=(sp(18), 0))
        self.btn_home_check = RoundButton(actions, "Проверить доступ",
                                          self._check_services, width=150,
                                          height=34, kind="primary", bg=T.CARD,
                                          icon="search")
        self.btn_home_check.pack(side="right")
        RoundButton(actions, "YouTube", self._open_youtube, width=120,
                    height=34, kind="secondary", bg=T.CARD,
                    icon="play").pack(side="right", padx=(0, sp(8)))
        RoundButton(actions, "Стратегии", lambda: self.show_page("strategies"),
                    width=122, height=34, kind="ghost", bg=T.CARD,
                    icon="shield").pack(side="right", padx=(0, sp(8)))
        self._check_buttons.append(self.btn_home_check)

        # ---- services
        row, self.services_hint = self._section(
            body, "Сервисы", "нажмите «Проверить доступ»")
        grid = tk.Frame(body, bg=T.BG)
        grid.pack(fill="x", pady=(0, sp(12)))
        self.service_cards: dict[str, ServiceCard] = {}
        for i, (name, _url) in enumerate(SERVICES):
            grid.columnconfigure(i, weight=1, uniform="svc")
            card = ServiceCard(grid, name, width=220, height=104)
            card.grid(row=0, column=i, sticky="ew",
                      padx=(0 if i == 0 else sp(4),
                            0 if i == len(SERVICES) - 1 else sp(4)))
            self.service_cards[name] = card

        # ---- quick start
        self._group_label(body, "Быстрый старт")
        group = Panel(body, fill=T.CARD, border=T.HAIR, radius=12, pad=12)
        group.pack(fill="x", pady=(0, sp(8)))
        for i, (num, icon_name, title, desc) in enumerate(QUICK_START):
            if i:
                HLine(group.inner, bg=T.CARD, color=T.HAIR).pack(
                    fill="x", padx=sp(6))
            step = tk.Frame(group.inner, bg=T.CARD)
            step.pack(fill="x")
            row_in = tk.Frame(step, bg=T.CARD)
            row_in.pack(fill="x", padx=sp(6), pady=sp(10))
            badge = tk.Canvas(row_in, width=sp(28), height=sp(28), bg=T.CARD,
                              highlightthickness=0, bd=0)
            badge.pack(side="left", padx=(0, sp(12)))
            tile = rounded_photo(sp(28), sp(28), sp(14), T.ACCENT_SOFT)
            badge.create_image(0, 0, image=tile, anchor="nw")
            badge._pic = tile
            draw_icon(badge, icon_name, sp(14), sp(14), sp(14), T.ACCENT, 1.7)
            txt = tk.Frame(row_in, bg=T.CARD)
            txt.pack(side="left", fill="x", expand=True)
            tk.Label(txt, text=title, bg=T.CARD, fg=T.TEXT,
                     font=ft("semi", 13)).pack(anchor="w")
            tk.Label(txt, text=desc, bg=T.CARD, fg=T.MUTED, font=ft("text", 11.5),
                     justify="left", wraplength=sp(740)).pack(anchor="w",
                                                              pady=(sp(2), 0))
            tk.Label(row_in, text=f"0{num}", bg=T.CARD, fg=T.MUTED,
                     font=ft("mono", 11)).pack(side="right", anchor="n",
                                               pady=(sp(4), 0))

    def _stat(self, parent, column, label, value, mono=False):
        col = tk.Frame(parent, bg=T.CARD)
        col.grid(row=0, column=column, sticky="w")
        tk.Label(col, text=label, bg=T.CARD, fg=T.MUTED,
                 font=ft("semi", 10)).pack(anchor="w")
        val = tk.Label(col, text=value, bg=T.CARD, fg=T.TEXT,
                       font=ft("mono" if mono else "semi", 13))
        val.pack(anchor="w", pady=(sp(3), 0))
        return val

    def _short_uptime(self) -> str:
        if not self.running:
            return "остановлен"
        secs = self.engine.uptime()
        hh, rem = divmod(secs, 3600)
        mm, ss = divmod(rem, 60)
        return f"{hh:02d}:{mm:02d}:{ss:02d}"

    # -------------------------------------------------------------- network
    def _build_network(self):
        page = self._new_page("network")
        head, right = self._header(
            page, "Соединение", "Доступность сервисов и живой журнал событий")
        self.btn_net_check = RoundButton(right, "Проверить всё",
                                         self._check_services, width=150,
                                         height=34, kind="primary", bg=T.BG,
                                         icon="refresh")
        self.btn_net_check.pack(side="right")
        RoundButton(right, "YouTube", self._open_youtube, width=120, height=34,
                    kind="ghost", bg=T.BG,
                    icon="external").pack(side="right", padx=(0, sp(8)))
        self._check_buttons.append(self.btn_net_check)

        summary = Panel(page, fill=T.CARD, border=T.HAIR, radius=12, pad=20)
        summary.pack(fill="x", pady=(0, sp(16)))
        row = tk.Frame(summary.inner, bg=T.CARD)
        row.pack(fill="x")
        left = tk.Frame(row, bg=T.CARD)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="ДОСТУПНОСТЬ СЕРВИСОВ", bg=T.CARD, fg=T.MUTED,
                 font=ft("semi", 10)).pack(anchor="w")
        self.lbl_net_value = tk.Label(left, text=f"— из {len(SERVICES)}",
                                      bg=T.CARD, fg=T.TEXT,
                                      font=ft("display_semi", 24))
        self.lbl_net_value.pack(anchor="w", pady=(sp(2), sp(2)))
        self.lbl_net_state = tk.Label(left, text="нажмите «Проверить всё»",
                                      bg=T.CARD, fg=T.MUTED,
                                      font=ft("text", 12))
        self.lbl_net_state.pack(anchor="w")

        bar_box = tk.Frame(row, bg=T.CARD)
        bar_box.pack(side="right", padx=(sp(24), 0))
        bar_head = tk.Frame(bar_box, bg=T.CARD)
        bar_head.pack(fill="x")
        tk.Label(bar_head, text="HTTPS-пробы", bg=T.CARD, fg=T.MUTED,
                 font=ft("text", 11)).pack(side="left")
        self.lbl_net_pct = tk.Label(bar_head, text="—", bg=T.CARD, fg=T.TEXT_DIM,
                                    font=ft("mono", 11))
        self.lbl_net_pct.pack(side="right")
        self.net_bar = tk.Canvas(bar_box, width=sp(300), height=sp(8), bg=T.CARD,
                                 highlightthickness=0, bd=0)
        self.net_bar.pack(anchor="e", pady=(sp(8), 0))
        self.net_bar.bind("<Configure>", lambda e: self._draw_bar())

        grid = tk.Frame(page, bg=T.BG)
        grid.pack(fill="x", pady=(0, sp(16)))
        self.net_cards: dict[str, ServiceCard] = {}
        for i, (name, _url) in enumerate(SERVICES):
            grid.columnconfigure(i, weight=1, uniform="netsvc")
            card = ServiceCard(grid, name, width=290, height=108)
            card.grid(row=0, column=i, sticky="ew",
                      padx=(0 if i == 0 else sp(4),
                            0 if i == len(SERVICES) - 1 else sp(4)))
            self.net_cards[name] = card

        card = Panel(page, fill=T.CARD, border=T.HAIR, radius=12, pad=12,
                     fill_height=True)
        card.pack(fill="both", expand=True)
        bar = tk.Frame(card.inner, bg=T.CARD)
        bar.pack(fill="x", padx=sp(6), pady=(sp(2), sp(6)))
        tk.Label(bar, text="Журнал событий", bg=T.CARD, fg=T.TEXT,
                 font=ft("semi", 13)).pack(side="left")
        for text, icon_name, cmd in (
                ("Копировать", "copy", self._copy_log),
                ("Очистить", "trash", self._clear_log),
                ("Папка", "folder", lambda: eng.open_path(LOG_DIR))):
            RoundButton(bar, text, cmd, width=106, height=28, kind="ghost",
                        bg=T.CARD, icon=icon_name,
                        font=ft("text", 11.5)).pack(side="right",
                                                    padx=(sp(6), 0))
        HLine(card.inner, bg=T.CARD, color=T.HAIR).pack(fill="x", padx=sp(6))
        self.log_view = LogView(card.inner, height=6, bg=T.CARD)
        self.log_view.pack(fill="both", expand=True, pady=(sp(2), 0))

    def _draw_net_summary(self):
        cards = list(getattr(self, "net_cards", {}).values())
        total = len(cards) or len(SERVICES)
        ok = sum(1 for c in cards if c.state == "ok")
        checked = bool(cards) and any(c.state != "idle" for c in cards)
        self._net_ok, self._net_checked = ok, checked
        if not hasattr(self, "lbl_net_value"):
            return
        self.lbl_net_value.configure(text=f"{ok} из {total}" if checked
                                     else f"— из {total}")
        if self.checking:
            state, color = "идёт проверка…", T.AMBER
        elif checked:
            if ok == total:
                state, color = "все сервисы доступны", T.GREEN
            elif ok:
                state, color = f"недоступно {total - ok} из {total}", T.AMBER
            else:
                state, color = "сервисы недоступны — смените пресет", T.RED
        else:
            state, color = "нажмите «Проверить всё»", T.MUTED
        self.lbl_net_state.configure(text=state, fg=color)
        pct = round(ok / total * 100) if checked else None
        self.lbl_net_pct.configure(text=f"{pct}%" if pct is not None else "—")
        self._draw_bar()

    def _draw_bar(self):
        if not hasattr(self, "net_bar"):
            return
        c = self.net_bar
        w = c.winfo_width()
        h = sp(8)
        if w < 20:
            return
        c.delete("all")
        track = rounded_photo(w, h, h // 2, T.HAIR_SOFT)
        c.create_image(0, 0, image=track, anchor="nw")
        self._bar_track = track
        if self._net_checked and self._net_ok:
            fw = max(h, int(w * self._net_ok / max(1, len(SERVICES))))
            fill = rounded_photo(fw, h, h // 2, T.ACCENT_FILL)
            c.create_image(0, 0, image=fill, anchor="nw")
            self._bar_fill = fill

    # ------------------------------------------------------------ strategies
    def _build_strategies(self):
        page = self._new_page("strategies")
        self._header(page, "Стратегии",
                     "Выберите способ обхода DPI — можно менять на ходу")

        note = Panel(page, fill=T.CARD_ALT, border=None, radius=10, pad=14)
        note.pack(fill="x", pady=(0, sp(18)))
        row = tk.Frame(note.inner, bg=T.CARD_ALT)
        row.pack(fill="x")
        _icon(row, "bolt", 16, T.ACCENT, T.CARD_ALT).pack(side="left",
                                                          padx=(0, sp(9)))
        tk.Label(row, text="Начните с «Универсального». Не открылся нужный сайт — "
                           "попробуйте другой пресет: провайдеры блокируют по-разному.",
                 bg=T.CARD_ALT, fg=T.TEXT_DIM, font=ft("text", 11.5),
                 justify="left",
                 wraplength=sp(800)).pack(side="left", anchor="w")

        self.strat_scroll = ScrollFrame(page, bg=T.BG)
        self.strat_scroll.pack(fill="both", expand=True)
        inner = self.strat_scroll.inner

        self._group_label(inner, "Пресеты")
        self.preset_cards: dict[str, PresetCard] = {}
        holder = tk.Frame(inner, bg=T.BG)
        holder.pack(fill="x")
        for i, preset in enumerate(PRESETS):
            card = PresetCard(holder, preset, self._select_preset, width=760,
                              height=92, first=(i == 0),
                              last=(i == len(PRESETS) - 1), bg=T.BG)
            card.pack(fill="x")
            card.set_selected(preset.id == self.cfg.preset)
            self.preset_cards[preset.id] = card

        self._group_label(inner, "Дополнительные параметры")
        args_panel = Panel(inner, fill=T.CARD, border=T.HAIR, radius=10, pad=0)
        args_panel.pack(fill="x")
        self.args_panel = args_panel
        args_row = tk.Frame(args_panel.inner, bg=T.CARD)
        args_row.pack(fill="x")
        tk.Label(args_row, text="--", bg=T.CARD, fg=T.MUTED,
                 font=ft("mono", 12.5)).pack(side="left", padx=(sp(14), 0))
        self.extra_var = tk.StringVar(value=self.cfg.extra_args)
        entry = tk.Entry(args_row, textvariable=self.extra_var, bg=T.CARD,
                         fg=T.TEXT, bd=0, relief="flat",
                         insertbackground=T.ACCENT, font=ft("mono", 12),
                         highlightthickness=0)
        entry.pack(side="left", fill="x", expand=True, padx=(sp(8), sp(14)),
                   pady=sp(11))
        entry.bind("<Return>", self._save_extra)
        entry.bind("<FocusIn>", lambda e: args_panel.set_border(T.ACCENT))
        entry.bind("<FocusOut>", self._extra_blur)
        self.extra_hint = tk.Label(inner, text="Например: --debug — применяется "
                                                "при следующем запуске",
                                   bg=T.BG, fg=T.MUTED, font=ft("text", 11))
        self.extra_hint.pack(anchor="w", pady=(sp(7), sp(14)))

    def _select_preset(self, preset):
        if self.cfg.preset == preset.id:
            return
        self.cfg.preset = preset.id
        eng.save_config(self.cfg)
        for pid, card in self.preset_cards.items():
            card.set_selected(pid == preset.id)
        self._update_status()
        self.log(f"Выбрана стратегия: {preset.title}", "accent")
        self.toast(f"Стратегия: {preset.title}")
        if self.engine.is_running():
            self.log("Перезапуск движка с новой стратегией…", "info")
            self.engine.start(preset, self.cfg.extra_args, self.cfg.debug_log)

    def _extra_blur(self, _=None):
        self._save_extra()
        self.args_panel.set_border(T.HAIR)

    def _save_extra(self, _=None):
        val = self.extra_var.get().strip()
        if val == self.cfg.extra_args:
            return
        self.cfg.extra_args = val
        eng.save_config(self.cfg)
        if self.engine.is_running():
            self.extra_hint.configure(text="Сохранено. Перезапустите защиту, "
                                           "чтобы применить.")
        else:
            self.extra_hint.configure(text="Сохранено. Применится при следующем "
                                           "запуске.")
        self.log("Дополнительные параметры сохранены", "info")

    # ------------------------------------------------------------------- log
    def log(self, text: str, level="info"):
        stamps = time.strftime("%H:%M:%S")
        if hasattr(self, "log_view"):
            self.log_view.append(f"{stamps}   {text}", level)
        eng.log_line(text)

    def _copy_log(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.log_view.text.get("1.0", "end-1c"))
            self.log("Журнал скопирован в буфер обмена", "muted")
            self.toast("Журнал скопирован")
        except Exception:
            pass

    def _clear_log(self):
        self.log_view.clear()
        self.log("Журнал очищен", "muted")

    # -------------------------------------------------------------- settings
    def _build_settings(self):
        page = self._new_page("settings")
        self._header(page, "Настройки", "Поведение приложения и автозапуск")

        scroller = ScrollFrame(page, bg=T.BG)
        scroller.pack(fill="both", expand=True)
        wrap = scroller.inner

        # предупреждение о правах — вверху, чтобы его не прятал скролл
        if not self.is_admin:
            warn = Panel(wrap, fill=T.RED_SOFT, border=None, radius=12, pad=14)
            warn.pack(fill="x", pady=(0, sp(18)))
            row = tk.Frame(warn.inner, bg=T.RED_SOFT)
            row.pack(fill="x")
            _icon(row, "lock", 16, T.RED, T.RED_SOFT).pack(side="left",
                                                           padx=(0, sp(9)))
            text = tk.Frame(row, bg=T.RED_SOFT)
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text="Нет прав администратора", bg=T.RED_SOFT,
                     fg=T.TEXT, font=ft("semi", 12.5)).pack(anchor="w")
            tk.Label(text, text="Включение защиты и изменение автозапуска "
                                "недоступны — перезапустите приложение от "
                                "имени администратора.",
                     bg=T.RED_SOFT, fg=T.TEXT_DIM, font=ft("text", 11.5),
                     justify="left", wraplength=sp(620)).pack(anchor="w",
                                                              pady=(sp(2), 0))
            RoundButton(row, "Перезапустить от админа", self._relaunch_admin,
                        width=196, height=30, kind="danger",
                        bg=T.RED_SOFT).pack(side="right", padx=(sp(16), 0))

        def group(title):
            self._group_label(wrap, title)
            card = Panel(wrap, fill=T.CARD, border=T.HAIR, radius=12, pad=12)
            card.pack(fill="x", pady=(0, sp(22)))
            return card.inner

        box = group("Система")
        self.sw_autostart = self._setting_row(
            box, "Запускать вместе с Windows",
            "Создаёт задачу планировщика с правами администратора — без запроса "
            "UAC при входе.", eng.autostart_enabled(), self._toggle_autostart)
        self.sw_autoenable = self._setting_row(
            box, "Включать защиту при автозапуске",
            "Сразу поднимать движок после входа в систему.",
            self.cfg.auto_enable, lambda v: self._set_cfg("auto_enable", v))
        self.sw_minimized = self._setting_row(
            box, "Запускать свёрнутым",
            "Окно автозапуска не будет мешать — приложение останется на панели "
            "задач.", self.cfg.start_minimized,
            lambda v: self._set_cfg("start_minimized", v), last=True)

        box = group("Движок")
        self.sw_engine_updates = self._setting_row(
            box, "Обновлять движки автоматически",
            "При запуске проверять официальные релизы zapret и GoodbyeDPI "
            "и устанавливать новые версии. Обновление проверяется на временной "
            "копии, выбранная стратегия и дополнительные параметры не меняются.",
            self.cfg.auto_update_engines,
            lambda v: self._set_cfg("auto_update_engines", v))
        self.sw_debug = self._setting_row(
            box, "Подробный журнал",
            "Добавляет --debug: больше информации о пакетах, полезно при подборе "
            "стратегии.", self.cfg.debug_log, self._toggle_debug, last=True)

        HLine(box, bg=T.CARD, color=T.HAIR).pack(fill="x", padx=sp(6))
        info = tk.Frame(box, bg=T.CARD)
        info.pack(fill="x", padx=sp(6), pady=(sp(12), sp(12)))
        tk.Label(info, text="Версия движков", bg=T.CARD, fg=T.TEXT,
                 font=ft("semi", 13)).pack(anchor="w")
        self.lbl_engine_versions = tk.Label(
            info, text=self._engine_line(), bg=T.CARD,
            fg=T.MUTED, font=ft("text", 11.5),
            justify="left")
        self.lbl_engine_versions.pack(anchor="w", pady=(sp(2), 0))
        tk.Label(info, text=str(ENGINE_DIR), bg=T.CARD, fg=T.MUTED,
                 font=ft("mono", 11), justify="left",
                 wraplength=sp(700)).pack(anchor="w", pady=(sp(2), sp(10)))
        btns = tk.Frame(info, bg=T.CARD)
        btns.pack(anchor="w")
        RoundButton(btns, "Переустановить файлы", self._repair_engine, width=180,
                    height=30, kind="secondary", bg=T.CARD,
                    icon="refresh").pack(side="left", padx=(0, sp(8)))
        RoundButton(btns, "Открыть папку", lambda: eng.open_path(ENGINE_DIR),
                    width=134, height=30, kind="ghost", bg=T.CARD,
                    icon="folder").pack(side="left")

        box = group("Сброс")
        reset_row = tk.Frame(box, bg=T.CARD)
        reset_row.pack(fill="x", padx=sp(6), pady=sp(6))
        tk.Label(reset_row, text="Вернуть настройки по умолчанию", bg=T.CARD,
                 fg=T.TEXT, font=ft("text", 13)).pack(side="left")
        RoundButton(reset_row, "Сбросить", self._reset_settings, width=110,
                    height=30, kind="danger",
                    bg=T.CARD).pack(side="right")

    def _setting_row(self, parent, title, desc, value, command, last=False):
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x")
        box = tk.Frame(row, bg=T.CARD)
        box.pack(fill="x", padx=sp(6), pady=sp(12))
        left = tk.Frame(box, bg=T.CARD)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, bg=T.CARD, fg=T.TEXT,
                 font=ft("text", 13)).pack(anchor="w")
        tk.Label(left, text=desc, bg=T.CARD, fg=T.MUTED, font=ft("text", 11.5),
                 wraplength=sp(600), justify="left").pack(anchor="w",
                                                          pady=(sp(2), 0))
        sw = Switch(box, value=value, command=command, bg=T.CARD)
        sw.pack(side="right", padx=(sp(20), 0))
        if not last:
            HLine(parent, bg=T.CARD, color=T.HAIR).pack(fill="x", padx=sp(6))
        return sw

    def _set_cfg(self, name, value):
        setattr(self.cfg, name, value)
        eng.save_config(self.cfg)

    def _toggle_autostart(self, value):
        ok, err = eng.set_autostart(value)
        if not ok:
            self.sw_autostart.set(not value, animate=False)
            self.log(f"Не удалось изменить автозапуск: {err}", "err")
            self.toast("Не удалось изменить автозапуск", "err")
            return
        self._set_cfg("autostart", value)
        self.log("Автозапуск включён" if value else "Автозапуск выключен",
                 "ok" if value else "info")

    def _toggle_debug(self, value):
        self._set_cfg("debug_log", value)
        if self.engine.is_running():
            self.log("Перезапуск для применения режима журнала…", "info")
            self.engine.start(preset_by_id(self.cfg.preset), self.cfg.extra_args,
                              self.cfg.debug_log)

    def _repair_engine(self):
        def work():
            try:
                if eng.ensure_engine(repair=True):
                    self.after(0, lambda: self.log("Файлы движка переустановлены", "ok"))
                    self.after(0, lambda: self.toast("Файлы движка переустановлены"))
                else:
                    self.after(0, lambda: self.log(
                        "Часть файлов занята другим процессом — переустановка "
                        "завершится при следующем запуске.", "warn"))
            except Exception as exc:
                self.after(0, lambda: self.log(f"Ошибка переустановки: {exc}", "err"))
        self.log("Переустановка файлов движка…", "info")
        threading.Thread(target=work, daemon=True).start()

    def _reset_settings(self):
        self.cfg = eng.Config()
        eng.save_config(self.cfg)
        self.extra_var.set("")
        self.extra_hint.configure(text="Например: --debug — применяется при "
                                       "следующем запуске")
        self.args_panel.set_border(T.HAIR)
        self.sw_autoenable.set(True, animate=False)
        self.sw_minimized.set(True, animate=False)
        self.sw_debug.set(False, animate=False)
        self.sw_autostart.set(eng.autostart_enabled(), animate=False)
        for pid, card in self.preset_cards.items():
            card.set_selected(pid == self.cfg.preset)
        self._update_status()
        self.log("Настройки сброшены", "ok")
        self.toast("Настройки сброшены")

    def _relaunch_admin(self):
        try:
            if getattr(sys, "frozen", False):
                exe = sys.executable
                params = " ".join(f'"{a}"' for a in sys.argv[1:])
            else:
                exe = sys.executable
                params = f'"{Path(sys.argv[0]).resolve()}" ' + " ".join(
                    f'"{a}"' for a in sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
            self._on_close()
        except Exception as exc:
            self.log(f"Не удалось перезапуститься: {exc}", "err")

    # ----------------------------------------------------------------- about
    def _build_about(self):
        page = self._new_page("about")
        self._header(page, "О программе",
                     "MarinByPass — открытая оболочка для обхода DPI")

        scroller = ScrollFrame(page, bg=T.BG)
        scroller.pack(fill="both", expand=True)
        wrap = scroller.inner

        top = Panel(wrap, fill=T.CARD, border=T.HAIR, radius=12, pad=24)
        top.pack(fill="x", pady=(0, sp(22)))
        inner = tk.Frame(top.inner, bg=T.CARD)
        inner.pack(fill="x")
        logo = tk.Canvas(inner, width=sp(56), height=sp(56), bg=T.CARD,
                         highlightthickness=0, bd=0)
        logo.pack(side="left", padx=(0, sp(18)))
        draw_logo(logo, sp(28), sp(28), sp(56))
        txt = tk.Frame(inner, bg=T.CARD)
        txt.pack(side="left", fill="x", expand=True)
        name_row = tk.Frame(txt, bg=T.CARD)
        name_row.pack(anchor="w")
        tk.Label(name_row, text=APP_NAME, bg=T.CARD, fg=T.TEXT,
                 font=ft("display_semi", 20)).pack(side="left", padx=(0, sp(10)))
        Chip(name_row, f"v{APP_VER}", fg=T.TEXT_DIM, bg=T.CARD_ALT,
             bg_parent=T.CARD, height=21,
             font=ft("text", 10.5)).pack(side="left")
        tk.Label(txt, text="Графический интерфейс для zapret и GoodbyeDPI. Работает "
                           "полностью локально: без серверов, аккаунтов и "
                           "телеметрии.",
                 bg=T.CARD, fg=T.TEXT_DIM, font=ft("text", 12),
                 justify="left", wraplength=sp(700)).pack(anchor="w",
                                                          pady=(sp(4), sp(10)))
        Chip(txt, "open source · GPLv2 / Apache 2.0", fg=T.GREEN, bg=T.GREEN_SOFT,
             bg_parent=T.CARD, height=21,
             font=ft("text", 10.5)).pack(anchor="w")

        self._group_label(wrap, "Движки и библиотеки")
        libs = Panel(wrap, fill=T.CARD, border=T.HAIR, radius=12, pad=12)
        libs.pack(fill="x", pady=(0, sp(22)))
        rows = [
            ("zapret · bol-van",
             "Пакетный фильтр winws / winws2 — основа обхода DPI. GPLv2.",
             "https://github.com/bol-van/zapret"),
            ("GoodbyeDPI · ValdikSS",
             "Режимы фрагментации и подмены для Windows. Apache 2.0.",
             "https://github.com/ValdikSS/GoodbyeDPI"),
            ("WinDivert",
             "Перехват и модификация сетевых пакетов в режиме ядра. LGPLv3.",
             "https://reqrypt.org/windivert.html"),
        ]
        for i, (name, desc, url) in enumerate(rows):
            if i:
                HLine(libs.inner, bg=T.CARD, color=T.HAIR).pack(fill="x",
                                                               padx=sp(6))
            row = tk.Frame(libs.inner, bg=T.CARD, cursor="hand2")
            row.pack(fill="x")
            box = tk.Frame(row, bg=T.CARD)
            box.pack(fill="x", padx=sp(6), pady=sp(11))
            link = tk.Label(box, text=name, bg=T.CARD, fg=T.ACCENT,
                            font=ft("semi", 13), cursor="hand2")
            link.pack(anchor="w")
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            tk.Label(box, text=desc, bg=T.CARD, fg=T.MUTED,
                     font=ft("text", 11.5), justify="left",
                     wraplength=sp(700)).pack(anchor="w", pady=(sp(2), 0))
            ext = _icon(box, "external", 14, T.FAINT, T.CARD)
            ext.place(relx=1.0, rely=0.0, anchor="ne", x=-sp(2), y=sp(2))
            ext.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        warn = Panel(wrap, fill=T.CARD_ALT, border=None, radius=12, pad=18)
        warn.pack(fill="x", pady=(0, sp(8)))
        box = warn.inner
        head = tk.Frame(box, bg=T.CARD_ALT)
        head.pack(fill="x", pady=(0, sp(6)))
        _icon(head, "info", 15, T.AMBER, T.CARD_ALT).pack(side="left",
                                                         padx=(0, sp(8)))
        tk.Label(head, text="Важно", bg=T.CARD_ALT, fg=T.TEXT,
                 font=ft("semi", 12.5)).pack(side="left")
        tk.Label(box, text="Обход DPI — не VPN и не гарантия. Он помогает против "
                           "блокировок по TLS/QUIC-признакам, но не против "
                           "блокировки по IP-адресу и не скрывает ваш IP. "
                           "Используйте инструмент в соответствии с "
                           "законодательством вашей страны. При проблемах с "
                           "антивирусом добавьте папку программы в исключения: "
                           "WinDivert — легитимный драйвер, но эвристики относят "
                           "его к «хакерским инструментам».",
                 bg=T.CARD_ALT, fg=T.TEXT_DIM, font=ft("text", 12),
                 justify="left", wraplength=sp(800)).pack(anchor="w")

    # ------------------------------------------------------------ navigation
    def show_page(self, key: str, animate: bool = True):
        key = {"log": "network"}.get(key, key)
        if key not in self.pages or key == self._page:
            return
        tk.Misc.lift(self.pages[key])
        for name, item in self.nav.items():
            if item.active != (name == key):
                item.set_active(name == key)
        if self._toast is not None and self._toast.winfo_ismapped():
            tk.Misc.lift(self._toast)
        self._page = key

    # ------------------------------------------------------- engine updates
    def _start_engine_updates(self):
        if not self.cfg.auto_update_engines:
            self._finish_engine_updates()
            return
        threading.Thread(target=self._engine_update_work, daemon=True,
                         name="engine-update").start()

    def _ui_log(self, text, level="muted"):
        try:
            self.after(0, lambda t=str(text), l=level: self.log(t, l))
        except Exception:
            pass

    def _engine_update_work(self):
        installed: list[dict] = []
        try:
            updates = engine_update.check_updates(ENGINE_DIR)
            available = [u for u in updates if u["newer"] and not u["error"]]
            errors = [u for u in updates if u["error"]]
            if errors and not available:
                self._ui_log("Не удалось проверить обновления движков: "
                             + errors[0]["error"], "warn")
                return
            if not available:
                return

            titles = ", ".join(u["title"] for u in available)
            self._ui_log(f"Найдены обновления движков: {titles}", "accent")
            self._updating_engine = True
            was_running = self.engine.is_running()
            if was_running:
                self._ui_log("Останавливаю защиту на время обновления…", "info")
                self.engine.stop(silent=True)
                time.sleep(0.6)

            for item in available:
                self._ui_log(f"Обновление {item['title']}…", "info")
                try:
                    result = engine_update.update_one(
                        ENGINE_DIR, item["name"], tag_override=item["tag"],
                        log=lambda msg: self._ui_log("    " + str(msg)))
                except Exception as exc:
                    self._ui_log(f"Не удалось обновить {item['title']}: {exc}",
                                 "err")
                    continue
                if result.get("updated"):
                    installed.append(result)

            if installed:
                self.after(0, lambda: self._after_engine_update(installed,
                                                                was_running))
        except Exception as exc:
            self._ui_log(f"Не удалось проверить обновления движков: {exc}", "warn")
        finally:
            self._updating_engine = False
            try:
                self.after(0, self._finish_engine_updates)
            except Exception:
                pass

    def _after_engine_update(self, installed: list[dict], was_running: bool):
        try:
            self.lbl_engine_versions.configure(text=self._engine_line())
        except Exception:
            pass
        for res in installed:
            old = res.get("old") or "—"
            self.log(f"Движок {res['title']} обновлён: {old} → {res['new']}",
                     "ok")
        if len(installed) == 1:
            res = installed[0]
            self.toast(f"Движок {res['title']} обновлён до {res['new']}")
        else:
            self.toast(f"Обновлено движков: {len(installed)}")
        if was_running and self.is_admin and not self.engine.is_running():
            self.log("Перезапуск защиты после обновления…", "info")
            self._start_engine()

    def _finish_engine_updates(self):
        self._update_done = True
        if (self._auto_start_pending and self.is_admin
                and not self.engine.is_running() and not self._starting):
            self._auto_start_pending = False
            self._start_engine()

    # ---------------------------------------------------------------- engine
    def _toggle_engine(self):
        if self._updating_engine:
            self.toast("Идёт обновление движка — подождите", "warn")
            return
        if self._starting:
            return
        if self.engine.is_running():
            self.engine.stop()
            return
        self._start_engine()

    def _start_engine(self):
        if not self.is_admin:
            self.log("Запуск невозможен: нет прав администратора", "err")
            self.toast("Нужны права администратора", "warn")
            return
        preset = preset_by_id(self.cfg.preset)
        self.log(f"Запуск: {preset.title} ({ENGINE_NAMES.get(preset.engine, '')})",
                 "accent")
        self._starting = True
        self._update_status()
        if not self.engine.start(preset, self.cfg.extra_args, self.cfg.debug_log):
            self._starting = False
            self._update_status()
            self.toast("Не удалось запустить движок", "err")

    def _pump(self):
        try:
            while True:
                ev = self.engine.events.get_nowait()
                kind = ev[0]
                if kind == "started":
                    self.running = True
                    self._starting = False
                    self._refresh()
                    self.log("Движок запущен — " + ev[1], "ok")
                    self.toast("Защита включена")
                elif kind == "stopped":
                    self.running = False
                    self._starting = False
                    self._refresh()
                    self.log("Защита выключена", "info")
                    self.toast("Защита выключена", "info")
                elif kind == "died":
                    self.running = False
                    self._starting = False
                    self._refresh()
                    self.log(f"Движок неожиданно завершился (код {ev[1]}). "
                             f"Проверьте журнал.", "err")
                    self.toast("Движок завершился с ошибкой", "err")
                elif kind == "error":
                    self.running = False
                    self._starting = False
                    self._refresh()
                    self.log(ev[1], "err")
                    self.toast("Ошибка запуска движка", "err")
                elif kind == "log":
                    self.log_view.append("        " + ev[1], ev[2])
        except Exception:
            pass
        self.after(140, self._pump)

    def _refresh(self):
        self._update_status()
        if self.running and getattr(self, "services_hint", None) is not None:
            self.services_hint.configure(text="проверьте, открываются ли сервисы")

    def _tick(self):
        if self.running:
            uptime = self._short_uptime()
            try:
                self.val_uptime.configure(text=uptime)
                preset = preset_by_id(self.cfg.preset)
                self.lbl_side_meta.configure(
                    text=f"{ENGINE_NAMES.get(preset.engine, '')} · {uptime}")
            except Exception:
                pass
        self.after(1000, self._tick)

    def _update_status(self):
        running, starting = self.running, self._starting
        preset = preset_by_id(self.cfg.preset)
        engine_name = ENGINE_NAMES.get(preset.engine, "")
        if starting:
            dot, caption, title = T.AMBER_DOT, "ПОДКЛЮЧЕНИЕ", "Подключение…"
            state, state_col = "Подключение", T.AMBER
        elif running:
            dot, caption, title = T.GREEN_DOT, "ЗАЩИТА АКТИВНА", "Защита включена"
            state, state_col = "Активна", T.GREEN
        else:
            dot, caption, title = T.FAINT, "ЗАЩИТА ВЫКЛЮЧЕНА", "Защита выключена"
            state, state_col = "Выключена", T.TEXT

        self.hero_dot.delete("all")
        draw_dot(self.hero_dot, sp(6), sp(6), sp(8), dot)
        self.side_dot.delete("all")
        draw_dot(self.side_dot, sp(6), sp(6), sp(8), dot)

        self.lbl_hero_status.configure(text=caption)
        self.lbl_hero_title.configure(text=title)
        self.lbl_hero_preset.configure(
            text=f"Пресет «{preset.title}»  ·  {engine_name}")
        self.lbl_hero_desc.configure(text=preset.desc)
        self.val_uptime.configure(text=self._short_uptime() if running else "—")
        self.val_preset.configure(text=preset.title)
        self.val_engine.configure(text=engine_name or "—")

        self.lbl_side_state.configure(text=state, fg=state_col)
        self.lbl_side_preset.configure(text=preset.title)
        meta = engine_name
        if running:
            meta = f"{engine_name} · {self._short_uptime()}"
        self.lbl_side_meta.configure(text=meta)

        enabled = self.is_admin and not starting
        self.power.set_on(running)
        self.power.set_busy(starting)
        self.power.set_enabled(enabled)
        if starting:
            cap = "запуск движка…"
        elif not self.is_admin:
            cap = "нужны права администратора"
        elif running:
            cap = "нажмите, чтобы выключить"
        else:
            cap = "нажмите, чтобы включить"
        self.lbl_power_cap.configure(text=cap)

    # -------------------------------------------------------------- services
    def _set_check_enabled(self, value: bool):
        for btn in self._check_buttons:
            btn.set_enabled(value)

    def _check_services(self):
        if self.checking:
            return
        self.checking = True
        self._net_pending = len(SERVICES)
        if getattr(self, "services_hint", None) is not None:
            self.services_hint.configure(text="проверка…")
        for card in list(self.service_cards.values()) + list(self.net_cards.values()):
            card.set_state("checking")
        self._set_check_enabled(False)
        self._draw_net_summary()
        self.log("Проверка доступности сервисов…", "info")
        self.net.busy = False
        self.net.run()
        self.after(120, self._poll_net)

    def _poll_net(self):
        try:
            while True:
                name, ok, ms, detail = self.net.q.get_nowait()
                for mapping in (self.service_cards, self.net_cards):
                    card = mapping.get(name)
                    if card:
                        card.set_state("ok" if ok else "fail", detail, ms)
                suffix = f", {ms} мс)" if ms else ")"
                self.log(f"{name}: {'доступен' if ok else 'недоступен'} "
                         f"({detail}" + suffix, "ok" if ok else "err")
                self._net_pending -= 1
        except Exception:
            pass
        if self._net_pending > 0:
            self.after(120, self._poll_net)
        else:
            self.checking = False
            self._set_check_enabled(True)
            ok_count = sum(1 for c in self.service_cards.values()
                           if c.state == "ok")
            if getattr(self, "services_hint", None) is not None:
                self.services_hint.configure(
                    text=f"доступно {ok_count} из {len(SERVICES)}")
            self._draw_net_summary()
            if ok_count == len(SERVICES):
                toast_kind = "ok"
            elif ok_count:
                toast_kind = "warn"
            else:
                toast_kind = "err"
            self.toast(f"Проверка завершена: {ok_count} из {len(SERVICES)}",
                       toast_kind)

    def _open_youtube(self):
        webbrowser.open("https://www.youtube.com/")

    # ---------------------------------------------------------------- toast
    def _toast_clear(self):
        for job in self._toast_jobs:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._toast_jobs.clear()

    def toast(self, text: str, kind: str = "ok"):
        if not hasattr(self, "content"):
            return
        self._toast_clear()
        if self._toast is None:
            self._toast = tk.Canvas(self.content, bg=T.BG, highlightthickness=0,
                                    bd=0)
        c = self._toast
        font = ft("text", 12)
        tw = tkfont.Font(font=font).measure(text)
        w = min(sp(440), tw + sp(62))
        h = sp(54)
        pic, pad = shadow_photo(w, h, sp(12), T.CARD, T.HAIR, blur=18,
                                alpha=0.18, dy=6)
        c.configure(width=w + 2 * pad, height=h + 2 * pad)
        c.delete("all")
        c.create_image(0, 0, image=pic, anchor="nw")
        self._toast_pic = pic
        colors = {"ok": T.GREEN_DOT, "err": T.RED_DOT, "warn": T.AMBER_DOT,
                  "info": T.ACCENT}
        draw_dot(c, pad + sp(22), pad + h / 2, sp(9),
                 colors.get(kind, T.GREEN_DOT))
        c.create_text(pad + sp(38), pad + h / 2 + 1, text=text, anchor="w",
                      fill=T.TEXT, font=font, width=w - sp(50))

        def place_at(y):
            try:
                c.place(relx=1.0, rely=1.0, anchor="se", x=-sp(22), y=y)
                tk.Misc.lift(c)
            except Exception:
                pass

        def hide():
            try:
                c.place_forget()
            except Exception:
                pass

        place_at(sp(10))

        def slide(i=1):
            if i > 5:
                self._toast_jobs.append(self.after(2600, hide))
                return
            place_at(int(sp(10) - (sp(10) + sp(16)) * i / 5))
            self._toast_jobs.append(self.after(16, lambda: slide(i + 1)))

        slide()

    # ----------------------------------------------------------------- close
    def _on_close(self):
        try:
            self.engine.cleanup()
        except Exception:
            pass
        self.destroy()


def main():
    autostart = "--autostart" in sys.argv or os.environ.get("FDPI_AUTOSTART") == "1"
    minimize = "--autostart" in sys.argv
    if not eng.single_instance():
        root = tk.Tk()
        root.withdraw()
        from tkinter import messagebox
        messagebox.showinfo(APP_NAME, "MarinByPass уже запущен.")
        root.destroy()
        return
    eng.ensure_dirs()
    try:
        eng.ensure_engine()
    except Exception as exc:
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(APP_NAME, f"Не удалось распаковать движок:\n{exc}")
        r.destroy()
        return
    eng.kill_own_stale()
    app = App(autostart=autostart, minimize=minimize)
    app.mainloop()


if __name__ == "__main__":
    main()
