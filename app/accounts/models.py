from django.db import models, transaction
from django.utils import timezone
from users.models import CustomUser
from locations.models import Province
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group


class Account(models.Model):
    ACCOUNT_TYPES = [("holder", "Titular"), ("dependent", "Adherido")]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deactivated_accounts",
    )
    deactivation_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "-created_at"
        ]  # Ordenar por fecha de creación, más recientes primero
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(account_type="holder"),
                name="one_holder_account_per_user",
                violation_error_message="Un usuario solo puede tener una única cuenta titular",
            )
        ]

    def clean(self):
        if self.account_type == "dependent" and self.pk:
            dependents_as_holder = Dependents.objects.filter(holder_account=self)
            if dependents_as_holder.exists():
                raise ValidationError("Una cuenta adherente no puede tener adherentes")

    def __str__(self):
        return f"Cuenta {self.get_account_type_display()} {self.id} - {self.user.email}"


class Dependents(models.Model):
    holder_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="dependents_as_holder"
    )
    dependent_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="dependents_as_dependent"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["holder_account", "dependent_account"],
                condition=models.Q(end_date__isnull=True),
                name="unique_active_dependent_per_holder",
                violation_error_message="La cuenta adherida ya está asociada a la cuenta titular",
            )
        ]

    def clean(self):
        # Validar que holder_account sea de tipo 'holder'
        if self.holder_account.account_type != "holder":
            raise ValidationError("Solo las cuentas titulares pueden tener adherentes")

        # Validar que dependent_account sea de tipo 'dependent'
        if self.dependent_account.account_type != "dependent":
            raise ValidationError("Solo las cuentas adherentes pueden ser adheridas")

    def __str__(self):
        return f"Dependent {self.id} - {self.holder_account.user.email} to {self.dependent_account.user.email}"


class DependentInvitation(models.Model):
    INVITATION_STATUS = [
        ("pending", "Pendiente"),
        ("accepted", "Aceptada"),
        ("rejected", "Rechazada"),
        ("cancelled", "Cancelada"),
    ]

    holder_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="sent_invitations"
    )
    dependent_email = models.EmailField(default="")
    invitation_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=INVITATION_STATUS, default="pending"
    )
    response_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["holder_account", "dependent_email"],
                condition=models.Q(status="pending"),
                name="unique_pending_invitation",
                violation_error_message="Ya existe una invitación pendiente para este correo electrónico",
            )
        ]

    def clean(self):
        # Validar que holder_account sea de tipo 'holder'
        if self.holder_account.account_type != "holder":
            raise ValidationError(
                "Solo las cuentas titulares pueden enviar invitaciones"
            )

        # Validar que no exista ya una relación activa
        existing_relationship = Dependents.objects.filter(
            holder_account=self.holder_account,
            dependent_account__user__email=self.dependent_email,
            end_date__isnull=True,
        ).exists()

        if existing_relationship:
            raise ValidationError("Ya existe una relación activa entre estas cuentas")

    def accept_invitation(self):
        """Acepta la invitación y crea la relación de dependiente (adherido)"""
        if self.status != "pending":
            raise ValidationError("Solo se pueden aceptar invitaciones pendientes")

        with transaction.atomic():
            # Crear la cuenta adherente
            dependent_account = Account.objects.create(
                user=CustomUser.objects.get(email=self.dependent_email),
                balance=0,
                account_type="dependent",
            )

            # Actualizar el estado de la invitación
            self.status = "accepted"
            self.response_date = timezone.now()
            self.save()

            # Crear la relación de dependiente (adherida)
            Dependents.objects.create(
                holder_account=self.holder_account,
                dependent_account=dependent_account,
                start_date=timezone.now().date(),
            )

            # Asignar rol de Flota al usuario adherido
            try:
                fleet_group = Group.objects.get(name="Flota")
                dependent_user = CustomUser.objects.get(email=self.dependent_email)
                dependent_user.groups.add(fleet_group)
            except Group.DoesNotExist:
                pass

    def reject_invitation(self):
        """Rechaza la invitación"""
        if self.status != "pending":
            raise ValidationError("Solo se pueden rechazar invitaciones pendientes")

        self.status = "rejected"
        self.response_date = timezone.now()
        self.save()

    def cancel_invitation(self):
        """Cancela la invitación (solo el titular puede hacerlo)"""
        if self.status != "pending":
            raise ValidationError("Solo se pueden cancelar invitaciones pendientes")

        self.status = "cancelled"
        self.response_date = timezone.now()
        self.save()

    def __str__(self):
        return f"Invitación {self.id} - {self.holder_account.user.email} invita a {self.dependent_email} ({self.status})"


class Plates(models.Model):
    plate_number = models.CharField(max_length=10)
    holder_account = models.ForeignKey(Account, on_delete=models.CASCADE)
    brand = models.CharField(max_length=50, null=True, blank=True)
    model = models.CharField(max_length=50, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plate_number", "holder_account"],
                condition=models.Q(end_date__isnull=True),
                name="unique_active_plate_per_holder",
                violation_error_message="Ya existe una patente activa con este número para esta cuenta titular",
            ),
            models.UniqueConstraint(
                fields=["plate_number"],
                condition=models.Q(end_date__isnull=True),
                name="unique_active_plate_globally",
                violation_error_message="Ya existe una patente activa con este número en el sistema",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        # Solo cuentas titulares pueden tener patentes
        if self.holder_account.account_type != "holder":
            raise ValidationError(
                "Solo las cuentas titulares pueden tener patentes asignadas"
            )

        # Validar que la patente sea única globalmente para patentes activas
        if self.plate_number:
            existing_plates = Plates.objects.filter(
                plate_number=self.plate_number, end_date__isnull=True
            )

            # Si estamos editando una patente existente, excluirla de la validación
            if self.pk:
                existing_plates = existing_plates.exclude(pk=self.pk)

            if existing_plates.exists():
                raise ValidationError(
                    f"La patente '{self.plate_number}' ya está registrada en el sistema"
                )

    def __str__(self):
        return f"{self.plate_number}"


class AuthorizedPlate(models.Model):
    dependent_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="auth_plate_dependent"
    )
    plate = models.ForeignKey(Plates, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plate", "dependent_account"],
                condition=models.Q(end_date__isnull=True),
                name="unique_active_authorized_plate",
                violation_error_message="Ya existe una autorización activa con esta patente para esta cuenta",
            )
        ]

    def __str__(self):
        return f"Authorized Plate {self.plate.plate_number} for {self.dependent_account.user.email}"


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)
    province = models.ForeignKey(Province, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class CompanyAssignment(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return (
            f"Company Assignment {self.id} - {self.user.email} to {self.company.name}"
        )
