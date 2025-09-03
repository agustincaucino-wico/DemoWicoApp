from django.db import models


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Province(models.Model):
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="provinces"
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.country.name})"


class City(models.Model):
    name = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    province = models.ForeignKey(
        Province, on_delete=models.CASCADE, related_name="cities"
    )

    def __str__(self):
        return f"{self.name}, {self.province.name}"


class Address(models.Model):
    street = models.CharField(max_length=100)
    number = models.IntegerField()
    # floor/apartment can be optional for many addresses
    floor = models.IntegerField(null=True, blank=True)
    apartment = models.CharField(max_length=10, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="addresses")

    def __str__(self):
        parts = [f"{self.street} {self.number}"]
        if self.floor is not None:
            parts.append(f"Flr {self.floor}")
        if self.apartment:
            parts.append(f"Apt {self.apartment}")
        parts.append(self.city.name)
        return ", ".join(parts)
