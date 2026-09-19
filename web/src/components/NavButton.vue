<script setup lang="ts">
import TravelIcon from './TravelIcon.vue'

/**
 * NavButton · 页面间的导航按钮
 *
 * 存在的理由：项目里多处「去别的页面」原本是一行纯文字链接
 * （`color` + `font-size`，无边框无内边距），例如
 *   「← 全部行程」「← 返回登录」「或用账号登录后再规划」
 * 它们看起来不像可点的控件，鼠标悬停前也看不出可点。
 * 逐个页面各写一份样式，结果就是三处三种写法、彼此还不一致。
 *
 * 与 `link-btn`（忘记密码 / 返回登录这类）的区别：
 *   link-btn 是**表单内的内联链接**——蓝色文字 + 悬停下划线是表单的通用
 *   惯用法，读者预期如此；做成按钮反而会与提交按钮抢视觉焦点。
 *   NavButton 是**导航**——离开当前页面/区块，控件属性更强，故用按钮。
 *
 * 视觉规格与 LoginView / AdminLayout 已有的返回按钮一致：
 * 次要按钮（ghost）形态，浅色底、细边框、悬停轻微上浮。
 */
withDefaults(
  defineProps<{
    /** 跳转目标 */
    to: string
    /** 按钮文案 */
    label: string
    /** 是否显示返回箭头图标（默认显示）。纯前进语义的入口可关掉 */
    arrow?: boolean
    /** 是否占满父容器宽度 */
    block?: boolean
  }>(),
  { arrow: true, block: false }
)
</script>

<template>
  <RouterLink :to="to" class="navbtn" :class="{ 'navbtn--block': block }">
    <TravelIcon v-if="arrow" name="arrow-left" :size="15" />
    {{ label }}
  </RouterLink>
</template>

<style scoped>
.navbtn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 9px 15px;
  border: 1px solid var(--border);
  border-radius: var(--r-s);
  background: var(--panel);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text2);
  /* transition 覆盖 transform，让悬停上浮是平滑的而不是瞬移 */
  transition: background-color 0.18s, border-color 0.18s, color 0.18s, transform 0.18s;
}
.navbtn:hover {
  background: var(--panel2);
  border-color: var(--blue-200);
  color: var(--prim);
  transform: translateY(-1px);
}
.navbtn:active {
  transform: translateY(0);
}
/* 键盘聚焦要有可见指示 */
.navbtn:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}
.navbtn--block {
  display: flex;
  width: 100%;
}
</style>
