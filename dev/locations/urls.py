from locations import views
from django.urls import include, path
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r"countries", views.CountryViewSet)
router.register(r"provinces", views.ProvinceViewSet)
router.register(r"cities", views.CityViewSet)
router.register(r"addresses", views.AddressViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
