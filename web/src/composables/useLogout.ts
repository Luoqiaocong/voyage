/**
 * 退出登录。
 *
 * 抽成 composable 而不是各页面自己写：原先只有 ProfileView 有这段逻辑，
 * 用户要退出必须先进「我的」页、再滚到最底部才能找到 —— 登出是账号级操作，
 * 藏在二级页面的底部不合常规，也不便使用。
 * 现在导航栏的头像菜单与个人页共用同一份实现，行为必然一致
 * （尤其是失败处理：后端撤销失败也必须完成本地登出，否则用户被困住）。
 */
import { useRouter } from 'vue-router'
import { logout as revokeToken } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

export function useLogout() {
  const router = useRouter()
  const user = useUserStore()
  const ui = useUiStore()

  /**
   * 退出登录。
   *
   * @param confirm 是否先弹确认（头像菜单里误点概率低，但登出会丢当前状态，
   *                默认仍确认一次；个人页里那是个大按钮，更需要确认）
   */
  async function doLogout(confirm = true) {
    if (confirm) {
      // 只问一句：退出登录意味着要重新登录，这是常识，不必在确认框里解释
      const sure = await ui.confirm('确定退出登录吗？')
      if (!sure) return
    }

    try {
      if (user.refreshToken) await revokeToken(user.refreshToken)
    } catch {
      // 后端撤销失败也要继续本地登出 —— 否则令牌已失效但界面仍显示登录态，
      // 用户会困在一个「看起来登录着、实际什么都做不了」的状态里
    }
    user.clearAuth()
    ui.toast('已退出登录', 'success')
    router.replace('/login')
  }

  return { doLogout }
}
