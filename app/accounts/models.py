from django.db import models, transaction
from django.utils import timezone
from users.models import CustomUser
from locations.models import Province
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group


class Organism(models.Model):
    BILLING_TYPES = [
        ("invoice", "Postpago"),
        ("prepaid", "Prepago"),
    ]

    TAX_CONDITIONS = [
        ("responsable_inscripto", "Responsable Inscripto"),
        ("exento", "Exento"),
    ]

    name = models.CharField(max_length=255, unique=True)
    cuit = models.CharField(max_length=13, unique=True)
    billing_type = models.CharField(max_length=20, choices=BILLING_TYPES)
    tax_condition = models.CharField(
        max_length=30,
        choices=TAX_CONDITIONS,
        default="responsable_inscripto",
        verbose_name="Condición ante IVA",
        help_text="Condición fiscal del organismo frente al IVA",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Organismo"
        verbose_name_plural = "Organismos"

    def __str__(self):
        return self.name


class Account(models.Model):
    ACCOUNT_TYPES = [("holder", "Titular"), ("dependent", "Adherido")]
    DISPLAY_TYPES = [
        ("pesos", "Pesos"),
        ("litros", "Litros"),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True)
    balance = models.DecimalField(max_digits=15, decimal_places=2)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    display_type = models.CharField(
        max_length=20,
        choices=DISPLAY_TYPES,
        default="pesos",
        help_text="Determina cómo se muestra el saldo y los movimientos: en pesos o en litros",
    )
    special = models.CharField(max_length=50, null=True, blank=True)
    unlimited_balance = models.BooleanField(default=False)
    company = models.ForeignKey(
        "Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts",
        help_text="Empresa a la que pertenece esta cuenta",
    )
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
        indexes = [
            models.Index(fields=["is_active", "id"]),
            models.Index(fields=["user", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(account_type="holder", is_active=True),
                name="one_holder_account_per_user",
                violation_error_message="Un usuario solo puede tener una única cuenta titular activa",
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
        indexes = [
            models.Index(fields=["holder_account", "end_date"]),
        ]
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
    dependent_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_invitations",
        help_text="Usuario destinatario de la invitación, si ya está registrado. "
        "No reemplaza a dependent_email todavía: se irá poblando en una etapa posterior.",
    )
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

        # Validar que no exista ya una relación activa. Sin dependent_user no
        # hay destinatario contra el cual comprobarla.
        if self.dependent_user_id is None:
            return

        existing_relationship = Dependents.objects.filter(
            holder_account=self.holder_account,
            dependent_account__user=self.dependent_user,
            end_date__isnull=True,
        ).exists()

        if existing_relationship:
            raise ValidationError("Ya existe una relación activa entre estas cuentas")

    def accept_invitation(self):
        """Acepta la invitación y crea la relación de dependiente (adherido)"""
        if self.status != "pending":
            raise ValidationError("Solo se pueden aceptar invitaciones pendientes")

        # El destinatario se resuelve al crear la invitación. Si el FK quedó
        # en null (invitación anterior a la migración y sin backfill, o
        # usuario eliminado después) no se puede determinar a quién
        # corresponde: resolverlo por email acá volvería a atar la cuenta a
        # quien tenga esa dirección en este momento, que es exactamente lo
        # que se está corrigiendo.
        if self.dependent_user_id is None:
            raise ValidationError(
                "La invitación no tiene un usuario destinatario asociado"
            )

        dependent_user = self.dependent_user

        with transaction.atomic():
            # Crear la cuenta adherente, copiando company/display_type/
            # unlimited_balance de la cuenta titular (lectura en vivo: a
            # diferencia de AuthorizedEmail, DependentInvitation no
            # snapshotea estos campos al crear la invitación).
            dependent_account = Account.objects.create(
                user=dependent_user,
                balance=0,
                account_type="dependent",
                company=self.holder_account.company,
                display_type=self.holder_account.display_type,
                unlimited_balance=self.holder_account.unlimited_balance,
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
    year = models.PositiveIntegerField(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["holder_account", "end_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["plate_number", "holder_account"],
                condition=models.Q(end_date__isnull=True),
                name="unique_active_plate_per_holder",
                violation_error_message="Ya existe una patente activa con este número para esta cuenta titular",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        # Solo cuentas titulares pueden tener patentes
        if self.holder_account.account_type != "holder":
            raise ValidationError(
                "Solo las cuentas titulares pueden tener patentes asignadas"
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
    BILLING_TYPES = [
        ("invoice", "Postpago"),
        ("prepaid", "Prepago"),
    ]

    TAX_CONDITIONS = [
        ("responsable_inscripto", "Responsable Inscripto"),
        ("exento", "Exento"),
    ]

    name = models.CharField(max_length=255, unique=True)
    province = models.ForeignKey(Province, on_delete=models.CASCADE)
    organism = models.ForeignKey(
        Organism,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="companies",
    )
    cuit = models.CharField(
        max_length=13,
        null=True,
        blank=True,
        verbose_name="CUIT",
    )
    billing_type = models.CharField(
        max_length=20,
        choices=BILLING_TYPES,
        null=True,
        blank=True,
        verbose_name="Tipo de facturación",
    )
    tax_condition = models.CharField(
        max_length=30,
        choices=TAX_CONDITIONS,
        null=True,
        blank=True,
        verbose_name="Condición ante IVA",
        help_text="Condición fiscal de la empresa frente al IVA",
    )

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

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


class AuthorizedEmail(models.Model):
    """
    Represents an invitation sent to an unregistered email.
    When a holder tries to add a dependent whose email is not registered in the app,
    an AuthorizedEmail record is created and an invitation email is sent.
    When the user registers with that email, the dependent account is auto-created.
    """

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("accepted", "Aceptada"),
        ("expired", "Expirada"),
        ("cancelled", "Cancelada"),
    ]

    email = models.EmailField()
    dependent_of = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="authorized_emails",
        help_text="Cuenta titular a la que se asociará el adherente",
    )
    special = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Si tiene valor, la cuenta adherente creada también será special",
    )
    display_type = models.CharField(
        max_length=20,
        choices=Account.DISPLAY_TYPES,
        default="pesos",
        help_text="Tipo de visualización para la cuenta adherente creada (pesos o litros)",
    )
    unlimited_balance = models.BooleanField(
        default=False,
        help_text="Si es True, la cuenta adherente creada tendrá saldo ilimitado",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authorized_emails",
    )
    organism = models.ForeignKey(
        Organism,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authorized_emails",
    )
    pending_plates = models.ManyToManyField(
        "Plates",
        blank=True,
        related_name="pending_authorized_emails",
        help_text="Patentes a asignar automáticamente cuando el usuario se registre",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-invited_at"]
        verbose_name = "Email autorizado"
        verbose_name_plural = "Emails autorizados"

    def __str__(self):
        return f"AuthorizedEmail {self.email} -> {self.dependent_of.user.email} ({self.status})"

    def accept(self, user):
        """
        Accept the authorized email: create dependent account, Dependents relation,
        assign Flota role, and CompanyAssignment if applicable.
        """
        if self.status != "pending":
            raise ValidationError("Solo se pueden aceptar invitaciones pendientes")

        with transaction.atomic():
            # Create dependent account with matching special, display_type, unlimited_balance and company fields
            dependent_account = Account.objects.create(
                user=user,
                balance=0,
                account_type="dependent",
                special=self.special,
                display_type=self.display_type,
                unlimited_balance=self.unlimited_balance,
                company=self.company,
            )

            # Create the dependent relationship
            Dependents.objects.create(
                holder_account=self.dependent_of,
                dependent_account=dependent_account,
                start_date=timezone.now().date(),
            )

            # Assign Flota role
            try:
                fleet_group = Group.objects.get(name="Flota")
                user.groups.add(fleet_group)
            except Group.DoesNotExist:
                pass

            # Assign pending plates pre-loaded from the Excel import
            for plate in self.pending_plates.all():
                # Only create if there's no active authorization already
                if not AuthorizedPlate.objects.filter(
                    dependent_account=dependent_account,
                    plate=plate,
                    end_date__isnull=True,
                ).exists():
                    AuthorizedPlate.objects.create(
                        dependent_account=dependent_account,
                        plate=plate,
                        start_date=timezone.now().date(),
                    )

            # Update status
            self.status = "accepted"
            self.accepted_at = timezone.now()
            self.save()

            return dependent_account

    def cancel(self):
        """Cancel this authorized email invitation."""
        if self.status != "pending":
            raise ValidationError("Solo se pueden cancelar invitaciones pendientes")
        self.status = "cancelled"
        self.save()
