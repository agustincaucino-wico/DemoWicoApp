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
    path("precio_flete_x_litro/", views.precio_flete_x_litro),
    path("mapas/distancia_desde_planta/<str:destino>", views.distancia_desde_planta),
    path("NotasVentasApp/dni/<str:dni>/", views.notas_venta_por_dni),
    path("NotasVentasApp/upload/", views.upload_imagenes_nota_venta),
    path("NotasVentasApp/", views.submit_nota_venta),
    # Autorizaciones de precio de combustible
    path("autPrecioComb/pendientes/", views.aut_precio_comb_pendientes),
    path("autPrecioComb/proximo_id/", views.aut_precio_comb_proximo_id),
    path("autPrecioComb/estado/<str:codigo>/", views.aut_precio_comb_estado),
    path("autPrecioComb/<str:id_aut>/", views.aut_precio_comb_actualizar),
    path("autPrecioComb/", views.aut_precio_comb_crear),
]
