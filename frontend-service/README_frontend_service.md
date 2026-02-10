# Frontend Service (React)

Frontend simple en React + Vite para:

- lanzar una optimizacion (`POST /optimizations`)
- recibir estado/progreso por SSE (`GET /optimizations/:job_id/events`)
- mostrar soluciones Pareto
- dibujar PNML de cada solucion con Cytoscape

## Desarrollo local

```bash
cd frontend-service
npm install
npm run dev
```

Variables:

- `VITE_OPTIMIZATION_API_URL` (default: `http://localhost:8080`)

## Con Docker Compose

Desde raiz:

```bash
docker compose up --build frontend_service optimization_service prom_service
```

Abre:

- `http://localhost:5173`
