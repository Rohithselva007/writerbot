from django.urls import path
from .views import generate_text,stripe_webhook

urlpatterns = [
    path('generate/', generate_text),
    path('stripe-webhook/', stripe_webhook),
]
