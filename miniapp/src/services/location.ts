import { request } from './api';
import type { UserLocation } from '@/types';

// ==================== 地理位置(用户常用地点) ====================

export function listLocations() {
  return request<UserLocation[]>({ url: '/api/location' });
}

export function addLocation(data: {
  name: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  is_default?: boolean;
}) {
  return request<UserLocation>({ url: '/api/location', method: 'POST', data });
}

export function deleteLocation(id: number) {
  return request<{ ok: boolean }>({ url: `/api/location/${id}`, method: 'DELETE' });
}

export function setDefaultLocation(id: number) {
  return request<{ ok: boolean }>({ url: `/api/location/${id}/default`, method: 'POST' });
}
