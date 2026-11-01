# -*- coding: utf-8 -*-
"""一次性修复：_repaint_nav 支持折叠模式（240/64），并同步 settings 默认值。"""
import ast
import re

# ── app.py：重写 _repaint_nav 条目部分，支持 collapsed ──
p = "src/netwright/app.py"
s = open(p, encoding="utf-8").read()

old_block = '''        rail.delete("items")
        y = 12
        rail.create_text(14, y, text="工 作 区", anchor="w", fill=theme.muted,
                         font=FONT_SMALL, tags="items")
        y += 34
        for key, (name, icon, _cls) in PAGE_REGISTRY.items():
            active = key == getattr(self, "_active_key", "")
            hover = key == getattr(self, "_hover_key", "")
            if active:
                rail.create_rectangle(8, y - 4, w - 8, y + 30,
                                      fill=theme.accent_deep, outline="", width=0,
                                      tags="items")
            elif hover:
                rail.create_rectangle(8, y - 4, w - 8, y + 30,
                                      fill=_lerp(theme.nav1, "#ffffff", 0.10),
                                      outline="", width=0, tags="items")
            fg = "#ffffff" if active or hover else theme.muted
            rail.create_text(18, y + 12, text=f"{icon}  {name}", anchor="w",
                             fill=fg,
                             font=("Microsoft YaHei UI", 11,
                                   "bold" if active else "normal"),
                             tags=("items", f"nav:{key}"))
            self._nav_rects[key] = y
            y += 38'''

new_block = '''        rail.delete("items")
        collapsed = getattr(self, "nav_collapsed", False)
        y = 12
        if not collapsed:
            rail.create_text(14, y, text="工 作 区", anchor="w", fill=theme.muted,
                             font=FONT_SMALL, tags="items")
            y += 34
        for key, (name, icon, _cls) in PAGE_REGISTRY.items():
            active = key == getattr(self, "_active_key", "")
            hover = key == getattr(self, "_hover_key", "")
            if active:
                rail.create_rectangle(8 if not collapsed else 10, y - 4,
                                      w - 8 if not collapsed else w - 10, y + 34,
                                      fill=theme.accent_soft, outline="", width=0,
                                      tags="items")
                rail.create_rectangle(0, y - 4, 3, y + 34,
                                      fill=theme.accent, outline="", width=0,
                                      tags="items")
            elif hover:
                rail.create_rectangle(8 if not collapsed else 10, y - 4,
                                      w - 8 if not collapsed else w - 10, y + 34,
                                      fill=theme.panel_alt, outline="", width=0,
                                      tags="items")
            if collapsed:
                rail.create_text(w / 2, y + 14, text=icon, fill=theme.fg if active
                                 else theme.muted, font=("", 14),
                                 tags=("items", f"nav:{key}"))
            else:
                fg = theme.accent if active else theme.muted
                rail.create_text(18, y + 12, text=f"{icon}  {name}", anchor="w",
                                 fill=fg,
                                 font=("Microsoft YaHei UI", 11,
                                       "bold" if active else "normal"),
                                 tags=("items", f"nav:{key}"))
            self._nav_rects[key] = y
            y += 40'''

assert old_block in s, "old nav block not found"
s = s.replace(old_block, new_block, 1)

# _build_nav 里的点击命中区域行高同步 40
s = s.replace('''    def _nav_hit(self, y: int) -> str | None:
        for key, top in self._nav_rects.items():
            if top - 6 <= y <= top + 32:
                return key
        return None''',
'''    def _nav_hit(self, y: int) -> str | None:
        for key, top in self._nav_rects.items():
            if top - 6 <= y <= top + 38:
                return key
        return None''')

# toggle_nav 已存在则确认；不存在则补
if "def toggle_nav" not in s:
    s = s.replace("    def _nav_hit(self, y: int)",
'''    def toggle_nav(self):
        """侧栏折叠 240 ↔ 64。"""
        self.nav_collapsed = not getattr(self, "nav_collapsed", False)
        self.rail.config(width=64 if self.nav_collapsed else 240)
        self._repaint_nav(full=True)

    def _nav_hit(self, y: int)''')

# 侧栏默认宽 240（旧 172）
s = s.replace("w = max(rail.winfo_width(), 172)", "w = max(rail.winfo_width(), 240)")
s = s.replace("self.rail = tk.Canvas(main, width=172,", "self.rail = tk.Canvas(main, width=240,")
open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("app nav collapsed-mode OK")

# ── settings.py 默认值 ──
p2 = "src/netwright/lib/settings.py"
s2 = open(p2, encoding="utf-8").read()
s2 = re.sub(r'DEFAULTS = \{[^}]*\}',
            'DEFAULTS = {"theme_mode": "light", "theme_hue": "蓝", "rest_port": 8899,\n            "last_page": "dashboard"}',
            s2, count=1)
open(p2, "w", encoding="utf-8").write(s2)
ast.parse(s2)
print("settings defaults OK")
