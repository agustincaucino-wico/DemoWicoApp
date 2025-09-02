from django.db import models
from users.models import CustomUser
from locations.models import Province


class Account(models.Model):
    ACCOUNT_TYPES = [("holder", "Holder"), ("dependent", "Dependent")]

    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Account {self.id} - {self.user.email}"


class Dependents(models.Model):
    holder_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="dependents_as_holder"
    )
    dependent_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="dependents_as_dependent"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Dependent {self.id} - {self.holder_account.user.email} to {self.dependent_account.user.email}"


class Plates(models.Model):
    plate_number = models.CharField(max_length=10, unique=True)
    holder_account = models.ForeignKey(Account, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.plate_number}"


class AuthorizedPlate(models.Model):
    holder_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="auth_plate_holder"
    )
    dependent_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="auth_plate_dependent"
    )
    plate = models.ForeignKey(Plates, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)


class Company(models.Model):
    name = models.CharField(max_length=255)
    province = models.ForeignKey(Province, on_delete=models.CASCADE)


class CompanyAssignment(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return (
            f"Company Assignment {self.id} - {self.user.email} to {self.company.name}"
        )
