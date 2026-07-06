# Plan de Implementación de Paginación

**Fecha:** 8 de junio de 2026  
**Objetivo:** Implementar paginación en áreas críticas del sistema con retrocompatibilidad total para la app móvil actual.

---

## Diagnóstico del estado actual

| Frontend | Comportamiento actual | Estado |
|---|---|---|
| `front/` (app móvil) | Consume arrays directos en casi todos los endpoints | 🔴 No soporta paginación |
| `gestorCordoba/` | Usa `Array.isArray(data) ? data : data.results ?? []` | 🟢 Ya es defensivo |
| `retail/back-office/` | Consume arrays directos | 🔴 No soporta paginación |
| `notifications/` (backend) | Paginación custom implementada | ✅ Ya implementado |

---

## Estrategia de retrocompatibilidad

**Paginación condicional por query params.**

- Si el request incluye `?page=N` o `?page_size=N`, el endpoint devuelve formato paginado.
- Si no incluye esos parámetros, devuelve un array directo como actualmente.
- La app móvil actual nunca envía esos parámetros → sigue funcionando sin cambios.

```
GET /operations/fuel-load-operations/             → [ ... ]        ← app actual, sin cambios
GET /operations/fuel-load-operations/?page=1      → { count, next, previous, results: [...] }
GET /operations/fuel-load-operations/?page=2&page_size=25 → { count, ... }
```

---

## Fase 1 — Backend: Clase de paginación condicional

### Archivo a crear: `back/app/utils/pagination.py`

```python
from rest_framework.pagination import PageNumberPagination

class ConditionalPageNumberPagination(PageNumberPagination):
    """
    Paginación opt-in: solo pagina si el request incluye ?page o ?page_size.
    Si no se incluyen, devuelve la lista completa (retrocompatible).
    """
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200
    page_query_param = "page"

    def paginate_queryset(self, queryset, request, view=None):
        if self.page_query_param not in request.query_params and \
           self.page_size_query_param not in request.query_params:
            return None  # DRF interpreta None como "devolver todo sin paginar"
        return super().paginate_queryset(queryset, request, view)
```

### Cambio en `back/app/myapp/settings/base.py`

Agregar en `REST_FRAMEWORK`:

```python
"DEFAULT_PAGINATION_CLASS": "utils.pagination.ConditionalPageNumberPagination",
"PAGE_SIZE": 25,
```

Con esto, **todos los ViewSets quedan paginables automáticamente** sin tocar cada view individualmente. Los que tienen paginación custom (notifications) no se ven afectados porque la sobreescriben localmente.

---

## Fase 2 — Endpoints a paginar

### 🔴 Alta prioridad — datos transaccionales (crecen sin límite)

| Endpoint | Módulo | Justificación |
|---|---|---|
| `/operations/fuel-load-operations/` | `operation` | Log de transacciones. Crece constantemente. |
| `/operations/modify-funds/` | `operation` | Log de auditoría. Admin-only. |
| `/operations/recharge-requests/` | `operation` | Historial de recargas. |
| `/actions/user/movements/` | `actions` | Movimientos por cuenta. Los usuarios lo consultan frecuentemente. |

### 🟡 Media prioridad — crecen con la base de usuarios

| Endpoint | Módulo | Justificación |
|---|---|---|
| `/accounts/accounts/` | `accounts` | Una por usuario activo. |
| `/accounts/plates/` | `accounts` | Varias por cuenta. |
| `/accounts/dependents/` | `accounts` | Crecen con cuentas empresariales. |
| `/users/` | `users` | Lista completa de usuarios del sistema. |
| `/support/error-reports/` | `support` | Crece con el uso. Admin-only. |
| `/support/fleet-contact-requests/` | `support` | Crece con el uso. |

### 🟢 Sin cambios necesarios

| Endpoint | Razón |
|---|---|
| `/locations/*` | Datos geográficos estáticos (<200 registros) |
| `/stations/stations/` | Acotado a infraestructura física |
| `/stations/fuel-types/` | Catálogo muy pequeño |
| `/promotions/*` | Gestionado por admin, pocos registros |
| `/appconfig/*` | Objetos únicos (singleton) |
| `/ventas/*` | Proxies a sistema externo, sin control local |

---

## Fase 3 — gestorCordoba (Vite + React)

gestorCordoba **ya normaliza** las respuestas (`Array.isArray(data) ? data : data.results ?? []`). Los cambios son de UI y de paso de parámetros.

### Archivos a modificar

- `gestorCordoba/src/api/services/fleetService.js` — agregar parámetro `page` a cada función de listado
- Vistas que muestran listados — agregar componente de paginación

### Patrón para cada función de servicio

```javascript
// Ejemplo: fetchFuelLoads actualizado
export async function fetchFuelLoads({ station, status, account, page = null, pageSize = 25 } = {}) {
  const params = new URLSearchParams();
  if (page !== null) {
    params.append("page", page);
    params.append("page_size", pageSize);
  }
  if (station) params.append("station", station);
  if (status) params.append("status", status);
  if (account) params.append("account", account);

  const response = await apiClient.get(`/operations/fuel-load-operations/?${params}`);
  const data = response.data;
  return {
    results: Array.isArray(data) ? data : (data.results ?? []),
    count: data.count ?? null,
    next: data.next ?? null,
    previous: data.previous ?? null,
  };
}
```

### Vistas a actualizar en gestorCordoba

- Listado de operaciones de combustible
- Listado de movimientos de usuario
- Listado de cuentas
- Listado de dependientes y placas
- Reportes de soporte

