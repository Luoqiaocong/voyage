/**
 * 角色定义与判断。
 *
 * 为什么单独抽一个文件，而不是在各处写 role === 'admin'：
 *   引入「超级管理员」时，前端有 4 处判断只认 'admin'（导航栏入口、路由守卫、
 *   个人页标识、用户详情），漏改任何一处都会导致超管看不到管理端 ——
 *   而后端已经放行，表现为「后端说你是管理员，界面却不给你入口」，
 *   排查时容易往权限实现上怀疑，实际是前端字符串没同步。
 *
 *   把判断收敛到一处后，新增角色只需改这个文件。
 *
 * 与后端 app/modules/user/constants.py 的 ROLE_RANK 保持一致：
 *   user 0 < admin 1 < super_admin 2
 */

export type UserRole = 'user' | 'admin' | 'super_admin'

/** 角色层级；未知角色返回 -1（默认拒绝，不默认放行） */
export const ROLE_RANK: Record<string, number> = {
  user: 0,
  admin: 1,
  super_admin: 2
}

/** 角色的中文名，供界面展示 */
export const ROLE_LABEL: Record<string, string> = {
  user: '普通用户',
  admin: '普通管理员',
  super_admin: '超级管理员'
}

export function roleRank(role: string | null | undefined): number {
  return ROLE_RANK[role ?? ''] ?? -1
}

/**
 * 能否进入管理端（**读取**权限）。
 * 普通管理员与超级管理员都可以 —— 后者只是多了写权限。
 */
export function canAccessAdmin(role: string | null | undefined): boolean {
  return roleRank(role) >= ROLE_RANK.admin
}

/**
 * 是否有管理端的**写入**权限。
 *
 * 注意：界面据此隐藏按钮只是避免「点了才被拒」，**不是安全边界** ——
 * 真正的校验在服务端（写接口走 get_current_super_admin）。
 * 因此即便这里判断错了，也只会影响体验，不会造成越权。
 */
export function canWriteAdmin(role: string | null | undefined): boolean {
  return roleRank(role) >= ROLE_RANK.super_admin
}

/** 角色中文名；未知角色原样返回，便于排查 */
export function roleLabel(role: string | null | undefined): string {
  if (!role) return '普通用户'
  return ROLE_LABEL[role] ?? role
}
