import requests
import stripe
import json

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response

from .models import Story, Chapter


# ===============================
# CONFIG
# ===============================

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"
FREE_DAILY_LIMIT = 10

stripe.api_key = settings.STRIPE_SECRET_KEY
User = get_user_model()


# ===============================
# PROMPT BUILDER
# ===============================

def build_prompt(data, context=""):
    return f"""
You are InkForge, a professional storytelling AI.

Story Context:
{context}

Task Type: {data.get('type')}
Genre: {data.get('genre')}
Tone: {data.get('tone')}
Length: {data.get('length')}

User Idea:
{data.get('prompt')}

Write polished, immersive, high-quality content.
"""


# ===============================
# AI TEXT GENERATION (STREAMING)
# ===============================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_text(request):
    try:
        usage = request.user.usage

        # Reset daily usage if needed
        today = timezone.now().date()
        if usage.last_reset != today:
            usage.daily_generations = 0
            usage.last_reset = today
            usage.save()

        # Enforce free tier limit
        if (
            usage.subscription_tier == "free"
            and usage.daily_generations >= FREE_DAILY_LIMIT
        ):
            return Response({
                "success": False,
                "error": "Daily free limit reached."
            }, status=403)

        story_id = request.data.get("story_id")
        context = ""

        if story_id:
            story = get_object_or_404(Story, id=story_id, user=request.user)
            chapters = Chapter.objects.filter(story=story).order_by("order")
            context = "\n\n".join([c.content for c in chapters])

        prompt = build_prompt(request.data, context)

        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": True,
            },
            stream=True,
            timeout=120,
        )

        response.raise_for_status()

        def stream_generator():
            full_text = ""

            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("response", "")
                    full_text += token
                    yield token

            # Increment usage AFTER generation completes
            usage.daily_generations += 1
            usage.save()

        return StreamingHttpResponse(
            stream_generator(),
            content_type="text/plain"
        )

    except requests.exceptions.Timeout:
        return Response({
            "success": False,
            "error": "Model took too long to respond."
        }, status=status.HTTP_504_GATEWAY_TIMEOUT)

    except requests.exceptions.ConnectionError:
        return Response({
            "success": False,
            "error": "Cannot connect to AI engine."
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    except Exception as e:
        return Response({
            "success": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===============================
# STRIPE CHECKOUT
# ===============================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{
                "price": "YOUR_STRIPE_PRICE_ID",
                "quantity": 1,
            }],
            success_url="http://localhost:3000/success",
            cancel_url="http://localhost:3000/cancel",
            customer_email=request.user.email,
        )

        return Response({"id": session.id})

    except Exception as e:
        return Response({"error": str(e)}, status=400)


# ===============================
# STRIPE WEBHOOK (UPGRADE + DOWNGRADE)
# ===============================

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    if not sig_header:
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        return HttpResponse(status=400)

    event_type = event["type"]

    # ===============================
    # UPGRADE TO PRO
    # ===============================
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_email")

        if email:
            try:
                user = User.objects.get(email=email)
                usage = user.usage
                usage.subscription_tier = "pro"
                usage.save()
            except User.DoesNotExist:
                pass

    # ===============================
    # DOWNGRADE TO FREE
    # ===============================
    elif event_type in [
        "customer.subscription.deleted",
        "invoice.payment_failed"
    ]:
        subscription = event["data"]["object"]
        customer_email = subscription.get("customer_email")

        if customer_email:
            try:
                user = User.objects.get(email=customer_email)
                usage = user.usage
                usage.subscription_tier = "free"
                usage.save()
            except User.DoesNotExist:
                pass

    return HttpResponse(status=200)
