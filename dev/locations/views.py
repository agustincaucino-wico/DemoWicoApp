from rest_framework import mixins, viewsets
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.authentication import JWTAuthentication
from locations.permissions import IsAdminOrReadOnly

from .models import Country, Province, City, Address
from .serializers import (
    CountrySerializer,
    ProvinceSerializer,
    CitySerializer,
    AddressSerializer,
)


class BaseLCViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminOrReadOnly]


class CountryViewSet(BaseLCViewSet):
    """
    API endpoint that allows countries to be created, viewed or deleted.
    """

    queryset = Country.objects.all().order_by("id")
    serializer_class = CountrySerializer


class ProvinceViewSet(BaseLCViewSet):
    """
    API endpoint that allows provinces to be created, viewed or deleted.
    """

    serializer_class = ProvinceSerializer
    queryset = Province.objects.all().order_by("id")

    def get_queryset(self):
        qs = Province.objects.select_related("country").order_by("id")
        return qs


class CityViewSet(BaseLCViewSet):
    """
    API endpoint that allows cities to be created, viewed or deleted.
    """

    queryset = City.objects.all().order_by("id")
    serializer_class = CitySerializer

    def get_queryset(self):
        qs = City.objects.select_related("province", "province__country").order_by("id")
        province_id = self.request.query_params.get("province_id")
        if province_id:
            qs = qs.filter(province_id=province_id)
        return qs

    def perform_create(self, serializer):
        province_id = self.request.query_params.get(
            "province_id"
        ) or self.request.data.get("province")
        if province_id and not self.request.data.get("province"):
            province = get_object_or_404(Province, pk=province_id)
            serializer.save(province=province)
        else:
            serializer.save()


class AddressViewSet(BaseLCViewSet):
    """
    API endpoint that allows addresses to be created, viewed or deleted.
    """

    queryset = Address.objects.all().order_by("id")
    serializer_class = AddressSerializer

    def get_queryset(self):
        qs = Address.objects.select_related(
            "city", "city__province", "city__province__country"
        ).order_by("id")
        city_id = self.request.query_params.get("city_id")
        if city_id:
            qs = qs.filter(city_id=city_id)
        return qs

    def perform_create(self, serializer):
        city_id = self.request.query_params.get("city_id") or self.request.data.get(
            "city"
        )
        if city_id and not self.request.data.get("city"):
            city = get_object_or_404(City, pk=city_id)
            serializer.save(city=city)
        else:
            serializer.save()
