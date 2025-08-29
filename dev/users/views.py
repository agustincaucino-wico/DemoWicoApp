# from django.contrib.auth.models import
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import permissions, viewsets
from rest_framework.decorators import action

from users.serializers import UserSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsStaffOrTargetUser
from django.contrib.auth import get_user_model

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be created, viewed or edited.
    """

    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsStaffOrTargetUser]

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated],
    )
    def me(self, request):
        """Return the current authenticated user's data."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
