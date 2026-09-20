<script setup lang="ts">
/**
 * SharePanel · 分享这份行程
 *
 * 布局思路：整个面板按「上创建、下列表」两段组织，
 * 每段内部统一采用**左侧信息 / 右侧操作**的表格式结构，
 * 操作列靠右对齐，扫视时一眼就能定位「能做什么」。
 */
import { onMounted, reactive, ref } from 'vue'
import {
  createShare,
  listShares,
  revokeShare,
  updateShare,
  shareStatusLabel,
  type ShareItem
} from '@/api/share'
import { useUiStore } from '@/stores/ui'
import TravelIcon from '@/components/TravelIcon.vue'

const props = defineProps<{ itineraryId: number }>()
const ui = useUiStore()

const shares = ref<ShareItem[]>([])
const loading = ref(false)
const creating = ref(false)
const busyId = ref<number | null>(null)
/** 已展开密码的分享 id 集合 */
const revealed = ref(new Set<number>())

const EXPIRY_OPTIONS = [
  { value: 1, label: '1 天' },
  { value: 7, label: '7 天' },
  { value: 30, label: '30 天' },
  { value: null, label: '永不过期' }
]

const form = reactive({
  allow_copy: true,
  allow_edit: false,
  password: '',
  expires_in_days: 7 as number | null
})

async function load() {
  loading.value = true
  try {
    shares.value = await listShares(props.itineraryId)
  } catch (e: any) {
    ui.toast(e?.message ?? '分享列表加载失败', 'error')
  } finally {
    loading.value = false
  }
}

async function create() {
  creating.value = true
  try {
    await createShare(props.itineraryId, {
      allow_copy: form.allow_copy,
      allow_edit: form.allow_edit,
      password: form.password.trim() || null,
      expires_in_days: form.expires_in_days
    })
    ui.toast('分享链接已创建', 'success')
    form.password = ''
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '创建失败', 'error')
  } finally {
    creating.value = false
  }
}

async function copyLink(s: ShareItem) {
  try {
    await navigator.clipboard.writeText(s.url)
    ui.toast('链接已复制', 'success')
  } catch {
    // 剪贴板可能因权限被拒：退化为提示用户手动复制
    ui.toast('复制失败，请手动选中链接复制', 'error')
  }
}

