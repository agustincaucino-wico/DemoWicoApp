from django.urls import path, include
from rest_framework import routers
from .views import RedeemPromotionView, PromotionalImageViewSet

router = routers.DefaultRouter()
router.register(r"images", PromotionalImageViewSet, basename="promotional-images")

urlpatterns = [
    path("redeem/", RedeemPromotionView.as_view(), name="redeem-promotion"),
    path("", include(router.urls)),
]
