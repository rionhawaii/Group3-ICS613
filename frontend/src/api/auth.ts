// Auth API — /auth/* endpoints.
import { apiRequest, setTokens } from './client';
import type {
  ForgotPasswordRequest,
  InviteCreate,
  InviteResponse,
  LoginRequest,
  MessageResponse,
  RefreshRequest,
  RegisterRequest,
  ResendRequest,
  ResetPasswordRequest,
  TokenPairResponse,
  UserProfile,
  UserUpdate,
  VerifyEmailRequest,
} from '../types/api';

export const authApi = {
  login: (data: LoginRequest) =>
    apiRequest<TokenPairResponse>('POST', '/auth/login', data).then((tokens) => {
      setTokens(tokens.access_token, tokens.refresh_token);
      return tokens;
    }),

  register: (data: RegisterRequest) =>
    apiRequest<MessageResponse>('POST', '/auth/register', data),

  verifyEmail: (data: VerifyEmailRequest) =>
    apiRequest<TokenPairResponse>('POST', '/auth/verify-email', data).then((tokens) => {
      setTokens(tokens.access_token, tokens.refresh_token);
      return tokens;
    }),

  resendVerification: (data: ResendRequest) =>
    apiRequest<MessageResponse>('POST', '/auth/resend-verification', data),

  refresh: (data: RefreshRequest) =>
    apiRequest<TokenPairResponse>('POST', '/auth/refresh', data).then((tokens) => {
      setTokens(tokens.access_token, tokens.refresh_token);
      return tokens;
    }),

  logout: () => apiRequest<MessageResponse>('POST', '/auth/logout'),

  me: () => apiRequest<UserProfile>('GET', '/auth/me'),

  updateMe: (data: UserUpdate) =>
    apiRequest<UserProfile>('PUT', '/auth/me', data),

  uploadProfilePhoto: (file: File) => {
    const formData = new FormData();
    formData.append('photo', file);
    return apiRequest<UserProfile>(
      'POST',
      '/auth/me/photo',
      formData,
      { isFormData: true },
    );
  },

  deleteMe: () => apiRequest<void>('DELETE', '/auth/me'),

  forgotPassword: (data: ForgotPasswordRequest) =>
    apiRequest<MessageResponse>('POST', '/auth/forgot-password', data),

  resetPassword: (data: ResetPasswordRequest) =>
    apiRequest<TokenPairResponse>('POST', '/auth/reset-password', data).then((tokens) => {
      setTokens(tokens.access_token, tokens.refresh_token);
      return tokens;
    }),

  // Admin-only
  createInvite: (data: InviteCreate) =>
    apiRequest<InviteResponse>('POST', '/auth/invites', data),

  listInvites: () => apiRequest<InviteResponse[]>('GET', '/auth/invites'),

  revokeInvite: (inviteId: string) =>
    apiRequest<InviteResponse>('POST', `/auth/invites/${inviteId}/revoke`),
};
