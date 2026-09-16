<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import MemoryPanel from '@/components/MemoryPanel.vue'
import { AVATAR_BASE_URL } from '@/constants'
import { changePassword, deleteAccount, getAvatars, logout, updateProfile } from '@/api/user'
import { useUiStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const ui = useUiStore()
const user = useUserStore()

const avatars = ref<string[]>([])
const username = ref('')
const avatar = ref('')
const savingProfile = ref(false)

const pwdForm = reactive({ current: '', next: '', confirm: '' })
const savingPwd = ref(false)

onMounted(async () => {
  const info = await user.fetchUserInfo(true)
  if (info) {
    username.value = info.username ?? ''
    avatar.value = info.avatar ?? ''
  }
  try {
    const lib = await getAvatars()
    avatars.value = lib.avatars
  } catch (e: any) {
    ui.toast(e?.message ?? '头像库加载失败', 'error')
  }
})

const avatarUrl = computed(() => (avatar.value ? AVATAR_BASE_URL + avatar.value : ''))

async function saveProfile() {
  if (!username.value.trim()) {
    ui.toast('昵称不能为空', 'error')
    return
  }
  savingProfile.value = true
  try {
    const patch: { username?: string; avatar?: string } = { username: username.value.trim() }
    if (avatar.value) patch.avatar = avatar.value
    const updated = await updateProfile(patch)
    user.$patch({ userInfo: updated })
    ui.toast('资料已更新', 'success')
  } catch (e: any) {
    ui.toast(e?.message ?? '保存失败', 'error')
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  if (pwdForm.next.length < 8) {
    ui.toast('新密码至少 8 位', 'error')
    return
  }
  if (pwdForm.next !== pwdForm.confirm) {
    ui.toast('两次输入的新密码不一致', 'error')
    return
  }
  savingPwd.value = true
  try {
    await changePassword(pwdForm.current, pwdForm.next)
    ui.toast('密码已修改，请重新登录', 'success', 4500)
    user.clearAuth()
    router.replace('/login')
  } catch (e: any) {
    ui.toast(e?.message ?? '修改失败', 'error')
  } finally {
    savingPwd.value = false
  }
}

async function handleLogout() {
  const sure = await ui.confirm('确定退出登录吗？')
  if (!sure) return
  try {
    if (user.refreshToken) await logout(user.refreshToken)
  } catch {
    /* 即使后端撤销失败也继续本地登出 */
  }
  user.clearAuth()
  ui.toast('已退出登录', 'success')
  router.replace('/login')
}

async function handleDeleteAccount() {
  const sure = await ui.confirm('确定永久注销账号吗？所有会话和行程将被删除，且无法恢复！')
  if (!sure) return
  try {
    await deleteAccount()
    user.clearAuth()
    ui.toast('账号已注销', 'success')
    router.replace('/')
  } catch (e: any) {
    ui.toast(e?.message ?? '注销失败', 'error')
  }
}
</script>

<template>
  <div class="pf-page">
    <AppNavbar />
    <main id="main" tabindex="-1">
      <div class="container page">
        <div class="page-head">
          <h1 class="page-title">个人资料</h1>
        </div>

        <div class="pf-grid">
          <section class="card pf-card">
            <h2 class="pf-title">基本信息</h2>

            <div class="pf-avatar">
              <img v-if="avatarUrl" :src="avatarUrl" alt="当前头像" class="pf-avatar__img" />
              <span v-else class="pf-avatar__img pf-avatar__img--empty">
                {{ (user.userInfo?.username || user.userInfo?.email || '?').slice(0, 1).toUpperCase() }}
              </span>
            </div>

            <div class="field">
              <label for="pf-username">昵称</label>
              <input id="pf-username" v-model="username" class="input" maxlength="10" placeholder="2-10 个字符" />
            </div>

            <div class="field">
              <label for="pf-email">邮箱（不可修改）</label>
              <input id="pf-email" class="input" :value="user.userInfo?.email ?? ''" disabled />
            </div>

            <div class="field" v-if="avatars.length">
              <label>选择头像</label>
              <div class="pf-avatar-grid">
                <button
                  v-for="a in avatars"
                  :key="a"
                  class="pf-avatar-opt"
                  :class="{ 'pf-avatar-opt--active': a === avatar }"
                  :aria-label="'选择头像 ' + a"
                  type="button"
                  @click="avatar = a"
                >
                  <img :src="AVATAR_BASE_URL + a" :alt="a" loading="lazy" />
                </button>
              </div>
            </div>

            <button class="btn btn-primary btn--block" :disabled="savingProfile" @click="saveProfile">
              {{ savingProfile ? '保存中…' : '保存资料' }}
            </button>
          </section>

          <section class="card pf-card">
            <h2 class="pf-title">账号安全</h2>

            <div class="field">
              <label for="pwd-current">当前密码</label>
              <input id="pwd-current" v-model="pwdForm.current" class="input" type="password" autocomplete="current-password" />
            </div>
            <div class="field">
              <label for="pwd-next">新密码</label>
              <input id="pwd-next" v-model="pwdForm.next" class="input" type="password" minlength="8" autocomplete="new-password" placeholder="至少 8 位" />
            </div>
            <div class="field">
              <label for="pwd-confirm">确认新密码</label>
              <input id="pwd-confirm" v-model="pwdForm.confirm" class="input" type="password" minlength="8" autocomplete="new-password" />
            </div>
            <p class="form-hint pwd-hint">修改密码后，所有设备将退出登录。</p>
            <button class="btn btn-ink btn--block" :disabled="savingPwd" @click="savePassword">
              {{ savingPwd ? '提交中…' : '修改密码' }}
            </button>

            <hr class="pf-hr" />

            <h2 class="pf-title">会话与账号</h2>
            <button class="btn btn-ghost btn--block" @click="handleLogout">退出登录</button>
            <button class="btn btn-danger btn--block logout-btn" @click="handleDeleteAccount">注销账号</button>
          </section>
        </div>

        <!-- 长期记忆：通栏放在两栏之下，它是独立主题、不属于「资料」或「安全」 -->
        <div class="pf-memory">
          <MemoryPanel />
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.pf-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.pf-card { padding: 26px 28px; display: flex; flex-direction: column; gap: 16px; }

/* 记忆面板：与上方两栏保持同样的纵向间距 */
.pf-memory { margin-top: 20px; }

.pf-title { font-size: 1.15rem; }

.pf-avatar { display: flex; justify-content: center; }

.pf-avatar__img {
  width: 84px;
  height: 84px;
  border-radius: 50%;
  object-fit: cover;
  border: 3px solid var(--primary-soft);
}

.pf-avatar__img--empty {
  display: grid;
  place-items: center;
  background: var(--primary);
  color: #fff;
  font-family: var(--display);
  font-size: 2rem;
  font-weight: 700;
}

.pf-avatar-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
  gap: 10px;
}

.pf-avatar-opt {
  border: 2px solid transparent;
  border-radius: 12px;
  padding: 0;
  overflow: hidden;
  background: var(--surface-soft);
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.pf-avatar-opt img { width: 100%; aspect-ratio: 1; object-fit: cover; }

.pf-avatar-opt:hover { transform: translateY(-2px); }

.pf-avatar-opt--active { border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }

.pwd-hint { margin: -4px 0 14px; }

.logout-btn { margin-top: 10px; }

.pf-hr { border: none; border-top: 1px dashed var(--line); margin: 6px 0 14px; }

@media (max-width: 760px) {
  .pf-grid { grid-template-columns: 1fr; }
}
</style>
