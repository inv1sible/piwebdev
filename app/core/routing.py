from django.urls import path
from .consumers import PiConsumer, TerminalConsumer

websocket_urlpatterns = [
    path("ws/sessions/<int:session_id>/", PiConsumer.as_asgi()),
    path("ws/terminal/<int:terminal_id>/", TerminalConsumer.as_asgi()),
]
