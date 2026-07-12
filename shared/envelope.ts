/**
 * 統一回應信封（✅ D-23／D-24，乙-5）：三端共用的信封型別、錯誤與解包。
 * 純 TS、零依賴——App（Expo）以相對路徑引用、web 端以 @shared 別名引用。
 */

export type ApiErrorBody = { code: string; message: string };

export type Envelope<T> = {
  success: boolean;
  data: T | null;
  error: ApiErrorBody | null;
  meta: Record<string, unknown> | null;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message?: string,
  ) {
    super(message || code);
  }
}

/** 解包信封：成功回 data，失敗擲 ApiError（message 為後端繁中人話，UI 可直接顯示）。 */
export function unwrapEnvelope<T>(status: number, body: Envelope<T>): T {
  if (!body.success || body.data === null) {
    const code = body.error?.code ?? `http_${status}`;
    throw new ApiError(status, code, body.error?.message);
  }
  return body.data;
}
