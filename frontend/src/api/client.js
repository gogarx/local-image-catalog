const BASE_URL = (import.meta.env.VITE_API_URL ?? '').trim().replace(/\/+$/, '')

export function apiUrl(path = '') {
  return `${BASE_URL}${path}`
}

async function errorMessage(response) {
  try {
    const body = await response.json()
    return body.detail || `HTTP ${response.status}`
  } catch {
    return `HTTP ${response.status}`
  }
}

export async function request(path, { signal } = {}) {
  const response = await fetch(apiUrl(path), { signal })
  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }
  return response.json()
}
