from django.urls import path
from . import views

urlpatterns = [
    path("vendedores/dni/<str:dni>/", views.vendedor_por_dni),
    path("vendedorClientes/<str:id_vendedor>/", views.clientes_por_vendedor),
    path("precioTiposCombXArea/<str:id_area>/", views.precios_por_area),
    path("vendedores/telemarketers/", views.telemarketers),
    path("formasDePago/", views.formas_de_pago),
    path("provincias/", views.provincias),
    path("localidadesProvinciasView/provincia/<str:id_provincia>/", views.localidades_por_provincia),
    path("puntosEntrega/cliente/<str:id_cliente>/", views.puntos_entrega_por_cliente),
    path("NotasVentasApp/dni/<str:dni>/", views.notas_venta_por_dni),
    path("NotasVentasApp/upload/", views.upload_imagenes_nota_venta),
    path("NotasVentasApp/", views.submit_nota_venta),
]
