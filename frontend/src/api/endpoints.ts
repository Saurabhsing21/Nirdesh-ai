export function resolveApiBaseUrl(
  configuredUrl: string | undefined,
  pageOrigin: string,
): string {
  const baseUrl = configuredUrl?.trim() || pageOrigin;
  return baseUrl.replace(/\/+$/, "");
}
