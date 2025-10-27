from users import views
from django.urls import include, path
from rest_framework import routers


router = routers.DefaultRouter()
router.register(r"", views.UserViewSet, basename="users")

urlpatterns = [
    path("", include(router.urls)),
]
