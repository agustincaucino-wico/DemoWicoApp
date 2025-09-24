from rest_framework import mixins, viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from drf_spectacular.utils import extend_schema

from users.models import CustomUser
from users.serializers import UserSerializer
from .permissions import DjangoModelOrObjectOwner
from utils.email_service import email_service


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
    AddDependentSerializer,
    RemoveDependentSerializer,
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


class UserActionsViewSet(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = AccountSerializer  # Default serializer for schema generation

    @extend_schema(
        responses={200: None},
        description="Get user account information including accounts, dependents, plates, and company",
        summary="Get User Account Info",
    )
    @action(detail=False, methods=["get"], url_path="info")
    def info(self, request):
        user = request.user
        # Get accounts associated to user
        accounts = Account.objects.filter(user=user)
        accounts_data = AccountSerializer(accounts, many=True).data

        # Get dependents data for those accounts (only active ones)
        dependent_relations = Dependents.objects.filter(
            holder_account__in=accounts, end_date__isnull=True
        )
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

    @extend_schema(
        request=AddDependentSerializer,
        responses={201: None, 400: None, 404: None, 500: None},
        description="Add a dependent user to a holder account",
        summary="Add Dependent",
    )
    @action(detail=False, methods=["post"], url_path="add-dependent")
    def add_dependent(self, request):
        """
        Add a dependent to a holder account.
        Expects: holder_account_id, dependent_email
        """
        serializer = AddDependentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        holder_account_id = serializer.validated_data["holder_account_id"]
        dependent_email = serializer.validated_data["dependent_email"]

        try:
            # Verify the holder account belongs to the current user and is holder type
            holder_account = get_object_or_404(
                Account, id=holder_account_id, user=request.user, account_type="holder"
            )

            # Get the dependent user by email
            dependent_user = get_object_or_404(CustomUser, email=dependent_email)

            # Prevent users from adding themselves as dependents
            if dependent_user == request.user:
                return Response(
                    {"error": "You cannot add yourself as a dependent"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if there's already an active relationship between this holder and dependent user
            # A dependent user can have multiple dependent accounts, but not multiple relationships with the same holder
            existing_relationship = Dependents.objects.filter(
                holder_account=holder_account,
                dependent_account__user=dependent_user,
                end_date__isnull=True,
            ).first()

            if existing_relationship:
                return Response(
                    {
                        "error": "This user is already a dependent of this holder account"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                # Create a new dependent account for this specific holder-dependent relationship
                dependent_account = Account.objects.create(
                    user=dependent_user,
                    balance=Decimal("0.00"),
                    account_type="dependent",
                )

                # Create the dependent relationship
                Dependents.objects.create(
                    holder_account=holder_account,
                    dependent_account=dependent_account,
                    start_date=timezone.now().date(),
                    status="pending",
                )

                # Send invitation email
                email_service.send_invitation_email(
                    request.user, dependent_user, holder_account
                )

                # Return the created relationship data
                response_data = {
                    "message": "Invitation sent successfully",
                }

                return Response(response_data, status=status.HTTP_201_CREATED)

        except Account.DoesNotExist:
            return Response(
                {"error": "Holder account not found or does not belong to you"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User with this email does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        request=RemoveDependentSerializer,
        responses={200: None, 400: None, 404: None, 500: None},
        description="Remove a dependent user from a holder account",
        summary="Remove Dependent",
    )
    @action(detail=False, methods=["post"], url_path="remove-dependent")
    def remove_dependent(self, request):
        """
        Remove a dependent from a holder account.
        Expects: holder_account_id, dependent_account_id
        """
        serializer = RemoveDependentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        holder_account_id = serializer.validated_data["holder_account_id"]
        dependent_account_id = serializer.validated_data["dependent_account_id"]

        try:
            # Verify the holder account belongs to the current user and is holder type
            holder_account = get_object_or_404(
                Account, id=holder_account_id, user=request.user, account_type="holder"
            )

            # Get the dependent account by ID
            dependent_account = get_object_or_404(
                Account, id=dependent_account_id, account_type="dependent"
            )

            # Prevent users from removing themselves (edge case)
            if dependent_account.user == request.user:
                return Response(
                    {"error": "Invalid operation"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Find the active relationship between this holder and dependent account
            dependent_relation = get_object_or_404(
                Dependents,
                holder_account=holder_account,
                dependent_account=dependent_account,
                end_date__isnull=True,
            )

            with transaction.atomic():
                # Set end_date to mark as inactive instead of deleting
                dependent_relation.end_date = timezone.now().date()
                dependent_relation.save()

                # Send removal notification email
                email_service.send_dependent_removal_notification(
                    request.user, dependent_account.user, holder_account
                )

                response_data = {
                    "message": "Dependent removed successfully",
                }

                return Response(response_data, status=status.HTTP_200_OK)

        except Account.DoesNotExist:
            return Response(
                {"error": "Holder account not found or does not belong to you"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User with this email does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Dependents.DoesNotExist:
            return Response(
                {"error": "Dependent relationship not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
