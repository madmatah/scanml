export class ApiError extends Error {
  override readonly name = 'ApiError';
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail === '' ? `HTTP ${status}` : detail);
    this.status = status;
    this.detail = detail;
  }
}

export class NetworkError extends Error {
  override readonly name = 'NetworkError';

  constructor() {
    super('Network error');
  }
}
