import createClient from 'openapi-fetch';
import type { paths } from './schema';

// Same origin as the page: in development, Vite proxies /api to FastAPI.
export const api = createClient<paths>();
