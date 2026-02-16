from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import UserUsage

@receiver(post_save, sender=User)
def create_user_usage(sender, instance, created, **kwargs):
    if created:
        UserUsage.objects.create(user=instance)
