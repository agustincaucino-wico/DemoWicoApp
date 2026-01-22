from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from users.admin import my_admin_site
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from users.views import CustomTokenObtainPairView
from .views import HealthCheckView, AdminSpectacularAPIView, AdminSpectacularSwaggerView

urlpatterns = [
    path("", HealthCheckView.as_view(), name="root"),
    path("admin/", my_admin_site.urls),
    path("users/", include("users.urls")),
    path("locations/", include("locations.urls")),
    path("accounts/", include("accounts.urls")),
    path("stations/", include("stations.urls")),
    path("operations/", include("operation.urls")),
    path("actions/", include("actions.urls")),
    path("support/", include("support.urls")),
    path("notifications/", include("notifications.urls")),
    path("promotions/", include("promotions.urls")),
    path("appconfig/", include("appconfig.urls")),
    # JWT authentication
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # API schema (admin only)
    path(
        "docs/",
        AdminSpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/schema/", AdminSpectacularAPIView.as_view(), name="schema"),
    path("health/", HealthCheckView.as_view(), name="health_check"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
