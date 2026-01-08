from django.db import models
from django.utils import timezone
from users.models import CustomUser


class PromotionCode(models.Model):
    ACTION_CHOICES = [
        ("CREATE_HOLDER_ACCOUNT", "Crear Cuenta Titular"),
        ("GIFT_BALANCE", "Regalar Saldo"),
    ]

    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES)
    action_params = models.JSONField(default=dict, blank=True)

    # Usage limits (null = unlimited)
    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Número máximo de veces que puede ser canjeado (vacío = ilimitado)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_current_uses(self):
        """Returns the number of times this code has been redeemed"""
        return self.redemptions.count()

    def has_uses_remaining(self):
        """Check if the code has remaining uses"""
        if self.max_uses is None:
            return True  # Unlimited uses
        return self.get_current_uses() < self.max_uses

    def is_valid(self):
        now = timezone.now()
        if not self.active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        if not self.has_uses_remaining():
            return False
        return True

    def __str__(self):
        return self.code


class PromotionRedemption(models.Model):
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="redemptions"
    )
    promotion_code = models.ForeignKey(
        PromotionCode, on_delete=models.CASCADE, related_name="redemptions"
    )
    redeemed_at = models.DateTimeField(auto_now_add=True)
    amount_gifted = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Saldo regalado (si aplica)",
    )

    class Meta:
        indexes = [
            models.Index(fields=["user", "promotion_code"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.promotion_code.code} - {self.redeemed_at.strftime('%Y-%m-%d %H:%M')}"
