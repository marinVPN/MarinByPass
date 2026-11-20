"""Описание стратегий обхода DPI."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _zapret2_base(root: Path):
    return [
        "--lua-init=@" + str(root / "lua" / "zapret-lib.lua"),
        "--lua-init=@" + str(root / "lua" / "zapret-antidpi.lua"),
        "--lua-init=fake_default_tls = tls_mod(fake_default_tls,'rnd,rndsni')",
        "--blob=quic_google:@" + str(root / "files" / "quic_initial_www_google_com.bin"),
    ]


def _zapret2_common_filters(root: Path):
    wf = root / "windivert.filter"
    return [
        "--wf-raw-part=@" + str(wf / "windivert_part.discord_media.txt"),
        "--wf-raw-part=@" + str(wf / "windivert_part.stun.txt"),
        "--wf-raw-part=@" + str(wf / "windivert_part.wireguard.txt"),
        "--wf-raw-part=@" + str(wf / "windivert_part.quic_initial_ietf.txt"),
    ]


def args_universal(root: Path):
    return (
        ["--wf-tcp-out=80,443"]
        + _zapret2_base(root)
        + _zapret2_common_filters(root)
        + [
            "--filter-tcp=80", "--filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-2,3-20:ip6_autottl=-2,3-20:tcp_md5",
            "--lua-desync=fakedsplit:ip_autottl=-2,3-20:ip6_autottl=-2,3-20:tcp_md5",
            "--new",
            "--filter-tcp=443", "--filter-l7=tls",
            "--hostlist=" + str(root / "files" / "list-youtube.txt"),
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=11:tls_mod=rnd,dupsid,sni=www.google.com",
            "--lua-desync=multidisorder:pos=1,midsld",
            "--new",
            "--filter-tcp=443", "--filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_md5:tcp_seq=-10000:repeats=6",
            "--lua-desync=multidisorder:pos=midsld",
            "--new",
            "--filter-udp=443", "--filter-l7=quic",
            "--hostlist=" + str(root / "files" / "list-youtube.txt"),
            "--payload=quic_initial",
            "--lua-desync=fake:blob=quic_google:repeats=11",
            "--new",
            "--filter-udp=443", "--filter-l7=quic",
            "--payload=quic_initial",
            "--lua-desync=fake:blob=fake_default_quic:repeats=11",
            "--new",
            "--filter-l7=wireguard,stun,discord",
            "--payload=wireguard_initiation,wireguard_cookie,stun,discord_ip_discovery",
            "--lua-desync=fake:blob=0x00000000000000000000000000000000:repeats=2",
        ]
    )


def args_youtube(root: Path):
    return (
        ["--wf-tcp-out=80,443"]
        + _zapret2_base(root)
        + [
            "--filter-tcp=443", "--filter-l7=tls",
            "--hostlist=" + str(root / "files" / "list-youtube.txt"),
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=11:tls_mod=rnd,dupsid,sni=www.google.com",
            "--lua-desync=multidisorder:pos=1,midsld",
            "--new",
            "--filter-udp=443", "--filter-l7=quic",
            "--hostlist=" + str(root / "files" / "list-youtube.txt"),
            "--payload=quic_initial",
            "--lua-desync=fake:blob=quic_google:repeats=11",
        ]
    )


def args_wireguard(root: Path):
    return (
        _zapret2_base(root)
        + ["--lua-init=@" + str(root / "lua" / "zapret-auto.lua")]
        + [
            "--wf-raw-part=@" + str(root / "windivert.filter" / "windivert_part.wireguard.txt"),
            "--filter-l7=wireguard",
            "--payload=wireguard_initiation",
            "--lua-desync=repeater:instances=2:repeats=3",
            '--lua-desync=luaexec:code="desync.rnd=brandom(math.random(32,64))"',
            "--lua-desync=fake:blob=rnd",
        ]
    )


def args_zapret1(root: Path):
    """Классический рабочий пресет zapret 1 (winws.exe)."""
    return [
        "--wf-tcp=80,443",
        "--wf-raw-part=@" + str(root / "windivert.filter" / "windivert_part.discord_media.txt"),
        "--wf-raw-part=@" + str(root / "windivert.filter" / "windivert_part.stun.txt"),
        "--wf-raw-part=@" + str(root / "windivert.filter" / "windivert_part.wireguard.txt"),
        "--wf-raw-part=@" + str(root / "windivert.filter" / "windivert_part.quic_initial_ietf.txt"),
        "--filter-tcp=80",
        "--dpi-desync=fake,fakedsplit",
        "--dpi-desync-autottl=2",
        "--dpi-desync-fooling=md5sig",
        "--new",
        "--filter-tcp=443",
        "--hostlist=" + str(root / "files" / "list-youtube.txt"),
        "--dpi-desync=fake,multidisorder",
        "--dpi-desync-split-pos=1,midsld",
        "--dpi-desync-repeats=11",
        "--dpi-desync-fooling=md5sig",
        "--dpi-desync-fake-tls-mod=rnd,dupsid,sni=www.google.com",
        "--new",
        "--filter-tcp=443",
        "--dpi-desync=fake,multidisorder",
        "--dpi-desync-split-pos=midsld",
        "--dpi-desync-repeats=6",
        "--dpi-desync-fooling=badseq,md5sig",
        "--new",
        "--filter-l7=quic",
        "--hostlist=" + str(root / "files" / "list-youtube.txt"),
        "--dpi-desync=fake",
        "--dpi-desync-repeats=11",
        "--dpi-desync-fake-quic=" + str(root / "files" / "quic_initial_www_google_com.bin"),
        "--new",
        "--filter-l7=quic",
        "--dpi-desync=fake",
        "--dpi-desync-repeats=11",
    ]


@dataclass
class Preset:
    id: str
    title: str
    desc: str
    engine: str
    args_fn: callable
    recommended: bool = False
    tag: str = ""
    needs: tuple = ()

    def badges(self):
        """Пара (текст, семантический тип) — оформление задаёт интерфейс."""
        engines = {"zapret2": "engine", "zapret1": "engine", "goodbyedpi": "engine"}
        out = [(ENGINE_NAMES.get(self.engine, self.engine),
                engines.get(self.engine, "engine"))]
        if self.recommended:
            out.append(("рекомендуется", "recommended"))
        if self.tag:
            out.append((self.tag, "tag"))
        return out


PRESETS = [
    Preset(
        id="z2-universal",
        title="Универсальный",
        desc="YouTube, Discord, Google, QUIC и медиа. Лучший выбор для большинства провайдеров.",
        engine="zapret2",
        args_fn=args_universal,
        recommended=True,
    ),
    Preset(
        id="z2-youtube",
        title="Только YouTube и Google",
        desc="Воздействует лишь на домены YouTube/Google — минимальное вмешательство в трафик.",
        engine="zapret2",
        args_fn=args_youtube,
    ),
    Preset(
        id="z2-wireguard",
        title="WireGuard / VPN",
        desc="Обход блокировки протокола WireGuard. Для тех, у кого не подключается VPN.",
        engine="zapret2",
        args_fn=args_wireguard,
        tag="VPN",
    ),
    Preset(
        id="z1-classic",
        title="Классический Zapret",
        desc="Проверенная стратегия первого поколения. Запасной вариант, если Zapret 2 не подошёл.",
        engine="zapret1",
        args_fn=args_zapret1,
    ),
    Preset(
        id="gdpi-blacklist",
        title="Режим 5 · чёрный список РФ",
        desc="Фрагментация пакетов по чёрному списку доменов РФ. Без вмешательства в остальной трафик.",
        engine="goodbyedpi",
        args_fn=lambda root: ["-5", "--blacklist", str(root / "russia-blacklist.txt")],
        tag="запасной",
    ),
    Preset(
        id="gdpi-dns",
        title="Режим 5 + подмена DNS",
        desc="То же самое плюс подмена DNS на Яндекс DNS (обходит подмену адресов провайдером).",
        engine="goodbyedpi",
        args_fn=lambda root: [
            "-5", "--dns-addr", "77.88.8.8", "--dns-port", "1253",
            "--dnsv6-addr", "2a02:6b8::feed:0ff", "--dnsv6-port", "1253",
            "--blacklist", str(root / "russia-blacklist.txt"),
        ],
        tag="запасной",
    ),
]

PRESET_MAP = {p.id: p for p in PRESETS}
DEFAULT_PRESET = "z2-universal"

ENGINE_NAMES = {
    "zapret2": "Zapret 2",
    "zapret1": "Zapret 1",
    "goodbyedpi": "GoodbyeDPI",
}


def preset_by_id(pid: str) -> Preset:
    return PRESET_MAP.get(pid, PRESET_MAP[DEFAULT_PRESET])
