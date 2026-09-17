/**
 * 路由进度状态。
 *
 * 单独放一个模块，让路由守卫与 App 外壳都能引用，
 * 又不必让二者互相依赖（App 引用 router，router 又引用 App 就成了循环）。
 */
import { ref } from 'vue'

/** 是否正在切换路由（用于顶部进度条） */
export const routeLoading = ref(false)

/** 切换期间的提示语，按目标路径给出更贴切的文案 */
export const routeLoadingText = ref('')
