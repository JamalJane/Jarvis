import inspect
import flet as ft

with open("flet_inspect_out.txt", "w") as f:
    f.write("=== flet version ===\n")
    f.write(str(ft.__version__) + "\n")
    
    f.write("\n=== ft.Icon signature ===\n")
    f.write(str(inspect.signature(ft.Icon.__init__)) + "\n")
    
    f.write("\n=== ft.IconButton signature ===\n")
    f.write(str(inspect.signature(ft.IconButton.__init__)) + "\n")
