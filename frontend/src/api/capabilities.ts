import { resolveApiBaseUrl } from "./endpoints";

export type PublicCapabilities = {
  features?: Record<string, boolean | undefined>;
};

const API_BASE_URL = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  window.location.origin,
);

export async function getCapabilities(): Promise<PublicCapabilities> {
  const response = await fetch(`${API_BASE_URL}/capabilities`);
  if (!response.ok) return {};
  return (await response.json()) as PublicCapabilities;
}
