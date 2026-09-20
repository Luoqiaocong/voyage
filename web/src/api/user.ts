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
  /** 角色：前端据此决定是否展示管理台入口 */
  role: 'user' | 'admin'
  is_active: boolean
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

/**
 * 注销账号（不可逆），需邮箱验证码二次确认。
 *
 * 验证码由 sendCode(email) 发到当前账号绑定的邮箱；
 * 这里**只传 code**，不传邮箱 —— 邮箱由后端从鉴权态取，
 * 前端传邮箱会变成「给任意邮箱发码」的越权口子。
 */
export async function deleteAccount(code: string): Promise<void> {
  await http.delete('/users/', { data: { code } })
}

export async function getAvatars(): Promise<AvatarLibrary> {
  return http.get('/users/avatars')
}
