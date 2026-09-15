import http from './http'

export interface LoginResult {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserInfo {
  id: string
  email: string
  username: string | null
  avatar: string | null
}

export interface AvatarLibrary {
  base_url: string
  avatars: string[]
}

export async function login(email: string, password: string): Promise<LoginResult> {
  return http.post('/users/login', { email, password })
}

export async function register(data: {
  email: string
  password: string
  username: string
  code: string
}): Promise<void> {
  await http.post('/users/reg', data)
}

export async function sendCode(email: string): Promise<void> {
  await http.post('/auth/code', { email })
}

export async function resetToken(email: string, code: string): Promise<{ token: string }> {
  return http.post('/auth/reset-token', { email, code })
}

export async function resetPassword(password: string, token: string): Promise<void> {
  await http.post('/users/reset', { password, token })
}

export async function getInfo(): Promise<UserInfo> {
  return http.get('/users/info')
}

export async function updateProfile(patch: { username?: string; avatar?: string }): Promise<UserInfo> {
  return http.patch('/users/info', patch)
}

export async function changePassword(current_password: string, new_password: string): Promise<void> {
  await http.put('/users/pwd', { current_password, new_password })
}

export async function logout(refresh_token: string): Promise<void> {
  await http.post('/users/logout', { refresh_token })
}

export async function deleteAccount(): Promise<void> {
  await http.delete('/users/')
}

export async function getAvatars(): Promise<AvatarLibrary> {
  return http.get('/users/avatars')
}
