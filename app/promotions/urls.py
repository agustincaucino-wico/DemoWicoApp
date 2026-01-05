from django.urls import path
from .views import RedeemPromotionView

urlpatterns = [
    path('redeem/', RedeemPromotionView.as_view(), name='redeem-promotion'),
]
