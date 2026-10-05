export const OWNER = "armageddonvivas@gmail.com";
export const SUPABASE = "https://mtdavgadkiiofwikzdtn.supabase.co";
export type Config = {
  owner_email: string;
  supabase_url: string;
  publishable_key: string;
  configured: boolean;
};
export type Session = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: { email: string };
};
export function checkConfig(config: Config) {
  if (config.owner_email !== OWNER || config.supabase_url !== SUPABASE)
    throw new Error("Account configuration mismatch. Connection stopped.");
  return config;
}
export async function configRequest(): Promise<Config> {
  const r = await fetch("/api/config", { cache: "no-store" });
  if (!r.ok) throw new Error("The personal backend is unavailable.");
  return checkConfig(await r.json());
}
export async function signIn(
  config: Config,
  password: string,
): Promise<Session> {
  checkConfig(config);
  if (!config.configured)
    throw new Error("Personal account setup is incomplete.");
  const r = await fetch(SUPABASE + "/auth/v1/token?grant_type=password", {
    method: "POST",
    headers: {
      apikey: config.publishable_key,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email: OWNER, password }),
  });
  const data = await r.json();
  if (!r.ok)
    throw new Error("Sign-in failed. Check your personal workspace password.");
  if (data.user?.email?.toLowerCase() !== OWNER)
    throw new Error("Wrong account. Sign-in stopped.");
  return data;
}
export async function refreshSession(
  config: Config,
  refresh_token: string,
): Promise<Session> {
  checkConfig(config);
  const r = await fetch(SUPABASE + "/auth/v1/token?grant_type=refresh_token", {
    method: "POST",
    headers: {
      apikey: config.publishable_key,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ refresh_token }),
  });
  const data = await r.json();
  if (!r.ok || data.user?.email?.toLowerCase() !== OWNER)
    throw new Error("Your session expired. Sign in again.");
  return data;
}
export async function api<T>(
  token: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  if (!path.startsWith("/api/")) throw new Error("Unsupported request");
  const r = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    cache: "no-store",
    signal,
    headers: {
      Authorization: "Bearer " + token,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok)
    throw new Error(
      data.detail ||
        String(data.error || "Request failed").replaceAll("_", " "),
    );
  return data;
}
