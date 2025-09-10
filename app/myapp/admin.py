from django.contrib import admin

class MyCustomAdminSite(admin.AdminSite):
    site_header = "Gestor App Wico"
    site_title = "Gestor App Wico"
    index_title = "Portal de administración de Wico"

my_admin_site = MyCustomAdminSite(name='myadmin')