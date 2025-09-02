from accounts import views
from django.urls import include, path
from rest_framework import routers

router = routers.DefaultRouter()
# router.register(r"countries", views.CountryViewSet)


urlpatterns = [
    path("", include(router.urls)),
]