### Componente `PaginationControls` a crear

```jsx
// gestorCordoba/src/components/PaginationControls.jsx
export function PaginationControls({ count, page, pageSize, onPageChange }) {
  const totalPages = Math.ceil(count / pageSize);
  return (
    <div className="pagination">
      <button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Anterior</button>
      <span>Página {page} de {totalPages} ({count} registros)</span>
      <button disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Siguiente</button>
    </div>
  );
}
```

---

## Fase 4 — retail/back-office (React + TypeScript)

retail actualmente consume arrays directos. Necesita:
1. Tipo `PaginatedResponse<T>` compartido
2. Helper `fetchPaginated` reutilizable
3. Actualizar cada servicio
4. Agregar UI de paginación en tablas

### Tipo compartido — `retail/back-office/src/types/pagination.ts` (archivo nuevo)

```typescript
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Normaliza tanto arrays directos como respuestas paginadas
export function normalizePaginated<T>(data: T[] | PaginatedResponse<T>): PaginatedResponse<T> {
  if (Array.isArray(data)) {
    return { count: data.length, next: null, previous: null, results: data };
  }
  return data;
}
```

### Helper en el cliente API

```typescript
// En el archivo base de API (api.ts o apiClient.ts)
export async function fetchPaginated<T>(
  url: string,
  params: Record<string, string | number> = {}
): Promise<PaginatedResponse<T>> {
  const response = await api.get<T[] | PaginatedResponse<T>>(url, { params });
  return normalizePaginated(response.data);
}
```

### Servicios a actualizar en retail

- `dashboardService` — fuel load operations, accounts
- `userService` — usuarios, cuentas, placas, dependientes
- `stationsService` — estaciones, asignaciones
- `supportService` — reportes de error, fleet contact requests

### Componente `Pagination` a crear

```tsx
// retail/back-office/src/components/Pagination.tsx
interface PaginationProps {
  count: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ count, page, pageSize, onPageChange }: PaginationProps) {
  const totalPages = Math.ceil(count / pageSize);
  return (
    <div className="flex items-center gap-2">
      <button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Anterior</button>
      <span>Página {page} de {totalPages} — {count} registros</span>
      <button disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Siguiente</button>
    </div>
  );
}
```

---

## Fase 5 — Próxima versión de la app móvil (front/)

**La app actual no requiere cambios.** Para la siguiente versión:

### Helper de normalización — `front/api/pagination.ts` (archivo nuevo)

```typescript
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export function normalizePaginatedResponse<T>(
  data: T[] | PaginatedResponse<T>
): PaginatedResponse<T> {
  if (Array.isArray(data)) {
    return { count: data.length, next: null, previous: null, results: data };
  }
  return data;
}
```

### Stores y hooks a actualizar

- Movimientos de cuenta (`/actions/user/movements/`) → infinite scroll (append al hacer scroll)
- Notas de venta (`/ventas/NotasVentasApp/dni/`) → ya tiene soporte parcial de parámetros
- Clientes del vendedor (`/ventas/vendedorClientes/`) → paginación por demanda

### Patrón recomendado: infinite scroll

Para listados de transacciones en mobile, usar **infinite scroll** (agregar resultados al final) en lugar de botones de página anterior/siguiente, que es mejor UX en móvil.

```typescript
// Hook reutilizable para infinite scroll
function useInfiniteList<T>(fetchFn: (page: number) => Promise<PaginatedResponse<T>>) {
  const [items, setItems] = useState<T[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const loadMore = async () => {
    const response = await fetchFn(page);
    setItems(prev => [...prev, ...response.results]);
    setHasMore(response.next !== null);
    setPage(prev => prev + 1);
  };

  return { items, loadMore, hasMore };
}
```

---

## Orden de implementación

```
Semana 1 — Backend
  [X] Crear back/app/utils/pagination.py
  [X] Agregar DEFAULT_PAGINATION_CLASS en settings/base.py
  [X] Verificar que endpoints críticos responden correctamente con y sin ?page
  [X] Tests de regresión: confirmar que sin ?page la respuesta sigue siendo array directo

Semana 2 — retail/back-office
  [X] Crear types/pagination.ts con PaginatedResponse<T> y normalizePaginated
  [X] Crear componente Pagination.tsx
  [X] Crear componente InfiniteList.tsx con useInfiniteList + InfiniteScrollSentinel (scroll infinito)
  [X] Agregar fetchPaginated helper en apiClient.ts
  [X] Actualizar userService — fetchUsersPaginated, fetchAccountsPaginated usan fetchPaginated
  [X] Actualizar fuelOperationsService — fetchFuelOperationsPaginated + fetchAllFuelOperations
  [X] Actualizar tablas/listados del back-office

Siguiente versión app móvil (1.3.3)
  [X] Crear front/api/pagination.ts con helper de normalización
  [X] Actualizar stores y hooks para movimientos y notas de venta
  [X] Implementar infinite scroll en listados de transacciones
  [X] Implementar infinite scroll en listados de notas de ventas
```

---

## Resumen de impacto por capa

| Capa | Cambios requeridos | Riesgo de regresión |
|---|---|---|
| **Backend** | 1 archivo nuevo + 2 líneas en settings | 🟢 Ninguno — retrocompatible por diseño |
| **retail** | Tipos + servicios + componente UI + tablas | 🟠 Medio — consume arrays directos hoy |
| **app móvil (versión actual)** | Sin cambios | 🟢 Ninguno |
| **app móvil (próxima versión)** | Helper + stores + UX infinite scroll | 🟡 Bajo — opt-in explícito |
