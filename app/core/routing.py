from django.urls import path
from .consumers import PiConsumer

websocket_urlpatterns = [
    path("ws/sessions/<int:session_id>/", PiConsumer.as_asgi()),
]
