from rest_framework.pagination import PageNumberPagination


class ConditionalPageNumberPagination(PageNumberPagination):
    """
    Paginación opt-in: solo pagina si el request incluye ?page o ?page_size.

    Si ninguno de esos parámetros está presente, devuelve la lista completa
    como array directo (comportamiento retrocompatible con la app móvil actual).

    Cuando se activa:
      - Formato de respuesta: { count, next, previous, results: [...] }
      - page_size default: 25
      - page_size máximo: 200
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200
    page_query_param = "page"

    def paginate_queryset(self, queryset, request, view=None):
        if (
            self.page_query_param not in request.query_params
            and self.page_size_query_param not in request.query_params
        ):
            # Sin parámetros de paginación → DRF devuelve array directo
            return None
        return super().paginate_queryset(queryset, request, view)
