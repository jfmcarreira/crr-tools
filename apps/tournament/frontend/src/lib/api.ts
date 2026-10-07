export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

export function applicationPath(path: string): string {
  return `${import.meta.env.BASE_URL.slice(0, -1)}/${path.replace(/^\//, '')}`;
}

function errorFromPayload(status: number, payload: unknown): ApiError {
  if (payload && typeof payload === 'object') {
    const value = payload as Record<string, unknown>;
    const message = typeof value.message === 'string'
      ? value.message
      : typeof value.error === 'string'
        ? value.error
        : 'Não foi possível concluir o pedido.';
    const errors = value.errors && typeof value.errors === 'object'
      ? Object.fromEntries(
          Object.entries(value.errors as Record<string, unknown>)
            .filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
        )
      : {};
    return new ApiError(status, message, errors);
  }

  return new ApiError(status, 'Não foi possível concluir o pedido.');
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(applicationPath(path), { ...init, headers, credentials: 'include' });
  } catch {
    throw new ApiError(0, 'Não foi possível contactar o servidor. Verifique a ligação e tente novamente.');
  }

  const isJson = response.headers.get('content-type')?.includes('application/json');
  const payload: unknown = isJson ? await response.json().catch(() => null) : null;
  if (!response.ok) {
    throw errorFromPayload(response.status, payload);
  }

  return payload as T;
}

export function messageFor(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Ocorreu um erro inesperado. Tente novamente.';
}
