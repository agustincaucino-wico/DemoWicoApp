from django.contrib.auth import get_user_model
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from typing import List
from locations.models import Province, City
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

# from django.contrib.auth.models import User

UserModel = get_user_model()


class ResendVerificationSerializer(serializers.Serializer):
    """Serializer for resending verification email"""

    email = serializers.EmailField(required=True)


class AssignRoleSerializer(serializers.Serializer):
    """Serializer for assigning role to user"""

    role_name = serializers.ChoiceField(
        choices=["Playero", "Encargado", "Marketing"], required=True
    )


class RemoveRoleSerializer(serializers.Serializer):
    """Serializer for removing role from user"""

    role_name = serializers.ChoiceField(
        choices=["Playero", "Encargado", "Marketing"], required=True
    )


class DevUserLoginSerializer(serializers.Serializer):
    """Serializer for dev user login endpoint"""

    user_id = serializers.IntegerField(required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True)


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=True)
    dni = serializers.CharField(required=True)  # Obligatorio en el registro
    gender = serializers.ChoiceField(
        choices=["M", "F"], required=False, allow_null=True
    )
    phone_number = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    id_province = serializers.PrimaryKeyRelatedField(
        queryset=Province.objects.all(), required=False, allow_null=True
    )
    id_city = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(), required=False, allow_null=True
    )
    groups = serializers.SerializerMethodField()
    province_name = serializers.SerializerMethodField()
    city_name = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(read_only=True)
    email_verified = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserModel
        fields = [
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "dni",
            "phone_number",
            "id_province",
            "province_name",
            "id_city",
            "city_name",
            "gender",
            "groups",
            "date_joined",
            "email_verified",
            "is_superuser",
            "is_staff",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        """
        Hacer DNI obligatorio solo en creación, no en actualizaciones.
        """
        super().__init__(*args, **kwargs)
        # Si es una actualización (instance existe), hacer DNI opcional
        if self.instance is not None:
            self.fields["dni"].required = False
            self.fields["dni"].allow_blank = True
            self.fields["dni"].allow_null = True

    def validate_dni(self, value):
        if value:
            # Exclude current instance during update
            queryset = UserModel.objects.filter(dni=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError("Este DNI ya está registrado.")
        return value

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_groups(self, obj) -> List[str]:
        return [group.name for group in obj.groups.all()]

    def create(self, validated_data):
        # Remover campos sensibles de seguridad para prevenir escalación de privilegios
        validated_data.pop("is_superuser", None)
        validated_data.pop("is_staff", None)
        user = UserModel.objects.create_user(**validated_data)
        return user

    def update(self, instance, validated_data):
        # Remover campos sensibles de seguridad para prevenir escalación de privilegios
        validated_data.pop("is_superuser", None)
        validated_data.pop("is_staff", None)

        # Manejar la contraseña de forma segura si se proporciona
        password = validated_data.pop("password", None)

        # Actualizar campos normales
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Actualizar contraseña si se proporcionó
        if password:
            instance.set_password(password)

        instance.save()
        return instance

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_province_name(self, obj) -> str | None:
        province = getattr(obj, "id_province", None)
        return province.name if province else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_city_name(self, obj) -> str | None:
        city = getattr(obj, "id_city", None)
        return city.name if city else None


class EmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        if not self.user.email_verified:
            raise serializers.ValidationError(
                {
                    "status": "unverified",
                    "detail": "La cuenta no ha sido verificada. Por favor verifica tu correo electrónico.",
                },
                code="account_not_verified",
            )

        return data
