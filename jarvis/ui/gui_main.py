import flet as ft
from jarvis.main_loop import Jarvis
from jarvis.ui.display import Display
import threading

def main(page: ft.Page):
    # Setup floating window properties
    page.title = "Jarvis UI"
    page.window.width = 400
    page.window.height = 600
    page.window.always_on_top = True
    page.window.frameless = False # Let's keep framing for now so user can move it
    page.theme_mode = "dark"
    page.padding = 10
    
    # Initialize Jarvis
    jarvis = Jarvis()

    # Chat history view
    chat_view = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=True,
    )

    def append_message(text: str, msg_type: str):
        color = ft.Colors.WHITE
        icon = None
        alignment = "start"

        if msg_type == "user":
            color = ft.Colors.BLUE_200
            alignment = "end"
        elif msg_type == "error":
            color = ft.Colors.RED_400
            icon = "❌"
        elif msg_type == "success":
            color = ft.Colors.GREEN_400
            icon = "✅"
        elif msg_type == "warning":
            color = ft.Colors.AMBER_400
            icon = "⚠️"
        elif msg_type == "status":
            color = ft.Colors.GREY_500
            icon = "ℹ️"

        row_controls = []
        if icon and alignment == "start":
            row_controls.append(ft.Text(icon, size=16))
        
        row_controls.append(ft.Text(text, color=color, selectable=True, width=300))
        
        chat_view.controls.append(
            ft.Row(
                controls=row_controls,
                alignment=alignment,
                vertical_alignment="start"
            )
        )
        page.update()

    # Register Display callback before running Jarvis initialization
    Display.set_callback(append_message)

    # Input handlers
    def submit_command(e):
        cmd = user_input.value.strip()
        if not cmd:
            return
        append_message(cmd, "user")
        user_input.value = ""
        user_input.focus()
        page.update()
        
        # Run in thread so UI doesn't freeze
        threading.Thread(target=jarvis.process_command, args=(cmd,), daemon=True).start()

    def submit_voice(e):
        # Trigger voice via thread
        threading.Thread(target=jarvis.process_command, args=("",), daemon=True).start()

    user_input = ft.TextField(
        hint_text="Ask Jarvis...",
        expand=True,
        on_submit=submit_command,
        border_radius=20,
        filled=True
    )
    
    voice_btn = ft.ElevatedButton(
        text="🎤 Voice",
        on_click=submit_voice,
        color=ft.Colors.BLUE_400
    )

    send_btn = ft.ElevatedButton(
        text="➤ Send",
        on_click=submit_command,
        color=ft.Colors.BLUE_400
    )

    bottom_row = ft.Row([user_input, voice_btn, send_btn])

    page.add(
        ft.Container(
            content=ft.Column([
                chat_view,
                bottom_row
            ]),
            expand=True,
        )
    )

    # Start Jarvis setup
    threading.Thread(target=jarvis.run, daemon=True).start()

if __name__ == "__main__":
    ft.app(target=main)
