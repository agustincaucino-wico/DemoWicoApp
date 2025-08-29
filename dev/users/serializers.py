from django.contrib.auth import get_user_model
#from django.contrib.auth.models import User
from rest_framework import serializers

UserModel = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    class Meta:
        model = UserModel
        fields = ['id', 'email', 'password', 'first_name', 'last_name', 'dni', 'phone_number', 'id_province', 'gender']

    def create(self, validated_data):
        return UserModel.objects.create_user(**validated_data)