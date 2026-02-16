from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Story(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="stories"
    )

    title = models.CharField(max_length=255)
    genre = models.CharField(max_length=100)

    description = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return self.title


class Chapter(models.Model):
    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="chapters"
    )

    title = models.CharField(max_length=255)
    content = models.TextField()

    order = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        unique_together = ("story", "order")
        indexes = [
            models.Index(fields=["story"]),
        ]

    def __str__(self):
        return f"{self.story.title} - Chapter {self.order}"

    daily_generations = models.IntegerField(default=0)
    last_reset = models.DateField(default=timezone.now)

    subscription_tier = models.CharField(
        max_length=50,
        default="free"  # free | pro | creator
    )

    def reset_if_needed(self):
        today = timezone.now().date()
        if self.last_reset != today:
            self.daily_generations = 0
            self.last_reset = today
            self.save()

    def __str__(self):
        return f"{self.user.username} - {self.subscription_tier}"

from django.utils import timezone
from django.db import models
from django.conf import settings


class Usage(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    daily_generations = models.IntegerField(default=0)
    last_reset = models.DateField(default=timezone.now)
    subscription_tier = models.CharField(
        max_length=20,
        default="free"
    )

    def reset_if_needed(self):
        today = timezone.now().date()
        if self.last_reset != today:
            self.daily_generations = 0
            self.last_reset = today
            self.save()
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_usage(sender, instance, created, **kwargs):
    if created:
        Usage.objects.create(user=instance)
