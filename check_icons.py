import flet as ft
with open("icon_test.txt", "w") as f:
    icons = [i for i in dir(ft.icons) if "MIC" in i.upper() or "VOICE" in i.upper()]
    f.write("\n".join(icons))
