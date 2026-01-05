from django.db import models
from django.utils import timezone
from users.models import CustomUser

class PromotionCode(models.Model):
    ACTION_CHOICES = [
        ('CREATE_HOLDER_ACCOUNT', 'Crear Cuenta Titular'),
    ]

    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES)
    action_params = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_valid(self):
        now = timezone.now()
        if not self.active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        return True

    def __str__(self):
        return self.code

class PromotionRedemption(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='redemptions')
    promotion_code = models.ForeignKey(PromotionCode, on_delete=models.CASCADE, related_name='redemptions')
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'promotion_code'], name='unique_user_code_redemption')
        ]

    def __str__(self):
        return f"{self.user.email} - {self.promotion_code.code}"
