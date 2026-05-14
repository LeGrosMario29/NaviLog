import customtkinter as ctk

class Fonts:
    FONT_TITLE  = None
    FONT_LABEL  = None
    FONT_VALUE  = None
    FONT_SMALL  = None
    FONT_BIG    = None
    FONT_MEDIUM = None

    @classmethod
    def init(cls):
        cls.FONT_TITLE  = ctk.CTkFont(family="Courier New", size=16, weight="bold")
        cls.FONT_LABEL  = ctk.CTkFont(family="Courier New", size=14)
        cls.FONT_SMALL  = ctk.CTkFont(family="Courier New", size=12)
        cls.FONT_VALUE  = ctk.CTkFont(family="Courier New", size=19, weight="bold")
        cls.FONT_BIG    = ctk.CTkFont(family="Courier New", size=26, weight="bold")
        cls.FONT_MEDIUM = ctk.CTkFont(family="Courier New", size=20, weight="bold")

class Colors:
    # ── Palette marine sombre ───────────────────────────────────────────────────
    BG       = "#0d1b2a"
    BG2      = "#1b2d3e"
    BG3      = "#24404f"
    ACCENT   = "#00b4d8"
    ACCENT2  = "#48cae4"
    WARN     = "#f4a261"
    OK       = "#52b788"
    TEXT     = "#e0f4ff"
    TEXT2    = "#90b8cc"
    TEXT_DIM = "#506070"
    RED      = "#e63946"