async function toggleCopy(s: ShareItem) {
  busyId.value = s.id
  try {
    await updateShare(s.id, { allow_copy: !s.allow_copy })
    s.allow_copy = !s.allow_copy
  } catch (e: any) {
    ui.toast(e?.message ?? '修改失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function toggleEdit(s: ShareItem) {
  busyId.value = s.id
  try {
    await updateShare(s.id, { allow_edit: !s.allow_edit })
    s.allow_edit = !s.allow_edit
  } catch (e: any) {
    ui.toast(e?.message ?? '修改失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function revoke(s: ShareItem) {
  // 现在是真的删除（记录会从列表移除），不只是失效——文案要说清，
  // 别让用户以为删完还能找回
  const ok = await ui.confirm(
    '删除后该链接立即失效，记录也会从列表中移除，无法恢复。确认删除？'
  )
  if (!ok) return
  busyId.value = s.id
  try {
    await revokeShare(s.id)
    ui.toast('分享链接已删除', 'success')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '删除失败', 'error')
  } finally {
    busyId.value = null
  }
}

function toggleReveal(id: number) {
  const next = new Set(revealed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  revealed.value = next
}

/** 有效期显示成「还剩几天」比一串时间戳更直观 */
function expiryText(s: ShareItem): string {
  if (!s.expires_at) return '永不过期'
  const end = new Date(s.expires_at).getTime()
  if (Number.isNaN(end)) return `有效期至 ${s.expires_at}`
  const days = Math.ceil((end - Date.now()) / 86_400_000)
  if (days < 0) return '已过期'
  if (days === 0) return '今天到期'
  return `${days} 天后过期`
}

onMounted(load)
defineExpose({ reload: load })
</script>

<template>
  <section class="card sp">
    <header class="sp__head">
      <h2>分享这份行程</h2>
      <p>把链接发给同行的人。可限制对方能做什么，也能随时删除。</p>
    </header>

    <!-- ==================== 创建 ==================== -->
    <div class="creator">
      <div class="creator__fields">
        <div class="creator__group">
          <span class="creator__label">对方可以</span>
          <label class="chk">
            <input v-model="form.allow_copy" type="checkbox" />
            <span>复制到自己账号</span>
          </label>
          <label class="chk">
            <input v-model="form.allow_edit" type="checkbox" />
            <span>直接编辑</span>
          </label>
        </div>

        <div class="creator__group">
          <label class="fld">
            <span class="creator__label">访问密码</span>
            <input
              v-model="form.password"
              class="input input--sm"
              type="text"
              placeholder="留空则免密码"
              maxlength="32"
            />
          </label>
          <label class="fld">
            <span class="creator__label">有效期</span>
            <select v-model="form.expires_in_days" class="select input--sm">
              <option v-for="o in EXPIRY_OPTIONS" :key="String(o.value)" :value="o.value">
                {{ o.label }}
              </option>
            </select>
          </label>
        </div>
      </div>

      <!-- 主按钮固定在右侧：与下方列表的操作列对齐 -->
      <div class="creator__submit">
        <button class="btn btn-primary btn--sm" :disabled="creating" @click="create">
          <TravelIcon name="spark" :size="15" />
          {{ creating ? '创建中…' : '创建分享链接' }}
        </button>
      </div>
    </div>

    <!-- ==================== 列表 ==================== -->
    <p v-if="loading" class="sp__empty">加载中…</p>

    <div v-else-if="!shares.length" class="sp__empty sp__empty--rich">
      <TravelIcon name="spark" :size="20" />
      <span>还没有分享链接。设置好权限后点右侧「创建分享链接」即可。</span>
    </div>

    <ul v-else class="list">
      <li
        v-for="s in shares"
        :key="s.id"
        class="row"
        :class="{ 'is-dead': s.status !== 'active' }"
      >
        <!-- 上行：状态 + 链接 + **对链接本身**的操作 -->
        <div class="row__main">
          <span class="row__status" :class="`row__status--${shareStatusLabel(s.status).tone}`">
            {{ shareStatusLabel(s.status).text }}
          </span>

          <input
            class="row__url"
            :value="s.url"
            readonly
            aria-label="分享链接"
            @focus="($event.target as HTMLInputElement).select()"
          />

          <div class="row__ops">
            <button
              class="btn btn-primary btn--xs"
              :disabled="busyId === s.id"
              @click="copyLink(s)"
            >
              <TravelIcon name="spark" :size="13" />
              复制链接
            </button>
            <!-- 删除对所有状态都可点：既然是真删除，已过期/已失效的链接
                 也应允许清理掉，否则只能一直挂在列表里 -->
            <button
              class="btn btn-ghost btn--xs row__del"
              :disabled="busyId === s.id"
              @click="revoke(s)"
            >
              删除
            </button>
          </div>
        </div>

        <!--
          下行分两块，对应两个不同维度，用竖线隔开：

            「对方可以…」是**对访问者的授权**（能不能把行程存进自己账号、
              能不能直接改）——原先把它与「复制链接」并排放，两个按钮都带
              「复制」二字却指两件事（复制给谁？），用户会以为是一件事的两个
              状态。分开后才看得出这是授权而非链接操作。

            「访问 / 有效期 / 密码」是**这条链接的状态信息**，只读。

          授权用开关而非按钮：开关的形态本身就表达「一项持续生效的设置」，
          而按钮更像「点一次执行一个动作」。文案也写成完整的一句话，
          不再依赖用户补全主语。
        -->
        <div class="row__meta">
          <div class="row__perm">
            <span class="row__perm-title">对方可以</span>
            <label class="sw" :title="'允许对方把这份行程复制到自己的账号'">
              <input
                type="checkbox"
                :checked="s.allow_copy"
                :disabled="busyId === s.id"
                @change="toggleCopy(s)"
              />
              <span class="sw__track" aria-hidden="true"><span class="sw__dot"></span></span>
              <span class="sw__text">存为自己的行程</span>
            </label>
            <label class="sw" :title="'允许对方直接修改这份行程的内容'">
              <input
                type="checkbox"
                :checked="s.allow_edit"
                :disabled="busyId === s.id"
                @change="toggleEdit(s)"
              />
              <span class="sw__track" aria-hidden="true"><span class="sw__dot"></span></span>
              <span class="sw__text">直接修改内容</span>
            </label>
          </div>

          <div class="row__stat">
            <span>访问 {{ s.view_count }} 次</span>
            <i aria-hidden="true">·</i>
            <span>{{ expiryText(s) }}</span>
            <i aria-hidden="true">·</i>
            <span v-if="s.has_password" class="row__pwd">
              密码
              <b>{{ revealed.has(s.id) ? s.password : '••••••' }}</b>
              <button class="linkbtn" @click="toggleReveal(s.id)">
                {{ revealed.has(s.id) ? '隐藏' : '显示' }}
              </button>
            </span>
            <span v-else>免密码</span>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.sp { padding: 22px 24px; margin-bottom: 20px; }

/* ---- 标题区 ---- */
.sp__head { margin-bottom: 18px; }
.sp__head h2 { font-size: 1rem; font-weight: 700; }
.sp__head p { margin-top: 5px; font-size: 0.8rem; color: var(--text3); line-height: 1.6; }

/* ---- 创建区：左选项 / 右主按钮 ---- */
.creator {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: var(--r-m);
  /* 极淡的底：把它与下方列表区分开，但不用重底色压住内容 */
  background: var(--surface-soft);
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.creator__fields {
  display: flex;
  align-items: flex-end;
  gap: 28px;
  flex-wrap: wrap;
  min-width: 0;
}
.creator__group { display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap; }

/* 小标签：说明每一组的用途，比让用户从控件本身猜更省事 */
.creator__label {
  display: block;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text3);
  margin-bottom: 6px;
  white-space: nowrap;
}

.chk {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.83rem;
  color: var(--text2);
  /* 与右侧输入框基线对齐：勾选框没有上方的标签，靠下移一点补偿 */
  padding-bottom: 7px;
  cursor: pointer;
}
.chk input[type='checkbox'] { width: 15px; height: 15px; accent-color: var(--prim); cursor: pointer; }

.fld { display: flex; flex-direction: column; }
.fld .input--sm { width: 138px; padding: 7px 10px; font-size: 0.82rem; }

.creator__submit { flex-shrink: 0; margin-left: auto; }

/* ---- 列表 ---- */
.sp__empty { font-size: 0.84rem; color: var(--text3); padding: 14px 0; }
.sp__empty--rich {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  border: 1px dashed var(--line);
  border-radius: var(--r-m);
  line-height: 1.6;
}
.sp__empty--rich :deep(svg) { flex-shrink: 0; color: var(--blue-300); }

.list { display: flex; flex-direction: column; }

/* 行之间用分割线而不是每行一个卡片边框：
   卡片化会让「这是一个列表」的观感变弱，也更占空间 */
.row { padding: 14px 0; border-top: 1px solid var(--hairline); }
.row:first-child { border-top: none; padding-top: 4px; }
.row.is-dead { opacity: 0.6; }

.row__main { display: flex; align-items: center; gap: 10px; }
.row__main { flex-wrap: wrap; }

.row__status {
  flex-shrink: 0;
  font-size: 0.72rem;
  font-weight: 650;
  padding: 3px 9px;
  border-radius: 6px;
  white-space: nowrap;
}
.row__status--ok { background: rgba(72, 187, 120, 0.14); color: var(--success); }
.row__status--warn { background: var(--gold-soft); color: var(--gold-600); }
.row__status--muted { background: var(--surface-soft); color: var(--text3); }

.row__url {
  flex: 1;
  min-width: 0;
  font-family: var(--mono);
  font-size: 0.76rem;
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--panel2);
  color: var(--text2);
  text-overflow: ellipsis;
}
.row__url:focus { outline: 2px solid var(--prim); outline-offset: 1px; }

/* 操作列：贴右，形成一条对齐的操作线 */
.row__ops {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

/* 删除默认不显红——避免一列红色按钮，悬停时才提示破坏性 */
.row__del { color: var(--text3); }
.row__del:hover:not(:disabled) {
  color: var(--danger);
  border-color: rgba(224, 82, 82, 0.3);
  background: rgba(224, 82, 82, 0.08);
}

/*
 * 下行分两块：左侧授权（可操作），右侧链接状态（只读）。
 * 竖线把「你能改的」与「你只能看的」分开 —— 不靠颜色区分，
 * 因为两者都不是错误状态，用颜色反而会显得像警告。
 */
.row__meta {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 11px;
  padding-left: 2px;
  font-size: 0.75rem;
  color: var(--text3);
  flex-wrap: wrap;
}

.row__perm {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.row__perm-title {
  font-weight: 600;
  color: var(--text3);
  white-space: nowrap;
}

.row__stat {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-left: 16px;
  border-left: 1px solid var(--line);
}
.row__stat i { font-style: normal; opacity: 0.45; }
.row__pwd { color: var(--text2); }
.row__pwd b { font-family: var(--mono); font-weight: 600; }

/* ---- 开关 ----
   用开关而不是按钮表达授权：开关的形态本身就说明「这是一项持续生效的设置」，
   而按钮更像「点一次执行一个动作」。原先用按钮，用户要推断当前是开还是关
   （「禁止复制」到底是状态还是动作？），开关没有这个歧义。
   开关本身小，但 label 整块可点，点击区域足够大。 */
.sw {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  user-select: none;
}
.sw input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.sw__track {
  position: relative;
  width: 30px;
  height: 17px;
  border-radius: 9px;
  background: var(--slate-300);
  transition: background-color 0.2s ease;
  flex-shrink: 0;
}
.sw__dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.2);
  transition: transform 0.2s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.sw input:checked + .sw__track { background: var(--prim); }
.sw input:checked + .sw__track .sw__dot { transform: translateX(13px); }
.sw input:disabled + .sw__track { opacity: 0.5; }
.sw input:focus-visible + .sw__track {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}

.sw__text { color: var(--text2); white-space: nowrap; }
/* 关闭状态把文字压淡，让「开/关」的差别不只看轨道颜色 */
.sw input:not(:checked) ~ .sw__text { color: var(--text3); }

@media (prefers-reduced-motion: reduce) {
  .sw__track,
  .sw__dot { transition: none; }
}

.linkbtn {
  margin-left: 6px;
  padding: 0;
  border: none;
  background: none;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--prim);
  cursor: pointer;
}
.linkbtn:hover { text-decoration: underline; }

/* ---- 响应式 ----
 * 窄屏的核心矛盾：链接需要横向空间，而操作列有四个按钮。
 * 挤在一行会导致链接被压成省略号、按钮换行错位。
 * 故让操作列**整体换到下一行并靠左**，同时 URL 独占一行、
 * 状态标签留在最上——三层结构在手机上比强行并排易读得多。 */
@media (max-width: 720px) {
  .sp { padding: 18px 16px; }

  .creator { align-items: stretch; gap: 14px; }
  .creator__fields { gap: 16px; }
  .creator__group { gap: 12px; }
  .creator__submit { margin-left: 0; }
  .creator__submit .btn { width: 100%; justify-content: center; }

  .row__main { gap: 8px; }
  .row__status { order: 1; }
  .row__url { order: 2; flex: 1 1 100%; }
  .row__ops {
    order: 3;
    flex: 1 1 100%;
    margin-left: 0;
    flex-wrap: wrap;
  }
}
</style>
