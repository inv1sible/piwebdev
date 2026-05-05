import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "piwebdev.settings")

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

http_app = get_asgi_application()

from core.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": http_app,
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
