from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from users.serializers import UserSerializer, SettingSerializer
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.permissions import DjangoModelOrTargetUser, DjangoModelPermissionsOrOwner
from django.contrib.auth import get_user_model
from .models import Setting

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be created, viewed or edited.
    """

    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [DjangoModelOrTargetUser]

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated],
    )
    def me(self, request):
        """Return the current authenticated user's data."""
        serializer = self.get_serializer(request.user)
        data = serializer.data.copy()
        data.pop("id", None)
        return Response(data)


class SettingViewSet(
    mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    queryset = Setting.objects.all()
    serializer_class = SettingSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [DjangoModelPermissionsOrOwner]

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated],
    )
    def me(self, request):
        """Return the current authenticated user's settings."""
        setting, created = Setting.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(setting)
        data = serializer.data.copy()
        data.pop("user", None)
        return Response(data)
