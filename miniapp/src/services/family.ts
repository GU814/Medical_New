import { request } from './api';
import type { FamilyMember } from '@/types';

// ==================== 家庭成员 ====================

export function listFamily() {
  return request<FamilyMember[]>({ url: '/api/family' });
}

export function addFamily(data: {
  member_name: string;
  relationship?: string;
  gender?: string;
  birth_date?: string;
  phone?: string;
  emergency_contact?: boolean;
  notify_on_emergency?: boolean;
  address_shared?: boolean;
  can_view_status?: boolean;
}) {
  return request<FamilyMember>({ url: '/api/family', method: 'POST', data });
}

export function updateFamily(
  id: number,
  data: Partial<{
    member_name: string;
    relationship: string;
    gender: string;
    birth_date: string;
    phone: string;
    emergency_contact: boolean;
    notify_on_emergency: boolean;
    address_shared: boolean;
    can_view_status: boolean;
  }>,
) {
  return request<FamilyMember>({ url: `/api/family/${id}`, method: 'PUT', data });
}

export function deleteFamily(id: number) {
  return request<{ ok: boolean }>({ url: `/api/family/${id}`, method: 'DELETE' });
}

export function acceptFamily(token: string) {
  return request<FamilyMember>({ url: '/api/family/accept', method: 'POST', data: { token } });
}
