import { request } from './client'

export async function fetchImages({ limit = 24, offset = 0, signal } = {}) {
  return request(`/images?limit=${limit}&offset=${offset}`, { signal })
}

export async function fetchImage(imageId, { signal } = {}) {
  return request(`/images/${imageId}`, { signal })
}

export async function searchImages(q, { limit = 24, offset = 0, signal } = {}) {
  const params = new URLSearchParams({ q, limit, offset })
  return request(`/search?${params}`, { signal })
}
