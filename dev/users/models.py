from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from users.managers import CustomUserManager
from django.utils import timezone


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(
        unique=True,
        error_messages={"unique": "El correo electrónico ya se encuentra registrado."},
    )
    dni = models.CharField(
        max_length=20,
        unique=True,
        error_messages={"unique": "El DNI ya se encuentra registrado."},
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_joined = models.DateTimeField(default=timezone.now)
    id_province = models.ForeignKey(
        "locations.Province", on_delete=models.SET_NULL, null=True, blank=True
    )
    id_city = models.ForeignKey(
        "locations.City", on_delete=models.SET_NULL, null=True, blank=True
    )
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    gender = models.CharField(
        max_length=10,
        choices=[("M", "Masculino"), ("F", "Femenino"), ("X", "No binario")],
        default="X",
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_authorized_holder = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []  # Only email is required for creating superuser

    objects = CustomUserManager()

    def __str__(self):
        return self.email


class Setting(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, primary_key=True)
    push_notif = models.BooleanField(default=True)
    email_notif = models.BooleanField(default=True)

    def __str__(self):
        return f"Settings for {self.user.email}"
