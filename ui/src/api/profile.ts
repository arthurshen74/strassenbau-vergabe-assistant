import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { ProfileDTO } from '../types/generated';

export const profileKeys = {
  detail: ['profile'] as const,
};

export function useProfile() {
  return useQuery({
    queryKey: profileKeys.detail,
    queryFn: () => api.get<ProfileDTO>('/profile'),
  });
}
