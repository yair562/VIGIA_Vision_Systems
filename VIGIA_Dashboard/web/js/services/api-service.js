/**
 * VIGÍA Vision Systems — Servicio Canónico de Comunicación HTTP (Fase 3B)
 *
 * Responsabilidades:
 * - Centralizar la comunicación HTTP con VIGIA_API.
 * - Garantizar el transporte de sesión exclusivamente mediante la cookie HttpOnly
 *   'vigia_session' utilizando { credentials: 'include' }.
 * - Cero almacenamiento de tokens o credenciales en localStorage/sessionStorage.
 * - Clasificar errores de forma determinista diferenciando caídas de red (NetworkError)
 *   y errores de servidor (ServerError) de sesiones no autenticadas (AuthError 401)
 *   o accesos denegados (ForbiddenError 403).
 */

export class ApiError extends Error {
  constructor(message, status = 0, code = 'API_ERROR') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export class AuthError extends ApiError {
  constructor(message = 'Sesión no autorizada o credenciales incorrectas.', status = 401, code = 'UNAUTHORIZED') {
    super(message, status, code);
    this.name = 'AuthError';
  }
}

export class ForbiddenError extends ApiError {
  constructor(message = 'Acceso denegado para el rol actual.', status = 403, code = 'FORBIDDEN') {
    super(message, status, code);
    this.name = 'ForbiddenError';
  }
}

export class ServerError extends ApiError {
  constructor(message = 'Error interno o servicio no disponible.', status = 500, code = 'SERVER_ERROR') {
    super(message, status, code);
    this.name = 'ServerError';
  }
}

export class NetworkError extends ApiError {
  constructor(message = 'No se pudo conectar con el servidor VIGÍA.', originalError = null) {
    super(message, 0, 'NETWORK_ERROR');
    this.name = 'NetworkError';
    this.originalError = originalError;
  }
}

/**
 * Resuelve el prefijo de URL base de la API.
 * Por defecto devuelve cadena vacía para rutas relativas al mismo origen (/app, /api/v1/...).
 * Si window.__VIGIA_API_BASE_URL__ está definido, lo utiliza para soportar orígenes distintos.
 */
export function resolveApiBaseUrl() {
  if (typeof window !== 'undefined' && window.__VIGIA_API_BASE_URL__) {
    return String(window.__VIGIA_API_BASE_URL__).replace(/\/+$/, '');
  }
  return '';
}

/**
 * Crea e inicializa el cliente del servicio de API de VIGÍA.
 * @param {Object} [options]
 * @param {string} [options.baseUrl] - URL base opcional de la API
 * @param {typeof fetch} [options.fetchFn] - Implementación de fetch inyectable
 */
export function createApiService({ baseUrl, fetchFn } = {}) {
  const getBase = () => (baseUrl !== undefined ? baseUrl.replace(/\/+$/, '') : resolveApiBaseUrl());
  const customFetch = fetchFn || (typeof fetch !== 'undefined' ? fetch.bind(globalThis) : null);

  async function request(path, options = {}) {
    if (!customFetch) {
      throw new NetworkError('La función fetch no está disponible en este entorno.');
    }

    const fullUrl = `${getBase()}${path}`;
    const headers = {
      Accept: 'application/json',
      ...(options.headers || {})
    };

    let fetchBody = options.body;
    const isFormData = typeof FormData !== 'undefined' && fetchBody instanceof FormData;
    const isBlob = typeof Blob !== 'undefined' && fetchBody instanceof Blob;

    if (fetchBody !== undefined && typeof fetchBody !== 'string' && !isFormData && !isBlob) {
      fetchBody = JSON.stringify(fetchBody);
    }

    if (fetchBody && !headers['Content-Type'] && !isFormData) {
      headers['Content-Type'] = 'application/json';
    }

    // TRANSPORTE INNEGOCIABLE: credentials: 'include' para cookie vigia_session
    const fetchOptions = {
      ...options,
      headers,
      body: fetchBody,
      credentials: 'include'
    };

    let response;
    try {
      response = await customFetch(fullUrl, fetchOptions);
    } catch (networkErr) {
      throw new NetworkError(
        'Fallo de conexión con el servidor VIGÍA. Compruebe la conectividad de red o el estado del backend.',
        networkErr
      );
    }

    let data = null;
    const contentType = response.headers?.get?.('Content-Type') || '';
    if (contentType.includes('application/json')) {
      try {
        data = await response.json();
      } catch {
        data = null;
      }
    }

    if (!response.ok) {
      const errorMsg = data?.message || `Error HTTP ${response.status}`;
      const errorCode = data?.error || 'HTTP_ERROR';

      if (response.status === 401) {
        throw new AuthError(errorMsg, response.status, errorCode);
      }
      if (response.status === 403) {
        throw new ForbiddenError(errorMsg, response.status, errorCode);
      }
      if (response.status >= 500) {
        throw new ServerError(errorMsg, response.status, errorCode);
      }
      throw new ApiError(errorMsg, response.status, errorCode);
    }

    return data || {};
  }

  return Object.freeze({
    /**
     * Ejecuta una solicitud HTTP genérica contra VIGIA_API garantizando credentials: 'include'.
     * @param {string} path
     * @param {Object} [options]
     * @returns {Promise<any>}
     */
    request,

    /**
     * Realiza una solicitud HTTP GET con credentials: 'include'.
     * @param {string} path
     * @param {Object} [options]
     * @returns {Promise<any>}
     */
    async get(path, options = {}) {
      return request(path, { ...options, method: 'GET' });
    },

    /**
     * Realiza una solicitud HTTP POST con serialización JSON automática y credentials: 'include'.
     * @param {string} path
     * @param {any} [body]
     * @param {Object} [options]
     * @returns {Promise<any>}
     */
    async post(path, body, options = {}) {
      return request(path, { ...options, method: 'POST', body });
    },

    /**
     * Inicia sesión mediante POST /api/v1/auth/login.
     * El servidor emite la cookie HttpOnly 'vigia_session'.
     * @param {string} username
     * @param {string} password
     * @returns {Promise<Object>} Datos del usuario autenticado devueltos por el servidor.
     */
    async login(username, password) {
      const result = await request('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          username: String(username).trim(),
          password: String(password)
        })
      });

      if (!result.ok || !result.user) {
        throw new AuthError(result.message || 'Credenciales de acceso inválidas.', 401, 'INVALID_CREDENTIALS');
      }

      // No almacenar ni procesar tokens en localStorage ni sessionStorage
      return result.user;
    },

