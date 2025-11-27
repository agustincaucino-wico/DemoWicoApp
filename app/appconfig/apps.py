from django.apps import AppConfig as DjangoAppConfig


class AppconfigConfig(DjangoAppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "appconfig"
    verbose_name = "Configuración de la App"
