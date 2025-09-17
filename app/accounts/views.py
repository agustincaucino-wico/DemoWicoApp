from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.decorators import action
from rest_framework.response import Response

from users.serializers import UserSerializer
from .permissions import DjangoModelOrObjectOwner


from .models import (
    Account,
    Dependents,
    Plates,
    AuthorizedPlate,
    Company,
    CompanyAssignment,
)
from .serializers import (
    AccountSerializer,
    DependentsSerializer,
    PlatesSerializer,
    AuthorizedPlateSerializer,
    CompanySerializer,
    CompanyAssignmentSerializer,
)


class BaseLCViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [DjangoModelPermissions]


class AccountViewSet(BaseLCViewSet):
    queryset = Account.objects.all().order_by("id")
    serializer_class = AccountSerializer


class DependentsViewSet(BaseLCViewSet):
    queryset = Dependents.objects.all().order_by("id")
    serializer_class = DependentsSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class PlatesViewSet(BaseLCViewSet):
    queryset = Plates.objects.all().order_by("id")
    serializer_class = PlatesSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class AuthorizedPlateViewSet(BaseLCViewSet):
    queryset = AuthorizedPlate.objects.all().order_by("id")
    serializer_class = AuthorizedPlateSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class CompanyViewSet(BaseLCViewSet):
    queryset = Company.objects.all().order_by("id")
    serializer_class = CompanySerializer


class CompanyAssignmentViewSet(BaseLCViewSet):
    queryset = CompanyAssignment.objects.all().order_by("id")
    serializer_class = CompanyAssignmentSerializer


class UserAccountInfoViewSet(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        user = request.user
        # Get accounts associated to user
        accounts = Account.objects.filter(user=user)
        accounts_data = AccountSerializer(accounts, many=True).data

        # Get dependents data for those accounts
        dependent_relations = Dependents.objects.filter(holder_account__in=accounts)
        dependents_data = []

        for dependent_relation in dependent_relations:
            dependent_account = dependent_relation.dependent_account

            dependent_account_user = dependent_account.user

            dependents_data.append(
                {
                    "dependent_account": AccountSerializer(dependent_account).data,
                    "dependent_user": UserSerializer(dependent_account_user).data,
                }
            )

        # Get plates for those accounts
        plates = Plates.objects.filter(holder_account__in=accounts)
        plates_data = PlatesSerializer(plates, many=True).data

        # Get company assignment and company data
        company_assignment = CompanyAssignment.objects.filter(user=user).first()
        company_data = None
        if company_assignment:
            company_data = {
                "company": CompanySerializer(company_assignment.company).data,
                "start_date": company_assignment.start_date,
                "end_date": company_assignment.end_date,
            }

        return Response(
            {
                "accounts": accounts_data,
                "dependents": dependents_data,
                "plates": plates_data,
                "company": company_data,
            }
        )