    /**
     * Consulta la sesión activa del usuario mediante GET /api/v1/auth/me.
     * Retorna el objeto user si la cookie vigia_session es válida, o null si responde 401.
     * Lanza ServerError o NetworkError ante fallos del servidor o red (no confundir con sesión inválida).
     * @returns {Promise<Object | null>}
     */
    async getCurrentUser() {
      try {
        const result = await request('/api/v1/auth/me', {
          method: 'GET'
        });
        if (result.ok && result.user) {
          return result.user;
        }
        return null;
      } catch (err) {
        if (err instanceof AuthError && err.status === 401) {
          return null; // Sesión definitivamente no iniciada o expirada
        }
        // Errores de red (NetworkError) y servidor (ServerError 5xx) se relanzan intactos
        throw err;
      }
    },

    /**
     * Cierra la sesión activa mediante POST /api/v1/auth/logout.
     * Idempotente: siempre responde exitosamente y borra la cookie en el servidor.
     * @returns {Promise<boolean>}
     */
    async logout() {
      try {
        await request('/api/v1/auth/logout', {
          method: 'POST'
        });
        return true;
      } catch {
        // Idempotente: aunque la sesión ya no existiera o falle la red, consideramos logout ejecutado
        return true;
      }
    },

    /**
     * Consulta las cámaras lógicas y sus áreas de visión persistidas en PostgreSQL mediante GET /api/v1/cameras.
     * @returns {Promise<{ ok: boolean, cameras: Array<Object>, total: number }>}
     */
    async getCameras() {
      const result = await request('/api/v1/cameras', {
        method: 'GET'
      });

      const cameras = Array.isArray(result.cameras) ? result.cameras : [];
      const total = typeof result.total === 'number' ? result.total : cameras.length;

      return {
        ok: Boolean(result.ok),
        cameras,
        total
      };
    }
  });
}
